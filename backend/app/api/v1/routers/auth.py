from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, contexto_anonimo
from app.application.errores import Contexto, ErrorAplicacion
from app.core.config import settings
from app.core.limite import Limitador
from app.application.schemas import esquemas as s
from app.application.services.auth_service import AuthService, usuario_sesion

router = APIRouter(prefix="/auth", tags=["Autenticación"])
limitador_login = Limitador(settings.LOGIN_MAX_POR_MINUTO, 60)


class DemasiadosIntentos(ErrorAplicacion):
    codigo_http = 429


@router.post("/login", response_model=s.TokenSalida, summary="Iniciar sesión (local o Active Directory)")
def login(dto: s.LoginEntrada, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    if not limitador_login.permitir(ctx.ip or "?"):
        raise DemasiadosIntentos("Demasiados intentos de inicio de sesión. Espere un minuto.")
    return AuthService(session).login(dto.correo, dto.clave, ctx)


@router.post("/refresh", response_model=s.TokenSalida, summary="Renovar el access token (rota el refresh token)")
def refresh(dto: s.RefreshEntrada, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    return AuthService(session).refrescar(dto.refresh_token, ctx)


@router.post("/logout", response_model=s.Mensaje, summary="Cerrar sesión y revocar el refresh token")
def logout(dto: s.RefreshEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    AuthService(session).logout(dto.refresh_token, ctx)
    return {"mensaje": "Sesión cerrada"}


@router.get("/me", response_model=s.UsuarioSesion, summary="Usuario autenticado y sus permisos")
def me(ctx: Contexto = Depends(contexto)):
    return usuario_sesion(ctx.usuario)


@router.post("/cambiar-clave", response_model=s.TokenSalida, summary="Cambiar contraseña (revoca otras sesiones)")
def cambiar_clave(dto: s.CambioClaveEntrada, ctx: Contexto = Depends(contexto), session: Session = DbSession):
    svc = AuthService(session)
    svc.cambiar_clave(ctx.usuario, dto.clave_actual, dto.clave_nueva, ctx)
    import secrets

    return svc._emitir(ctx.usuario, ctx, familia=secrets.token_hex(16))
