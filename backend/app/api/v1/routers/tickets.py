from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as s
from app.application.services import export_service as ex
from app.domain.archivos import mime_descarga
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.ia_service import IaService
from app.application.services.ticket_service import TicketService, a_detalle, a_listado
from app.core.config import settings
from app.domain.enums import AccionAuditoria, Permiso

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def filtro_tickets(
    texto: str | None = None,
    estado: Annotated[list[str] | None, Query()] = None,
    categoria_id: int | None = None,
    subcategoria_id: int | None = None,
    prioridad_id: int | None = None,
    responsable_id: int | None = None,
    cliente_id: int | None = None,
    sla: Literal["CUMPLIDO", "INCUMPLIDO", "EN_CURSO", "EN_RIESGO"] | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    solo_mios: bool = False,
    orden: Literal["fecha_desc", "fecha_asc", "sla_desc", "prioridad"] = "fecha_desc",
) -> s.FiltroTickets:
    return s.FiltroTickets(**locals())


def _detalle(svc: TicketService, ticket_id: int, ctx: Contexto) -> dict:
    svc.session.flush()
    t = svc.obtener(ticket_id, ctx.usuario)
    svc.session.refresh(t)
    return a_detalle(svc, t, ctx.usuario)


@router.get("", response_model=s.Pagina[s.TicketListado], summary="Listar tickets visibles para el usuario")
def listar(
    f: s.FiltroTickets = Depends(filtro_tickets),
    pagina: int = Query(1, ge=1),
    tamano: int = Query(20, ge=1, le=200),
    ctx: Contexto = Depends(contexto),
    session: Session = DbSession,
):
    items, total = TicketService(session).listar(ctx.usuario, f, pagina, tamano)
    return {"items": [a_listado(t) for t in items], "total": total, "pagina": pagina, "tamano": tamano}


@router.get("/exportar", summary="Exportar tickets filtrados a Excel, PDF o CSV")
def exportar(
    formato: Literal["xlsx", "pdf", "csv"] = "xlsx",
    f: s.FiltroTickets = Depends(filtro_tickets),
    ctx: Contexto = Depends(requiere(Permiso.DATOS_EXPORTAR)),
    session: Session = DbSession,
):
    svc = TicketService(session)
    tickets = list(session.scalars(svc.consulta(ctx.usuario, f).limit(50000)).unique())
    filas = [ex.fila_ticket(t) for t in tickets]
    subtitulo = f"{len(filas)} tickets · filtros: " + ", ".join(f"{k}={v}" for k, v in f.model_dump(exclude_none=True, exclude={"orden", "solo_mios"}).items() if v) or "ninguno"
    AuditoriaService(session).registrar(ctx, AccionAuditoria.EXPORTACION, "tickets", None, {"formato": formato, "filas": len(filas), **f.model_dump(mode="json", exclude_none=True)})
    nombre = f"tickets_aducorp_{date.today():%Y%m%d}.{formato}"
    if formato == "xlsx":
        contenido, tipo = ex.excel([("Tickets", ex.COLUMNAS_TICKETS, filas)], subtitulo), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif formato == "csv":
        contenido, tipo = ex.csv_bytes(ex.COLUMNAS_TICKETS, filas), "text/csv; charset=utf-8"
    else:
        cols = [c for c in ex.COLUMNAS_TICKETS if c[0] in ex.COLUMNAS_PDF]
        contenido, tipo = ex.pdf("Reporte de tickets", subtitulo, [("Detalle", cols, filas)], empresa=ex.nombre_empresa(session)), "application/pdf"
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("", response_model=s.TicketDetalle, status_code=201, summary="Crear ticket")
def crear(dto: s.TicketCrear, ctx: Contexto = Depends(requiere(Permiso.TICKET_CREAR)), session: Session = DbSession):
    svc = TicketService(session)
    t = svc.crear(dto, ctx)
    return _detalle(svc, t.id, ctx)


@router.get("/{ticket_id}", response_model=s.TicketDetalle, summary="Detalle del ticket con comentarios, adjuntos e historial")
def detalle(ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return _detalle(TicketService(session), ticket_id, ctx)


@router.patch("/{ticket_id}", response_model=s.TicketDetalle, summary="Editar ticket")
def editar(ticket_id: int, dto: s.TicketEditar, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.editar(ticket_id, dto, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/asignar", response_model=s.TicketDetalle, summary="Asignar o reasignar responsable")
def asignar(ticket_id: int, dto: s.AsignarEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.asignar(ticket_id, dto, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/estado", response_model=s.TicketDetalle, summary="Cambiar estado")
def cambiar_estado(ticket_id: int, dto: s.EstadoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.cambiar_estado(ticket_id, dto.estado, dto.comentario, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/escalar", response_model=s.TicketDetalle, summary="Escalar ticket")
def escalar(ticket_id: int, dto: s.EscalarEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.escalar(ticket_id, dto, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/cerrar", response_model=s.TicketDetalle, summary="Cerrar ticket (resuelve si aún no lo está)")
def cerrar(ticket_id: int, dto: s.CerrarEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.cerrar(ticket_id, dto.comentario, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/reabrir", response_model=s.TicketDetalle, summary="Reabrir ticket resuelto o cerrado")
def reabrir(ticket_id: int, dto: s.MotivoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.reabrir(ticket_id, dto.motivo, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/comentarios", response_model=s.TicketDetalle, status_code=201, summary="Agregar comentario, nota interna o actividad")
def comentar(ticket_id: int, dto: s.ComentarioEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.comentar(ticket_id, dto, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.post("/{ticket_id}/adjuntos", response_model=s.TicketDetalle, status_code=201, summary="Adjuntar archivo")
async def adjuntar(ticket_id: int, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), session: Session = DbSession):
    contenido = await archivo.read(settings.ADJUNTOS_MAX_MB * 1024 * 1024 + 1)
    svc = TicketService(session)
    svc.adjuntar(ticket_id, archivo.filename or "archivo", archivo.content_type or "", contenido, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.get("/{ticket_id}/adjuntos/{adjunto_id}", summary="Descargar adjunto")
def descargar(ticket_id: int, adjunto_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    a, ruta = TicketService(session).adjunto(ticket_id, adjunto_id, ctx)
    return FileResponse(ruta, media_type=mime_descarga(a.tipo_mime), filename=a.nombre_original, content_disposition_type="attachment")


@router.post("/{ticket_id}/excepcion-sla", response_model=s.TicketDetalle, summary="Registrar excepción de SLA (extensión o exclusión)")
def excepcion_sla(ticket_id: int, dto: s.ExcepcionSlaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = TicketService(session)
    svc.excepcion_sla(ticket_id, dto, ctx)
    return _detalle(svc, ticket_id, ctx)


@router.delete("/{ticket_id}", response_model=s.Mensaje, summary="Eliminar ticket (borrado lógico)")
def eliminar(ticket_id: int, ctx: Contexto = Depends(requiere(Permiso.REGISTRO_ELIMINAR)), session: Session = DbSession):
    TicketService(session).eliminar(ticket_id, ctx)
    return {"mensaje": "Ticket eliminado"}


# ----------------------------------------------------------------------- IA
@router.post("/{ticket_id}/ia/respuesta", response_model=s.TextoSalida, summary="Respuesta sugerida por IA")
def ia_respuesta(ticket_id: int, ctx: Contexto = Depends(requiere(Permiso.IA_USAR)), session: Session = DbSession):
    t = TicketService(session).obtener(ticket_id, ctx.usuario)
    texto, proveedor = IaService(session).respuesta_sugerida(t, ctx.usuario.id)
    return {"texto": texto, "proveedor": proveedor}


@router.post("/{ticket_id}/ia/resumen", response_model=s.TextoSalida, summary="Resumen automático del ticket")
def ia_resumen(ticket_id: int, ctx: Contexto = Depends(requiere(Permiso.IA_USAR)), session: Session = DbSession):
    t = TicketService(session).obtener(ticket_id, ctx.usuario)
    texto, proveedor = IaService(session).resumen(t, ctx.usuario.id)
    return {"texto": texto, "proveedor": proveedor}


@router.get("/{ticket_id}/ia/riesgo", response_model=s.RiesgoSalida, summary="Riesgo de incumplimiento de SLA")
def ia_riesgo(ticket_id: int, ctx: Contexto = Depends(requiere(Permiso.IA_USAR)), session: Session = DbSession):
    t = TicketService(session).obtener(ticket_id, ctx.usuario)
    r, nivel, motivos = IaService(session).riesgo(t)
    return {"ticket_id": t.id, "numero": t.numero, "riesgo": r, "nivel": nivel, "motivos": motivos}
