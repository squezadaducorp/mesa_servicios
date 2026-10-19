"""Cliente mínimo de Microsoft Graph con permisos de aplicación."""
from __future__ import annotations

from collections.abc import Iterator

import httpx

from app.core.config import settings
from app.infrastructure.m365.credenciales import GRAPH_SCOPE, ErrorM365, token_aplicacion


class ClienteGraph:
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=30)

    def _url(self, ruta: str) -> str:
        return ruta if ruta.startswith("https://") else f"{settings.GRAPH_URL.rstrip('/')}/{ruta.lstrip('/')}"

    def _pedir(self, metodo: str, ruta: str, **kw) -> httpx.Response:
        cabeceras = {"Authorization": f"Bearer {token_aplicacion(GRAPH_SCOPE)}", **kw.pop("headers", {})}
        r = self.http.request(metodo, self._url(ruta), headers=cabeceras, **kw)
        if r.status_code >= 400:
            raise ErrorM365(f"Graph {metodo} {ruta} respondió {r.status_code}: {r.text[:300]}")
        return r

    def get(self, ruta: str, params: dict | None = None, headers: dict | None = None) -> dict:
        return self._pedir("GET", ruta, params=params, headers=headers or {}).json()

    def paginar(self, ruta: str, params: dict | None = None, headers: dict | None = None) -> Iterator[dict]:
        datos = self.get(ruta, params, headers)
        while True:
            yield from datos.get("value", [])
            siguiente = datos.get("@odata.nextLink")
            if not siguiente:
                return
            datos = self.get(siguiente, headers=headers)

    def post(self, ruta: str, json: dict) -> dict | None:
        r = self._pedir("POST", ruta, json=json)
        return r.json() if r.content else None

    def patch(self, ruta: str, json: dict) -> None:
        self._pedir("PATCH", ruta, json=json)

    # ---------------------------------------------------------- utilidades
    def enviar_correo(self, remitente: str, para: list[str], asunto: str, cuerpo_html: str, cc: list[str] | None = None) -> None:
        self.post(f"/users/{remitente}/sendMail", {
            "message": {
                "subject": asunto,
                "body": {"contentType": "HTML", "content": cuerpo_html},
                "toRecipients": [{"emailAddress": {"address": d}} for d in para],
                "ccRecipients": [{"emailAddress": {"address": d}} for d in (cc or [])],
            },
            "saveToSentItems": True,
        })
