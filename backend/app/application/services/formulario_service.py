"""Formulario público (/solicitud): personas sin cuenta en la Mesa (clientes, proveedores) registran un ticket.

Protección contra abuso, sin servicios de terceros:
* Ficha firmada (HMAC con JWT_SECRET) que entrega GET /publico/formulario. Se rechaza si se envía antes de
  FICHA_MIN_SEG (los robots envían al instante) o después de FICHA_MAX_SEG.
* Campo trampa «sitio_web», oculto para las personas.
* Límite de solicitudes por IP y por correo (FORMULARIO_WEB_MAX_POR_HORA) y limit_req de Nginx.
* Sin adjuntos: el equipo los pide por correo si hacen falta.

El ticket queda a nombre de una cuenta técnica sin clave (FORMULARIO_WEB_CORREO). El nombre y correo
reales van en el ticket (solicitante_nombre, correo, descripción) y los avisos se envían a ese correo.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from sqlalchemy.orm import Session

from app.application.errores import Contexto, ErrorAplicacion, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.buzon_service import clasificar
from app.application.services.export_service import nombre_empresa
from app.application.services.ticket_service import TicketService
from app.core.config import settings
from app.core.limite import Limitador
from app.core.security import utcnow
from app.domain.enums import Rol
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import UsuarioRepository

NOMBRE_CUENTA = "Formulario web (solicitantes externos)"
FICHA_MIN_SEG = 4
FICHA_MAX_SEG = 2 * 3600

limitador_ip = Limitador(settings.FORMULARIO_WEB_MAX_POR_HORA, 3600)
limitador_correo = Limitador(settings.FORMULARIO_WEB_MAX_POR_HORA, 3600)


class DemasiadasSolicitudes(ErrorAplicacion):
    codigo_http = 429


class FormularioDeshabilitado(ErrorAplicacion):
    codigo_http = 404


def _firma(ts: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), f"formulario-web:{ts}".encode(), hashlib.sha256).hexdigest()[:32]


def emitir_ficha(ahora: float | None = None) -> str:
    ts = str(int(ahora if ahora is not None else time.time()))
    return f"{ts}.{_firma(ts)}"


def ficha_valida(ficha: str, ahora: float | None = None) -> bool:
    ts, _, firma = (ficha or "").partition(".")
    if not ts.isdigit() or not hmac.compare_digest(firma, _firma(ts)):
        return False
    edad = (ahora if ahora is not None else time.time()) - int(ts)
    return FICHA_MIN_SEG <= edad <= FICHA_MAX_SEG


def reiniciar_limites() -> None:
    limitador_ip.reiniciar()
    limitador_correo.reiniciar()


class FormularioService:
    def __init__(self, session: Session):
        self.session = session
        self.tickets = TicketService(session)
        self.usuarios = UsuarioRepository(session)

    def formulario(self) -> dict:
        if not settings.FORMULARIO_WEB_ENABLED:
            raise FormularioDeshabilitado("El formulario público no está habilitado")
        categorias = []
        for c in self.tickets.catalogo.categorias():
            subs = [{"id": x.id, "nombre": x.nombre} for x in c.subcategorias if x.activo and not x.eliminado]
            if subs:
                categorias.append({"id": c.id, "nombre": c.nombre, "subcategorias": subs})
        return {"habilitado": True, "empresa": nombre_empresa(self.session), "categorias": categorias, "token": emitir_ficha()}

    def cuenta(self) -> m.Usuario:
        correo = settings.FORMULARIO_WEB_CORREO.lower()
        u = self.usuarios.por_correo(correo)
        if u is None:
            u = self.usuarios.add(m.Usuario(nombre=NOMBRE_CUENTA, correo=correo, origen_autenticacion="LOCAL", cargo="Cuenta de sistema",
                                            rol_id=self.usuarios.rol_por_codigo(Rol.CLIENTE).id, fecha_creacion=utcnow()))
            self.session.refresh(u)
        return u

    def registrar(self, dto: s.SolicitudPublica, ip: str | None, equipo: str | None) -> m.Ticket:
        if not settings.FORMULARIO_WEB_ENABLED:
            raise FormularioDeshabilitado("El formulario público no está habilitado")
        if (dto.sitio_web or "").strip() or not ficha_valida(dto.token):
            raise ReglaNegocio("No se pudo validar el formulario. Recargue la página e inténtelo de nuevo.")
        correo = str(dto.correo).lower()
        if not limitador_ip.permitir(ip or "?") or not limitador_correo.permitir(correo):
            raise DemasiadasSolicitudes("Recibimos varias solicitudes en poco tiempo. Inténtelo de nuevo en una hora o escríbanos por correo.")

        nombre, asunto, texto = dto.nombre.strip(), dto.asunto.strip(), dto.descripcion.strip()
        if dto.categoria_id and dto.subcategoria_id:
            categoria_id, subcategoria_id, aviso = dto.categoria_id, dto.subcategoria_id, None
        else:
            categoria_id, subcategoria_id, aviso = clasificar(self.tickets, asunto, texto)
        datos = [f"Solicitante externo: {nombre} <{correo}>"]
        if dto.empresa and dto.empresa.strip():
            datos.append(f"Empresa: {dto.empresa.strip()}")
        if dto.telefono and dto.telefono.strip():
            datos.append(f"Teléfono: {dto.telefono.strip()}")
        descripcion = "\n".join(datos) + "\n\n" + texto

        cuenta = self.cuenta()
        ctx = Contexto(usuario=cuenta, ip=ip, equipo=f"Formulario web · {equipo or ''}"[:300])
        t = self.tickets.crear(s.TicketCrear(asunto=asunto, descripcion=descripcion, categoria_id=categoria_id,
                                             subcategoria_id=subcategoria_id, telefono=(dto.telefono or "").strip() or None,
                                             correo=correo, canal="WEB"), ctx)
        t.solicitante_nombre = nombre[:150]
        if dto.empresa and dto.empresa.strip():
            t.solicitante_cargo = dto.empresa.strip()[:100]
        if aviso:
            self.tickets._agregar_comentario(t, cuenta, aviso, True, "SISTEMA", None, utcnow())
        self.session.flush()
        self.session.refresh(t)
        self.tickets.notif.correo_directo("ACUSE_WEB", correo, nombre, t, url=f"{settings.APP_URL.rstrip('/')}/solicitud")
        return t
