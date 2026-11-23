"""Verificación en dos pasos (mejora 28).

- Métodos: código de Microsoft/Google Authenticator (TOTP, RFC 6238) o código enviado por correo.
- El código por correo solo se ofrece si el envío de correos está activo (EMAIL_ENABLED) y la política lo permite:
  así nadie queda fuera mientras el correo esté apagado.
- Códigos de respaldo de un solo uso y «Confiar en este equipo» por N días.
- Política por rol en Configuración (claves seguridad.2fa_*). Las cuentas de emergencia quedan fuera.
- Un administrador puede restablecer la verificación de cualquier persona (queda en Auditoría).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoAutorizado, NoEncontrado, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import hash_token, utcnow, verificar_clave
from app.domain.enums import AccionAuditoria, Rol
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

log = logging.getLogger(__name__)

EMISOR = "Mesa ADUCORP"
MINUTOS_DESAFIO = 10
MAX_INTENTOS = 5
MAX_ENVIOS = 3
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O ni 1/I para no confundir
ROLES_ADMIN = {Rol.SUPER_ADMIN, Rol.ADMIN_MESA, Rol.SUPERVISOR}
ROLES_ANALISTA = {Rol.ANALISTA}

# clave: (valor por defecto, descripción). Todo apagado al instalar: cada uno lo activa cuando quiera.
POLITICA = {
    "seguridad.2fa_admin": ("no", "Verificación en dos pasos obligatoria para Administrador y Supervisor (si/no)"),
    "seguridad.2fa_analistas": ("no", "Verificación en dos pasos obligatoria para Analistas (si/no)"),
    "seguridad.2fa_opcional_otros": ("si", "Verificación en dos pasos opcional para clientes internos y gerencia (si = opcional, no = obligatoria)"),
    "seguridad.2fa_correo": ("si", "Permitir el código por correo como alternativa al celular (solo si el envío de correos está activo)"),
    "seguridad.2fa_solo_fuera_oficina": ("no", "Pedir el código solo al entrar desde fuera de la oficina (si/no)"),
    "seguridad.2fa_redes_oficina": ("", "IP o redes de la oficina separadas por coma, p. ej. 186.46.10.20, 192.168.1.0/24"),
    "seguridad.2fa_dias_confianza": ("30", "Días que se recuerda un equipo de confianza (0 = no ofrecer)"),
    "seguridad.2fa_exentos": ("admin@aducorp.com.ec", "Cuentas de emergencia fuera de la política, separadas por coma"),
}


def _si(v: str | None) -> bool:
    return (v or "").strip().lower() in ("si", "sí", "true", "1", "s")


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


# ----------------------------------------------------------------- TOTP
def nueva_clave() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _b32(clave: str) -> bytes:
    return base64.b32decode(clave + "=" * (-len(clave) % 8))


def codigo_totp(clave: str, paso: int) -> str:
    h = hmac.new(_b32(clave), struct.pack(">Q", paso), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def paso_actual(ahora: float | None = None) -> int:
    return int((ahora if ahora is not None else time.time()) // 30)


def verificar_totp(clave: str, codigo: str, ultimo: int | None, ahora: float | None = None) -> int | None:
    """Acepta el código del periodo actual o el anterior/siguiente (reloj del celular desfasado). Nunca uno ya usado."""
    p = paso_actual(ahora)
    for d in (0, -1, 1):
        if p + d > (ultimo or 0) and hmac.compare_digest(codigo_totp(clave, p + d), codigo):
            return p + d
    return None


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"aducorp-2fa:" + settings.JWT_SECRET.encode()).digest()))


def cifrar(clave: str) -> str:
    return _fernet().encrypt(clave.encode()).decode()


def descifrar(valor: str) -> str:
    try:
        return _fernet().decrypt(valor.encode()).decode()
    except InvalidToken as exc:   # JWT_SECRET cambió: la clave ya no se puede leer
        raise ReglaNegocio("La verificación de esta cuenta debe restablecerse (la clave del servidor cambió). Pida ayuda a TI.") from exc


def uri_authenticator(clave: str, correo: str) -> str:
    return f"otpauth://totp/{quote(EMISOR)}:{quote(correo)}?secret={clave}&issuer={quote(EMISOR)}&digits=6&period=30"


def qr_svg(texto: str) -> str:
    import segno

    return segno.make(texto, error="m").svg_data_uri(scale=5, border=2, dark="#10203C")


def _normalizar(codigo: str) -> str:
    return "".join(ch for ch in (codigo or "").upper() if ch.isalnum())


def mascara_correo(correo: str) -> str:
    local, _, dominio = correo.partition("@")
    return f"{local[:1]}•••••@{dominio}" if dominio else correo


class DosPasosService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ============================================================ política
    def politica(self) -> dict:
        cfg = CatalogoRepository(self.session).configuracion()
        v = {k: cfg.get(k, d) for k, (d, _) in POLITICA.items()}
        try:
            dias = max(0, min(int(v["seguridad.2fa_dias_confianza"] or 0), 365))
        except ValueError:
            dias = 30
        return {
            "obligatoria_admin": _si(v["seguridad.2fa_admin"]),
            "obligatoria_analistas": _si(v["seguridad.2fa_analistas"]),
            "opcional_otros": _si(v["seguridad.2fa_opcional_otros"]),
            "permitir_correo": _si(v["seguridad.2fa_correo"]),
            "solo_fuera_oficina": _si(v["seguridad.2fa_solo_fuera_oficina"]),
            "redes_oficina": v["seguridad.2fa_redes_oficina"] or "",
            "dias_confianza": dias,
            "exentos": [c.strip().lower() for c in (v["seguridad.2fa_exentos"] or "").replace(";", ",").split(",") if c.strip()],
            "correo_activo": bool(settings.EMAIL_ENABLED),
        }

    def correo_disponible(self, pol: dict | None = None) -> bool:
        pol = pol or self.politica()
        return bool(settings.EMAIL_ENABLED and pol["permitir_correo"])

    @staticmethod
    def _exigida_por_rol(u: m.Usuario, pol: dict) -> bool:
        if u.correo.lower() in pol["exentos"]:
            return False
        rol = u.rol.codigo
        if rol in ROLES_ADMIN:
            return pol["obligatoria_admin"]
        if rol in ROLES_ANALISTA:
            return pol["obligatoria_analistas"]
        return not pol["opcional_otros"]

    def exigida(self, u: m.Usuario, pol: dict | None = None) -> bool:
        return self._exigida_por_rol(u, pol or self.politica())

    @staticmethod
    def en_oficina(ip: str | None, redes: str) -> bool:
        if not ip or not redes.strip():
            return False
        try:
            direccion = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for r in redes.replace(";", ",").split(","):
            try:
                if r.strip() and direccion in ipaddress.ip_network(r.strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False

    def guardar_politica(self, datos: dict, ctx: Contexto) -> dict:
        valores = {
            "seguridad.2fa_admin": "si" if datos["obligatoria_admin"] else "no",
            "seguridad.2fa_analistas": "si" if datos["obligatoria_analistas"] else "no",
            "seguridad.2fa_opcional_otros": "si" if datos["opcional_otros"] else "no",
            "seguridad.2fa_correo": "si" if datos["permitir_correo"] else "no",
            "seguridad.2fa_solo_fuera_oficina": "si" if datos["solo_fuera_oficina"] else "no",
            "seguridad.2fa_redes_oficina": (datos.get("redes_oficina") or "").strip(),
            "seguridad.2fa_dias_confianza": str(int(datos["dias_confianza"])),
            "seguridad.2fa_exentos": ", ".join(c.strip().lower() for c in datos.get("exentos") or [] if c.strip()),
        }
        if valores["seguridad.2fa_solo_fuera_oficina"] == "si":
            for r in valores["seguridad.2fa_redes_oficina"].replace(";", ",").split(","):
                try:
                    if r.strip():
                        ipaddress.ip_network(r.strip(), strict=False)
                except ValueError as exc:
                    raise ReglaNegocio(f"«{r.strip()}» no es una IP o red válida") from exc
            if not valores["seguridad.2fa_redes_oficina"]:
                raise ReglaNegocio("Indique la IP o red de la oficina para no pedir el código allí")
        quien = ctx.usuario
        if quien is not None and quien.correo.lower() not in [c.strip() for c in valores["seguridad.2fa_exentos"].split(",")]:
            pass   # el administrador puede quedar dentro de la política: él mismo activa su verificación
        ahora = utcnow()
        for k, v in valores.items():
            fila = self.session.get(m.Configuracion, k)
            if fila is None:
                self.session.add(m.Configuracion(clave=k, valor=v, descripcion=POLITICA[k][1], fecha_actualizacion=ahora,
                                                 actualizado_por=quien.id if quien else None))
            elif fila.valor != v:
                fila.valor, fila.fecha_actualizacion, fila.actualizado_por = v, ahora, quien.id if quien else None
        self.session.flush()
        pol = self.politica()
        # Desde cuándo se le exige a cada quien que aún no la activa («Pendiente · 2 días»)
        for u in self._usuarios():
            if self._exigida_por_rol(u, pol) and not u.dosf_metodo:
                u.dosf_exigido_desde = u.dosf_exigido_desde or ahora
            elif not self._exigida_por_rol(u, pol):
                u.dosf_exigido_desde = None
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_POLITICA, "configuracion", None, {k: v for k, v in valores.items()})
        return pol

    def _usuarios(self) -> list[m.Usuario]:
        from app.application.services.notificacion_service import cuentas_sistema

        U = m.Usuario
        sistema = cuentas_sistema()
        return [u for u in self.session.scalars(select(U).where(U.activo == True, U.eliminado == False).order_by(U.nombre)).unique()
                if u.correo.lower() not in sistema]

    def estado_usuarios(self) -> list[dict]:
        pol = self.politica()
        ahora = utcnow()
        filas = []
        for u in self._usuarios():
            exigida = self._exigida_por_rol(u, pol)
            filas.append({
                "id": u.id, "nombre": u.nombre, "correo": u.correo, "rol": u.rol.nombre, "rol_codigo": u.rol.codigo,
                "metodo": u.dosf_metodo, "fecha": iso(u.dosf_fecha), "exigida": exigida,
                "exento": u.correo.lower() in pol["exentos"],
                "pendiente_dias": (ahora - u.dosf_exigido_desde).days if exigida and not u.dosf_metodo and u.dosf_exigido_desde else None,
                "codigos_restantes": len(self._codigos(u)) if u.dosf_metodo else None,
            })
        return filas

    # ================================================== al iniciar sesión
    def segundo_paso(self, u: m.Usuario, ctx: Contexto, equipo_token: str | None) -> dict | None:
        """None si puede entrar directo; si no, los datos para la pantalla de verificación o de activación."""
        pol = self.politica()
        exigida = self._exigida_por_rol(u, pol)
        if not u.dosf_metodo and not exigida:
            return None
        if pol["solo_fuera_oficina"] and self.en_oficina(ctx.ip, pol["redes_oficina"]):
            return None
        if u.dosf_metodo and equipo_token and self._equipo_valido(u, equipo_token):
            return None
        if not u.dosf_metodo:
            u.dosf_exigido_desde = u.dosf_exigido_desde or utcnow()
        token, desafio = self._crear_desafio(u, "LOGIN" if u.dosf_metodo else "ACTIVAR")
        enviado = False
        if u.dosf_metodo == "CORREO" and self.correo_disponible(pol):
            enviado = self._enviar_codigo(desafio)
        return {
            "desafio": token, "modo": "VERIFICAR" if u.dosf_metodo else "ACTIVAR", "metodo": u.dosf_metodo, "nombre": u.nombre,
            "correo_mascara": mascara_correo(u.correo), "puede_correo": self.correo_disponible(pol), "codigo_enviado": enviado,
            "dias_confianza": pol["dias_confianza"],
        }

    def _equipo_valido(self, u: m.Usuario, token: str) -> bool:
        E = m.DosfEquipo
        e = self.session.scalar(select(E).where(E.token_hash == hash_token(token)))
        return bool(e and e.usuario_id == u.id and not e.revocado and e.fecha_expiracion > utcnow())

    def _crear_desafio(self, u: m.Usuario, proposito: str) -> tuple[str, m.DosfDesafio]:
        token = secrets.token_urlsafe(32)
        ahora = utcnow()
        d = m.DosfDesafio(token_hash=hash_token(token), usuario_id=u.id, proposito=proposito, fecha_creacion=ahora,
                          fecha_expiracion=ahora + timedelta(minutes=MINUTOS_DESAFIO))
        d.usuario = u
        self.session.add(d)
        self.session.flush()
        return token, d

    def desafio(self, token: str, proposito: str | None = None) -> m.DosfDesafio:
        D = m.DosfDesafio
        d = self.session.scalar(select(D).where(D.token_hash == hash_token(token or "")))
        if d is None or d.usado or d.fecha_expiracion < utcnow() or (proposito and d.proposito != proposito):
            raise NoAutorizado("La verificación expiró. Vuelva a ingresar su contraseña.")
        if d.intentos >= MAX_INTENTOS:
            raise NoAutorizado("Demasiados códigos incorrectos. Vuelva a ingresar su contraseña.")
        u = d.usuario
        if not u.activo or u.eliminado:
            raise NoAutorizado("Usuario inactivo")
        return d

    def _enviar_codigo(self, d: m.DosfDesafio) -> bool:
        """Código de 6 dígitos por correo, válido 10 minutos. Se envía en el momento (no espera la cola del worker)."""
        from app.infrastructure.email.smtp import enviador, plantilla_base

        if not self.correo_disponible():
            raise ReglaNegocio("El código por correo no está disponible: use la app del celular o un código de respaldo.")
        if d.envios >= MAX_ENVIOS:
            raise ReglaNegocio("Ya se enviaron varios códigos. Revise su bandeja (y la carpeta de correo no deseado).")
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        d.codigo_hash, d.codigo_expira, d.envios = hash_token(codigo), utcnow() + timedelta(minutes=MINUTOS_DESAFIO), d.envios + 1
        cuerpo = (f"<p>Hola {d.usuario.nombre}:</p><p>Su código para entrar a la Mesa de Servicios es</p>"
                  f"<p style=\"font-size:30px;font-weight:700;letter-spacing:8px;color:#10203C\">{codigo}</p>"
                  f"<p>Vence en {MINUTOS_DESAFIO} minutos. Si usted no está intentando ingresar, cambie su contraseña y avise a TI.</p>")
        try:
            enviador().enviar(d.usuario.correo, f"{codigo} es su código de la Mesa de Servicios", plantilla_base(cuerpo))
        except Exception:   # noqa: BLE001 - el usuario debe enterarse sin ver detalles técnicos
            log.exception("No se pudo enviar el código de verificación a %s", d.usuario.correo)
            raise ReglaNegocio("No se pudo enviar el correo en este momento. Use la app del celular o un código de respaldo.")
        return True

    def enviar_codigo(self, token: str) -> dict:
        d = self.desafio(token)
        self._enviar_codigo(d)
        return {"enviado_a": mascara_correo(d.usuario.correo)}

    def _fallo(self, d: m.DosfDesafio, ctx: Contexto, motivo: str) -> None:
        d.intentos += 1
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_FALLIDA, "sesion", usuario=d.usuario, detalle={"motivo": motivo}, resultado="ERROR")
        self.session.commit()   # el contador de intentos debe quedar aunque la respuesta sea un error
        restantes = MAX_INTENTOS - d.intentos
        raise NoAutorizado("Código incorrecto." + (f" Le quedan {restantes} intentos." if restantes > 0 else " Vuelva a ingresar su contraseña."))

    def _codigos(self, u: m.Usuario) -> list[str]:
        try:
            return list(json.loads(u.dosf_codigos or "[]"))
        except ValueError:
            return []

    def _comprobar(self, u: m.Usuario, d: m.DosfDesafio | None, codigo: str, clave: str | None) -> str | None:
        """Devuelve el medio con que se validó (APP, CORREO o RESPALDO) o None."""
        limpio = _normalizar(codigo)
        if len(limpio) == 6 and limpio.isdigit():
            if d is not None and d.codigo_hash and d.codigo_expira and d.codigo_expira > utcnow() \
                    and hmac.compare_digest(d.codigo_hash, hash_token(limpio)):
                d.codigo_hash = None
                return "CORREO"
            if clave:
                paso = verificar_totp(clave, limpio, u.dosf_ultimo_paso)
                if paso is not None:
                    u.dosf_ultimo_paso = paso
                    return "APP"
            return None
        if len(limpio) == 8 and u.dosf_metodo:
            codigos = self._codigos(u)
            h = hashlib.sha256(limpio.encode()).hexdigest()
            if h in codigos:
                codigos.remove(h)
                u.dosf_codigos = json.dumps(codigos)
                return "RESPALDO"
        return None

    def verificar(self, token: str, codigo: str, confiar: bool, ctx: Contexto) -> tuple[m.Usuario, str | None, str]:
        d = self.desafio(token, "LOGIN")
        u = d.usuario
        clave = descifrar(u.dosf_secreto) if u.dosf_metodo == "APP" and u.dosf_secreto else None
        medio = self._comprobar(u, d, codigo, clave)
        if medio is None:
            self._fallo(d, ctx, "código incorrecto")
        d.usado = True
        equipo = self._confiar(u, ctx) if confiar else None
        return u, equipo, medio

    def _confiar(self, u: m.Usuario, ctx: Contexto) -> str | None:
        dias = self.politica()["dias_confianza"]
        if not dias:
            return None
        token = secrets.token_urlsafe(32)
        ahora = utcnow()
        self.session.add(m.DosfEquipo(usuario_id=u.id, token_hash=hash_token(token), equipo=(ctx.equipo or "")[:300], ip=ctx.ip,
                                      fecha_creacion=ahora, fecha_expiracion=ahora + timedelta(days=dias)))
        return token

    # ============================================================ activar
    def iniciar_activacion(self, u: m.Usuario, metodo: str, d: m.DosfDesafio | None = None) -> dict:
        if metodo == "CORREO":
            if not self.correo_disponible():
                raise ReglaNegocio("El código por correo no está disponible. Use Microsoft o Google Authenticator.")
            if d is None:
                _, d = self._crear_desafio(u, "ACTIVAR")
            self._enviar_codigo(d)
            return {"metodo": "CORREO", "enviado_a": mascara_correo(u.correo)}
        clave = nueva_clave()
        u.dosf_pendiente = cifrar(clave)
        uri = uri_authenticator(clave, u.correo)
        return {"metodo": "APP", "clave": " ".join(clave[i:i + 4] for i in range(0, len(clave), 4)), "uri": uri, "qr": qr_svg(uri)}

    def _desafio_activacion(self, u: m.Usuario) -> m.DosfDesafio | None:
        D = m.DosfDesafio
        return self.session.scalars(select(D).where(D.usuario_id == u.id, D.proposito == "ACTIVAR", D.usado == False,
                                                    D.fecha_expiracion > utcnow()).order_by(D.id.desc())).first()

    def confirmar_activacion(self, u: m.Usuario, metodo: str, codigo: str, ctx: Contexto, d: m.DosfDesafio | None = None) -> list[str]:
        if metodo == "CORREO":
            d = d or self._desafio_activacion(u)
            if d is None or self._comprobar(u, d, codigo, None) != "CORREO":
                if d is not None:
                    self._fallo(d, ctx, "código de activación incorrecto")
                raise ReglaNegocio("El código no es correcto o ya venció. Pida uno nuevo.")
            u.dosf_secreto = None
        else:
            if not u.dosf_pendiente:
                raise ReglaNegocio("Primero escanee el código QR")
            clave = descifrar(u.dosf_pendiente)
            paso = verificar_totp(clave, _normalizar(codigo), None)
            if paso is None:
                if d is not None:
                    self._fallo(d, ctx, "código de activación incorrecto")
                raise ReglaNegocio("El código no coincide. Revise que la hora del celular sea automática y escriba el código actual.")
            u.dosf_secreto, u.dosf_ultimo_paso = u.dosf_pendiente, paso
        if d is not None:
            d.usado = True
        u.dosf_pendiente = None
        u.dosf_metodo, u.dosf_fecha, u.dosf_exigido_desde = metodo, utcnow(), None
        codigos = self._nuevos_codigos(u)
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_ACTIVADA, "usuario", u.id, {"metodo": metodo}, usuario=u)
        return codigos

    def _nuevos_codigos(self, u: m.Usuario) -> list[str]:
        codigos = ["".join(secrets.choice(ALFABETO) for _ in range(8)) for _ in range(8)]
        u.dosf_codigos = json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codigos])
        return [f"{c[:4]}-{c[4:]}" for c in codigos]

    def regenerar_codigos(self, u: m.Usuario, ctx: Contexto) -> list[str]:
        if not u.dosf_metodo:
            raise ReglaNegocio("Primero active la verificación en dos pasos")
        codigos = self._nuevos_codigos(u)
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_ACTIVADA, "usuario", u.id, {"codigos_respaldo": "regenerados"})
        return codigos

    def desactivar(self, u: m.Usuario, clave: str, ctx: Contexto) -> None:
        if self.exigida(u):
            raise ReglaNegocio("Su rol tiene la verificación en dos pasos obligatoria: no se puede desactivar. Puede cambiar de celular volviendo a activarla.")
        if u.origen_autenticacion == "LOCAL" and not verificar_clave(clave or "", u.clave_hash):
            raise ReglaNegocio("La contraseña no es correcta")
        self._limpiar(u)
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_DESACTIVADA, "usuario", u.id)

    def _limpiar(self, u: m.Usuario) -> int:
        u.dosf_metodo = u.dosf_secreto = u.dosf_pendiente = u.dosf_codigos = None
        u.dosf_fecha = u.dosf_ultimo_paso = None
        return self.olvidar_equipos(u)

    def olvidar_equipos(self, u: m.Usuario) -> int:
        E = m.DosfEquipo
        filas = list(self.session.scalars(select(E).where(E.usuario_id == u.id, E.revocado == False)))
        for e in filas:
            e.revocado = True
        return len(filas)

    def restablecer(self, usuario_id: int, ctx: Contexto) -> m.Usuario:
        u = self.session.get(m.Usuario, usuario_id)
        if u is None or u.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        anterior = u.dosf_metodo
        self._limpiar(u)
        if self.exigida(u):
            u.dosf_exigido_desde = utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.DOSF_RESTABLECIDA, "usuario", u.id, {"usuario": u.nombre, "metodo_anterior": anterior})
        return u

    def estado(self, u: m.Usuario) -> dict:
        pol = self.politica()
        E = m.DosfEquipo
        equipos = list(self.session.scalars(select(E).where(E.usuario_id == u.id, E.revocado == False, E.fecha_expiracion > utcnow())))
        return {
            "metodo": u.dosf_metodo, "fecha": iso(u.dosf_fecha), "exigida": self._exigida_por_rol(u, pol),
            "puede_correo": self.correo_disponible(pol), "correo_mascara": mascara_correo(u.correo),
            "codigos_restantes": len(self._codigos(u)) if u.dosf_metodo else 0, "equipos_confianza": len(equipos),
            "dias_confianza": pol["dias_confianza"], "local": u.origen_autenticacion != "ENTRA",
        }
