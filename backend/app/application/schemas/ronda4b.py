"""Esquemas de la cuarta ronda, parte 2: problemas (30), panel gerencial (32), control de tiempo (31) y proveedores (33)."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ============================================================ 30 problemas
class ProblemaEntrada(BaseModel):
    titulo: str = Field(min_length=5, max_length=200)
    descripcion: str | None = Field(None, max_length=4000)
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    responsable_id: int | None = None
    palabras_clave: str | None = Field(None, max_length=500)
    tickets: list[int] = Field(default_factory=list, max_length=200)
    desde_patron: bool = False


class Porque(BaseModel):
    pregunta: str = Field("", max_length=300)
    respuesta: str = Field("", max_length=500)


class ProblemaEdicion(BaseModel):
    titulo: str = Field(min_length=5, max_length=200)
    descripcion: str | None = Field(None, max_length=4000)
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    responsable_id: int | None = None
    palabras_clave: str | None = Field(None, max_length=500)
    porques: list[Porque] = Field(default_factory=list, max_length=7)
    causa_raiz: str | None = Field(None, max_length=1000)
    solucion_definitiva: str | None = Field(None, max_length=1000)
    solucion_temporal: str | None = Field(None, max_length=2000)
    cambio_id: int | None = None


class ProblemaEstado(BaseModel):
    estado: Literal["DETECTADO", "EN_ANALISIS", "ERROR_CONOCIDO", "SOLUCION_EN_CAMBIO", "CERRADO"]
    nota: str | None = Field(None, max_length=1000)
    avisar: bool = True     # al cerrar, avisar a los solicitantes de los incidentes


class ProblemaVincular(BaseModel):
    ticket: str = Field(min_length=1, max_length=30, description="Número ADU-… o id del ticket")


class AplicarSolucion(BaseModel):
    responder: bool = True


class IgnorarPatron(BaseModel):
    firma: str = Field(min_length=10, max_length=64)


# ============================================================ 32 panel gerencial
SECCIONES_PANEL = ("indicadores", "tendencia", "sla_area", "satisfaccion", "problemas", "cambios", "proveedores", "horas")


class PanelEnvioEntrada(BaseModel):
    activo: bool = False
    destinatarios: list[EmailStr] = Field(default_factory=list, max_length=20)
    cuando: Literal["PRIMER_HABIL", "DIA_1"] = "PRIMER_HABIL"
    hora: str = Field("08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    secciones: list[Literal["indicadores", "tendencia", "sla_area", "satisfaccion", "problemas", "cambios", "proveedores", "horas"]] = \
        Field(default_factory=lambda: list(SECCIONES_PANEL))
    comentario: str | None = Field(None, max_length=800)


# ------------------------------------------------------------------ 31 Control de tiempo
class TiempoIniciar(BaseModel):
    actividad: str = Field(default="", max_length=200)


class TiempoManual(BaseModel):
    actividad: str = Field(min_length=2, max_length=200)
    minutos: int = Field(ge=1, le=1440)
    fecha: date | None = None


class TiempoEditar(BaseModel):
    actividad: str | None = Field(default=None, max_length=200)
    minutos: int | None = Field(default=None, ge=1, le=1440)


class TiempoAjustes(BaseModel):
    estimado_min: int | None = Field(default=None, ge=0, le=100000)
    facturable: bool | None = None


# ------------------------------------------------------------------ 33 Proveedores
class ProveedorEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    servicio: str = Field(min_length=2, max_length=150)
    telefono: str | None = Field(default=None, max_length=60)
    correo: EmailStr | None = None
    correos_copia: list[EmailStr] = Field(default_factory=list, max_length=10)
    portal: str | None = Field(default=None, max_length=200)
    contacto: str | None = Field(default=None, max_length=150)
    contrato_numero: str | None = Field(default=None, max_length=60)
    contrato_vence: date | None = None
    contrato_detalle: str | None = Field(default=None, max_length=300)
    atencion_24x7: bool = False
    plazo_horas: int = Field(default=8, ge=1, le=24 * 60)
    valor_mensual: Decimal | None = Field(default=None, ge=0, le=10_000_000)
    multa_pct_hora: Decimal | None = Field(default=None, ge=0, le=100)
    subcategorias: list[int] = Field(default_factory=list, max_length=40)
    notas: str | None = Field(default=None, max_length=1000)
    activo: bool = True


class EscalarProveedor(BaseModel):
    proveedor_id: int
    numero_caso: str | None = Field(default=None, max_length=60)
    reporte: str = Field(min_length=5, max_length=2000)
    medio: str | None = Field(default=None, max_length=100)
    contacto: str | None = Field(default=None, max_length=150)
    enviar_correo: bool = False


class ResolverCaso(BaseModel):
    solucion: str | None = Field(default=None, max_length=1000)


# ------------------------------------------------------------------ 34 Visualizadores
class VisualizadorEntrada(BaseModel):
    usuario_id: int
    avisos_correo: Literal["TODO", "ESTADO", "NINGUNO"] = "ESTADO"


class VisualizadorAvisos(BaseModel):
    avisos_correo: Literal["TODO", "ESTADO", "NINGUNO"]
