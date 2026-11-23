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


# Palabras que hacen una contraseña fácil de adivinar aunque cumpla la complejidad (mejora 37, A.5.17).
# Se revisan sin consultar servicios externos.
PALABRAS_OBVIAS = (
    "aducorp", "aduana", "ecuapass", "senae", "password", "passw0rd", "contrasena", "contraseña", "clave", "qwerty", "asdf",
    "123456", "654321", "abc123", "abcdef", "admin", "bienvenid", "welcome", "ecuador", "guayaquil", "quito", "tababela",
    "mesa", "soporte", "cambiar", "temporal", "invierno", "verano", "enero", "febrero", "diciembre", "iloveyou", "teamo",
)


def _sin_tildes(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))


def clave_obvia(clave: str, personales: tuple[str, ...] = ()) -> bool:
    """¿Contiene el nombre de la empresa, una palabra típica, una secuencia o datos de la persona (correo, nombre)?"""
    plano = _sin_tildes(clave)
    simple = plano.translate(str.maketrans("@4310$5!7", "aaeiosslt"))   # Aduc0rp → aducorp, P@ssw0rd → password
    for palabra in PALABRAS_OBVIAS + tuple(_sin_tildes(p) for p in personales if p and len(p) >= 4):
        if palabra in plano or palabra in simple:
            return True
    return len(set(plano)) <= 3   # «Aaaaaaaa1!»


def validar_politica_clave(clave: str, personales: tuple[str, ...] = ()) -> list[str]:
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
    if clave_obvia(clave, personales):
        errores.append("Es fácil de adivinar: evite el nombre de la empresa, su nombre o correo, palabras como «clave» o secuencias como 123456")
    return errores


def datos_personales(nombre: str | None, correo: str | None) -> tuple[str, ...]:
    """Partes del nombre y del correo que no deben aparecer en la contraseña."""
    partes = [p for p in (nombre or "").replace(".", " ").split() if len(p) >= 4]
    local = (correo or "").split("@")[0]
    partes += [p for p in local.replace("_", ".").replace("-", ".").split(".") if len(p) >= 4]
    return tuple(partes)


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
