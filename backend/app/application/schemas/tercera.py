"""Esquemas de la tercera ronda: aprobaciones, vínculos, acciones en lote, traspaso, avisos generales y seguimiento."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoAprobador = Literal["JEFE_DIRECTO", "SUPERVISOR_CATEGORIA", "PERSONA"]


# ============================================================ 21 aprobaciones
class ReglaAprobacionEntrada(BaseModel):
    categoria_id: int
    subcategoria_id: int | None = None
    nivel1_tipo: TipoAprobador = "JEFE_DIRECTO"
    nivel1_usuario_id: int | None = None
    nivel2_tipo: TipoAprobador | None = None
    nivel2_usuario_id: int | None = None
    recordar_horas: int = Field(default=4, ge=0, le=200)
    escalar_horas: int | None = Field(default=None, ge=1, le=400)
    escalar_a_id: int | None = None
    usar_reemplazo: bool = True
    auto_si_aprobador: bool = True
    activo: bool = True


class RespuestaAprobacion(BaseModel):
    aprobar: bool
    comentario: str | None = Field(default=None, max_length=1000)


# ============================================================ 22 vínculos
class VinculoEntrada(BaseModel):
    relacionado: str = Field(min_length=1, max_length=30, description="Número (ADU-2026-000123) o id del otro ticket")
    tipo: Literal["RELACIONADO", "BLOQUEADO_POR"] = "RELACIONADO"


class UnirEntrada(BaseModel):
    principal_id: int
    duplicados: list[int] = Field(min_length=1, max_length=20)
    mensaje: str | None = Field(default=None, max_length=1000)
    avisar: bool = True
    mantener_prioridad: bool = False


# ============================================================ 23 lote
class LoteEntrada(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)
    accion: Literal["REASIGNAR", "PRIORIDAD", "ESTADO", "CATEGORIA", "NOTA"]
    responsable_id: int | None = None
    prioridad_id: int | None = None
    estado: Literal["EN_PROCESO", "PENDIENTE_CLIENTE", "RESUELTO", "CERRADO", "CANCELADO"] | None = None
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    texto: str | None = Field(default=None, max_length=4000, description="Nota interna o comentario del cambio de estado")
    motivo: str | None = Field(default=None, max_length=500)


class LoteResultado(BaseModel):
    ok: list[str]
    sin_cambio: list[str] = []
    errores: list[dict]


class TraspasoEntrada(BaseModel):
    modo: Literal["UNO", "EQUILIBRADO", "COLA"] = "EQUILIBRADO"
    destinos: list[int] = Field(default_factory=list, max_length=30)
    asignaciones: dict[int, int] = Field(default_factory=dict, description="Ajustes manuales: ticket_id → analista")
    recurrentes_a_id: int | None = Field(default=None, description="A quién pasan sus tickets recurrentes (None = asignación automática)")
    traspasar_recurrentes: bool = True
    aprobaciones_a_id: int | None = Field(default=None, description="A quién pasan sus aprobaciones pendientes (None = su jefe directo)")
    traspasar_aprobaciones: bool = True
    desactivar: bool = False
    motivo: str = Field(min_length=5, max_length=300)
    avisar: bool = True


# ============================================================ 24 avisos
EstadoAviso = Literal["INVESTIGANDO", "IDENTIFICADO", "MONITOREANDO", "RESUELTO"]


class AvisoEntrada(BaseModel):
    titulo: str = Field(min_length=5, max_length=200)
    mensaje: str = Field(min_length=5, max_length=1000)
    sistema: str = Field(min_length=2, max_length=100)
    palabras_clave: str | None = Field(default=None, max_length=500)
    area_ids: list[int] = Field(default_factory=list, description="Vacío = se muestra a todos")
    mostrar_publico: bool = False
    ticket_maestro_id: int | None = None
    ticket_maestro: str | None = Field(default=None, max_length=30, description="Número del ticket maestro (alternativa a ticket_maestro_id)")
    proxima_novedad: str | None = Field(default=None, max_length=100)
    inicio: datetime | None = Field(default=None, description="Si la caída empezó antes de publicar el aviso (UTC)")


class AvisoActualizacionEntrada(BaseModel):
    estado: EstadoAviso
    texto: str = Field(min_length=3, max_length=1000)
    proxima_novedad: str | None = Field(default=None, max_length=100)
    avisar: bool = True
    resolver_tickets: bool = Field(default=True, description="Al marcar RESUELTO: resolver también los tickets vinculados")


class AfectaEntrada(BaseModel):
    comentario: str | None = Field(default=None, max_length=500)


# ============================================================ 20 seguimiento
class ReenviarSeguimiento(BaseModel):
    numero: str = Field(min_length=5, max_length=30)
    correo: str = Field(min_length=5, max_length=150)
