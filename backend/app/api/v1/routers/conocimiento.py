"""Base de conocimiento: artículos de autoayuda que se sugieren antes de crear un ticket."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import mejoras2 as s
from app.application.services.conocimiento_service import ConocimientoService, resumen

router = APIRouter(prefix="/conocimiento", tags=["Base de conocimiento"])


@router.get("", response_model=list[s.KbResumen], summary="Buscar artículos (la mesa ve también borradores y artículos internos)")
def listar(texto: str | None = None, categoria_id: int | None = None, estado: Literal["BORRADOR", "PUBLICADO", "ARCHIVADO"] | None = None,
           ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return [resumen(a) for a in ConocimientoService(session).listar(ctx.usuario, texto, categoria_id, estado)]


@router.get("/categorias", summary="Categorías con su número de artículos")
def categorias(ctx: Contexto = Depends(contexto), session: Session = DbSession) -> list[dict]:
    return ConocimientoService(session).categorias_con_conteo(ctx.usuario)


@router.post("/sugerir", response_model=list[s.KbResumen], summary="Artículos que podrían resolver lo que se está escribiendo en un ticket nuevo")
def sugerir(dto: s.KbSugerirEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ConocimientoService(session).sugerir(ctx.usuario, dto)


@router.post("/desde-ticket", summary="Borrador de artículo a partir de un ticket resuelto (no se guarda)")
def desde_ticket(dto: s.KbDesdeTicket, ctx: Contexto = Depends(contexto), session: Session = DbSession) -> dict:
    return ConocimientoService(session).borrador_desde_ticket(dto.ticket_id, ctx)


@router.get("/{articulo_id}", response_model=s.KbSalida, summary="Leer un artículo (suma una vista)")
def ver(articulo_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ConocimientoService(session)
    return svc.salida(svc.ver(articulo_id, ctx.usuario), ctx.usuario)


@router.post("", response_model=s.KbSalida, status_code=201, summary="Crear artículo")
def crear(dto: s.KbEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ConocimientoService(session)
    return svc.salida(svc.guardar(dto, ctx), ctx.usuario)


@router.put("/{articulo_id}", response_model=s.KbSalida, summary="Editar artículo")
def editar(articulo_id: int, dto: s.KbEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ConocimientoService(session)
    return svc.salida(svc.guardar(dto, ctx, articulo_id), ctx.usuario)


@router.delete("/{articulo_id}", response_model=es.Mensaje, summary="Eliminar artículo")
def eliminar(articulo_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    ConocimientoService(session).eliminar(articulo_id, ctx)
    return {"mensaje": "Artículo eliminado"}


@router.post("/{articulo_id}/voto", response_model=es.Mensaje, summary="«¿Le sirvió?» Sí / No")
def votar(articulo_id: int, dto: s.KbVotoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    ConocimientoService(session).votar(articulo_id, dto.util, ctx.usuario)
    return {"mensaje": "Gracias por su opinión"}


@router.post("/{articulo_id}/evitar-ticket", response_model=es.Mensaje, summary="«Se resolvió, no crear ticket»")
def evitar(articulo_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    ConocimientoService(session).evitar_ticket(articulo_id, ctx.usuario)
    return {"mensaje": "¡Qué bien! No se creó ningún ticket"}
