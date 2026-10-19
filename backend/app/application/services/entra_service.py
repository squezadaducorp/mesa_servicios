"""Inicio de sesión único con Entra ID y sincronización de usuarios y roles desde sus grupos."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoAutorizado
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.auth_service import AuthService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Rol
from app.infrastructure.db import models as m
from app.infrastructure.m365 import entra
from app.infrastructure.m365.graph import ClienteGraph
from app.infrastructure.repositories.repositorios import UsuarioRepository

log = logging.getLogger(__name__)

# Si un usuario está en varios grupos mapeados, gana el rol de mayor alcance.
PRECEDENCIA = [Rol.SUPER_ADMIN, Rol.ADMIN_MESA, Rol.SUPERVISOR, Rol.GERENCIA, Rol.ANALISTA, Rol.CLIENTE]
AUD_FLUJO, AUD_INTERCAMBIO = "aducorp-entra-flujo", "aducorp-entra-intercambio"
MINUTOS_FLUJO, SEGUNDOS_INTERCAMBIO = 10, 60


def _firmar(datos: dict, aud: str, segundos: int) -> str:
    ahora = utcnow()
    return jwt.encode({**datos, "aud": aud, "iat": ahora, "exp": ahora + timedelta(seconds=segundos)}, settings.JWT_SECRET, algorithm="HS256")


def _leer(token: str | None, aud: str) -> dict:
    if not token:
        raise NoAutorizado("La sesión de inicio con Microsoft expiró. Intente de nuevo.")
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], audience=aud)
    except jwt.PyJWTError as exc:
        raise NoAutorizado("La sesión de inicio con Microsoft expiró. Intente de nuevo.") from exc


def destino_seguro(destino: str | None) -> str:
    """Solo rutas internas de la aplicación (evita redirecciones abiertas)."""
    return destino if destino and destino.startswith("/") and not destino.startswith("//") else "/"


def rol_para(grupos: list[str], roles_app: list[str]) -> str | None:
    """Rol de la Mesa según los App Roles del token o los grupos mapeados en ENTRA_GRUPO_ROLES."""
    candidatos = {r.upper() for r in roles_app if r.upper() in Rol.__members__}
    mapa = {k.lower(): v.upper() for k, v in settings.ENTRA_GRUPO_ROLES.items()}
    candidatos |= {mapa[g.lower()] for g in grupos if g.lower() in mapa}
    for rol in PRECEDENCIA:
        if rol in candidatos:
            return rol
    return settings.ENTRA_ROL_DEFECTO.upper() or None


class EntraService:
    def __init__(self, session: Session, graph: ClienteGraph | None = None):
        self.session = session
        self.usuarios = UsuarioRepository(session)
        self.auditoria = AuditoriaService(session)
        self._graph = graph

    @property
    def graph(self) -> ClienteGraph:
        if self._graph is None:
            self._graph = ClienteGraph()
        return self._graph

    # ---------------------------------------------------------- flujo OIDC
    @staticmethod
    def iniciar(destino: str | None, pista: str | None = None) -> tuple[str, str]:
        """URL de autorización de Entra ID y la cookie firmada que guarda state, nonce y el verificador PKCE."""
        if not settings.entra_activo:
            raise NoAutorizado("El inicio de sesión con Microsoft no está habilitado")
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        verificador, reto = entra.nuevo_pkce()
        cookie = _firmar({"state": state, "nonce": nonce, "pkce": verificador, "destino": destino_seguro(destino)}, AUD_FLUJO, MINUTOS_FLUJO * 60)
        return entra.url_autorizacion(state, nonce, reto, pista), cookie

    def completar(self, codigo: str, state: str, cookie: str | None, ctx: Contexto, jwks=None, http=None) -> tuple[str, str]:
        """Canjea el código, valida el id_token y devuelve (código de intercambio de un solo uso, destino)."""
        flujo = _leer(cookie, AUD_FLUJO)
        if not secrets.compare_digest(flujo["state"], state or ""):
            raise NoAutorizado("La respuesta de Microsoft no corresponde a este inicio de sesión. Intente de nuevo.")
        tokens = entra.canjear_codigo(codigo, flujo["pkce"], http=http)
        try:
            identidad = entra.validar_id_token(tokens["id_token"], flujo["nonce"], jwks=jwks)
        except (jwt.PyJWTError, KeyError) as exc:
            log.warning("id_token de Entra ID rechazado: %s", exc)
            raise NoAutorizado("No se pudo validar la identidad devuelta por Microsoft") from exc
        if settings.ENTRA_EXIGIR_MFA and "mfa" not in identidad.amr:
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", correo=identidad.correo, detalle={"motivo": "sin MFA"}, resultado="ERROR")
            self.session.commit()
            raise NoAutorizado("Su inicio de sesión no usó autenticación multifactor (MFA)")
        usuario = self.sincronizar_usuario(identidad, ctx)
        codigo_intercambio = _firmar({"sub": str(usuario.id), "jti": secrets.token_hex(16)}, AUD_INTERCAMBIO, SEGUNDOS_INTERCAMBIO)
        return codigo_intercambio, flujo["destino"]

    def intercambiar(self, codigo: str, ctx: Contexto) -> dict:
        """El frontend cambia el código de un solo uso por los tokens de sesión de la Mesa."""
        datos = _leer(codigo, AUD_INTERCAMBIO)
        # Un solo uso: el jti se registra como bloqueo; si ya existe, el código fue usado.
        try:
            self.session.add(m.BloqueoProceso(nombre=f"sso:{datos['jti']}", propietario="sso", expira=utcnow() + timedelta(minutes=5)))
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise NoAutorizado("El código de inicio de sesión ya fue utilizado") from exc
        usuario = self.usuarios.get(int(datos["sub"]))
        if usuario is None or not usuario.activo or usuario.eliminado:
            raise NoAutorizado("Usuario inactivo")
        usuario.ultimo_login = utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.LOGIN, "sesion", usuario=usuario, detalle={"proveedor": "Entra ID"})
        return AuthService(self.session)._emitir(usuario, ctx, familia=secrets.token_hex(16))

    # ----------------------------------------------------- usuarios y roles
    def grupos_de(self, oid: str) -> list[str]:
        return [g["id"] for g in self.graph.paginar(f"/users/{oid}/transitiveMemberOf/microsoft.graph.group", {"$select": "id", "$top": "999"})]

    def sincronizar_usuario(self, identidad: entra.IdentidadEntra, ctx: Contexto) -> m.Usuario:
        grupos = self.grupos_de(identidad.oid) if identidad.grupos_excedidos else identidad.grupos
        rol = rol_para(grupos, identidad.roles)
        usuario = self._buscar(identidad.oid, identidad.correo)
        if rol is None:
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", usuario=usuario, correo=identidad.correo,
                                     detalle={"motivo": "sin grupo de la Mesa"}, resultado="ERROR")
            self.session.commit()
            raise NoAutorizado("Su cuenta no pertenece a ningún grupo autorizado para usar la Mesa de Servicios")
        if usuario is not None and (not usuario.activo or usuario.eliminado):
            raise NoAutorizado("Su usuario está desactivado en la Mesa de Servicios. Contacte al administrador.")
        return self._aplicar(usuario, identidad.oid, identidad.nombre, identidad.correo, None, rol, ctx)

    def _buscar(self, oid: str, correo: str) -> m.Usuario | None:
        u = self.session.scalars(select(m.Usuario).where(m.Usuario.entra_oid == oid)).first()
        return u or self.usuarios.por_correo(correo)

    def _aplicar(self, usuario: m.Usuario | None, oid: str, nombre: str, correo: str, cargo: str | None, rol: str, ctx: Contexto) -> m.Usuario:
        rol_obj = self.usuarios.rol_por_codigo(rol)
        if rol_obj is None:
            raise NoAutorizado(f"El rol «{rol}» configurado para Entra ID no existe en la Mesa")
        if usuario is None:
            usuario = self.usuarios.add(m.Usuario(nombre=nombre[:150], correo=correo[:150], entra_oid=oid, origen_autenticacion="ENTRA",
                                                  cargo=cargo, rol_id=rol_obj.id, fecha_creacion=utcnow()))
            self.session.refresh(usuario)
            self.auditoria.registrar(ctx, AccionAuditoria.USUARIO_MODIFICADO, "usuario", usuario.id, {"operacion": "crear", "correo": usuario.correo, "rol": rol, "origen": "Entra ID"})
            return usuario
        cambios = {}
        if usuario.rol.codigo != rol:
            cambios["rol"] = [usuario.rol.codigo, rol]
            usuario.rol_id = rol_obj.id
        usuario.entra_oid, usuario.origen_autenticacion = oid, "ENTRA"
        usuario.nombre, usuario.correo = nombre[:150], correo[:150]
        usuario.clave_hash, usuario.debe_cambiar_clave = None, False   # sin contraseña local
        if cargo:
            usuario.cargo = cargo
        usuario.fecha_actualizacion = utcnow()
        if cambios:
            self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_ROL, "usuario", usuario.id, {"correo": usuario.correo, **cambios, "origen": "grupos de Entra ID"})
        self.session.flush()
        self.session.refresh(usuario)
        return usuario

    def sincronizar_grupos(self) -> dict:
        """Recorre los miembros de cada grupo mapeado: crea usuarios, actualiza roles y desactiva cuentas deshabilitadas."""
        if not settings.ENTRA_GRUPO_ROLES:
            return {"omitido": "ENTRA_GRUPO_ROLES vacío"}
        ctx = Contexto(ip="sync-entra", equipo="worker")
        miembros: dict[str, dict] = {}
        for grupo in settings.ENTRA_GRUPO_ROLES:
            for u in self.graph.paginar(f"/groups/{grupo}/transitiveMembers/microsoft.graph.user",
                                        {"$select": "id,displayName,mail,userPrincipalName,jobTitle,accountEnabled", "$top": "999"}):
                miembros.setdefault(u["id"], {**u, "grupos": []})["grupos"].append(grupo)
        stats = {"miembros": len(miembros), "creados": 0, "actualizados": 0, "desactivados": 0}
        vistos = set()
        for oid, u in miembros.items():
            correo = (u.get("mail") or u.get("userPrincipalName") or "").lower()
            if "@" not in correo:
                continue
            vistos.add(oid)
            existente = self._buscar(oid, correo)
            if not u.get("accountEnabled", True):
                if existente and existente.activo:
                    existente.activo = False
                    stats["desactivados"] += 1
                continue
            rol = rol_para(u["grupos"], [])
            self._aplicar(existente, oid, u.get("displayName") or correo, correo, u.get("jobTitle"), rol, ctx)
            stats["creados" if existente is None else "actualizados"] += 1
        # Quien salió de todos los grupos mapeados vuelve al rol por defecto (o se desactiva si no hay rol por defecto)
        for u in self.session.scalars(select(m.Usuario).where(m.Usuario.origen_autenticacion == "ENTRA", m.Usuario.activo == True)).unique():
            if u.entra_oid and u.entra_oid not in vistos:
                defecto = settings.ENTRA_ROL_DEFECTO.upper()
                if not defecto:
                    u.activo = False
                    stats["desactivados"] += 1
                elif u.rol.codigo != defecto:
                    self._aplicar(u, u.entra_oid, u.nombre, u.correo, None, defecto, ctx)
                    stats["actualizados"] += 1
        self.session.commit()
        return stats
