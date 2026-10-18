"""Reglas de negocio del ciclo de vida del ticket."""
from app.domain.enums import Estado

TRANSICIONES: dict[Estado, set[Estado]] = {
    Estado.NUEVO: {Estado.ASIGNADO, Estado.EN_PROCESO, Estado.ESCALADO, Estado.CANCELADO},
    Estado.ASIGNADO: {Estado.EN_PROCESO, Estado.PENDIENTE_CLIENTE, Estado.ESCALADO, Estado.RESUELTO, Estado.CANCELADO},
    Estado.EN_PROCESO: {Estado.PENDIENTE_CLIENTE, Estado.ESCALADO, Estado.RESUELTO, Estado.CANCELADO},
    Estado.PENDIENTE_CLIENTE: {Estado.EN_PROCESO, Estado.ESCALADO, Estado.RESUELTO, Estado.CANCELADO},
    Estado.ESCALADO: {Estado.ASIGNADO, Estado.EN_PROCESO, Estado.PENDIENTE_CLIENTE, Estado.RESUELTO, Estado.CANCELADO},
    Estado.RESUELTO: {Estado.CERRADO, Estado.EN_PROCESO},   # EN_PROCESO = reapertura
    Estado.CERRADO: {Estado.EN_PROCESO},                    # reapertura
    Estado.CANCELADO: set(),
}


class TransicionInvalida(ValueError):
    pass


def validar_transicion(actual: Estado, nuevo: Estado) -> None:
    if nuevo == actual:
        raise TransicionInvalida(f"El ticket ya está en estado {actual}")
    if nuevo not in TRANSICIONES[actual]:
        raise TransicionInvalida(f"No se permite pasar de {actual} a {nuevo}")


def es_reapertura(actual: Estado, nuevo: Estado) -> bool:
    return actual in (Estado.RESUELTO, Estado.CERRADO) and nuevo == Estado.EN_PROCESO


def cuenta_como_primera_respuesta(nuevo: Estado) -> bool:
    """Pasar a cualquiera de estos estados implica que el equipo ya respondió."""
    return nuevo in (Estado.EN_PROCESO, Estado.PENDIENTE_CLIENTE, Estado.RESUELTO)
