"""Inventario de equipos e historial de fallas."""
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto, ReglaNegocio
from app.application.schemas import esquemas as es
from app.application.schemas import mejoras2 as s
from app.application.services.inventario_service import InventarioService
from app.domain.enums import Permiso

router = APIRouter(prefix="/inventario", tags=["Inventario de equipos"])
VER = requiere(Permiso.INVENTARIO_VER, Permiso.INVENTARIO_GESTIONAR)
GESTIONAR = requiere(Permiso.INVENTARIO_GESTIONAR)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_model=list[s.EquipoSalida], summary="Equipos con sus fallas de los últimos 12 meses")
def listar(texto: str | None = None, tipo: str | None = None, estado: Literal["EN_USO", "BODEGA", "REPARACION", "BAJA"] | None = None,
           ctx: Contexto = Depends(VER), session: Session = DbSession):
    return InventarioService(session).listar(texto, tipo, estado)


@router.get("/opciones", response_model=list[s.EquipoOpcion], summary="Equipos que se pueden elegir al crear un ticket")
def opciones(solicitante_id: int | None = None, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return InventarioService(session).opciones(ctx.usuario, solicitante_id)


@router.get("/plantilla", summary="Plantilla de Excel para importar equipos")
def plantilla(ctx: Contexto = Depends(GESTIONAR)):
    return Response(InventarioService.plantilla_excel(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-equipos.xlsx"'})


@router.post("/importar", response_model=s.ImportacionResultado, summary="Importar o actualizar equipos desde Excel")
async def importar(archivo: UploadFile = File(...), ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    contenido = await archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        raise ReglaNegocio("El archivo supera 5 MB")
    return InventarioService(session).importar(contenido, ctx)


@router.get("/{equipo_id}", response_model=s.EquipoDetalle, summary="Ficha del equipo con su historial de tickets")
def detalle(equipo_id: int, ctx: Contexto = Depends(VER), session: Session = DbSession):
    return InventarioService(session).detalle(equipo_id)


@router.post("", response_model=s.EquipoSalida, status_code=201, summary="Registrar equipo")
def crear(dto: s.EquipoEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = InventarioService(session)
    return svc.salida(svc.guardar(dto, ctx))


@router.put("/{equipo_id}", response_model=s.EquipoSalida, summary="Editar equipo")
def editar(equipo_id: int, dto: s.EquipoEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = InventarioService(session)
    return svc.salida(svc.guardar(dto, ctx, equipo_id))


@router.delete("/{equipo_id}", response_model=es.Mensaje, summary="Eliminar equipo")
def eliminar(equipo_id: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    InventarioService(session).eliminar(equipo_id, ctx)
    return {"mensaje": "Equipo eliminado"}
