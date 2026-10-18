"""Dependencias FastAPI: sesión de BD, usuario autenticado, permisos y contexto de auditoría."""
import ipaddress
from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoAutorizado, Prohibido
from app.core.config import settings
from app.core.security import decodificar_access_token, utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import get_session

bearer = HTTPBearer(auto_error=False, description="Token JWT obtenido en /auth/login")

DbSession = Depends(get_session)


@lru_cache
def _redes_confiables() -> tuple:
    return tuple(ipaddress.ip_network(r, strict=False) for r in settings.TRUSTED_PROXIES)


def _es_proxy_confiable(host: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return host == "testclient"
    return any(ip in red for red in _redes_confiables())


def ip_cliente(request: Request) -> str | None:
    """IP real del usuario. Las cabeceras de proxy solo se aceptan si la conexión viene de Nginx (TRUSTED_PROXIES)."""
    directa = request.client.host if request.client else None
    ip = None
    if _es_proxy_confiable(directa):
        ip = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return (ip or directa or "")[:45] or None


def equipo_cliente(request: Request) -> str | None:
    equipo = request.headers.get("x-equipo")   # nombre de equipo si lo envía un agente corporativo
    ua = request.headers.get("user-agent", "")
    return (f"{equipo} · {ua}" if equipo else ua)[:300] or None


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer), session: Session = DbSession
) -> m.Usuario:
    if credenciales is None:
        raise NoAutorizado("Se requiere autenticación")
    payload = decodificar_access_token(credenciales.credentials)
    if payload is None:
        raise NoAutorizado("Token inválido o expirado")
    usuario = session.get(m.Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo or usuario.eliminado:
        raise NoAutorizado("Usuario inactivo")
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > utcnow():
        raise NoAutorizado("Cuenta bloqueada")
    return usuario


def contexto(request: Request, usuario: m.Usuario = Depends(usuario_actual)) -> Contexto:
    return Contexto(usuario=usuario, ip=ip_cliente(request), equipo=equipo_cliente(request))


def contexto_anonimo(request: Request) -> Contexto:
    return Contexto(usuario=None, ip=ip_cliente(request), equipo=equipo_cliente(request))


def requiere(*permisos: str, todos: bool = False) -> Callable:
    """Dependencia que exige uno (o todos) los permisos indicados."""

    def _verificar(ctx: Contexto = Depends(contexto)) -> Contexto:
        tiene = ctx.usuario.permisos
        ok = all(p in tiene for p in permisos) if todos else any(p in tiene for p in permisos)
        if not ok:
            raise Prohibido("No tiene permisos para esta operación")
        return ctx

    return _verificar
