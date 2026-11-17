"""Tickets vinculados, unir duplicados, acciones en lote y traspaso de cartera (mejoras 22 y 23)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.api.v1.routers.tickets import _detalle
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import tercera as s
from app.application.services.lote_service import LoteService
from app.application.services.ticket_service import TicketService
from app.application.services.vinculo_service import VinculoService
from app.domain.enums import Permiso

router = APIRouter(tags=["Tickets vinculados y en lote"])


@router.post("/tickets/lote", response_model=s.LoteResultado, summary="Aplicar una acción a varios tickets (máx. 100)")
def lote(dto: s.LoteEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return LoteService(session).aplicar(dto, ctx)


@router.post("/tickets/unir", response_model=es.TicketDetalle, summary="Unir tickets duplicados en uno principal")
def unir(dto: s.UnirEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    t = VinculoService(session).unir(dto.principal_id, dto.duplicados, dto.mensaje, dto.avisar, dto.mantener_prioridad, ctx)
    return _detalle(TicketService(session), t.id, ctx)


@router.get("/tickets/{ticket_id}/posibles-duplicados", summary="Tickets parecidos de las últimas 24 h (solo sugerencia)")
def posibles(ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return VinculoService(session).posibles_duplicados(ticket_id, ctx.usuario)


@router.post("/tickets/{ticket_id}/posibles-duplicados/{otro_id}/descartar", response_model=es.Mensaje, summary="«No es duplicado»")
def descartar(ticket_id: int, otro_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    VinculoService(session).descartar(ticket_id, otro_id, ctx)
    return {"mensaje": "Listo"}


@router.post("/tickets/{ticket_id}/vinculos", summary="Vincular con otro ticket (relacionado o bloqueado por)")
def vincular(ticket_id: int, dto: s.VinculoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return VinculoService(session).vincular(ticket_id, dto.relacionado, dto.tipo, ctx)


@router.delete("/tickets/{ticket_id}/vinculos/{vinculo_id}", summary="Quitar un vínculo")
def desvincular(ticket_id: int, vinculo_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return VinculoService(session).desvincular(ticket_id, vinculo_id, ctx)


# ------------------------------------------------------------ traspaso
ADMIN_USUARIOS = requiere(Permiso.USUARIO_ADMINISTRAR)


@router.post("/admin/usuarios/{usuario_id}/traspaso/vista-previa", summary="A quién iría cada ticket (no cambia nada)")
def vista_previa(usuario_id: int, dto: s.TraspasoEntrada, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    return LoteService(session).plan(usuario_id, dto)


@router.post("/admin/usuarios/{usuario_id}/traspaso", summary="Traspasar los tickets abiertos, recurrentes y aprobaciones de una persona")
def traspasar(usuario_id: int, dto: s.TraspasoEntrada, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    return LoteService(session).traspasar(usuario_id, dto, ctx)
