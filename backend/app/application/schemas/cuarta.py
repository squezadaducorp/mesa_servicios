"""Esquemas de la cuarta ronda: catálogo de servicios (26) y gestión de cambios (27)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoCampo = Literal["texto", "parrafo", "fecha", "numero", "cedula", "correo", "telefono", "area", "usuario", "lista"]


# ============================================================ 26 catálogo
class CampoServicio(BaseModel):
    clave: str = Field("", max_length=40)
    etiqueta: str = Field(min_length=1, max_length=100)
    tipo: TipoCampo = "texto"
    requerido: bool = True
    opciones: list[str] = Field(default_factory=list, max_length=40)
    ancho: int = Field(2, ge=1, le=4)              # columnas de 4
    aprobador: bool = False                         # campo «usuario» que indica quién aprueba (p. ej. jefe de quien ingresa)
    ayuda: str | None = Field(None, max_length=200)


class OpcionServicio(BaseModel):
    clave: str = Field("", max_length=40)
    etiqueta: str = Field(min_length=1, max_length=100)
    tarea: str | None = Field(None, max_length=200)  # título de la tarea que genera (por defecto, la etiqueta)
    responsable_id: int | None = None                # None = el responsable del ticket
    marcado: bool = False                            # marcada por defecto en el formulario
    siempre: bool = False                            # tarea fija: no se muestra como casilla
    aviso: str | None = Field(None, max_length=300)  # se muestra al marcarla


class ServicioEntrada(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str = Field(min_length=3, max_length=400)
    icono: str = Field("servicio", max_length=30)
    grupo: str = Field("Accesos", min_length=2, max_length=30)
    categoria_id: int
    subcategoria_id: int
    plazo_horas: int = Field(8, ge=0, le=2000)
    plazo_texto: str | None = Field(None, max_length=40)
    requiere_aprobacion: bool = False
    lo_pide: str | None = Field(None, max_length=100)
    titulo_campos: str | None = Field(None, max_length=150)
    titulo_opciones: str | None = Field(None, max_length=150)
    aviso: str | None = Field(None, max_length=500)
    campos: list[CampoServicio] = Field(default_factory=list, max_length=30)
    opciones: list[OpcionServicio] = Field(default_factory=list, max_length=30)
    orden: int = 0
    activo: bool = True


class SolicitudServicio(BaseModel):
    respuestas: dict[str, str | int | None] = Field(default_factory=dict)
    opciones: list[str] = Field(default_factory=list, max_length=30)
    observaciones: str | None = Field(None, max_length=2000)
    solicitante_id: int | None = None
    en_nombre_motivo: str | None = Field(None, max_length=300)


class TareaMarcar(BaseModel):
    lista: bool


# ============================================================ 27 cambios
TipoSolicitud = Literal["ERROR", "MEJORA", "NUEVA", "CATALOGO", "ACCESO", "OTRO"]
Nivel = Literal["BAJO", "MEDIO", "ALTO"]
Probabilidad = Literal["BAJA", "MEDIA", "ALTA"]
Prioridad = Literal["ALTA", "MEDIA", "BAJA"]


class CambioEntrada(BaseModel):
    formato: Literal["MESA", "GENERAL"] = "MESA"
    titulo: str = Field(min_length=5, max_length=200)
    telefono: str | None = Field(None, max_length=30)
    tipo_solicitud: TipoSolicitud
    aplicacion: str | None = Field(None, max_length=150)
    partes: list[str] = Field(default_factory=list, max_length=15)
    pantalla: str | None = Field(None, max_length=200)
    desde_donde: Literal["COMPUTADORA", "CELULAR", "AMBOS"] | None = None
    ticket_relacionado: str | None = Field(None, max_length=200)
    situacion_actual: str = Field(min_length=5, max_length=8000)
    situacion_deseada: str = Field(min_length=5, max_length=8000)
    justificacion: str | None = Field(None, max_length=8000)
    beneficiados: Literal["SOLO_YO", "MI_AREA", "VARIAS_AREAS", "TODA_EMPRESA"] | None = None
    prioridad_sugerida: Prioridad = "MEDIA"


class EvaluacionEntrada(BaseModel):
    """Sección 7 · uso exclusivo de TI."""
    clasificacion: Literal["CORRECCION", "MEJORA", "NUEVA", "CONFIGURACION", "PERMISOS"]
    tipo_cambio: Literal["ESTANDAR", "NORMAL", "EMERGENCIA"]
    impacto: Nivel
    probabilidad: Probabilidad
    esfuerzo: Literal["MENOS_1", "1_3", "MAS_3"] | None = None
    prioridad_ti: Prioridad = "MEDIA"
    evaluacion: str | None = Field(None, max_length=8000)
    plan_implementacion: str | None = Field(None, max_length=8000)
    plan_reversion: str | None = Field(None, max_length=8000)
    responsable_id: int | None = None
    ventana_inicio: datetime | None = None
    ventana_fin: datetime | None = None
    decision: Literal["APROBAR", "RECHAZAR", "EN_ESPERA"] = "APROBAR"
    comentario: str | None = Field(None, max_length=1000)


class VentanaEntrada(BaseModel):
    ventana_inicio: datetime
    ventana_fin: datetime
    comentario: str | None = Field(None, max_length=500)


class RespuestaCambio(BaseModel):
    aprobar: bool
    comentario: str | None = Field(None, max_length=1000)


class ImplementarEntrada(BaseModel):
    version_ref: str | None = Field(None, max_length=100)
    comentario: str | None = Field(None, max_length=1000)


class RevisionEntrada(BaseModel):
    resultado: Literal["EXITOSO", "CON_PROBLEMAS", "REVERTIDO"]
    probado_solicitante: bool | None = None
    informado: bool = True
    observaciones: str | None = Field(None, max_length=4000)


class CongelamientoEntrada(BaseModel):
    titulo: str = Field(min_length=3, max_length=150)
    inicio: datetime
    fin: datetime
    motivo: str | None = Field(None, max_length=500)
