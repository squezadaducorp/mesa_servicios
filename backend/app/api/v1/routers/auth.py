import logging
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, contexto_anonimo
from app.application.errores import Contexto, ErrorAplicacion
from app.core.config import settings
from app.core.limite import Limitador
from app.application.schemas import esquemas as s
from app.application.services.auth_service import AuthService, usuario_sesion
from app.application.services.entra_service import EntraService
from app.infrastructure.m365.credenciales import ErrorM365

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Autenticación"])
COOKIE_ENTRA = "aducorp_entra"
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


# ------------------------------------------------------------- Entra ID (SSO)
class EntraConfig(BaseModel):
    activo: bool
    permitir_local: bool


class IntercambioEntrada(BaseModel):
    codigo: str


def _app(ruta: str) -> str:
    return f"{settings.APP_URL.rstrip('/')}{ruta}"


@router.get("/entra/config", response_model=EntraConfig, summary="¿Está habilitado el inicio de sesión con Microsoft?")
def entra_config():
    return {"activo": settings.entra_activo,
            "permitir_local": settings.AUTH_PROVIDER != "entra" or bool(settings.ENTRA_CUENTAS_EMERGENCIA)}


@router.get("/entra/login", summary="Redirige a Microsoft Entra ID (OIDC con PKCE)")
def entra_login(destino: str | None = Query(None), pista: str | None = Query(None, max_length=150)):
    url, cookie = EntraService.iniciar(destino, pista)
    r = RedirectResponse(url, status_code=302)
    r.set_cookie(COOKIE_ENTRA, cookie, max_age=600, httponly=True, samesite="lax",
                 secure=settings.APP_URL.startswith("https://"), path=f"{settings.API_PREFIX}/auth/entra")
    return r


@router.get("/entra/callback", include_in_schema=False)
def entra_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                   error_description: str | None = None, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    def fallo(mensaje: str) -> RedirectResponse:
        r = RedirectResponse(_app(f"/login?{urlencode({'error_sso': mensaje})}"), status_code=302)
        r.delete_cookie(COOKIE_ENTRA, path=f"{settings.API_PREFIX}/auth/entra")
        return r

    if error or not code:
        log.info("Entra ID devolvió error: %s %s", error, (error_description or "")[:200])
        return fallo("Microsoft no completó el inicio de sesión" if error != "access_denied" else "Inicio de sesión cancelado")
    try:
        codigo, destino = EntraService(session).completar(code, state or "", request.cookies.get(COOKIE_ENTRA), ctx)
        session.commit()
    except ErrorAplicacion as exc:
        return fallo(exc.mensaje)
    except ErrorM365:
        log.exception("Fallo al completar el inicio de sesión con Entra ID")
        return fallo("No se pudo contactar a Microsoft. Intente de nuevo en unos minutos.")
    r = RedirectResponse(_app(f"/auth/entra#codigo={quote(codigo)}&destino={quote(destino)}"), status_code=302)
    r.delete_cookie(COOKIE_ENTRA, path=f"{settings.API_PREFIX}/auth/entra")
    return r


@router.post("/entra/intercambio", response_model=s.TokenSalida, summary="Cambia el código de un solo uso por la sesión de la Mesa")
def entra_intercambio(dto: IntercambioEntrada, ctx: Contexto = Depends(contexto_anonimo), session: Session = DbSession):
    return EntraService(session).intercambiar(dto.codigo, ctx)
