"""Errores de aplicación. La capa API los traduce a códigos HTTP."""
from dataclasses import dataclass


class ErrorAplicacion(Exception):
    codigo_http = 400

    def __init__(self, mensaje: str, detalle: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle or {}


class NoEncontrado(ErrorAplicacion):
    codigo_http = 404


class NoAutorizado(ErrorAplicacion):
    codigo_http = 401


class Prohibido(ErrorAplicacion):
    codigo_http = 403


class Conflicto(ErrorAplicacion):
    codigo_http = 409


class ReglaNegocio(ErrorAplicacion):
    codigo_http = 422


@dataclass
class Contexto:
    """Quién hace la operación y desde dónde (para auditoría)."""

    usuario: object | None = None   # app.infrastructure.db.models.Usuario
    ip: str | None = None
    equipo: str | None = None
