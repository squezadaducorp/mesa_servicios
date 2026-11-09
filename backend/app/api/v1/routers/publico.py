"""Endpoints sin autenticación del formulario público de solicitudes (/solicitud)."""
from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.api.deps import DbSession, equipo_cliente, ip_cliente
from app.application.schemas import esquemas as s
from app.application.services.formulario_service import FormularioService

router = APIRouter(prefix="/publico", tags=["Formulario público"])


@router.get("/formulario", response_model=s.FormularioPublicoSalida,
            summary="Categorías y ficha anti-spam para el formulario público (sin cuenta)")
def formulario(session: Session = DbSession):
    return FormularioService(session).formulario()


@router.post("/tickets", response_model=s.SolicitudPublicaSalida, status_code=201,
             summary="Registrar una solicitud sin cuenta (clientes y personas externas)")
def registrar(dto: s.SolicitudPublica, request: Request, session: Session = DbSession):
    t = FormularioService(session).registrar(dto, ip_cliente(request), equipo_cliente(request))
    return {"numero": t.numero,
            "mensaje": f"Registramos su solicitud con el número {t.numero}. Le escribiremos a {t.correo} con las novedades."}
