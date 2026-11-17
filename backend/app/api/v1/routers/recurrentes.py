"""Tickets recurrentes (mantenimientos y tareas programadas)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import mejoras2 as s
from app.application.services.recurrentes_service import RecurrentesService
from app.domain.enums import Permiso

router = APIRouter(prefix="/recurrentes", tags=["Tickets recurrentes"])
GESTIONAR = requiere(Permiso.RECURRENTES_GESTIONAR)


@router.get("", response_model=list[s.RecurrenteSalida], summary="Programaciones de tickets")
def listar(ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = RecurrentesService(session)
    return [svc.salida(r) for r in svc.listar()]


@router.post("/vista-previa", response_model=s.VistaPreviaFechas, summary="Próximas 6 fechas en que se crearía el ticket")
def vista_previa(dto: s.RecurrenteEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    return RecurrentesService(session).vista_previa(dto)


@router.post("", response_model=s.RecurrenteSalida, status_code=201, summary="Programar un ticket")
def crear(dto: s.RecurrenteEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = RecurrentesService(session)
    return svc.salida(svc.guardar(dto, ctx))


@router.put("/{rid}", response_model=s.RecurrenteSalida, summary="Editar, pausar o reactivar una programación")
def editar(rid: int, dto: s.RecurrenteEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = RecurrentesService(session)
    return svc.salida(svc.guardar(dto, ctx, rid))


@router.delete("/{rid}", response_model=es.Mensaje, summary="Desactivar una programación")
def eliminar(rid: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    RecurrentesService(session).eliminar(rid, ctx)
    return {"mensaje": "Programación desactivada"}


@router.post("/{rid}/ejecutar", response_model=es.TicketCorto, status_code=201, summary="Crear ahora el ticket de esta programación")
def ejecutar(rid: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    t = RecurrentesService(session).ejecutar_ahora(rid, ctx)
    return {"id": t.id, "numero": t.numero, "asunto": t.asunto}
