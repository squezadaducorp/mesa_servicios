"""Punto de mensajería del bot de Microsoft Teams (lo llama el Bot Connector de Azure)."""
import logging

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.application.services.teams_service import TeamsService
from app.core.config import settings
from app.infrastructure.m365.teams import validar_llamada_bot

log = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["Microsoft 365"])


@router.post("/mensajes", summary="Actividades del bot de Teams (Bot Framework)")
async def mensajes(request: Request, session: Session = DbSession):
    if not settings.TEAMS_ENABLED:
        return Response(status_code=404)
    actividad = await request.json()
    try:
        validar_llamada_bot(request.headers.get("authorization"), actividad.get("serviceUrl"))
    except (jwt.PyJWTError, KeyError) as exc:
        log.warning("Llamada al bot rechazada: %s", exc)
        return Response(status_code=401)
    resultado = TeamsService(session).procesar(actividad)
    return JSONResponse(resultado) if resultado is not None else Response(status_code=200)
