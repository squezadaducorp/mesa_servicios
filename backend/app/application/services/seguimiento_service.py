"""Seguimiento sin cuenta (mejora 20).

Clientes y personas externas (formulario /solicitud o correo a la mesa) reciben en cada correo el botón
«Ver el estado de mi solicitud». El enlace lleva una llave HMAC del ticket (no se puede adivinar cambiando el número)
y muestra solo estado, responsable, plazo estimado y la conversación pública: nunca notas internas ni otros tickets.
Sigue funcionando hasta `seguimiento.dias_vigencia` días después de cerrar el ticket.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import timedelta

from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Estado
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

PASOS = ["Recibido", "Asignado", "En proceso", "Resuelto"]
PASO = {"POR_APROBAR": 0, "NUEVO": 0, "ASIGNADO": 1, "EN_PROCESO": 2, "PENDIENTE_CLIENTE": 2, "ESCALADO": 2, "RESUELTO": 3, "CERRADO": 3,
        "CANCELADO": 3}


def _si(valor: str | None, defecto: bool = True) -> bool:
    return defecto if valor is None else valor.strip().lower() not in ("no", "0", "false")


def token(t: m.Ticket) -> str:
    firma = hmac.new(settings.JWT_SECRET.encode(), f"seguimiento:{t.id}:{t.numero}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(firma).decode().rstrip("=")[:32]


class SeguimientoService:
    def __init__(self, session: Session):
        self.session = session
        self.config = CatalogoRepository(session).configuracion()

    @property
    def activo(self) -> bool:
        return _si(self.config.get("seguimiento.activo"))

    @property
    def permitir_responder(self) -> bool:
        return _si(self.config.get("seguimiento.permitir_responder"))

    @property
    def dias(self) -> int:
        try:
            return max(int(self.config.get("seguimiento.dias_vigencia", "30")), 1)
        except ValueError:
            return 30

    @staticmethod
    def es_externo(t: m.Ticket) -> bool:
        """Lo pidió alguien sin cuenta: por el formulario público o escribiendo al buzón de la mesa."""
        cuenta = (t.solicitante.correo if t.solicitante else "").lower()
        return cuenta in (settings.FORMULARIO_WEB_CORREO.lower(), settings.BUZON_CORREO.lower())

    def url(self, t: m.Ticket) -> str | None:
        """Enlace sin cuenta para cualquier solicitante (externo o del personal); llega en el acuse y en cada correo de su ticket."""
        if not self.activo:
            return None
        return f"{settings.APP_URL.rstrip('/')}/seguimiento/{t.id}/{token(t)}"

    def _vencido(self, t: m.Ticket) -> bool:
        fin = t.fecha_cierre if t.estado == Estado.CERRADO else (t.fecha_actualizacion if t.estado == Estado.CANCELADO else None)
        return bool(fin and fin + timedelta(days=self.dias) < utcnow())

    def verificar(self, ticket_id: int, llave: str) -> m.Ticket:
        t = self.session.get(m.Ticket, ticket_id)
        if not self.activo or t is None or t.eliminado or not hmac.compare_digest(token(t), llave or ""):
            raise NoEncontrado("Enlace no válido. Pida un enlace nuevo con el número de ticket y su correo.")
        if self._vencido(t):
            raise ReglaNegocio(f"Este enlace venció ({self.dias} días después del cierre). Si necesita más ayuda, registre una nueva solicitud.")
        return t

    # ================================================================ vista
    def vista(self, t: m.Ticket, ctx: Contexto) -> dict:
        from app.application.services.encuesta_service import EncuestaService
        from app.infrastructure.repositories.repositorios import TicketRepository

        repo = TicketRepository(self.session)
        cuenta = t.solicitante_id
        abierto = t.estado not in (Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO)
        estimada = t.sla_resolucion_vence if abierto and t.sla_pausa_desde is None and t.estado != Estado.POR_APROBAR else None
        if abierto and t.fecha_primera_respuesta is None and t.sla_respuesta_vence and t.sla_pausa_desde is None \
                and t.estado != Estado.POR_APROBAR and t.sla_respuesta_vence < t.sla_resolucion_vence:
            estimada = t.sla_respuesta_vence
        enc = EncuestaService(self.session)
        encuesta_url = None
        if enc.puede_calificar(None, t):
            encuesta_url = enc.enlaces(t)["url_nota_5"].rsplit("&nota=", 1)[0]
        AuditoriaService(self.session).registrar(ctx, AccionAuditoria.SEGUIMIENTO_PUBLICO_VISTO, "ticket", t.id, {"numero": t.numero})
        return {
            "numero": t.numero, "asunto": t.asunto, "estado": t.estado, "estado_nombre": t.estado_rel.nombre if t.estado_rel else t.estado,
            "pasos": PASOS, "paso": PASO.get(t.estado, 0), "cancelado": t.estado == Estado.CANCELADO,
            "responsable": t.responsable.nombre if t.responsable else None,
            "responsable_area": t.categoria.nombre if t.categoria else None,
            "respuesta_estimada": estimada, "solicitado_por": t.correo, "fecha_creacion": t.fecha_creacion,
            "esperando_su_respuesta": t.estado == Estado.PENDIENTE_CLIENTE,
            "conversacion": [{"autor": "Usted", "propio": True, "texto": t.descripcion, "fecha": t.fecha_creacion}]
            + [{"autor": "Usted" if c.usuario_id == cuenta else c.usuario.nombre, "propio": c.usuario_id == cuenta,
                "texto": c.texto, "fecha": c.fecha} for c in repo.comentarios(t.id, incluir_internos=False)],
            "adjuntos": [{"nombre": a.nombre_original, "propio": a.subido_por == cuenta, "fecha": a.fecha} for a in repo.adjuntos(t.id)],
            "puede_responder": self.permitir_responder and t.estado not in (Estado.CERRADO, Estado.CANCELADO),
            "encuesta_url": encuesta_url,
            "vigencia_dias": self.dias,
        }

    # ============================================================ responder
    def responder(self, t: m.Ticket, texto: str, archivos: list, ctx: Contexto) -> None:
        from app.application.services.ticket_service import TicketService

        if not self.permitir_responder or t.estado in (Estado.CERRADO, Estado.CANCELADO):
            raise ReglaNegocio("Esta solicitud ya no recibe respuestas por este medio")
        texto = (texto or "").strip()
        if len(texto) < 2 and not archivos:
            raise ReglaNegocio("Escriba su mensaje o adjunte un documento")
        svc = TicketService(self.session)
        max_mb, permitidas = svc.reglas_adjuntos()
        max_mb = min(max_mb, settings.FORMULARIO_WEB_ADJUNTOS_MAX_MB)
        if len(archivos) > settings.FORMULARIO_WEB_ADJUNTOS_MAX:
            raise ReglaNegocio(f"Máximo {settings.FORMULARIO_WEB_ADJUNTOS_MAX} archivos por mensaje")
        for a in archivos:
            svc.validar_archivo(a.nombre, a.contenido, max_mb, permitidas)
        ahora = utcnow()
        autor = t.solicitante
        if texto:
            svc._agregar_comentario(t, autor, texto[:4000], False, "COMENTARIO", None, ahora)
        for a in archivos:
            svc.guardar_adjunto(t, autor, a.nombre, a.tipo_mime, a.contenido, ctx)
        if t.estado == Estado.PENDIENTE_CLIENTE:
            svc._aplicar_estado(t, Estado.PENDIENTE_CLIENTE, Estado.EN_PROCESO, None, ctx, ahora,
                                motivo="Automático: el solicitante respondió desde el enlace de seguimiento")
            svc._hist(t, None, "REANUDACION", None, None, None, "El solicitante respondió desde el enlace de seguimiento; SLA reanudado", ahora)
        aviso = texto[:200] or f"Adjuntó {len(archivos)} archivo(s)"
        svc.notif.notificar([t.responsable or svc._supervisor(t)], "COMENTARIO", f"{t.numero}: respuesta del solicitante",
                            f"{t.correo} (desde el enlace de seguimiento): {aviso}", t)
        t.fecha_actualizacion = ahora
        AuditoriaService(self.session).registrar(ctx, AccionAuditoria.SEGUIMIENTO_PUBLICO_RESPUESTA, "ticket", t.id,
                                                 {"numero": t.numero, "adjuntos": len(archivos)})

    # ============================================================= reenviar
    def reenviar(self, numero: str, correo: str) -> None:
        """Si el número y el correo coinciden, envía un enlace nuevo a ese correo. Nunca revela si coincidieron."""
        from app.application.services.notificacion_service import NotificacionService
        from app.infrastructure.repositories.repositorios import TicketRepository

        t = TicketRepository(self.session).por_numero(numero.strip().upper())
        if t is None or not self.activo or (t.correo or "").strip().lower() != correo.strip().lower() or self._vencido(t):
            return
        NotificacionService(self.session).correo_directo("SEGUIMIENTO_ENLACE", t.correo, t.solicitante_nombre, t, url_seguimiento=self.url(t))
