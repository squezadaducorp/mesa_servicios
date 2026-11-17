"""Aprobaciones del jefe: bandeja «Por aprobar» y reglas por categoría (mejora 21)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import tercera as s
from app.application.services.aprobacion_service import AprobacionService
from app.domain.enums import Permiso
from app.infrastructure.db import models as m

router = APIRouter(prefix="/aprobaciones", tags=["Aprobaciones"])
GESTIONAR = requiere(Permiso.APROBACIONES_GESTIONAR)


@router.get("", summary="Mi bandeja «Por aprobar»: pendientes y resumen de los últimos 30 días")
def bandeja(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return AprobacionService(session).bandeja(ctx.usuario)


@router.get("/conteo", summary="Cuántas aprobaciones esperan mi respuesta (menú y campana)")
def conteo(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AprobacionService(session)
    u = ctx.usuario
    es_jefe = session.scalar(select(m.Usuario.id).where(m.Usuario.supervisor_id == u.id, m.Usuario.activo == True).limit(1)) is not None
    alguna = session.scalar(select(m.TicketAprobacion.id).where(m.TicketAprobacion.aprobador_id == u.id).limit(1)) is not None
    return {"pendientes": svc.contar_pendientes(u), "es_aprobador": es_jefe or alguna}


@router.get("/{aprobacion_id}", summary="Una aprobación (para el enlace del correo)")
def una(aprobacion_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AprobacionService(session)
    return svc.salida(svc.pendiente_de(aprobacion_id, ctx.usuario))


@router.post("/{aprobacion_id}/responder", summary="Aprobar o rechazar (rechazar exige comentario)")
def responder(aprobacion_id: int, dto: s.RespuestaAprobacion, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AprobacionService(session)
    fila = svc.responder(aprobacion_id, dto.aprobar, dto.comentario, ctx)
    session.flush()
    return svc.salida(fila)


# ----------------------------------------------------------------- reglas
@router.get("/admin/reglas", summary="Reglas de aprobación")
def reglas(ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AprobacionService(session)
    return {"reglas": [svc.regla_salida(r) for r in svc.reglas()], "jefes": svc.jefes_directos()}


@router.post("/admin/reglas", status_code=201, summary="Crear regla")
def crear_regla(dto: s.ReglaAprobacionEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AprobacionService(session)
    return svc.regla_salida(svc.guardar(dto, ctx))


@router.put("/admin/reglas/{regla_id}", summary="Editar, activar o desactivar una regla")
def editar_regla(regla_id: int, dto: s.ReglaAprobacionEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AprobacionService(session)
    return svc.regla_salida(svc.guardar(dto, ctx, regla_id))


@router.delete("/admin/reglas/{regla_id}", response_model=es.Mensaje, summary="Desactivar una regla (no se borra)")
def desactivar_regla(regla_id: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    AprobacionService(session).desactivar(regla_id, ctx)
    return {"mensaje": "Regla desactivada"}
