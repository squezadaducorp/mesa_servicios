"""Hash de contraseñas, JWT de acceso y refresh tokens opacos."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def utcnow() -> datetime:
    """Hora actual en UTC sin zona (formato de almacenamiento)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def hash_clave(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt(12)).decode()


def verificar_clave(clave: str, clave_hash: str | None) -> bool:
    if not clave_hash:
        return False
    try:
        return bcrypt.checkpw(clave.encode(), clave_hash.encode())
    except ValueError:
        return False


def validar_politica_clave(clave: str) -> list[str]:
    errores = []
    if len(clave) < settings.CLAVE_MIN_LONGITUD:
        errores.append(f"Debe tener al menos {settings.CLAVE_MIN_LONGITUD} caracteres")
    if not re.search(r"[A-Z]", clave):
        errores.append("Debe incluir una mayúscula")
    if not re.search(r"[a-z]", clave):
        errores.append("Debe incluir una minúscula")
    if not re.search(r"\d", clave):
        errores.append("Debe incluir un número")
    if not re.search(r"[^A-Za-z0-9]", clave):
        errores.append("Debe incluir un símbolo")
    return errores


def crear_access_token(usuario_id: int, rol: str, nombre: str) -> tuple[str, int]:
    expira_seg = settings.ACCESS_TOKEN_MINUTES * 60
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "rol": rol,
        "nombre": nombre,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=expira_seg),
        "typ": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), expira_seg


def decodificar_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "access" else None


def nuevo_refresh_token() -> tuple[str, str]:
    """Devuelve (token en claro para el cliente, hash SHA-256 para la BD)."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
