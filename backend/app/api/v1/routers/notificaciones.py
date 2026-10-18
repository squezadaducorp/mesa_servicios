from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto, NoEncontrado
from app.application.schemas import esquemas as s
from app.core.security import utcnow
from app.infrastructure.repositories.repositorios import NotificacionRepository

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


@router.get("", response_model=list[s.NotificacionSalida], summary="Centro de notificaciones del usuario")
def listar(solo_no_leidas: bool = False, limite: int = 50, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return NotificacionRepository(session).del_usuario(ctx.usuario.id, solo_no_leidas, min(limite, 200))


@router.get("/conteo", summary="Cantidad de notificaciones sin leer")
def conteo(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return {"no_leidas": NotificacionRepository(session).no_leidas(ctx.usuario.id)}


@router.post("/{notificacion_id}/leida", response_model=s.Mensaje)
def marcar(notificacion_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    n = NotificacionRepository(session).get(notificacion_id)
    if n is None or n.usuario_id != ctx.usuario.id:
        raise NoEncontrado("Notificación no encontrada")
    n.leida, n.fecha_lectura = True, utcnow()
    return {"mensaje": "ok"}


@router.post("/leidas", response_model=s.Mensaje, summary="Marcar todas como leídas")
def marcar_todas(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    NotificacionRepository(session).marcar_todas(ctx.usuario.id, utcnow())
    return {"mensaje": "ok"}
