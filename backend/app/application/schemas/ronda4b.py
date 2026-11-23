"""Esquemas de la cuarta ronda, parte 2: problemas (30), panel gerencial (32), control de tiempo (31) y proveedores (33)."""
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
