"""Avisos generales de caídas que afectan a muchos (mejora 24)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.schemas import tercera as s
from app.application.services.aviso_service import AvisoService, duracion
from app.domain.enums import Permiso

router = APIRouter(prefix="/avisos", tags=["Avisos generales"])
GESTIONAR = requiere(Permiso.AVISOS_GESTIONAR)


@router.get("/activos", summary="Avisos vigentes que debo ver (banner superior)")
def activos(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AvisoService(session)
    return [svc.salida(a, ctx.usuario) for a in svc.activos(ctx.usuario)]


@router.get("/coincidencias", summary="Avisos que parecen ser lo que estoy por reportar")
def coincidencias(texto: str = Query(min_length=3, max_length=500), ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return AvisoService(session).coincidencias(texto, ctx.usuario)


@router.post("/{aviso_id}/afecta", summary="«A mí también me afecta» (sin crear ticket)")
def me_afecta(aviso_id: int, dto: s.AfectaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AvisoService(session)
    return svc.salida(svc.me_afecta(aviso_id, dto.comentario, ctx), ctx.usuario)


@router.delete("/{aviso_id}/afecta", response_model=es.Mensaje, summary="Ya no me afecta")
def ya_no(aviso_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    AvisoService(session).ya_no_afecta(aviso_id, ctx)
    return {"mensaje": "Listo"}


# ------------------------------------------------------------------ gestión
@router.get("", summary="Avisos (activos e historial del año)")
def listar(anio: int | None = None, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AvisoService(session)
    anio = anio or date.today().year
    historial = svc.historial(anio)
    resumen: dict[str, dict] = {}
    for a in historial:
        if a.fin is None:
            continue
        r = resumen.setdefault(a.sistema, {"sistema": a.sistema, "caidas": 0, "minutos": 0})
        r["caidas"] += 1
        r["minutos"] += int((a.fin - a.inicio).total_seconds() // 60)
    return {
        "activos": [svc.salida(a, ctx.usuario, detalle=True) for a in svc.activos(ctx.usuario)],
        "historial": [svc.salida(a) for a in historial if a.estado == "RESUELTO"],
        "resumen": sorted(resumen.values(), key=lambda x: -x["minutos"]),
        "anio": anio,
    }


@router.post("", status_code=201, summary="Publicar un aviso")
def crear(dto: s.AvisoEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AvisoService(session)
    return svc.salida(svc.crear(dto, ctx), ctx.usuario, detalle=True)


@router.get("/{aviso_id}", summary="Detalle de un aviso con sus actualizaciones")
def detalle(aviso_id: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AvisoService(session)
    return svc.salida(svc.get(aviso_id), ctx.usuario, detalle=True)


@router.put("/{aviso_id}", summary="Editar título, mensaje, áreas o ticket maestro")
def editar(aviso_id: int, dto: s.AvisoEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AvisoService(session)
    return svc.salida(svc.editar(aviso_id, dto, ctx), ctx.usuario, detalle=True)


@router.post("/{aviso_id}/actualizaciones", summary="Publicar una novedad (y opcionalmente resolver y avisar a todos)")
def actualizar(aviso_id: int, dto: s.AvisoActualizacionEntrada, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    svc = AvisoService(session)
    return svc.salida(svc.actualizar(aviso_id, dto, ctx), ctx.usuario, detalle=True)


@router.get("/{aviso_id}/afectados", summary="Personas que marcaron «me afecta» y tickets vinculados")
def afectados(aviso_id: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    return AvisoService(session).lista_afectados(aviso_id)


@router.get("/{aviso_id}/constancia", summary="Constancia en PDF de la interrupción (para clientes)")
def constancia(aviso_id: int, ctx: Contexto = Depends(GESTIONAR), session: Session = DbSession):
    nombre, contenido = AvisoService(session).constancia_pdf(aviso_id, ctx)
    return Response(contenido, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
