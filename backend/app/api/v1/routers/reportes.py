from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requiere
from app.application.errores import Contexto, ReglaNegocio
from app.application.services import export_service as ex
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.report_service import FiltroReporte, ReportService
from app.domain.enums import AccionAuditoria, Permiso

router = APIRouter(prefix="/reportes", tags=["Reportes y Dashboard"])
lector = requiere(Permiso.REPORTE_VER, Permiso.DASHBOARD_VER)


def filtro(
    desde: date | None = Query(None, description="Por defecto, hace 90 días"),
    hasta: date | None = Query(None, description="Por defecto, hoy"),
    categoria_id: int | None = None,
    responsable_id: int | None = None,
    cliente_id: int | None = None,
    estado: str | None = None,
    sla: Literal["CUMPLIDO", "INCUMPLIDO", "EN_CURSO"] | None = None,
) -> FiltroReporte:
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=89)
    if desde > hasta:
        raise ReglaNegocio("La fecha inicial no puede ser posterior a la final")
    if (hasta - desde).days > 3660:
        raise ReglaNegocio("El rango máximo es de 10 años")
    return FiltroReporte(desde, hasta, categoria_id, responsable_id, cliente_id, estado, sla)


@router.get("/dashboard", summary="Dashboard ejecutivo: widgets, tendencia, top y tickets en riesgo")
def dashboard(f: FiltroReporte = Depends(filtro), ctx: Contexto = Depends(lector), session: Session = DbSession):
    return ReportService(session, ctx.usuario).dashboard(f)


@router.get("/categorias", summary="Indicadores por categoría")
def categorias(f: FiltroReporte = Depends(filtro), ctx: Contexto = Depends(lector), session: Session = DbSession):
    return ReportService(session, ctx.usuario).por_categoria(f)


@router.get("/responsables", summary="Indicadores por responsable y ranking de analistas")
def responsables(f: FiltroReporte = Depends(filtro), ctx: Contexto = Depends(lector), session: Session = DbSession):
    return ReportService(session, ctx.usuario).por_responsable(f)


@router.get("/clientes", summary="Indicadores por cliente")
def clientes(f: FiltroReporte = Depends(filtro), ctx: Contexto = Depends(lector), session: Session = DbSession):
    return ReportService(session, ctx.usuario).por_cliente(f)


@router.get("/tendencia", summary="Tickets por día, semana, mes o año")
def tendencia(
    agrupacion: Literal["DIA", "SEMANA", "MES", "ANIO"] = "MES",
    f: FiltroReporte = Depends(filtro), ctx: Contexto = Depends(lector), session: Session = DbSession,
):
    return ReportService(session, ctx.usuario).tendencia(f, agrupacion)


COL_CAT = [("categoria", "Categoría"), ("tickets_recibidos", "Recibidos"), ("tickets_resueltos", "Resueltos"), ("tickets_pendientes", "Pendientes"),
           ("tickets_vencidos", "Vencidos"), ("cumplimiento_sla_pct", "Cumplimiento SLA %"), ("tiempo_promedio_respuesta_h", "T. prom. respuesta (h)"),
           ("tiempo_promedio_resolucion_h", "T. prom. resolución (h)"), ("backlog", "Backlog")]
COL_RESP = [("ranking", "Ranking"), ("responsable", "Responsable"), ("tickets_asignados", "Asignados"), ("tickets_cerrados", "Cerrados"),
            ("sla_cumplido", "SLA cumplido"), ("sla_incumplido", "SLA incumplido"), ("cumplimiento_sla_pct", "Cumplimiento %"),
            ("productividad_dia", "Productividad (cerrados/día)"), ("puntaje", "Puntaje")]
COL_CLI = [("cliente", "Cliente"), ("tickets", "Tickets"), ("cumplimiento_sla_pct", "Cumplimiento SLA %"), ("categorias_txt", "Categorías más usadas")]
COL_TEN = [("periodo", "Período"), ("tickets", "Tickets"), ("cerrados", "Cerrados"), ("sla_cumplido", "SLA cumplido"),
           ("sla_incumplido", "SLA incumplido"), ("cumplimiento_sla_pct", "Cumplimiento %")]
ETIQUETAS = {"tickets_totales": "Totales", "tickets_abiertos": "Abiertos", "tickets_cerrados": "Cerrados", "tickets_escalados": "Escalados",
             "tickets_vencidos": "Vencidos", "cumplimiento_sla_pct": "Cumplimiento SLA %", "tiempo_promedio_respuesta_h": "T. prom. respuesta (h)",
             "tiempo_promedio_resolucion_h": "T. prom. resolución (h)"}


@router.get("/exportar", summary="Exportar indicadores gerenciales a Excel, PDF o CSV")
def exportar(
    formato: Literal["xlsx", "pdf", "csv"] = "xlsx",
    f: FiltroReporte = Depends(filtro),
    ctx: Contexto = Depends(requiere(Permiso.DATOS_EXPORTAR)),
    session: Session = DbSession,
):
    svc = ReportService(session, ctx.usuario)
    filas = svc.filas(f)
    resumen = {ETIQUETAS[k]: v for k, v in svc.resumen(filas).items() if k in ETIQUETAS}
    cat, resp = svc.por_categoria(f), svc.por_responsable(f)
    cli = [{**c, "categorias_txt": ", ".join(x["nombre"] for x in c["categorias"])} for c in svc.por_cliente(f)]
    ten = svc.tendencia(f, "MES")
    subtitulo = f"Período {f.desde:%d/%m/%Y} – {f.hasta:%d/%m/%Y}"
    AuditoriaService(session).registrar(ctx, AccionAuditoria.EXPORTACION, "indicadores", None, {"formato": formato, "desde": f.desde, "hasta": f.hasta})
    nombre = f"indicadores_aducorp_{f.desde:%Y%m%d}_{f.hasta:%Y%m%d}.{formato}"
    if formato == "xlsx":
        resumen_filas = [{"indicador": k, "valor": v} for k, v in resumen.items()]
        contenido = ex.excel([("Resumen", [("indicador", "Indicador"), ("valor", "Valor")], resumen_filas), ("Por categoría", COL_CAT, cat),
                              ("Por responsable", COL_RESP, resp), ("Por cliente", COL_CLI, cli), ("Tendencia mensual", COL_TEN, ten)], subtitulo)
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif formato == "csv":
        contenido, tipo = ex.csv_bytes(COL_CAT, cat), "text/csv; charset=utf-8"
    else:
        contenido = ex.pdf("Indicadores de la Mesa de Servicios", subtitulo,
                           [("Por categoría", COL_CAT, cat), ("Ranking de responsables", COL_RESP, resp), ("Por cliente", COL_CLI, cli),
                            ("Tendencia mensual", COL_TEN, ten)], resumen, ex.nombre_empresa(session))
        tipo = "application/pdf"
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
