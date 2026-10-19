"""Bot Framework: envío de actividades a Teams y validación de las llamadas entrantes del Bot Connector."""
from __future__ import annotations

from functools import lru_cache

import httpx
import jwt

from app.core.config import settings
from app.infrastructure.m365.credenciales import BOT_SCOPE, ErrorM365, token_aplicacion

OPENID_BOT = "https://login.botframework.com/v1/.well-known/openidconfiguration"
EMISOR_BOT = "https://api.botframework.com"


class ConectorBot:
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=30)

    def _cabeceras(self) -> dict:
        return {"Authorization": f"Bearer {token_aplicacion(BOT_SCOPE)}"}

    def enviar(self, service_url: str, conversacion: str, actividad: dict) -> dict:
        r = self.http.post(f"{service_url.rstrip('/')}/v3/conversations/{conversacion}/activities", json=actividad, headers=self._cabeceras())
        if r.status_code >= 400:
            raise ErrorM365(f"Teams respondió {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}


@lru_cache
def _jwks_bot() -> jwt.PyJWKClient:
    uri = httpx.get(OPENID_BOT, timeout=20).json()["jwks_uri"]
    return jwt.PyJWKClient(uri, cache_keys=True, lifespan=86400)


def validar_llamada_bot(autorizacion: str | None, service_url: str | None, jwks: jwt.PyJWKClient | None = None) -> dict:
    """Valida el JWT que el Bot Connector envía en cada actividad (emisor, audiencia = Id. del bot, serviceUrl)."""
    if not autorizacion or not autorizacion.lower().startswith("bearer "):
        raise jwt.InvalidTokenError("falta el token del Bot Connector")
    token = autorizacion.split(" ", 1)[1]
    clave = (jwks or _jwks_bot()).get_signing_key_from_jwt(token).key
    c = jwt.decode(token, clave, algorithms=["RS256"], audience=settings.teams_bot_id, issuer=EMISOR_BOT, leeway=300)
    if c.get("serviceurl") and service_url and c["serviceurl"].rstrip("/") != service_url.rstrip("/"):
        raise jwt.InvalidTokenError("serviceUrl no coincide")
    return c
