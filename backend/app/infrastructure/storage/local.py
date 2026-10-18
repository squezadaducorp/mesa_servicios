"""Almacenamiento de adjuntos en disco (volumen Docker). Nombres aleatorios, nunca el original."""
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings


class AlmacenamientoLocal:
    def __init__(self, raiz: str | None = None):
        self.raiz = Path(raiz or settings.STORAGE_PATH).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def guardar(self, contenido: bytes, extension: str) -> tuple[str, str]:
        """Guarda el archivo y devuelve (ruta relativa, sha256)."""
        hoy = datetime.now(timezone.utc)
        relativa = Path(f"{hoy:%Y}/{hoy:%m}/{uuid.uuid4().hex}.{extension}")
        destino = self.raiz / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        return relativa.as_posix(), hashlib.sha256(contenido).hexdigest()

    def ruta(self, relativa: str) -> Path:
        destino = (self.raiz / relativa).resolve()
        if not destino.is_relative_to(self.raiz):   # evita path traversal
            raise ValueError("Ruta de adjunto inválida")
        return destino
