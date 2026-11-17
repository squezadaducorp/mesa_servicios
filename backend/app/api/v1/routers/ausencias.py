"""Modo ausente / vacaciones con reemplazo."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto, NoEncontrado, Prohibido
from app.application.schemas import esquemas as s
from app.application.services.ausencia_service import AusenciaService, a_salida
from app.infrastructure.db import models as m

router = APIRouter(prefix="/ausencias", tags=["Ausencias y reemplazos"])


def _objetivo(svc: AusenciaService, ctx: Contexto, usuario_id: int | None) -> m.Usuario:
    u = svc.usuarios.get(usuario_id or ctx.usuario.id)
    if u is None:
        raise NoEncontrado("Usuario no encontrado")
    if not svc._puede_gestionar(ctx.usuario, u):
        raise Prohibido("No puede consultar las ausencias de otro usuario")
    return u


@router.get("/mias", response_model=list[s.AusenciaSalida], summary="Mis ausencias vigentes y a quién estoy cubriendo (con los tickets que se me pasaron)")
def mias(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AusenciaService(session)
    return [a_salida(a, svc.tickets_pasados(a.id) if a.reemplazo_id == ctx.usuario.id else None)
            for a in svc.de_usuario(ctx.usuario.id)]


@router.get("", response_model=list[s.AusenciaSalida], summary="Ausencias programadas y en curso del equipo")
def vigentes(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AusenciaService(session)
    if not svc.administra(ctx.usuario):
        return [a_salida(a) for a in svc.vigentes() if a.usuario.supervisor_id == ctx.usuario.id]
    return [a_salida(a) for a in svc.vigentes()]


@router.get("/reemplazos", response_model=list[s.ReemplazoSugerido], summary="Posibles reemplazos (mismas categorías, menos carga)")
def reemplazos(usuario_id: int | None = None, desde: datetime | None = None, hasta: datetime | None = None,
               ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AusenciaService(session)
    u = _objetivo(svc, ctx, usuario_id)
    return svc.sugerir_reemplazos(u.id, desde, hasta)


@router.get("/tickets", response_model=list[s.TicketCorto], summary="Tickets abiertos que pasarían al reemplazo")
def tickets(usuario_id: int | None = None, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AusenciaService(session)
    u = _objetivo(svc, ctx, usuario_id)
    return [{"id": t.id, "numero": t.numero, "asunto": t.asunto} for t in svc.tickets_abiertos(u.id)]


@router.post("", response_model=s.AusenciaSalida, status_code=201, summary="Registrar o programar una ausencia")
def crear(dto: s.AusenciaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return a_salida(AusenciaService(session).crear(dto, ctx))


@router.post("/{ausencia_id}/cancelar", response_model=s.AusenciaSalida,
             summary="Cancelar una ausencia programada o terminar ahora una en curso («Volví antes»)")
def cancelar(ausencia_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return a_salida(AusenciaService(session).cancelar(ausencia_id, ctx))
