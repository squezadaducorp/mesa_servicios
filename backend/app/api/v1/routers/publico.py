"""Endpoints sin autenticación del formulario público de solicitudes (/solicitud)."""
import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session


from app.api.deps import DbSession, contexto_anonimo, equipo_cliente, ip_cliente
from app.application.errores import Contexto, NoEncontrado, ReglaNegocio
from app.application.services.encuesta_service import EncuestaService, ticket_de_token
from app.infrastructure.db import models as m
from app.application.schemas import esquemas as s
from app.application.services.formulario_service import ArchivoPublico, FormularioService
from app.core.config import settings

router = APIRouter(prefix="/publico", tags=["Formulario público"])


@router.get("/formulario", response_model=s.FormularioPublicoSalida,
            summary="Categorías, reglas de adjuntos y ficha anti-spam para el formulario público (sin cuenta)")
def formulario(session: Session = DbSession):
    return FormularioService(session).formulario()


@router.post("/tickets", response_model=s.SolicitudPublicaSalida, status_code=201,
             summary="Registrar una solicitud sin cuenta (clientes y personas externas), con adjuntos opcionales")
async def registrar(request: Request,
                    datos: str = Form(..., description="JSON con los campos de SolicitudPublica"),
                    archivos: list[UploadFile] = File(default=[], description="Adjuntos opcionales (ver GET /publico/formulario)"),
                    session: Session = DbSession):
    try:
        dto = s.SolicitudPublica.model_validate(json.loads(datos))
    except (ValueError, ValidationError):
        raise ReglaNegocio("Revise los datos del formulario: hay campos incompletos o no válidos.")
    archivos = [a for a in archivos if a.filename]
    # Lectura acotada: nunca se carga en memoria más de lo permitido por archivo (Nginx limita además el cuerpo).
    limite = min(settings.FORMULARIO_WEB_ADJUNTOS_MAX_MB, settings.ADJUNTOS_MAX_MB) * 1024 * 1024 + 1
    leidos = []
    for a in archivos[: max(0, settings.FORMULARIO_WEB_ADJUNTOS_MAX) + 1]:
        leidos.append(ArchivoPublico(a.filename or "archivo", a.content_type or "", await a.read(limite)))
    t = FormularioService(session).registrar(dto, ip_cliente(request), equipo_cliente(request), leidos)
    n = len(leidos)
    extra = f" Recibimos {n} archivo{'s' if n != 1 else ''} adjunto{'s' if n != 1 else ''}." if n else ""
    return {"numero": t.numero, "adjuntos": n,
            "mensaje": f"Registramos su solicitud con el número {t.numero}. Le escribiremos a {t.correo} con las novedades.{extra}"}


# ------------------------------------------------------------ encuesta
def _ticket_encuesta(session: Session, token: str) -> m.Ticket:
    t = session.get(m.Ticket, ticket_de_token(token))
    if t is None or t.eliminado:
        raise NoEncontrado("Ticket no encontrado")
    return t


def _estado_encuesta(session: Session, t: m.Ticket) -> dict:
    e = EncuestaService(session).de_ticket(t.id)
    return {"numero": t.numero, "asunto": t.asunto, "responsable": t.responsable.nombre if t.responsable else None,
            "calificacion": e.calificacion if e else None, "comentario": e.comentario if e else None,
            "puede_comentar": bool(e and not e.comentario)}


@router.get("/encuesta", response_model=s.EncuestaPublicaSalida, summary="Datos del ticket del enlace de la encuesta (sin cuenta)")
def encuesta(t: str, session: Session = DbSession):
    return _estado_encuesta(session, _ticket_encuesta(session, t))


@router.post("/encuesta", response_model=s.EncuestaPublicaSalida,
             summary="Registrar la nota desde el enlace del correo; luego, en otra llamada, el comentario opcional")
def responder_encuesta(dto: s.EncuestaPublicaEntrada, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    from app.application.services.ticket_service import TicketService

    t = _ticket_encuesta(session, dto.token)
    svc = EncuestaService(session)
    existente = svc.de_ticket(t.id)
    if dto.calificacion is not None and (existente is None or existente.calificacion != dto.calificacion):
        svc.registrar(TicketService(session), t, dto.calificacion, dto.comentario, None, "CORREO", ctx)
    elif dto.comentario:
        svc.agregar_comentario(t, dto.comentario)
    session.flush()
    return _estado_encuesta(session, t)


# ------------------------------------------------------------ seguimiento sin cuenta (mejora 20)
from app.application.schemas.tercera import ReenviarSeguimiento  # noqa: E402
from app.application.services.formulario_service import DemasiadasSolicitudes  # noqa: E402
from app.application.services.seguimiento_service import SeguimientoService  # noqa: E402
from app.core.limite import Limitador  # noqa: E402

limitador_seguimiento = Limitador(5, 3600)
limitador_respuestas = Limitador(20, 3600)


@router.get("/seguimiento/{ticket_id}", summary="Estado de una solicitud desde el enlace del correo (sin cuenta)")
def seguimiento(ticket_id: int, t: str, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    svc = SeguimientoService(session)
    datos = svc.vista(svc.verificar(ticket_id, t), ctx)
    session.flush()
    return datos


@router.post("/seguimiento/{ticket_id}/responder", summary="Responder o adjuntar un documento desde el enlace de seguimiento")
async def responder_seguimiento(ticket_id: int, request: Request, t: str = Form(...), texto: str = Form(default=""),
                                archivos: list[UploadFile] = File(default=[]),
                                ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    if not limitador_respuestas.permitir(f"{ip_cliente(request)}:{ticket_id}"):
        raise DemasiadasSolicitudes("Recibimos varios mensajes en poco tiempo. Inténtelo de nuevo en una hora.")
    svc = SeguimientoService(session)
    ticket = svc.verificar(ticket_id, t)
    limite = min(settings.FORMULARIO_WEB_ADJUNTOS_MAX_MB, settings.ADJUNTOS_MAX_MB) * 1024 * 1024 + 1
    leidos = []
    for a in [a for a in archivos if a.filename][: max(0, settings.FORMULARIO_WEB_ADJUNTOS_MAX) + 1]:
        leidos.append(ArchivoPublico(a.filename or "archivo", a.content_type or "", await a.read(limite)))
    svc.responder(ticket, texto, leidos, ctx)
    session.flush()
    return svc.vista(ticket, ctx)


@router.post("/seguimiento/reenviar", summary="Pedir un enlace nuevo con el número de ticket y el correo (respuesta siempre igual)")
def reenviar_seguimiento(dto: ReenviarSeguimiento, request: Request, session: Session = DbSession):
    if limitador_seguimiento.permitir(ip_cliente(request)):
        SeguimientoService(session).reenviar(dto.numero, dto.correo)
        session.flush()
    return {"mensaje": "Si el número y el correo coinciden con una solicitud, le enviamos un enlace nuevo en unos minutos."}


@router.get("/avisos", summary="Avisos generales marcados como públicos (para el formulario /solicitud)")
def avisos_publicos(session: Session = DbSession):
    from app.application.services.aviso_service import AvisoService

    svc = AvisoService(session)
    return [svc.salida_publica(a) for a in svc.activos(None, publico=True)]
