"""Encuesta de satisfacción (1 a 5 estrellas + comentario) al resolver un ticket.

- En el portal: el solicitante califica desde el detalle del ticket resuelto.
- Por correo: cada estrella es un enlace firmado (sin iniciar sesión) a /encuesta?t=…&nota=N.
Calificar un ticket resuelto lo cierra. Las notas bajas avisan al supervisor de la categoría.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, coordinadores

TIPO_TOKEN = "encuesta"
DIAS_VALIDEZ = 30
NOMBRES = {1: "Muy mala", 2: "Mala", 3: "Regular", 4: "Buena", 5: "Excelente"}


def token_encuesta(ticket_id: int) -> str:
    ahora = datetime.now(timezone.utc)
    return jwt.encode({"typ": TIPO_TOKEN, "tid": ticket_id, "iat": ahora, "exp": ahora + timedelta(days=DIAS_VALIDEZ)},
                      settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def ticket_de_token(token: str) -> int:
    try:
        datos = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ReglaNegocio("El enlace de la encuesta venció. Puede calificar desde el portal de la Mesa de Servicios.")
    except jwt.PyJWTError:
        raise ReglaNegocio("Enlace de encuesta no válido")
    if datos.get("typ") != TIPO_TOKEN or not isinstance(datos.get("tid"), int):
        raise ReglaNegocio("Enlace de encuesta no válido")
    return datos["tid"]


class EncuestaService:
    def __init__(self, session: Session):
        self.session = session
        self.config = CatalogoRepository(session).configuracion()

    @property
    def activa(self) -> bool:
        return self.config.get("encuesta.activa", "si").strip().lower() not in ("no", "0", "false")

    @property
    def nota_aviso(self) -> int:
        try:
            return int(self.config.get("encuesta.aviso_nota_max", "2"))
        except ValueError:
            return 2

    def de_ticket(self, ticket_id: int) -> m.TicketEncuesta | None:
        return self.session.scalars(select(m.TicketEncuesta).where(m.TicketEncuesta.ticket_id == ticket_id)).first()

    def puede_calificar(self, u: m.Usuario | None, t: m.Ticket) -> bool:
        return (self.activa and t.estado in (Estado.RESUELTO, Estado.CERRADO) and (u is None or t.solicitante_id == u.id)
                and self.de_ticket(t.id) is None)

    # --------------------------------------------------------------- invitar
    def enlaces(self, t: m.Ticket) -> dict[str, str]:
        base = f"{settings.APP_URL.rstrip('/')}/encuesta?t={token_encuesta(t.id)}"
        return {f"url_nota_{n}": f"{base}&nota={n}" for n in range(1, 6)}

    def invitar(self, svc, t: m.Ticket) -> bool:
        """Correo al solicitante con las 5 estrellas (svc = TicketService, para respetar remitentes externos y formulario)."""
        if not self.activa or self.de_ticket(t.id) is not None:
            return False
        return svc.correo_solicitante("ENCUESTA", t, **self.enlaces(t))

    # ------------------------------------------------------------- registrar
    def registrar(self, svc, t: m.Ticket, calificacion: int, comentario: str | None, u: m.Usuario | None, origen: str,
                  ctx: Contexto) -> m.TicketEncuesta:
        if not self.activa:
            raise ReglaNegocio("La encuesta de satisfacción está desactivada")
        if not 1 <= calificacion <= 5:
            raise ReglaNegocio("La calificación debe estar entre 1 y 5")
        if u is not None and t.solicitante_id != u.id:
            raise Prohibido("Solo el solicitante puede calificar la atención")
        if t.estado not in (Estado.RESUELTO, Estado.CERRADO):
            raise ReglaNegocio("Solo se califican los tickets resueltos o cerrados")
        if self.de_ticket(t.id) is not None:
            raise Conflicto("Este ticket ya fue calificado. Gracias por su respuesta.")
        ahora = utcnow()
        comentario = (comentario or "").strip()[:1000] or None
        e = m.TicketEncuesta(ticket_id=t.id, calificacion=calificacion, comentario=comentario, usuario_id=u.id if u else None,
                             responsable_id=t.responsable_id, categoria_id=t.categoria_id, origen=origen, fecha=ahora,
                             fecha_comentario=ahora if comentario else None)
        self.session.add(e)
        detalle = f"Calificación del solicitante: {calificacion}/5 ({NOMBRES[calificacion]})" + (f". «{comentario}»" if comentario else "")
        svc._hist(t, u, "ENCUESTA", "calificacion", None, calificacion, detalle[:1000], ahora)
        if t.estado == Estado.RESUELTO:
            svc._aplicar_estado(t, Estado.RESUELTO, Estado.CERRADO, u, ctx, ahora,   # calificar confirma la solución
                                motivo=f"El solicitante calificó la atención ({calificacion}/5) y confirmó la solución")
        if t.responsable:
            svc.notif.notificar([t.responsable], "ENCUESTA", f"{t.numero}: calificación {calificacion}/5",
                                f"El solicitante calificó la atención de «{t.asunto}».", t, "INFO")
        if calificacion <= self.nota_aviso:
            self._aviso_nota_baja(svc, t, calificacion, comentario)
        self.session.flush()
        return e

    def agregar_comentario(self, t: m.Ticket, comentario: str) -> m.TicketEncuesta:
        """Comentario posterior a la nota enviada desde el correo (una sola vez)."""
        e = self.de_ticket(t.id)
        if e is None:
            raise NoEncontrado("Primero elija una calificación")
        if e.comentario:
            raise Conflicto("Ya registró un comentario para este ticket")
        texto = (comentario or "").strip()[:1000]
        if not texto:
            raise ReglaNegocio("Escriba un comentario")
        if utcnow() - e.fecha > timedelta(days=DIAS_VALIDEZ):
            raise ReglaNegocio("El plazo para comentar venció")
        e.comentario, e.fecha_comentario = texto, utcnow()
        self.session.add(m.TicketHistorial(ticket_id=t.id, accion="ENCUESTA", campo="comentario", valor_nuevo=texto[:500],
                                           detalle="Comentario del solicitante en la encuesta", fecha=utcnow()))
        if e.calificacion <= self.nota_aviso:
            from app.application.services.notificacion_service import NotificacionService
            from app.application.services.ticket_service import TicketService

            NotificacionService(self.session).notificar(
                [TicketService(self.session)._supervisor(t), *coordinadores(self.session)], "ENCUESTA_BAJA",
                f"{t.numero}: comentario de la calificación {e.calificacion}/5", f"«{texto[:300]}»", t, "AVISO")
        self.session.flush()
        return e

    def _aviso_nota_baja(self, svc, t: m.Ticket, nota: int, comentario: str | None) -> None:
        supervisor = svc._supervisor(t)
        texto = f"«{t.asunto}» ({t.responsable.nombre if t.responsable else 'sin responsable'}) recibió {nota}/5."
        if comentario:
            texto += f" Comentario: «{comentario[:300]}»"
        svc.notif.notificar([supervisor, *coordinadores(self.session)], "ENCUESTA_BAJA", f"{t.numero}: calificación baja ({nota}/5)",
                            texto, t, "AVISO")
        svc.notif.correo("ENCUESTA_BAJA", [supervisor], t, calificacion=str(nota), comentario=comentario or "(sin comentario)")


def a_salida(e: m.TicketEncuesta | None) -> dict | None:
    if e is None:
        return None
    return {"calificacion": e.calificacion, "comentario": e.comentario, "origen": e.origen, "fecha": e.fecha}
