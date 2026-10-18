from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as s
from app.application.services import export_service as ex
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.ticket_service import limites_dia_utc
from app.domain.enums import AccionAuditoria, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import AuditoriaRepository

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])


def _consulta(desde, hasta, usuario_id, accion, entidad, entidad_id, texto):
    A = m.Auditoria
    stmt = select(A)
    d, h = limites_dia_utc(desde, hasta)
    if d:
        stmt = stmt.where(A.fecha_hora >= d)
    if h:
        stmt = stmt.where(A.fecha_hora < h)
    if usuario_id:
        stmt = stmt.where(A.usuario_id == usuario_id)
    if accion:
        stmt = stmt.where(A.accion == accion)
    if entidad:
        stmt = stmt.where(A.entidad == entidad)
    if entidad_id:
        stmt = stmt.where(A.entidad_id == entidad_id)
    if texto:
        stmt = stmt.where(A.usuario_correo.ilike(f"%{texto}%") | A.ip.ilike(f"%{texto}%"))
    return stmt.order_by(A.fecha_hora.desc(), A.id.desc())


@router.get("", response_model=s.Pagina[s.AuditoriaSalida], summary="Consultar la auditoría")
def listar(
    desde: date | None = None, hasta: date | None = None, usuario_id: int | None = None, accion: str | None = None,
    entidad: str | None = None, entidad_id: str | None = None, texto: str | None = None,
    pagina: int = Query(1, ge=1), tamano: int = Query(50, ge=1, le=500),
    ctx: Contexto = Depends(requiere(Permiso.AUDITORIA_VER)), session: Session = DbSession,
):
    items, total = AuditoriaRepository(session).paginar(_consulta(desde, hasta, usuario_id, accion, entidad, entidad_id, texto), pagina, tamano)
    return {"items": items, "total": total, "pagina": pagina, "tamano": tamano}


@router.get("/acciones", summary="Acciones auditadas")
def acciones(ctx: Contexto = Depends(requiere(Permiso.AUDITORIA_VER))):
    return [a.value for a in AccionAuditoria]


COLUMNAS = [("fecha", "Fecha y hora"), ("usuario_correo", "Usuario"), ("accion", "Acción"), ("entidad", "Entidad"), ("entidad_id", "Id"),
            ("ip", "IP"), ("equipo", "Equipo"), ("resultado", "Resultado"), ("detalle", "Detalle")]


@router.get("/exportar", summary="Exportar auditoría")
def exportar(
    formato: Literal["xlsx", "csv"] = "xlsx", desde: date | None = None, hasta: date | None = None, usuario_id: int | None = None,
    accion: str | None = None, ctx: Contexto = Depends(requiere(Permiso.AUDITORIA_VER)), session: Session = DbSession,
):
    registros = session.scalars(_consulta(desde, hasta, usuario_id, accion, None, None, None).limit(100000))
    filas = [{**{c: getattr(a, c) for c, _ in COLUMNAS if c != "fecha"}, "fecha": ex._local(a.fecha_hora)} for a in registros]
    AuditoriaService(session).registrar(ctx, AccionAuditoria.EXPORTACION, "auditoria", None, {"formato": formato, "filas": len(filas)})
    if formato == "csv":
        contenido, tipo = ex.csv_bytes(COLUMNAS, filas), "text/csv; charset=utf-8"
    else:
        contenido, tipo = ex.excel([("Auditoría", COLUMNAS, filas)]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="auditoria_aducorp.{formato}"'})
