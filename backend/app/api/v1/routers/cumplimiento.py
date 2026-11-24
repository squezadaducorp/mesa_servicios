"""Seguridad y cumplimiento ISO 27001: política de acceso (37), revisión de accesos (38), servidor (40), vulnerabilidades (41)
y clasificación y retención (42)."""
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.services.estado_seguridad_service import EstadoSeguridadService
from app.application.services.retencion_service import RetencionService
from app.application.services.revision_acceso_service import RevisionAccesoService
from app.domain.enums import Permiso

router = APIRouter(tags=["Seguridad y cumplimiento"])
ADMIN = requiere(Permiso.USUARIO_ADMINISTRAR)
SISTEMA = requiere(Permiso.SISTEMA_ADMINISTRAR)


class DecisionEntrada(BaseModel):
    decision: Literal["MANTENER", "AJUSTAR", "BAJA"]
    comentario: str | None = Field(None, max_length=500)


class AprobarEntrada(BaseModel):
    observacion: str | None = Field(None, max_length=1000)


class ClasificacionEntrada(BaseModel):
    clasificacion: Literal["PUBLICA", "INTERNA", "CONFIDENCIAL"]
    motivo: str | None = Field(None, max_length=300)


class RetencionLegalEntrada(BaseModel):
    activa: bool
    motivo: str = Field(max_length=300)


class DepurarEntrada(BaseModel):
    confirmacion: str = Field(max_length=20)


class ClavesEntrada(BaseModel):
    claves_previas: int | None = Field(None, ge=0, le=24)
    max_intentos: int | None = Field(None, ge=3, le=20)
    bloqueo_min: int | None = Field(None, ge=5, le=1440)
    inactividad_min: int | None = Field(None, ge=0, le=480)
    aviso_bloqueo: bool = True


# ---------------------------------------------------------------- 37 política de acceso
@router.get("/cumplimiento/acceso", summary="Política de acceso y cumplimiento de la verificación en dos pasos")
def acceso(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    return EstadoSeguridadService(session).acceso()


@router.put("/cumplimiento/acceso/claves", summary="Guardar la política de contraseñas y bloqueo")
def guardar_claves(dto: ClavesEntrada, ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    return EstadoSeguridadService(session).guardar_claves(dto.model_dump(), ctx)


@router.post("/cumplimiento/acceso/recordar", summary="Recordar por correo a quien no ha activado la verificación obligatoria")
def recordar(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    return EstadoSeguridadService(session).recordar(ctx)


# ---------------------------------------------------------------- 40 servidor y 41 vulnerabilidades
@router.get("/cumplimiento/servidor", summary="Último informe de endurecimiento del servidor")
def servidor(ctx: Contexto = Depends(SISTEMA), session: Session = DbSession):
    return EstadoSeguridadService(session).servidor()


@router.get("/cumplimiento/vulnerabilidades", summary="Último escaneo de vulnerabilidades y alertas de Dependabot (GitHub)")
def vulnerabilidades(refrescar: bool = False, ctx: Contexto = Depends(SISTEMA), session: Session = DbSession):
    return EstadoSeguridadService(session).vulnerabilidades(refrescar)


# ---------------------------------------------------------------- 38 revisión de accesos
@router.get("/accesos/pendientes", summary="Accesos que me toca revisar en la campaña abierta")
def pendientes(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return RevisionAccesoService(session).pendientes(ctx.usuario)


@router.get("/accesos/revisiones", summary="Campañas de revisión de accesos")
def revisiones(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = RevisionAccesoService(session)
    return {"revisiones": svc.listar(), "config": svc.config()}


@router.post("/accesos/revisiones", status_code=201, summary="Abrir ahora la revisión de accesos")
def abrir(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = RevisionAccesoService(session)
    r = svc.abrir(ctx)
    return svc.detalle(r.id, ctx.usuario)


@router.get("/accesos/revisiones/{revision_id}", summary="Personas de la revisión (el jefe ve solo a su gente)")
def detalle(revision_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return RevisionAccesoService(session).detalle(revision_id, ctx.usuario)


@router.put("/accesos/items/{item_id}", summary="Mantener, ajustar o dar de baja un acceso")
def decidir(item_id: int, dto: DecisionEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return RevisionAccesoService(session).decidir(item_id, dto.decision, dto.comentario, ctx)


@router.post("/accesos/revisiones/{revision_id}/aprobar", summary="Aprobar el acta: aplica las bajas y envía el PDF")
def aprobar(revision_id: int, dto: AprobarEntrada, ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    return RevisionAccesoService(session).aprobar(revision_id, dto.observacion, ctx)


@router.get("/accesos/revisiones/{revision_id}/acta", summary="Acta de la revisión en PDF")
def acta(revision_id: int, ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = RevisionAccesoService(session)
    contenido = svc.acta_pdf(revision_id)
    periodo = svc.detalle(revision_id, ctx.usuario)["periodo"]
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="revision-accesos-{periodo}.pdf"'})


@router.get("/accesos/inactividad", summary="Cuentas cerca de la baja automática por inactividad")
def inactividad(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = RevisionAccesoService(session)
    return {"cuentas": svc.inactivos(), "config": svc.config()}


# ---------------------------------------------------------------- 42 clasificación y retención
@router.put("/tickets/{ticket_id}/clasificacion", summary="Cambiar la clasificación del ticket (bajarla pide motivo)")
def clasificar(ticket_id: int, dto: ClasificacionEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    t = RetencionService(session).clasificar(ticket_id, dto.clasificacion, dto.motivo, ctx)
    return {"id": t.id, "clasificacion": t.clasificacion, "retencion_legal": t.retencion_legal}


@router.put("/tickets/{ticket_id}/retencion-legal", summary="Poner o quitar la retención legal (no se depura)")
def retencion_legal(ticket_id: int, dto: RetencionLegalEntrada, ctx: Contexto = Depends(SISTEMA), session: Session = DbSession):
    t = RetencionService(session).retencion_legal(ticket_id, dto.activa, dto.motivo, ctx)
    return {"id": t.id, "clasificacion": t.clasificacion, "retencion_legal": t.retencion_legal}


@router.get("/retencion", summary="Clasificación de los tickets y tickets listos para depurar")
def retencion(ctx: Contexto = Depends(SISTEMA), session: Session = DbSession):
    return RetencionService(session).resumen()


@router.post("/retencion/depurar", summary="Aprobar la depuración (un lote de hasta 200 tickets)")
def depurar(dto: DepurarEntrada, ctx: Contexto = Depends(SISTEMA), session: Session = DbSession):
    return RetencionService(session).depurar(dto.confirmacion, ctx)
