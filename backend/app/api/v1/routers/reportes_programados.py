"""Reporte por correo a gerencia (semanal, diario o mensual)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import mejoras2 as s
from app.application.services.reportes_programados_service import ReportesProgramadosService
from app.domain.enums import Permiso

router = APIRouter(prefix="/reportes-programados", tags=["Reportes por correo"])
PROGRAMAR = requiere(Permiso.REPORTES_PROGRAMAR)


@router.get("", response_model=list[s.ReporteSalida], summary="Reportes programados")
def listar(ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    svc = ReportesProgramadosService(session)
    return [svc.salida(r) for r in svc.listar()]


@router.post("", response_model=s.ReporteSalida, status_code=201, summary="Programar un reporte")
def crear(dto: s.ReporteEntrada, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    svc = ReportesProgramadosService(session)
    return svc.salida(svc.guardar(dto, ctx))


@router.put("/{rid}", response_model=s.ReporteSalida, summary="Editar un reporte programado")
def editar(rid: int, dto: s.ReporteEntrada, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    svc = ReportesProgramadosService(session)
    return svc.salida(svc.guardar(dto, ctx, rid))


@router.delete("/{rid}", response_model=es.Mensaje, summary="Eliminar un reporte programado")
def eliminar(rid: int, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    ReportesProgramadosService(session).eliminar(rid, ctx)
    return {"mensaje": "Reporte eliminado"}


@router.get("/{rid}/envios", response_model=list[s.ReporteEnvioSalida], summary="Últimos envíos")
def envios(rid: int, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    return ReportesProgramadosService(session).envios(rid)


@router.get("/{rid}/vista-previa", summary="HTML del correo con los datos del último periodo")
def vista_previa(rid: int, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession) -> dict:
    return {"html": ReportesProgramadosService(session).vista_previa(rid, ctx)}


@router.post("/{rid}/prueba", response_model=es.Mensaje, summary="Enviarme una prueba ahora")
def prueba(rid: int, ctx: Contexto = Depends(PROGRAMAR), session: Session = DbSession):
    ReportesProgramadosService(session).enviar_prueba(rid, ctx)
    return {"mensaje": f"Prueba enviada a {ctx.usuario.correo}"}
