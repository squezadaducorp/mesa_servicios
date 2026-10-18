"""Aplicación FastAPI de la Mesa de Servicios ADUCORP."""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm.exc import StaleDataError

from app.api.v1.routers import admin, auditoria, auth, catalogos, notificaciones, reportes, tickets
from app.application.errores import ErrorAplicacion
from app.core.config import settings
from app.infrastructure.db.session import engine

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("aducorp.api")

DESCRIPCION = """
API REST de la **Mesa de Servicios de ADUCORP** (Agencia de Aduanas, Ecuador).

* Autenticación con **JWT** (15 min) y **refresh token rotativo** (7 días): `POST /auth/login`, luego el botón *Authorize*.
* Control de acceso por **roles y permisos** (RBAC) con alcance de datos por rol.
* SLA en **horas laborables** con pausas, excepciones y escalamiento automático al 75 %, 90 % y 100 %.
* Todas las fechas se devuelven en **UTC** (sufijo `Z`).
"""

TAGS = [
    {"name": "Autenticación", "description": "Login, refresh, logout y cambio de contraseña"},
    {"name": "Tickets", "description": "Ciclo de vida completo del ticket"},
    {"name": "Catálogos e IA", "description": "Datos para formularios y sugerencias de IA"},
    {"name": "Reportes y Dashboard", "description": "Indicadores gerenciales y exportaciones"},
    {"name": "Notificaciones", "description": "Centro de notificaciones"},
    {"name": "Auditoría", "description": "Trazabilidad completa"},
    {"name": "Administración", "description": "Usuarios, roles, catálogo, SLA y configuración"},
]

app = FastAPI(
    title="Mesa de Servicios ADUCORP",
    version="1.0.0",
    description=DESCRIPCION,
    openapi_tags=TAGS,
    docs_url=f"{settings.API_PREFIX}/docs" if settings.DOCS_ENABLED else None,
    redoc_url=f"{settings.API_PREFIX}/redoc" if settings.DOCS_ENABLED else None,
    openapi_url=f"{settings.API_PREFIX}/openapi.json" if settings.DOCS_ENABLED else None,
    swagger_ui_parameters={"persistAuthorization": True, "docExpansion": "none"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Equipo"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    inicio = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    respuesta = await call_next(request)
    respuesta.headers["X-Request-ID"] = request_id
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not request.url.path.endswith(("/docs", "/redoc")):
        respuesta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    respuesta.headers["Cache-Control"] = respuesta.headers.get("Cache-Control", "no-store")
    if settings.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    log.info("%s %s %s %.0fms id=%s", request.method, request.url.path, respuesta.status_code, (time.perf_counter() - inicio) * 1000, request_id)
    return respuesta


@app.exception_handler(ErrorAplicacion)
async def error_aplicacion(_: Request, exc: ErrorAplicacion):
    return JSONResponse(status_code=exc.codigo_http, content={"detail": exc.mensaje, **({"errores": exc.detalle} if exc.detalle else {})})


@app.exception_handler(StaleDataError)
async def conflicto_version(_: Request, __: StaleDataError):
    return JSONResponse(status_code=409, content={"detail": "El ticket fue modificado al mismo tiempo por otro proceso. Intente de nuevo."})


@app.exception_handler(RequestValidationError)
async def error_validacion(_: Request, exc: RequestValidationError):
    errores = [{"campo": ".".join(str(x) for x in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Datos inválidos", "errores": errores})


@app.exception_handler(Exception)
async def error_inesperado(request: Request, exc: Exception):
    log.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


for r in (auth, tickets, catalogos, reportes, notificaciones, auditoria, admin):
    app.include_router(r.router, prefix=settings.API_PREFIX)


@app.get(f"{settings.API_PREFIX}/health", tags=["Sistema"], summary="Estado del servicio y de la base de datos")
def health():
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "error"
    return JSONResponse(status_code=200 if db == "ok" else 503, content={"estado": "ok" if db == "ok" else "degradado", "base_datos": db, "version": app.version})
