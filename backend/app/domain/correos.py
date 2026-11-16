"""Listas de correos en copia (CC): normalización y validación compartidas por tickets, comentarios y catálogo."""
from __future__ import annotations

import re
from collections.abc import Iterable

MAX_COPIAS = 10
MAX_LARGO = 500          # cabe en cola_correos.cc y en las columnas correos_copia / copia_a
_CORREO = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")
_SEPARADORES = re.compile(r"[\s,;]+")


def normalizar_correos(valor: Iterable[str] | str | None) -> list[str]:
    """Devuelve los correos en minúsculas, sin repetir y en el orden recibido. Lanza ValueError si alguno no es válido."""
    if valor is None:
        return []
    partes = [valor] if isinstance(valor, str) else list(valor)
    vistos: list[str] = []
    for parte in partes:
        for c in _SEPARADORES.split(str(parte or "").strip()):
            c = c.strip().lower()
            if not c:
                continue
            if len(c) > 150 or not _CORREO.match(c):
                raise ValueError(f"Correo no válido: {c[:80]}")
            if c not in vistos:
                vistos.append(c)
    if len(vistos) > MAX_COPIAS:
        raise ValueError(f"Máximo {MAX_COPIAS} correos en copia")
    if len(", ".join(vistos)) > MAX_LARGO:
        raise ValueError("La lista de correos en copia es demasiado larga")
    return vistos


def unir(correos: Iterable[str]) -> str | None:
    texto = ", ".join(correos)
    return texto or None


def separar(texto: str | None) -> list[str]:
    return [c for c in _SEPARADORES.split(texto or "") if c]
