"""Panel gerencial con PDF mensual por correo (mejora 32)."""
from datetime import timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import ronda4b as s
from app.application.services.panel_service import NOMBRE_SECCION, TZ, PanelService
from app.core.security import utcnow

router = APIRouter(prefix="/panel", tags=["Panel gerencial"])


def _mes(anio: int | None, mes: int | None) -> tuple[int, int]:
    hoy = utcnow().replace(tzinfo=timezone.utc).astimezone(TZ)
    return (anio or hoy.year, mes or hoy.month)


@router.get("", summary="Indicadores del mes, tendencia y cumplimiento por área")
def panel(anio: int | None = Query(None, ge=2020, le=2100), mes: int | None = Query(None, ge=1, le=12), area_id: int | None = None,
          ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = PanelService(session)
    svc._exigir(ctx.usuario)
    a, mm = _mes(anio, mes)
    d = svc.datos(a, mm, area_id)
    return {**d, "puede_configurar": svc.puede_configurar(ctx.usuario)}


@router.get("/pdf", summary="Descargar el PDF del mes (3 páginas)")
def pdf(anio: int | None = Query(None, ge=2020, le=2100), mes: int | None = Query(None, ge=1, le=12), area_id: int | None = None,
        ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = PanelService(session)
    svc._exigir(ctx.usuario)
    a, mm = _mes(anio, mes)
    cfg = svc.config()
    contenido = svc.pdf(svc.datos(a, mm, area_id), None, cfg["comentario"])
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{svc.archivo(a, mm)}"'})


@router.get("/envio", summary="Configuración del envío mensual y envíos anteriores")
def envio(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = PanelService(session)
    svc._exigir(ctx.usuario)
    return {"config": svc.config(), "secciones": NOMBRE_SECCION, "envios": svc.envios(), "proximo": svc.proximo_envio(),
            "puede_configurar": svc.puede_configurar(ctx.usuario)}


@router.put("/envio", summary="Guardar la configuración del envío mensual")
def guardar(dto: s.PanelEnvioEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = PanelService(session)
    return {"config": svc.guardar_config(dto, ctx), "proximo": svc.proximo_envio()}


@router.post("/envio/prueba", summary="Enviarme el PDF del mes elegido para revisarlo")
def prueba(anio: int | None = Query(None, ge=2020, le=2100), mes: int | None = Query(None, ge=1, le=12),
           ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = PanelService(session)
    a, mm = _mes(anio, mes)
    e = svc.enviar_prueba(a, mm, ctx)
    return {"mensaje": f"PDF enviado a {ctx.usuario.correo}", "id": e.id}


@router.get("/envios/{envio_id}/pdf", summary="Descargar el PDF de un envío anterior")
def pdf_envio(envio_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    nombre, contenido = PanelService(session).pdf_envio(envio_id, ctx.usuario)
    return Response(contenido, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
