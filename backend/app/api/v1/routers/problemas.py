"""Gestión de problemas: causa de fondo de incidentes repetidos, error conocido y patrón detectado (mejora 30)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import ronda4b as s
from app.application.services.problema_service import ProblemaService

router = APIRouter(prefix="/problemas", tags=["Gestión de problemas"])


@router.get("", summary="Problemas con indicadores y patrones detectados")
def listar(estado: str | None = Query(None), q: str | None = Query(None, max_length=100), ctx: Contexto = Depends(contexto),
           session: Session = DbSession):
    svc = ProblemaService(session)
    problemas = svc.listar(ctx.usuario, estado, q)
    return {"problemas": [svc.salida_lista(p) for p in problemas], "resumen": svc.resumen(),
            "patrones": svc.patrones() if svc.gestor(ctx.usuario) else [], "gestor": svc.gestor(ctx.usuario)}


@router.get("/opciones", summary="Responsables, cambios y estados")
def opciones(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    svc._exigir_ver(ctx.usuario)
    return svc.opciones()


@router.post("/patrones/ignorar", response_model=es.Mensaje, summary="Ignorar un patrón detectado durante 14 días")
def ignorar(dto: s.IgnorarPatron, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    ProblemaService(session).ignorar_patron(dto.firma, ctx)
    return {"mensaje": "Patrón ignorado"}


@router.get("/ticket/{ticket_id}", summary="Problemas del ticket y errores conocidos parecidos")
def del_ticket(ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProblemaService(session).del_ticket(ticket_id, ctx.usuario)


@router.post("", status_code=201, summary="Registrar un problema (opcionalmente con los tickets de un patrón)")
def crear(dto: s.ProblemaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.crear(dto, ctx), ctx.usuario)


@router.get("/{problema_id}", summary="Detalle: 5 porqués, incidentes agrupados e impacto")
def uno(problema_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.obtener(problema_id, ctx.usuario), ctx.usuario)


@router.put("/{problema_id}", summary="Guardar el análisis")
def editar(problema_id: int, dto: s.ProblemaEdicion, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.editar(problema_id, dto, ctx), ctx.usuario)


@router.post("/{problema_id}/estado", summary="Avanzar o cerrar (al cerrar se avisa a los solicitantes)")
def estado(problema_id: int, dto: s.ProblemaEstado, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.cambiar_estado(problema_id, dto.estado, dto.nota, dto.avisar, ctx), ctx.usuario)


@router.post("/{problema_id}/publicar", summary="Publicar la solución temporal en la base de conocimiento")
def publicar(problema_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.publicar(problema_id, ctx), ctx.usuario)


@router.post("/{problema_id}/tickets", summary="Agrupar un incidente")
def vincular(problema_id: int, dto: s.ProblemaVincular, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.vincular(problema_id, dto.ticket, ctx), ctx.usuario)


@router.delete("/{problema_id}/tickets/{ticket_id}", summary="Quitar un incidente del problema")
def desvincular(problema_id: int, ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProblemaService(session)
    return svc.salida(svc.desvincular(problema_id, ticket_id, ctx), ctx.usuario)


@router.post("/{problema_id}/aplicar/{ticket_id}", summary="Vincular el ticket y responder con la solución temporal")
def aplicar(problema_id: int, ticket_id: int, dto: s.AplicarSolucion, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProblemaService(session).aplicar(problema_id, ticket_id, dto.responder, ctx)


@router.post("/{problema_id}/descartar/{ticket_id}", summary="«No es esto»: no volver a sugerirlo en este ticket")
def descartar(problema_id: int, ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProblemaService(session).descartar(problema_id, ticket_id, ctx)
