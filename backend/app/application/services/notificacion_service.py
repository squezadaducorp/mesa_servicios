"""Notificaciones dentro del sistema y correos encolados con plantillas."""
from __future__ import annotations

import html
import logging
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base
from app.infrastructure.repositories.repositorios import CatalogoRepository

log = logging.getLogger(__name__)

TZ_LABEL = "hora Ecuador"


def fecha_local(d) -> str:
    if d is None:
        return "—"
    from datetime import timezone
    from zoneinfo import ZoneInfo

    return d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")


class NotificacionService:
    def __init__(self, session: Session):
        self.session = session
        self.catalogo = CatalogoRepository(session)

    def notificar(
        self, usuarios: Iterable[m.Usuario | None], tipo: str, titulo: str, mensaje: str,
        ticket: m.Ticket | None = None, severidad: str = "INFO",
    ) -> None:
        vistos: set[int] = set()
        for u in usuarios:
            if u is None or u.id in vistos or not u.activo:
                continue
            vistos.add(u.id)
            self.session.add(
                m.Notificacion(usuario_id=u.id, ticket_id=ticket.id if ticket else None, tipo=tipo, severidad=severidad,
                               titulo=titulo[:200], mensaje=mensaje[:1000], fecha=utcnow())
            )

    def contexto_ticket(self, t: m.Ticket, **extra) -> dict[str, str]:
        ctx = {
            "numero": t.numero,
            "asunto": t.asunto,
            "categoria": t.categoria.nombre if t.categoria else "",
            "subcategoria": t.subcategoria.nombre if t.subcategoria else "",
            "prioridad": t.prioridad.nombre if t.prioridad else "",
            "responsable": t.responsable.nombre if t.responsable else "Sin asignar",
            "solicitante": t.solicitante_nombre,
            "sla_pct": f"{float(t.sla_consumido_pct or 0):.0f}",
            "sla_respuesta_vence": f"{fecha_local(t.sla_respuesta_vence)} ({TZ_LABEL})",
            "sla_resolucion_vence": f"{fecha_local(t.sla_resolucion_vence)} ({TZ_LABEL})",
            "url": f"{settings.APP_URL}/tickets/{t.id}",
        }
        ctx.update({k: str(v) for k, v in extra.items()})
        return ctx

    def correo(self, codigo: str, destinatarios: Iterable[m.Usuario | None], ticket: m.Ticket, **extra) -> None:
        plantilla = self.catalogo.plantilla(codigo)
        if plantilla is None:
            log.warning("Plantilla de correo %s no encontrada", codigo)
            return
        enviados: set[str] = set()
        for u in destinatarios:
            if u is None or not u.activo or u.correo in enviados:
                continue
            enviados.add(u.correo)
            ctx = self.contexto_ticket(ticket, destinatario=u.nombre, **extra)
            asunto, cuerpo = plantilla.asunto, plantilla.cuerpo_html
            for k, v in ctx.items():
                seguro = v if k == "url" else html.escape(v)
                asunto = asunto.replace("{" + k + "}", v)
                cuerpo = cuerpo.replace("{" + k + "}", seguro)
            self.session.add(
                m.ColaCorreo(para=u.correo, asunto=asunto[:250], cuerpo_html=plantilla_base(cuerpo), ticket_id=ticket.id,
                             plantilla=codigo, estado="PENDIENTE", proximo_intento=utcnow(), fecha_creacion=utcnow())
            )
