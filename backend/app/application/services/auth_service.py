"""Login, refresh token rotativo, logout y cambio de contraseña."""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoAutorizado, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import (
    crear_access_token,
    hash_clave,
    hash_token,
    nuevo_refresh_token,
    utcnow,
    validar_politica_clave,
    verificar_clave,
)
from app.domain.enums import AccionAuditoria, Rol
from app.infrastructure.auth.proveedores import ProveedorLdap, ProveedorLocal
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, RefreshTokenRepository, UsuarioRepository

MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"


def usuario_sesion(u: m.Usuario) -> dict:
    return {
        "id": u.id, "nombre": u.nombre, "correo": u.correo, "cargo": u.cargo, "telefono": u.telefono,
        "rol": u.rol.codigo, "rol_nombre": u.rol.nombre, "area": u.area.nombre if u.area else None,
        "permisos": sorted(u.permisos), "debe_cambiar_clave": u.debe_cambiar_clave,
    }


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.usuarios = UsuarioRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.auditoria = AuditoriaService(session)

    # ---------------------------------------------------------------- login
    def login(self, identificador: str, clave: str, ctx: Contexto) -> dict:
        ahora = utcnow()
        identificador = identificador.strip()
        if settings.AUTH_PROVIDER == "entra" and identificador.lower() not in {c.lower() for c in settings.ENTRA_CUENTAS_EMERGENCIA}:
            # Con Entra ID no hay contraseñas locales, salvo las cuentas de emergencia declaradas
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", correo=identificador[:150], detalle={"motivo": "login local deshabilitado"}, resultado="ERROR")
            self.session.commit()
            raise NoAutorizado("Inicie sesión con su cuenta de Microsoft 365")
        usuario = self.usuarios.por_correo(identificador) or (
            self.usuarios.por_usuario_ad(identificador.split("\\")[-1]) if "@" not in identificador else None
        )

        if usuario and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", usuario=usuario, detalle={"motivo": "bloqueado"}, resultado="ERROR")
            raise NoAutorizado("Cuenta bloqueada temporalmente por intentos fallidos. Intente más tarde.")

        valido = False
        usar_ad = settings.AUTH_PROVIDER == "ldap" and (usuario is None or usuario.origen_autenticacion == "AD")
        if usar_ad:
            identidad = ProveedorLdap().autenticar(identificador, clave)
            if identidad:
                usuario = self._sincronizar_ad(usuario, identidad)
                valido = usuario is not None
        elif usuario:
            valido = ProveedorLocal().verificar(clave, usuario.clave_hash)

        if not valido or usuario is None or not usuario.activo:
            if usuario:
                maximo, minutos = self._politica_bloqueo()
                usuario.intentos_fallidos += 1
                if usuario.intentos_fallidos >= maximo:
                    usuario.bloqueado_hasta = ahora + timedelta(minutes=minutos)
                    usuario.intentos_fallidos = 0
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", usuario=usuario, correo=identificador[:150], resultado="ERROR")
            # commit explícito: el contador de intentos debe persistir aunque la request termine en error
            self.session.commit()
            raise NoAutorizado(MENSAJE_CREDENCIALES)

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_login = ahora
        self.auditoria.registrar(ctx, AccionAuditoria.LOGIN, "sesion", usuario=usuario)
        return self._emitir(usuario, ctx, familia=secrets.token_hex(16))

    def _politica_bloqueo(self) -> tuple[int, int]:
        """Intentos y minutos de bloqueo definidos en Configuración; si no son válidos, los del .env."""
        config = CatalogoRepository(self.session).configuracion()
        try:
            maximo = int(config.get("seguridad.max_intentos", settings.MAX_LOGIN_INTENTOS))
            minutos = int(config.get("seguridad.bloqueo_min", settings.BLOQUEO_MINUTOS))
        except ValueError:
            return settings.MAX_LOGIN_INTENTOS, settings.BLOQUEO_MINUTOS
        return (maximo if maximo > 0 else settings.MAX_LOGIN_INTENTOS), (minutos if minutos > 0 else settings.BLOQUEO_MINUTOS)

    def _sincronizar_ad(self, usuario: m.Usuario | None, identidad) -> m.Usuario | None:
        rol_ad = ProveedorLdap.rol_por_grupos(identidad.grupos)
        if usuario is None:
            if not settings.LDAP_CREAR_USUARIOS:
                return None
            usuario = self.usuarios.por_correo(identidad.correo)
        if usuario is None:
            rol = self.usuarios.rol_por_codigo(rol_ad or Rol.CLIENTE)
            usuario = self.usuarios.add(m.Usuario(nombre=identidad.nombre, correo=identidad.correo, usuario_ad=identidad.usuario_ad,
                                                  origen_autenticacion="AD", cargo=identidad.cargo, rol_id=rol.id))
            self.session.refresh(usuario)
        else:
            usuario.nombre, usuario.usuario_ad, usuario.origen_autenticacion = identidad.nombre, identidad.usuario_ad, "AD"
            if identidad.cargo:
                usuario.cargo = identidad.cargo
            if rol_ad and rol_ad != usuario.rol.codigo:
                usuario.rol_id = self.usuarios.rol_por_codigo(rol_ad).id
        return usuario

    def _emitir(self, usuario: m.Usuario, ctx: Contexto, familia: str) -> dict:
        access, expira = crear_access_token(usuario.id, usuario.rol.codigo, usuario.nombre)
        refresh, refresh_hash = nuevo_refresh_token()
        registro = self.tokens.add(
            m.RefreshToken(usuario_id=usuario.id, token_hash=refresh_hash, familia=familia, fecha_creacion=utcnow(),
                           fecha_expiracion=utcnow() + timedelta(days=settings.REFRESH_TOKEN_DAYS), ip=ctx.ip, equipo=(ctx.equipo or "")[:300])
        )
        self.session.flush()
        self._ultimo_emitido = registro
        return {"access_token": access, "refresh_token": refresh, "expires_in": expira, "usuario": usuario_sesion(usuario)}

    # -------------------------------------------------------------- refresh
    def refrescar(self, refresh_token: str, ctx: Contexto) -> dict:
        ahora = utcnow()
        registro = self.tokens.por_hash(hash_token(refresh_token))
        if registro is None:
            raise NoAutorizado("Sesión inválida")
        if registro.revocado:
            # Reutilización de un token ya rotado: posible robo. Se revoca toda la cadena.
            self.tokens.revocar_familia(registro.familia, ahora)
            self.auditoria.registrar(ctx, "REFRESH_REUTILIZADO", "sesion", usuario=self.usuarios.get(registro.usuario_id), resultado="ERROR")
            self.session.commit()
            raise NoAutorizado("Sesión revocada por seguridad. Inicie sesión nuevamente.")
        if registro.fecha_expiracion < ahora:
            raise NoAutorizado("La sesión expiró. Inicie sesión nuevamente.")
        usuario = self.usuarios.get(registro.usuario_id)
        if usuario is None or not usuario.activo or usuario.eliminado:
            raise NoAutorizado("Usuario inactivo")
        respuesta = self._emitir(usuario, ctx, registro.familia)
        registro.revocado, registro.fecha_revocacion, registro.reemplazado_por = True, ahora, self._ultimo_emitido.id
        return respuesta

    # --------------------------------------------------------------- logout
    def logout(self, refresh_token: str | None, ctx: Contexto) -> None:
        if refresh_token:
            registro = self.tokens.por_hash(hash_token(refresh_token))
            if registro and not registro.revocado:
                self.tokens.revocar_familia(registro.familia, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.LOGOUT, "sesion")

    # --------------------------------------------------------- cambio clave
    def cambiar_clave(self, usuario: m.Usuario, actual: str, nueva: str, ctx: Contexto) -> None:
        if usuario.origen_autenticacion == "AD":
            raise ReglaNegocio("La contraseña de esta cuenta se administra en Active Directory")
        if usuario.origen_autenticacion == "ENTRA":
            raise ReglaNegocio("La contraseña de esta cuenta se administra en Microsoft 365")
        if not verificar_clave(actual, usuario.clave_hash):
            raise ReglaNegocio("La contraseña actual no es correcta")
        errores = validar_politica_clave(nueva)
        if errores:
            raise ReglaNegocio("La nueva contraseña no cumple la política", {"errores": errores})
        if verificar_clave(nueva, usuario.clave_hash):
            raise ReglaNegocio("La nueva contraseña debe ser distinta de la actual")
        usuario.clave_hash = hash_clave(nueva)
        usuario.debe_cambiar_clave = False
        usuario.fecha_actualizacion = utcnow()
        self.tokens.revocar_usuario(usuario.id, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_CLAVE, "usuario", usuario.id)
