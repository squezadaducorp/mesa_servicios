"""Control de tiempo (mejora 31): cronómetro por ticket, problema o cambio, registros a mano y reporte semanal de horas."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import ronda4b as s
from app.application.services.tiempo_service import TiempoService

router = APIRouter(prefix="/tiempo", tags=["Control de tiempo"])
Tipo = Literal["ticket", "problema", "cambio"]


@router.get("/activo", summary="Cronómetro de la barra superior (el que corre o el último en pausa)")
def activo(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return {"activo": TiempoService(session).activo(ctx.usuario)}


@router.get("/reporte", summary="Reporte de horas de la semana")
def reporte(desde: date | None = None, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return TiempoService(session).reporte(ctx.usuario, desde)


@router.get("/reporte/excel", summary="Reporte de horas de la semana en Excel")
def reporte_excel(desde: date | None = None, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    nombre, contenido = TiempoService(session).excel(ctx.usuario, desde)
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/{tipo}/{objeto_id}", summary="Tiempo trabajado en un ticket, problema o cambio")
def del_objeto(tipo: Tipo, objeto_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return TiempoService(session).del_objeto(tipo, objeto_id, ctx.usuario)


@router.post("/{tipo}/{objeto_id}/iniciar", summary="Iniciar el cronómetro (pausa cualquier otro que esté corriendo)")
def iniciar(tipo: Tipo, objeto_id: int, dto: s.TiempoIniciar, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TiempoService(session)
    svc.iniciar(tipo, objeto_id, dto.actividad, ctx)
    return svc.del_objeto(tipo, objeto_id, ctx.usuario)


@router.post("/{tipo}/{objeto_id}/manual", summary="Agregar tiempo a mano")
def manual(tipo: Tipo, objeto_id: int, dto: s.TiempoManual, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TiempoService(session)
    svc.manual(tipo, objeto_id, dto.actividad, dto.minutos, dto.fecha, ctx)
    return svc.del_objeto(tipo, objeto_id, ctx.usuario)


@router.put("/ticket/{ticket_id}/ajustes", summary="Tiempo estimado y si es facturable al cliente")
def ajustes(ticket_id: int, dto: s.TiempoAjustes, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TiempoService(session)
    svc.ajustes(ticket_id, dto.estimado_min, dto.facturable, ctx)
    return svc.del_objeto("ticket", ticket_id, ctx.usuario)


def _accion(registro_id: int, accion: str, ctx: Contexto, session: Session) -> dict:
    svc = TiempoService(session)
    r = getattr(svc, accion)(registro_id, ctx)
    session.flush()
    return {"registro": svc.salida(r, ctx.usuario), "activo": svc.activo(ctx.usuario)}


@router.post("/registros/{registro_id}/pausar", summary="Pausar el cronómetro")
def pausar(registro_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return _accion(registro_id, "pausar", ctx, session)


@router.post("/registros/{registro_id}/reanudar", summary="Reanudar el cronómetro")
def reanudar(registro_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return _accion(registro_id, "reanudar", ctx, session)


@router.post("/registros/{registro_id}/detener", summary="Detener y guardar")
def detener(registro_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return _accion(registro_id, "detener", ctx, session)


@router.put("/registros/{registro_id}", summary="Corregir actividad o minutos")
def editar(registro_id: int, dto: s.TiempoEditar, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TiempoService(session)
    r = svc.editar(registro_id, dto.actividad, dto.minutos, ctx)
    return {"registro": svc.salida(r, ctx.usuario)}


@router.delete("/registros/{registro_id}", response_model=es.Mensaje, summary="Borrar un registro")
def borrar(registro_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    TiempoService(session).borrar(registro_id, ctx)
    return {"mensaje": "Registro borrado"}
