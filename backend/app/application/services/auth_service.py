"""Login, refresh token rotativo, logout y cambio de contraseña."""
from __future__ import annotations

import html
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoAutorizado, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import (
    crear_access_token,
    datos_personales,
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
MENSAJE_INACTIVIDAD = "Su sesión se cerró por inactividad. Inicie sesión nuevamente."
# Hash de una clave que nadie usa: si el correo no existe se compara igual contra él, para que la respuesta tarde lo mismo
# y no se pueda saber por el tiempo qué correos tienen cuenta (auditoría 2026-11, hallazgo 9).
_HASH_FICTICIO = hash_clave(secrets.token_urlsafe(16))


def usuario_sesion(u: m.Usuario) -> dict:
    return {
        "id": u.id, "nombre": u.nombre, "correo": u.correo, "cargo": u.cargo, "telefono": u.telefono,
        "rol": u.rol.codigo, "rol_nombre": u.rol.nombre, "area": u.area.nombre if u.area else None,
        "permisos": sorted(u.permisos), "debe_cambiar_clave": u.debe_cambiar_clave, "equipo_ti": bool(u.equipo_ti),
        "dosf_dias_restantes": _dias_2fa(u),
    }


def _dias_2fa(u: m.Usuario) -> int | None:
    from sqlalchemy.orm import object_session

    from app.application.services.dos_pasos_service import DosPasosService

    sesion = object_session(u)
    return DosPasosService(sesion).dias_restantes(u) if sesion is not None and not u.dosf_metodo else None


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.usuarios = UsuarioRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.auditoria = AuditoriaService(session)

    # ---------------------------------------------------------------- login
    def login(self, identificador: str, clave: str, ctx: Contexto, equipo_token: str | None = None) -> dict:
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
        else:
            verificar_clave(clave, _HASH_FICTICIO)

        if not valido or usuario is None or not usuario.activo:
            if usuario:
                maximo, minutos = self._politica_bloqueo()
                usuario.intentos_fallidos += 1
                if usuario.intentos_fallidos >= maximo:
                    usuario.bloqueado_hasta = ahora + timedelta(minutes=minutos)
                    usuario.intentos_fallidos = 0
                    self._avisar_bloqueo(usuario, ctx, maximo, minutos)
            self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_FALLIDO, "sesion", usuario=usuario, correo=identificador[:150], resultado="ERROR")
            # commit explícito: el contador de intentos debe persistir aunque la request termine en error
            self.session.commit()
            raise NoAutorizado(MENSAJE_CREDENCIALES)

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        from app.application.services.dos_pasos_service import DosPasosService

        paso = DosPasosService(self.session).segundo_paso(usuario, ctx, equipo_token)
        if paso is not None:   # contraseña correcta: falta el código del celular, del correo o de respaldo
            return {"segundo_paso": paso}
        return self.completar_login(usuario, ctx)

    def completar_login(self, usuario: m.Usuario, ctx: Contexto, detalle: dict | None = None, **extra) -> dict:
        usuario.ultimo_login = utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.LOGIN, "sesion", usuario=usuario, detalle=detalle)
        self._avisar_si_emergencia(usuario, ctx)
        return {**self._emitir(usuario, ctx, familia=secrets.token_hex(16)), **extra}

    # ------------------------------------------------- avisos de seguridad (37)
    def _correo(self, para: str, asunto: str, cuerpo: str, plantilla: str) -> None:
        from app.infrastructure.email.smtp import plantilla_base

        if para:
            self.session.add(m.ColaCorreo(para=para[:500], asunto=asunto[:250], cuerpo_html=plantilla_base(cuerpo), plantilla=plantilla,
                                          estado="PENDIENTE", proximo_intento=utcnow(), fecha_creacion=utcnow()))

    def _avisar_bloqueo(self, usuario: m.Usuario, ctx: Contexto, intentos: int, minutos: int) -> None:
        """Correo a la persona cuando su cuenta se bloquea: si no fue ella, alguien está probando su contraseña."""
        from app.application.services.notificacion_service import TZ_LABEL, cuentas_sistema, fecha_local

        self.auditoria.registrar(ctx, AccionAuditoria.CUENTA_BLOQUEADA, "usuario", usuario.id,
                                 {"intentos": intentos, "minutos": minutos}, usuario=usuario)
        config = CatalogoRepository(self.session).configuracion()
        if (config.get("seguridad.aviso_bloqueo", "si") or "").strip().lower() not in ("si", "sí", "true", "1") \
                or usuario.correo.lower() in cuentas_sistema():
            return
        filas = [("Fecha y hora", f"{fecha_local(utcnow())} ({TZ_LABEL})"), ("Dirección IP", ctx.ip or "desconocida"),
                 ("Navegador", (ctx.equipo or "desconocido")[:120]), ("Se desbloquea", f"{fecha_local(usuario.bloqueado_hasta)}")]
        tabla = "".join(f"<tr><td style='color:#5A6577;padding:4px 12px 4px 0'>{k}</td><td><b>{html.escape(v)}</b></td></tr>" for k, v in filas)
        cuerpo = (f"<p>Hola {html.escape(usuario.nombre)}:</p><p>Hubo {intentos} intentos fallidos de entrar a la Mesa de Servicios con su usuario. "
                  f"Por seguridad, su cuenta quedó bloqueada {minutos} minutos.</p><table>{tabla}</table>"
                  "<p><b>¿Fue usted?</b> Espere y vuelva a intentarlo, o pida a TI que restablezca su contraseña.</p>"
                  "<p><b>¿No fue usted?</b> Responda este correo o avise a TI: alguien podría estar intentando entrar con su usuario.</p>")
        self._correo(usuario.correo, "Su cuenta de la Mesa de Servicios se bloqueó temporalmente", cuerpo, "CUENTA_BLOQUEADA")

    def _avisar_si_emergencia(self, usuario: m.Usuario, ctx: Contexto) -> None:
        """Ingreso con una cuenta exenta de la verificación en dos pasos (cuenta de emergencia): aviso inmediato a TI."""
        from app.application.services.dos_pasos_service import DosPasosService
        from app.application.services.notificacion_service import TZ_LABEL, fecha_local

        if usuario.correo.lower() not in DosPasosService(self.session).politica()["exentos"]:
            return
        self.auditoria.registrar(ctx, AccionAuditoria.LOGIN_EMERGENCIA, "sesion", usuario=usuario, detalle={"ip": ctx.ip})
        para = CatalogoRepository(self.session).configuracion().get("seguridad.correos_alerta", "") or ""
        cuerpo = (f"<p>Alguien entró a la Mesa de Servicios con la cuenta de emergencia <b>{html.escape(usuario.correo)}</b>, "
                  "que no pide verificación en dos pasos.</p>"
                  f"<p>Fecha: <b>{fecha_local(utcnow())} ({TZ_LABEL})</b><br>IP: <b>{html.escape(ctx.ip or 'desconocida')}</b><br>"
                  f"Navegador: {html.escape((ctx.equipo or '')[:150])}</p>"
                  "<p>Si no fue una emergencia conocida, cambie de inmediato la contraseña de esa cuenta y revise la Auditoría.</p>")
        self._correo(", ".join(c.strip() for c in para.replace(";", ",").split(",") if c.strip()),
                     f"Ingreso con la cuenta de emergencia {usuario.correo}", cuerpo, "LOGIN_EMERGENCIA")

    def _politica_bloqueo(self) -> tuple[int, int]:
        """Intentos y minutos de bloqueo definidos en Configuración; si no son válidos, los del .env."""
        config = CatalogoRepository(self.session).configuracion()
        try:
            maximo = int(config.get("seguridad.max_intentos", settings.MAX_LOGIN_INTENTOS))
            minutos = int(config.get("seguridad.bloqueo_min", settings.BLOQUEO_MINUTOS))
        except ValueError:
            return settings.MAX_LOGIN_INTENTOS, settings.BLOQUEO_MINUTOS
        return (maximo if maximo > 0 else settings.MAX_LOGIN_INTENTOS), (minutos if minutos > 0 else settings.BLOQUEO_MINUTOS)

    def inactividad_min(self) -> int:
        """Minutos sin actividad antes de cerrar la sesión (Configuración; 0 = desactivado)."""
        valor = CatalogoRepository(self.session).configuracion().get("seguridad.inactividad_min")
        try:
            minutos = int(valor) if valor is not None else settings.INACTIVIDAD_MINUTOS
        except ValueError:
            minutos = settings.INACTIVIDAD_MINUTOS
        return max(minutos, 0)

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
        ahora = utcnow()
        registro = self.tokens.add(
            m.RefreshToken(usuario_id=usuario.id, token_hash=refresh_hash, familia=familia, fecha_creacion=ahora,
                           fecha_expiracion=ahora + timedelta(days=settings.REFRESH_TOKEN_DAYS), ip=ctx.ip, equipo=(ctx.equipo or "")[:300])
        )
        self.session.flush()
        self._ultimo_emitido = registro
        return {"access_token": access, "refresh_token": refresh, "expires_in": expira,
                "inactividad_min": self.inactividad_min(), "usuario": usuario_sesion(usuario)}

    # -------------------------------------------------------------- refresh
    def refrescar(self, refresh_token: str, ctx: Contexto, inactivo_seg: int | None = None) -> dict:
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
        # Cierre por inactividad: el navegador informa cuántos segundos lleva el usuario sin interactuar.
        # Las consultas automáticas (notificaciones, listas) renuevan el token, pero no cuentan como actividad.
        # Si no lo informa (versión anterior de la página), se usa la última renovación de esta sesión.
        actividad = registro.fecha_creacion if inactivo_seg is None else ahora - timedelta(seconds=inactivo_seg)
        limite = self.inactividad_min()
        if limite and ahora - actividad > timedelta(minutes=limite):
            self.tokens.revocar_familia(registro.familia, ahora)
            self.auditoria.registrar(ctx, "SESION_INACTIVA", "sesion", usuario=usuario, detalle={"minutos": limite})
            self.session.commit()
            raise NoAutorizado(MENSAJE_INACTIVIDAD)
        respuesta = self._emitir(usuario, ctx, registro.familia)
        registro.revocado, registro.fecha_revocacion, registro.reemplazado_por = True, ahora, self._ultimo_emitido.id
        return respuesta

    # --------------------------------------------------------------- logout
    def logout(self, refresh_token: str | None, ctx: Contexto) -> None:
        if refresh_token:
            registro = self.tokens.por_hash(hash_token(refresh_token))
            if registro and not registro.revocado:
                self.tokens.revocar_familia(registro.familia, utcnow())
                from app.application.services.tiempo_service import TiempoService

                TiempoService(self.session).pausar_usuario(registro.usuario_id)   # (31) el cronómetro se pausa al salir
        self.auditoria.registrar(ctx, AccionAuditoria.LOGOUT, "sesion")

    # --------------------------------------------------------- cambio clave
    def cambiar_clave(self, usuario: m.Usuario, actual: str, nueva: str, ctx: Contexto) -> None:
        if usuario.origen_autenticacion == "AD":
            raise ReglaNegocio("La contraseña de esta cuenta se administra en Active Directory")
        if usuario.origen_autenticacion == "ENTRA":
            raise ReglaNegocio("La contraseña de esta cuenta se administra en Microsoft 365")
        if not verificar_clave(actual, usuario.clave_hash):
            raise ReglaNegocio("La contraseña actual no es correcta")
        errores = validar_politica_clave(nueva, datos_personales(usuario.nombre, usuario.correo))
        if errores:
            raise ReglaNegocio("La nueva contraseña no cumple la política", {"errores": errores})
        if verificar_clave(nueva, usuario.clave_hash):
            raise ReglaNegocio("La nueva contraseña debe ser distinta de la actual")
        previas = self._claves_previas(usuario)
        if any(verificar_clave(nueva, p.clave_hash) for p in previas):
            raise ReglaNegocio(f"No puede repetir ninguna de sus últimas {self._cuantas_previas()} contraseñas")
        self._guardar_previa(usuario, len(previas))
        usuario.clave_hash = hash_clave(nueva)
        usuario.debe_cambiar_clave = False
        usuario.fecha_actualizacion = utcnow()
        self.tokens.revocar_usuario(usuario.id, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_CLAVE, "usuario", usuario.id)

    # ---------------------------------------- contraseñas anteriores (37)
    def _cuantas_previas(self) -> int:
        """Cuántas contraseñas anteriores no se pueden repetir (además de la actual). Configuración › seguridad.claves_previas."""
        valor = CatalogoRepository(self.session).configuracion().get("seguridad.claves_previas", "5")
        try:
            return max(0, min(int(valor), 24))
        except (TypeError, ValueError):
            return 5

    def _claves_previas(self, usuario: m.Usuario) -> list[m.UsuarioClavePrevia]:
        n = self._cuantas_previas()
        if n <= 1:
            return []
        P = m.UsuarioClavePrevia
        return list(self.session.scalars(select(P).where(P.usuario_id == usuario.id).order_by(P.fecha.desc(), P.id.desc()).limit(n - 1)))

    def _guardar_previa(self, usuario: m.Usuario, tenia: int) -> None:
        """Guarda la contraseña que se reemplaza y borra las que ya no hacen falta para el historial."""
        if not usuario.clave_hash or self._cuantas_previas() <= 1:
            return
        P = m.UsuarioClavePrevia
        self.session.add(P(usuario_id=usuario.id, clave_hash=usuario.clave_hash, fecha=utcnow()))
        self.session.flush()
        sobrantes = list(self.session.scalars(select(P).where(P.usuario_id == usuario.id).order_by(P.fecha.desc(), P.id.desc())
                                              .offset(self._cuantas_previas() - 1)))
        for x in sobrantes:
            self.session.delete(x)
