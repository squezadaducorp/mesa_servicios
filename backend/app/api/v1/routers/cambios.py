"""Gestión de cambios: TI-FOR-001/002 en pantalla, registro CAM, aprobaciones, calendario y congelamientos (mejora 27)."""
from datetime import date

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto
from app.application.errores import Contexto
from app.application.schemas import cuarta as s
from app.application.schemas import esquemas as es
from app.application.services.cambio_service import CambioService, NOMBRE_ESTADO, TEXTO
from app.domain.archivos import mime_descarga

router = APIRouter(prefix="/cambios", tags=["Gestión de cambios"])


@router.get("", summary="Registro de cambios con indicadores")
def listar(estado: str | None = Query(None), q: str | None = Query(None, max_length=100), ctx: Contexto = Depends(contexto),
           session: Session = DbSession):
    svc = CambioService(session)
    return {"cambios": [svc.salida_lista(c) for c in svc.listar(ctx.usuario, estado, q)], "resumen": svc.resumen(ctx.usuario),
            "gestor": svc.gestor(ctx.usuario)}


@router.get("/opciones", summary="Listas del formulario (aplicaciones, responsables, quién aprueba)")
def opciones(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    jefe, ger = svc.jefe_ti(), svc.gerencia()
    return {"aplicaciones": svc.aplicaciones(), "responsables": svc.responsables() if svc.gestor(ctx.usuario) else [],
            "jefe_ti": jefe.nombre if jefe else None, "gerencia": ger.nombre if ger else None, "estados": NOMBRE_ESTADO,
            "textos": TEXTO, "congelamientos": svc.proximos_congelamientos(), "gestor": svc.gestor(ctx.usuario)}


@router.get("/calendario", summary="Ventanas de la semana y periodos congelados")
def calendario(desde: date | None = Query(None, description="Cualquier día de la semana (se toma su lunes)"), ctx: Contexto = Depends(contexto),
               session: Session = DbSession):
    return CambioService(session).calendario(ctx.usuario, desde)


@router.get("/exportar", summary="Exportar el registro de cambios a Excel")
def exportar(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    datos = CambioService(session).exportar(ctx.usuario)
    return Response(datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Registro-de-Cambios.xlsx"'})


@router.post("", status_code=201, summary="Solicitar un cambio (secciones 1 a 6)")
def crear(dto: s.CambioEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.crear(dto, ctx), ctx.usuario)


@router.post("/congelamientos", status_code=201, summary="Agregar un periodo sin cambios")
def crear_congelamiento(dto: s.CongelamientoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    f = CambioService(session).crear_congelamiento(dto, ctx)
    return {"id": f.id, "titulo": f.titulo}


@router.delete("/congelamientos/{congelamiento_id}", response_model=es.Mensaje, summary="Quitar un periodo sin cambios")
def borrar_congelamiento(congelamiento_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    CambioService(session).borrar_congelamiento(congelamiento_id, ctx)
    return {"mensaje": "Periodo eliminado"}


@router.get("/{cambio_id}", summary="Detalle del cambio")
def uno(cambio_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.obtener(cambio_id, ctx.usuario), ctx.usuario)


@router.put("/{cambio_id}", summary="El solicitante corrige su solicitud antes de la evaluación")
def editar(cambio_id: int, dto: s.CambioEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.editar(cambio_id, dto, ctx), ctx.usuario)


@router.post("/{cambio_id}/evaluar", summary="Sección 7: evaluación de TI (aprobar, rechazar o dejar en espera)")
def evaluar(cambio_id: int, dto: s.EvaluacionEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    c = svc.evaluar(cambio_id, dto, ctx)
    session.flush()
    return svc.salida(c, ctx.usuario)


@router.post("/{cambio_id}/responder", summary="Aprobar o rechazar (Jefe de TI o Gerencia)")
def responder(cambio_id: int, dto: s.RespuestaCambio, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    c = svc.responder(cambio_id, dto.aprobar, dto.comentario, ctx)
    session.flush()
    return svc.salida(c, ctx.usuario)


@router.post("/{cambio_id}/ventana", summary="Cambiar la ventana de implementación")
def reprogramar(cambio_id: int, dto: s.VentanaEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.reprogramar(cambio_id, dto, ctx), ctx.usuario)


@router.post("/{cambio_id}/implementar", summary="Marcar como implementado (pasa a revisión posterior)")
def implementar(cambio_id: int, dto: s.ImplementarEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.implementar(cambio_id, dto, ctx), ctx.usuario)


@router.post("/{cambio_id}/revision", summary="Revisión posterior: exitoso, con problemas o revertido")
def revisar(cambio_id: int, dto: s.RevisionEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = CambioService(session)
    return svc.salida(svc.revisar(cambio_id, dto, ctx), ctx.usuario)


@router.post("/{cambio_id}/adjuntos", status_code=201, summary="Adjuntar un archivo o captura")
async def adjuntar(cambio_id: int, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), session: Session = DbSession):
    contenido = await archivo.read()
    svc = CambioService(session)
    svc.adjuntar(cambio_id, archivo.filename or "archivo", archivo.content_type or "", contenido, ctx)
    return svc.salida(svc.obtener(cambio_id, ctx.usuario), ctx.usuario)


@router.get("/{cambio_id}/adjuntos/{adjunto_id}", summary="Descargar un adjunto")
def descargar(cambio_id: int, adjunto_id: int, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    a, ruta = CambioService(session).adjunto(cambio_id, adjunto_id, ctx)
    return FileResponse(ruta, media_type=mime_descarga(a.tipo_mime), filename=a.nombre_original, content_disposition_type="attachment")
