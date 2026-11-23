"""DTOs de la segunda ronda: base de conocimiento, respuestas rápidas, recurrentes, reportes programados, inventario y delegaciones."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.application.schemas.esquemas import Modelo
from app.domain.correos import normalizar_correos


# ------------------------------------------------------- base de conocimiento
class KbEntrada(BaseModel):
    titulo: str = Field(min_length=5, max_length=200)
    sintoma: str | None = Field(default=None, max_length=1000)
    solucion: str = Field(min_length=10)
    nota: str | None = Field(default=None, max_length=500)
    palabras_clave: str | None = Field(default=None, max_length=500)
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    estado: Literal["BORRADOR", "PUBLICADO", "ARCHIVADO"] = "BORRADOR"
    visibilidad: Literal["EXTERNO", "INTERNO"]   # obligatorio: lo elige quien escribe el artículo (35)
    ticket_origen_id: int | None = None
    articulo_relacionado_id: int | None = None


class KbResumen(Modelo):
    id: int
    titulo: str
    categoria_id: int | None
    categoria: str | None = None
    subcategoria: str | None = None
    estado: str
    visibilidad: str
    vistas: int
    util_pct: int | None
    tickets_evitados: int
    extracto: str | None = None


class KbSalida(KbResumen):
    sintoma: str | None
    solucion: str
    nota: str | None
    palabras_clave: str | None
    subcategoria_id: int | None
    ticket_origen_id: int | None
    ticket_origen_numero: str | None = None
    util_si: int
    util_no: int
    actualizado_por: str | None = None
    fecha_actualizacion: datetime | None
    fecha_creacion: datetime
    puede_editar: bool = False
    puede_publicar_externo: bool = False
    articulo_relacionado_id: int | None = None
    articulo_relacionado: str | None = None


class KbSugerirEntrada(BaseModel):
    texto: str = Field(max_length=6000)
    categoria_id: int | None = None
    subcategoria_id: int | None = None


class KbVotoEntrada(BaseModel):
    util: bool


class KbDesdeTicket(BaseModel):
    ticket_id: int


# ------------------------------------------------------------ respuestas rápidas
class RespuestaEntrada(BaseModel):
    atajo: str = Field(min_length=2, max_length=30, pattern=r"^/?[a-z0-9_\-]+$")
    titulo: str = Field(min_length=3, max_length=150)
    texto: str = Field(min_length=3, max_length=4000)
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    estado_destino: Literal["EN_PROCESO", "PENDIENTE_CLIENTE", "RESUELTO"] | None = None
    alcance: Literal["TODOS", "AREA", "PERSONAL"] = "TODOS"
    area_id: int | None = None
    activo: bool = True

    @field_validator("atajo")
    @classmethod
    def _atajo(cls, v: str) -> str:
        v = v.strip().lower()
        return v if v.startswith("/") else "/" + v


class RespuestaSalida(Modelo):
    id: int
    atajo: str
    titulo: str
    texto: str
    categoria_id: int | None
    subcategoria_id: int | None
    categoria: str | None = None
    subcategoria: str | None = None
    estado_destino: str | None
    alcance: str
    area_id: int | None
    area: str | None = None
    propietario_id: int | None
    propietario: str | None = None
    usos: int
    activo: bool
    puede_editar: bool = False


class RespuestaParaTicket(Modelo):
    id: int
    atajo: str
    titulo: str
    texto: str            # con los datos del ticket ya reemplazados
    estado_destino: str | None
    sugerida: bool        # de la subcategoría o categoría del ticket
    alcance: str
    usos: int


# ----------------------------------------------------------- tickets recurrentes
Frecuencia = Literal["DIARIA", "SEMANAL", "MENSUAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"]


class RecurrenteEntrada(BaseModel):
    nombre: str = Field(min_length=3, max_length=150)
    asunto: str = Field(min_length=5, max_length=200)
    descripcion: str = Field(min_length=10, max_length=4000)
    tareas: str | None = Field(default=None, max_length=4000)
    categoria_id: int
    subcategoria_id: int
    prioridad_id: int
    responsable_id: int | None = None
    solicitante_id: int | None = Field(default=None, description="Si se omite, figura quien crea la programación")
    frecuencia: Frecuencia
    dia_semana: int | None = Field(default=None, ge=1, le=7)
    dia_mes: int | None = Field(default=None, ge=-1, le=31)
    semana_mes: int | None = Field(default=None, ge=-1, le=4)
    hora: time = time(8, 30)
    desde: date
    hasta: date | None = None
    omitir_si_abierto: bool = True
    activo: bool = True


class RecurrenteSalida(Modelo):
    id: int
    nombre: str
    asunto: str
    descripcion: str
    tareas: str | None
    categoria_id: int
    subcategoria_id: int
    prioridad_id: int
    responsable_id: int | None
    solicitante_id: int
    categoria: str
    subcategoria: str
    prioridad: str
    responsable: str | None
    frecuencia: str
    dia_semana: int | None
    dia_mes: int | None
    semana_mes: int | None
    hora: time
    desde: date
    hasta: date | None
    omitir_si_abierto: bool
    activo: bool
    descripcion_frecuencia: str
    proxima_ejecucion: datetime | None
    ultima_ejecucion: datetime | None
    ultimo_ticket_id: int | None
    ultimo_ticket_numero: str | None = None
    ultimo_resultado: str | None


class VistaPreviaFechas(Modelo):
    fechas: list[str]               # UTC (ISO con sufijo Z)
    movidas: list[str]              # aviso por fecha movida por feriado/fin de semana (mismo orden; "" si no)


# ----------------------------------------------------------- reportes programados
SECCIONES = ("totales", "sla_area", "vencidos", "categorias", "satisfaccion", "comparacion", "responsables", "recurrentes")


class ReporteEntrada(BaseModel):
    nombre: str = Field(min_length=3, max_length=150)
    destinatarios: list[EmailStr] = Field(min_length=1, max_length=20)
    frecuencia: Literal["DIARIA", "SEMANAL", "MENSUAL"] = "SEMANAL"
    dia_semana: int | None = Field(default=1, ge=1, le=7)
    dia_mes: int | None = Field(default=None, ge=1, le=28)
    hora: time = time(8, 0)
    secciones: list[Literal["totales", "sla_area", "vencidos", "categorias", "satisfaccion", "comparacion", "responsables", "recurrentes"]] = Field(min_length=1)
    areas: list[int] | None = None
    adjuntar_excel: bool = True
    activo: bool = True

    @field_validator("destinatarios", mode="before")
    @classmethod
    def _dest(cls, v):
        return normalizar_correos(v) if isinstance(v, (list, str)) else v


class ReporteSalida(Modelo):
    id: int
    nombre: str
    destinatarios: list[str]
    frecuencia: str
    dia_semana: int | None
    dia_mes: int | None
    hora: time
    secciones: list[str]
    areas: list[int] | None
    adjuntar_excel: bool
    activo: bool
    proximo_envio: datetime | None
    ultimo_envio: datetime | None
    descripcion_frecuencia: str


class ReporteEnvioSalida(Modelo):
    id: int
    fecha: datetime
    periodo: str
    destinatarios: str
    es_prueba: bool
    estado: str | None = None


# ---------------------------------------------------------------- inventario
TipoEquipo = Literal["ESCRITORIO", "PORTATIL", "IMPRESORA", "RED", "TOKEN", "TELEFONO", "MONITOR", "SERVIDOR", "OTRO"]


class EquipoEntrada(BaseModel):
    codigo: str = Field(min_length=2, max_length=30)
    tipo: TipoEquipo
    marca_modelo: str = Field(min_length=2, max_length=150)
    serie: str | None = Field(default=None, max_length=80)
    usuario_id: int | None = None
    area_id: int | None = None
    compartido: bool = False
    ubicacion: str | None = Field(default=None, max_length=150)
    estado: Literal["EN_USO", "BODEGA", "REPARACION", "BAJA"] = "EN_USO"
    fecha_compra: date | None = None
    garantia_hasta: date | None = None
    sistema: str | None = Field(default=None, max_length=150)
    notas: str | None = Field(default=None, max_length=1000)

    @field_validator("codigo")
    @classmethod
    def _codigo(cls, v: str) -> str:
        return v.strip().upper()


class EquipoSalida(Modelo):
    id: int
    codigo: str
    tipo: str
    marca_modelo: str
    serie: str | None
    usuario_id: int | None
    usuario: str | None = None
    area_id: int | None
    area: str | None = None
    compartido: bool
    ubicacion: str | None
    estado: str
    fecha_compra: date | None
    garantia_hasta: date | None
    sistema: str | None
    notas: str | None
    fallas_12m: int = 0


class EquipoFalla(Modelo):
    ticket_id: int
    numero: str
    asunto: str
    estado: str
    fecha_creacion: datetime
    minutos_resolucion: int | None


class EquipoDetalle(EquipoSalida):
    historial: list[EquipoFalla]
    aviso: str | None = None


class EquipoOpcion(Modelo):
    id: int
    codigo: str
    tipo: str
    marca_modelo: str
    propio: bool
    compartido: bool
    fallas_12m: int


class ImportacionResultado(Modelo):
    creados: int
    actualizados: int
    errores: list[str]


# ---------------------------------------------------------------- delegaciones
class DelegacionEntrada(BaseModel):
    activa: bool
    areas: list[int] | None = Field(default=None, description="Áreas de las personas a cuyo nombre puede crear; vacío = todas")
    hasta: date | None = None


class DelegacionSalida(Modelo):
    activa: bool
    areas: list[int] | None = None
    hasta: date | None = None
    otorgado_por: str | None = None
    fecha: datetime | None = None


class PersonaEnNombre(Modelo):
    id: int
    nombre: str
    correo: str
    area: str | None = None
    cargo: str | None = None
