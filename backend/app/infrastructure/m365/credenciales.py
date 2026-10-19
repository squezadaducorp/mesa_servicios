"""Tokens de aplicación (client credentials) con caché en memoria por scope."""
from __future__ import annotations

import threading
import time

import httpx

from app.core.config import settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
BOT_SCOPE = "https://api.botframework.com/.default"

_cache: dict[str, tuple[str, float]] = {}
_candado = threading.Lock()


class ErrorM365(Exception):
    """Fallo al comunicarse con Microsoft 365 (se reintenta en el siguiente ciclo)."""


def url_token() -> str:
    return f"{settings.M365_AUTHORITY.rstrip('/')}/{settings.M365_TENANT_ID}/oauth2/v2.0/token"


def token_aplicacion(scope: str, http: httpx.Client | None = None) -> str:
    if not settings.m365_configurado:
        raise ErrorM365("Microsoft 365 no está configurado (M365_TENANT_ID, M365_CLIENT_ID, M365_CLIENT_SECRET)")
    with _candado:
        guardado = _cache.get(scope)
        if guardado and guardado[1] - 120 > time.time():
            return guardado[0]
        cliente = http or httpx.Client(timeout=20)
        try:
            r = cliente.post(url_token(), data={
                "grant_type": "client_credentials", "client_id": settings.M365_CLIENT_ID,
                "client_secret": settings.M365_CLIENT_SECRET, "scope": scope,
            })
        finally:
            if http is None:
                cliente.close()
        if r.status_code != 200:
            raise ErrorM365(f"No se obtuvo token de Entra ID ({r.status_code}): {r.text[:300]}")
        datos = r.json()
        _cache[scope] = (datos["access_token"], time.time() + int(datos.get("expires_in", 3600)))
        return datos["access_token"]


def limpiar_cache() -> None:
    with _candado:
        _cache.clear()
