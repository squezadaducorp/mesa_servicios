"""Endpoints sin autenticación del formulario público de solicitudes (/solicitud)."""
import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import DbSession, equipo_cliente, ip_cliente
from app.application.errores import ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.formulario_service import ArchivoPublico, FormularioService
from app.core.config import settings

router = APIRouter(prefix="/publico", tags=["Formulario público"])


@router.get("/formulario", response_model=s.FormularioPublicoSalida,
            summary="Categorías, reglas de adjuntos y ficha anti-spam para el formulario público (sin cuenta)")
def formulario(session: Session = DbSession):
    return FormularioService(session).formulario()


@router.post("/tickets", response_model=s.SolicitudPublicaSalida, status_code=201,
             summary="Registrar una solicitud sin cuenta (clientes y personas externas), con adjuntos opcionales")
async def registrar(request: Request,
                    datos: str = Form(..., description="JSON con los campos de SolicitudPublica"),
                    archivos: list[UploadFile] = File(default=[], description="Adjuntos opcionales (ver GET /publico/formulario)"),
                    session: Session = DbSession):
    try:
        dto = s.SolicitudPublica.model_validate(json.loads(datos))
    except (ValueError, ValidationError):
        raise ReglaNegocio("Revise los datos del formulario: hay campos incompletos o no válidos.")
    archivos = [a for a in archivos if a.filename]
    # Lectura acotada: nunca se carga en memoria más de lo permitido por archivo (Nginx limita además el cuerpo).
    limite = min(settings.FORMULARIO_WEB_ADJUNTOS_MAX_MB, settings.ADJUNTOS_MAX_MB) * 1024 * 1024 + 1
    leidos = []
    for a in archivos[: max(0, settings.FORMULARIO_WEB_ADJUNTOS_MAX) + 1]:
        leidos.append(ArchivoPublico(a.filename or "archivo", a.content_type or "", await a.read(limite)))
    t = FormularioService(session).registrar(dto, ip_cliente(request), equipo_cliente(request), leidos)
    n = len(leidos)
    extra = f" Recibimos {n} archivo{'s' if n != 1 else ''} adjunto{'s' if n != 1 else ''}." if n else ""
    return {"numero": t.numero, "adjuntos": n,
            "mensaje": f"Registramos su solicitud con el número {t.numero}. Le escribiremos a {t.correo} con las novedades.{extra}"}
