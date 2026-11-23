"""Catálogo de servicios con formularios (mejora 26)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import cuarta as s
from app.application.services.catalogo_servicio_service import CatalogoServicioService
from app.domain.enums import Permiso

router = APIRouter(prefix="/servicios", tags=["Catálogo de servicios"])
GESTIONAR = requiere(Permiso.SERVICIOS_GESTIONAR)


@router.get("", summary="Servicios activos (tarjetas del catálogo) y mis solicitudes en curso")
def catalogo(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CatalogoServicioService(session)
    servicios = svc.listar()
    return {"servicios": [svc.salida(x) for x in servicios], "grupos": sorted({x.grupo for x in servicios}),
            "mis_solicitudes": svc.mis_solicitudes(ctx.usuario)}


@router.get("/opciones", summary="Áreas y personas para los campos del formulario")
def opciones(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return CatalogoServicioService(session).opciones_formulario()


@router.get("/admin", summary="Todos los servicios, incluidos los inactivos")
def admin_listar(ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = CatalogoServicioService(session)
    return [svc.salida(x, completo=True) for x in svc.listar(incluir_inactivos=True)]


@router.post("/admin", status_code=201, summary="Crear servicio")
def crear(dto: s.ServicioEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = CatalogoServicioService(session)
    return svc.salida(svc.guardar(dto, ctx), completo=True)


@router.put("/admin/{servicio_id}", summary="Editar, activar o desactivar un servicio")
def editar(servicio_id: int, dto: s.ServicioEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = CatalogoServicioService(session)
    return svc.salida(svc.guardar(dto, ctx, servicio_id), completo=True)


@router.get("/{servicio_id}", summary="Formulario de un servicio")
def uno(servicio_id: int, todos: bool = Query(False), ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CatalogoServicioService(session)
    activo = not (todos and ctx.usuario.tiene(Permiso.SERVICIOS_GESTIONAR))
    return svc.salida(svc.obtener(servicio_id, solo_activo=activo), completo=True)


@router.post("/{servicio_id}/solicitar", status_code=201, summary="Enviar el formulario: crea el ticket con sus tareas")
def solicitar(servicio_id: int, dto: s.SolicitudServicio, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    t = CatalogoServicioService(session).solicitar(servicio_id, dto, ctx)
    return {"id": t.id, "numero": t.numero, "estado": t.estado}


@router.post("/tickets/{ticket_id}/tareas/{tarea_id}", summary="Marcar una tarea como lista (o reabrirla)")
def marcar(ticket_id: int, tarea_id: int, dto: s.TareaMarcar, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    x = CatalogoServicioService(session).marcar(ticket_id, tarea_id, dto.lista, ctx)
    return {"id": x.id, "estado": x.estado}
