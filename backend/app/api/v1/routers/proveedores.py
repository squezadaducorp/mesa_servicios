"""Proveedores y contratos (mejora 33): escalar tickets a proveedores externos y medir el plazo de su contrato."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import ronda4b as s
from app.application.services.proveedor_service import ProveedorService

router = APIRouter(prefix="/proveedores", tags=["Proveedores y contratos"])


@router.get("", summary="Proveedores, cumplimiento y contratos por vencer")
def listar(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProveedorService(session).listar(ctx.usuario)


@router.get("/opciones", summary="Subcategorías que se pueden escalar")
def opciones(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProveedorService(session)
    svc._exigir_gestor(ctx.usuario)
    return svc.opciones()


@router.get("/ticket/{ticket_id}", summary="Proveedores para el diálogo «Escalar a proveedor»")
def para_ticket(ticket_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProveedorService(session).para_ticket(ticket_id, ctx.usuario)


@router.post("/ticket/{ticket_id}/escalar", status_code=201, summary="Escalar el ticket a un proveedor")
def escalar(ticket_id: int, dto: s.EscalarProveedor, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProveedorService(session)
    c = svc.escalar(ticket_id, dto, ctx)
    session.flush()
    return svc.caso_salida(c)


@router.post("/casos/{caso_id}/resolver", summary="El proveedor dio solución: el ticket vuelve a «En proceso»")
def resolver(caso_id: int, dto: s.ResolverCaso, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProveedorService(session)
    c = svc.resolver(caso_id, dto.solucion, ctx)
    session.flush()
    return svc.caso_salida(c)


@router.post("", status_code=201, summary="Registrar proveedor")
def crear(dto: s.ProveedorEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProveedorService(session)
    p = svc.guardar(dto, ctx)
    return svc.detalle(p.id, ctx.usuario)


@router.get("/{proveedor_id}", summary="Ficha del proveedor con sus casos del año")
def detalle(proveedor_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return ProveedorService(session).detalle(proveedor_id, ctx.usuario)


@router.put("/{proveedor_id}", summary="Editar proveedor y contrato")
def editar(proveedor_id: int, dto: s.ProveedorEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = ProveedorService(session)
    svc.guardar(dto, ctx, proveedor_id)
    return svc.detalle(proveedor_id, ctx.usuario)


@router.delete("/{proveedor_id}", response_model=es.Mensaje, summary="Eliminar proveedor")
def eliminar(proveedor_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    ProveedorService(session).eliminar(proveedor_id, ctx)
    return {"mensaje": "Proveedor eliminado"}
