"""Respuestas rápidas del equipo de la mesa."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import mejoras2 as s
from app.application.services.respuestas_service import RespuestasService
from app.application.services.ticket_service import TicketService

router = APIRouter(prefix="/respuestas", tags=["Respuestas rápidas"])


@router.get("", response_model=list[s.RespuestaSalida], summary="Respuestas disponibles (todas=true: administrar las compartidas)")
def listar(todas: bool = False, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = RespuestasService(session)
    return [svc.salida(r, ctx.usuario) for r in svc.listar(ctx.usuario, todas)]


@router.get("/ticket/{ticket_id}", response_model=list[s.RespuestaParaTicket],
            summary="Respuestas para un ticket, con sus datos ya reemplazados; primero las de su subcategoría")
def para_ticket(ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    t = TicketService(session).obtener(ticket_id, ctx.usuario)
    return RespuestasService(session).para_ticket(t, ctx.usuario)


@router.post("", response_model=s.RespuestaSalida, status_code=201, summary="Crear respuesta rápida")
def crear(dto: s.RespuestaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = RespuestasService(session)
    return svc.salida(svc.guardar(dto, ctx), ctx.usuario)


@router.put("/{respuesta_id}", response_model=s.RespuestaSalida, summary="Editar o desactivar una respuesta rápida")
def editar(respuesta_id: int, dto: s.RespuestaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = RespuestasService(session)
    return svc.salida(svc.guardar(dto, ctx, respuesta_id), ctx.usuario)
