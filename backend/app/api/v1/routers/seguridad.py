"""Seguridad de la cuenta: verificación en dos pasos de cada usuario y política por rol (mejora 28)."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as es
from app.application.services.dos_pasos_service import DosPasosService
from app.domain.enums import Permiso

router = APIRouter(prefix="/seguridad", tags=["Seguridad de la cuenta"])
ADMIN = requiere(Permiso.USUARIO_ADMINISTRAR)


class MetodoEntrada(BaseModel):
    metodo: Literal["APP", "CORREO"] = "APP"


class ConfirmarEntrada(MetodoEntrada):
    codigo: str = Field(max_length=20)


class ClaveEntrada(BaseModel):
    clave: str | None = Field(None, max_length=200)


class PoliticaEntrada(BaseModel):
    obligatoria_admin: bool
    obligatoria_analistas: bool
    opcional_otros: bool
    permitir_correo: bool
    solo_fuera_oficina: bool = False
    redes_oficina: str | None = Field(None, max_length=900)
    dias_confianza: int = Field(30, ge=0, le=365)
    exentos: list[str] = Field(default_factory=list, max_length=20)
    dias_gracia: int | None = Field(None, ge=0, le=90)


@router.get("/mi-cuenta", summary="Estado de mi verificación en dos pasos")
def mi_estado(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return DosPasosService(session).estado(ctx.usuario)


@router.post("/mi-cuenta/iniciar", summary="Empezar a activar: QR para el Authenticator o código por correo")
def iniciar(dto: MetodoEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return DosPasosService(session).iniciar_activacion(ctx.usuario, dto.metodo)


@router.post("/mi-cuenta/confirmar", summary="Confirmar con el primer código; devuelve los códigos de respaldo")
def confirmar(dto: ConfirmarEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return {"codigos": DosPasosService(session).confirmar_activacion(ctx.usuario, dto.metodo, dto.codigo, ctx)}


@router.post("/mi-cuenta/codigos", summary="Generar nuevos códigos de respaldo (los anteriores dejan de servir)")
def codigos(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return {"codigos": DosPasosService(session).regenerar_codigos(ctx.usuario, ctx)}


@router.post("/mi-cuenta/desactivar", response_model=es.Mensaje, summary="Desactivar (solo si mi rol no la tiene obligatoria)")
def desactivar(dto: ClaveEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    DosPasosService(session).desactivar(ctx.usuario, dto.clave or "", ctx)
    return {"mensaje": "Verificación en dos pasos desactivada"}


@router.post("/mi-cuenta/olvidar-equipos", summary="Dejar de confiar en todos mis equipos")
def olvidar(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    return {"equipos": DosPasosService(session).olvidar_equipos(ctx.usuario)}


@router.get("/politica", summary="Política de verificación y estado por usuario")
def politica(ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = DosPasosService(session)
    return {"politica": svc.politica(), "usuarios": svc.estado_usuarios()}


@router.put("/politica", summary="Guardar la política de verificación por rol")
def guardar_politica(dto: PoliticaEntrada, ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    svc = DosPasosService(session)
    pol = svc.guardar_politica(dto.model_dump(), ctx)
    session.flush()
    return {"politica": pol, "usuarios": svc.estado_usuarios()}


@router.post("/usuarios/{usuario_id}/restablecer", response_model=es.Mensaje,
             summary="Restablecer la verificación de un usuario (cambió de celular o lo perdió)")
def restablecer(usuario_id: int, ctx: Contexto = Depends(ADMIN), session: Session = DbSession):
    u = DosPasosService(session).restablecer(usuario_id, ctx)
    return {"mensaje": f"Verificación de {u.nombre} restablecida: la configurará de nuevo en su próximo ingreso"}
