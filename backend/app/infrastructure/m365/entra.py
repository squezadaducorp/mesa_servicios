"""Entra ID: flujo OpenID Connect (código de autorización con PKCE) y validación del id_token."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings
from app.infrastructure.m365.credenciales import ErrorM365

ALCANCES = "openid profile email offline_access"


@dataclass
class IdentidadEntra:
    oid: str
    nombre: str
    correo: str
    tenant: str
    grupos: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    grupos_excedidos: bool = False      # el token no trae los grupos (más de 200): hay que pedirlos a Graph
    amr: list[str] = field(default_factory=list)


def _base() -> str:
    return f"{settings.M365_AUTHORITY.rstrip('/')}/{settings.M365_TENANT_ID}"


def emisor() -> str:
    return f"{_base()}/v2.0"


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{_base()}/discovery/v2.0/keys", cache_keys=True, lifespan=3600)


def nuevo_pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, reto


def url_autorizacion(state: str, nonce: str, reto: str, pista: str | None = None) -> str:
    q = {
        "client_id": settings.M365_CLIENT_ID, "response_type": "code", "redirect_uri": settings.entra_redirect_uri,
        "response_mode": "query", "scope": ALCANCES, "state": state, "nonce": nonce,
        "code_challenge": reto, "code_challenge_method": "S256",
    }
    if pista:
        q["login_hint"] = pista
    return f"{_base()}/oauth2/v2.0/authorize?{urlencode(q)}"


def canjear_codigo(codigo: str, verificador: str, http: httpx.Client | None = None) -> dict:
    cliente = http or httpx.Client(timeout=20)
    try:
        r = cliente.post(f"{_base()}/oauth2/v2.0/token", data={
            "grant_type": "authorization_code", "client_id": settings.M365_CLIENT_ID,
            "client_secret": settings.M365_CLIENT_SECRET, "code": codigo, "redirect_uri": settings.entra_redirect_uri,
            "code_verifier": verificador, "scope": ALCANCES,
        })
    finally:
        if http is None:
            cliente.close()
    if r.status_code != 200:
        raise ErrorM365(f"Entra ID rechazó el código de autorización ({r.status_code}): {r.text[:300]}")
    return r.json()


def validar_id_token(id_token: str, nonce: str, jwks: jwt.PyJWKClient | None = None) -> IdentidadEntra:
    """Firma (JWKS del inquilino), emisor, audiencia, vigencia, nonce e inquilino."""
    clave = (jwks or _jwks()).get_signing_key_from_jwt(id_token).key
    c = jwt.decode(id_token, clave, algorithms=["RS256"], audience=settings.M365_CLIENT_ID, issuer=emisor(), leeway=60,
                   options={"require": ["exp", "iat", "aud", "iss", "sub"]})
    if not secrets.compare_digest(str(c.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce no coincide")
    if c.get("tid") != settings.M365_TENANT_ID:
        raise jwt.InvalidTokenError("el token pertenece a otro inquilino")
    correo = (c.get("email") or c.get("preferred_username") or c.get("upn") or "").lower()
    if not c.get("oid") or "@" not in correo:
        raise jwt.InvalidTokenError("el token no trae oid o correo")
    return IdentidadEntra(
        oid=c["oid"], nombre=c.get("name") or correo, correo=correo, tenant=c["tid"],
        grupos=list(c.get("groups") or []), roles=list(c.get("roles") or []),
        grupos_excedidos="groups" in (c.get("_claim_names") or {}), amr=list(c.get("amr") or []),
    )
