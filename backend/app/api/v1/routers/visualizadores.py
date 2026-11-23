"""Visualizadores del ticket (mejora 34): personas de Aducorp que lo siguen desde la Mesa."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.api.v1.routers.tickets import _detalle
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import ronda4b as s
from app.application.services.ticket_service import TicketService
from app.application.services.visualizador_service import VisualizadorService

router = APIRouter(prefix="/tickets", tags=["Visualizadores"])


@router.get("/{ticket_id}/visualizadores/candidatos", summary="Personas que se pueden agregar como visualizadores")
def candidatos(ticket_id: int, q: str | None = Query(None, max_length=80), ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return VisualizadorService(session).candidatos(ticket_id, q, ctx.usuario)


@router.post("/{ticket_id}/visualizadores", response_model=es.TicketDetalle, summary="Agregar un visualizador")
def agregar(ticket_id: int, dto: s.VisualizadorEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    VisualizadorService(session).agregar(ticket_id, dto.usuario_id, dto.avisos_correo, ctx)
    return _detalle(TicketService(session), ticket_id, ctx)


@router.post("/{ticket_id}/seguir", response_model=es.TicketDetalle, summary="Seguir el ticket")
def seguir(ticket_id: int, dto: s.VisualizadorAvisos | None = None, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    VisualizadorService(session).seguir(ticket_id, dto.avisos_correo if dto else "ESTADO", ctx)
    return _detalle(TicketService(session), ticket_id, ctx)


@router.put("/{ticket_id}/visualizadores/{usuario_id}", response_model=es.TicketDetalle, summary="Cambiar los avisos por correo")
def avisos(ticket_id: int, usuario_id: int, dto: s.VisualizadorAvisos, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    VisualizadorService(session).cambiar_avisos(ticket_id, usuario_id, dto.avisos_correo, ctx)
    return _detalle(TicketService(session), ticket_id, ctx)


@router.delete("/{ticket_id}/visualizadores/{usuario_id}", summary="Quitar un visualizador o dejar de seguir")
def quitar(ticket_id: int, usuario_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    VisualizadorService(session).quitar(ticket_id, usuario_id, ctx)
    session.flush()
    svc = TicketService(session)
    if not svc.repo.puede_ver(ctx.usuario, ticket_id):   # dejó de seguir un ticket que solo veía como visualizador
        return {"visible": False}
    return {"visible": True, "ticket": _detalle(svc, ticket_id, ctx)}
