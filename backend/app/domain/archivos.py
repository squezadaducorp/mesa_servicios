"""Validación del contenido de archivos adjuntos por firma (magic bytes)."""

# Firmas conocidas por extensión; si la extensión no está aquí solo se aplica la lista negra.
FIRMAS: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "zip": (b"PK\x03\x04", b"PK\x05\x06"),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "pptx": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "msg": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}

# Ejecutables y scripts que nunca se aceptan, aunque cambien de extensión
PROHIBIDAS: tuple[bytes, ...] = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")

# Tipos que el navegador puede mostrar sin riesgo; el resto se descarga como binario
MIME_SEGUROS = {
    "application/pdf", "image/png", "image/jpeg", "image/gif", "text/plain", "text/csv",
    "application/zip", "application/msword", "application/vnd.ms-excel", "application/vnd.ms-outlook", "message/rfc822",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def contenido_valido(extension: str, contenido: bytes) -> bool:
    cabecera = contenido[:16]
    if any(cabecera.startswith(f) for f in PROHIBIDAS):
        return False
    firmas = FIRMAS.get(extension)
    return firmas is None or any(cabecera.startswith(f) for f in firmas)


def mime_descarga(mime: str | None) -> str:
    return mime if mime in MIME_SEGUROS else "application/octet-stream"
