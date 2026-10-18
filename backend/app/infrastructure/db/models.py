"""Modelos ORM. Reflejan exactamente database/01_tablas.sql (fuente de verdad del esquema)."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Table,
    Column,
    Time,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utcnow
from app.infrastructure.db.session import Base

# BIGINT IDENTITY en SQL Server, INTEGER autoincremental en SQLite (pruebas)
BigId = BigInteger().with_variant(Integer, "sqlite")


rol_permisos = Table(
    "rol_permisos",
    Base.metadata,
    Column("rol_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------- seguridad
class Rol(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(100))
    descripcion: Mapped[str | None] = mapped_column(Unicode(300))
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    permisos: Mapped[list[Permiso]] = relationship(secondary=rol_permisos, lazy="selectin")


class Permiso(Base):
    __tablename__ = "permisos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    modulo: Mapped[str] = mapped_column(Unicode(60))
    descripcion: Mapped[str] = mapped_column(Unicode(300))


class Area(Base):
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(100), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(150))
    correo: Mapped[str] = mapped_column(Unicode(150), unique=True)
    usuario_ad: Mapped[str | None] = mapped_column(Unicode(100))
    origen_autenticacion: Mapped[str] = mapped_column(String(10), default="LOCAL")
    clave_hash: Mapped[str | None] = mapped_column(String(100))
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=False)
    cargo: Mapped[str | None] = mapped_column(Unicode(100))
    telefono: Mapped[str | None] = mapped_column(Unicode(30))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)

    rol: Mapped[Rol] = relationship(lazy="joined")
    area: Mapped[Area | None] = relationship(lazy="joined")

    @property
    def permisos(self) -> set[str]:
        return {p.codigo for p in self.rol.permisos}

    def tiene(self, permiso: str) -> bool:
        return permiso in self.permisos


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    familia: Mapped[str] = mapped_column(CHAR(32))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime)
    revocado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_revocacion: Mapped[datetime | None] = mapped_column(DateTime)
    reemplazado_por: Mapped[int | None] = mapped_column(BigId)
    ip: Mapped[str | None] = mapped_column(String(45))
    equipo: Mapped[str | None] = mapped_column(Unicode(300))


# ----------------------------------------------------------------- catálogo
class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruc: Mapped[str | None] = mapped_column(String(13), unique=True)
    razon_social: Mapped[str] = mapped_column(Unicode(200))
    nombre_comercial: Mapped[str | None] = mapped_column(Unicode(200))
    correo: Mapped[str | None] = mapped_column(Unicode(150))
    telefono: Mapped[str | None] = mapped_column(Unicode(30))
    es_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)


class CategoriaResponsable(Base):
    __tablename__ = "categoria_responsables"
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id", ondelete="CASCADE"), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    descripcion: Mapped[str | None] = mapped_column(Unicode(500))
    palabras_clave: Mapped[str | None] = mapped_column(Unicode(1000))
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    modo_asignacion: Mapped[str] = mapped_column(String(15), default="PRINCIPAL")
    color: Mapped[str | None] = mapped_column(CHAR(7))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)

    supervisor: Mapped[Usuario | None] = relationship(lazy="joined")
    subcategorias: Mapped[list[Subcategoria]] = relationship(back_populates="categoria", lazy="selectin")
    responsables: Mapped[list[CategoriaResponsable]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class Subcategoria(Base):
    __tablename__ = "subcategorias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    nombre: Mapped[str] = mapped_column(Unicode(120))
    palabras_clave: Mapped[str | None] = mapped_column(Unicode(1000))
    respuesta_plantilla: Mapped[str | None] = mapped_column(Unicode(2000))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria: Mapped[Categoria] = relationship(back_populates="subcategorias")


# ---------------------------------------------------------------------- SLA
class Prioridad(Base):
    __tablename__ = "prioridades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(15), unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(50))
    orden: Mapped[int] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(CHAR(7))
    sla_respuesta_min: Mapped[int] = mapped_column(Integer)
    sla_resolucion_min: Mapped[int] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class SlaPolitica(Base):
    __tablename__ = "sla_politicas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    prioridad_id: Mapped[int] = mapped_column(ForeignKey("prioridades.id"))
    sla_respuesta_min: Mapped[int] = mapped_column(Integer)
    sla_resolucion_min: Mapped[int] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class HorarioLaboral(Base):
    __tablename__ = "horarios_laborales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(100))
    zona_horaria: Mapped[str] = mapped_column(String(50), default="America/Guayaquil")
    es_predeterminado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    tramos: Mapped[list[HorarioTramo]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class HorarioTramo(Base):
    __tablename__ = "horario_tramos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horario_id: Mapped[int] = mapped_column(ForeignKey("horarios_laborales.id", ondelete="CASCADE"))
    dia_semana: Mapped[int] = mapped_column(SmallInteger)   # 1 = lunes … 7 = domingo
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)


class CalendarioExcepcion(Base):
    __tablename__ = "calendario_excepciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horario_id: Mapped[int | None] = mapped_column(ForeignKey("horarios_laborales.id"))
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(20))
    hora_inicio: Mapped[time | None] = mapped_column(Time)
    hora_fin: Mapped[time | None] = mapped_column(Time)
    descripcion: Mapped[str] = mapped_column(Unicode(200))


# ------------------------------------------------------------------ tickets
class EstadoTicket(Base):
    __tablename__ = "estados"
    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(50))
    orden: Mapped[int] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(CHAR(7))
    pausa_sla: Mapped[bool] = mapped_column(Boolean)
    es_final: Mapped[bool] = mapped_column(Boolean)


class TicketSecuencia(Base):
    __tablename__ = "ticket_secuencias"
    anio: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ultimo: Mapped[int] = mapped_column(Integer)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    asunto: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str] = mapped_column(UnicodeText)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    solicitante_nombre: Mapped[str] = mapped_column(Unicode(150))
    solicitante_cargo: Mapped[str | None] = mapped_column(Unicode(100))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    correo: Mapped[str] = mapped_column(Unicode(150))
    telefono: Mapped[str | None] = mapped_column(Unicode(30))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategorias.id"))
    prioridad_id: Mapped[int] = mapped_column(ForeignKey("prioridades.id"))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    estado: Mapped[str] = mapped_column(ForeignKey("estados.codigo"))
    canal: Mapped[str] = mapped_column(String(20), default="PORTAL")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_asignacion: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_primera_respuesta: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    sla_respuesta_min: Mapped[int] = mapped_column(Integer)
    sla_resolucion_min: Mapped[int] = mapped_column(Integer)
    sla_respuesta_vence: Mapped[datetime] = mapped_column(DateTime)
    sla_resolucion_vence: Mapped[datetime] = mapped_column(DateTime)
    sla_minutos_pausa: Mapped[int] = mapped_column(Integer, default=0)
    sla_minutos_extension: Mapped[int] = mapped_column(Integer, default=0)
    sla_pausa_desde: Mapped[datetime | None] = mapped_column(DateTime)
    sla_minutos_consumidos: Mapped[int] = mapped_column(Integer, default=0)
    sla_consumido_pct: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    sla_respuesta_cumplido: Mapped[bool | None] = mapped_column(Boolean)
    sla_resolucion_cumplido: Mapped[bool | None] = mapped_column(Boolean)
    sla_incumplido: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_excluido: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_nivel_alerta: Mapped[int] = mapped_column(SmallInteger, default=0)
    minutos_respuesta: Mapped[int | None] = mapped_column(Integer)
    minutos_resolucion: Mapped[int | None] = mapped_column(Integer)
    reaperturas: Mapped[int] = mapped_column(Integer, default=0)
    resumen_ia: Mapped[str | None] = mapped_column(Unicode(1000))
    riesgo_ia: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    version: Mapped[int] = mapped_column(Integer, default=1)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    eliminado_por: Mapped[int | None] = mapped_column(Integer)
    fecha_eliminacion: Mapped[datetime | None] = mapped_column(DateTime)

    # Las tablas con triggers en SQL Server no admiten OUTPUT sin INTO: se usa SCOPE_IDENTITY().
    __table_args__ = {"implicit_returning": False}
    __mapper_args__ = {"version_id_col": version}

    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id], lazy="joined")
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")
    categoria: Mapped[Categoria] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria] = relationship(lazy="joined")
    prioridad: Mapped[Prioridad] = relationship(lazy="joined")
    cliente: Mapped[Cliente | None] = relationship(lazy="joined")
    area: Mapped[Area | None] = relationship(lazy="joined")
    estado_rel: Mapped[EstadoTicket] = relationship(lazy="joined")

    @property
    def cumplimiento_sla(self) -> str:
        if self.sla_excluido:
            return "EXCLUIDO"
        if self.sla_incumplido:
            return "INCUMPLIDO"
        if self.sla_resolucion_cumplido:
            return "CUMPLIDO"
        return "EN_CURSO"


class TicketComentario(Base):
    __tablename__ = "ticket_comentarios"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(UnicodeText)
    es_interno: Mapped[bool] = mapped_column(Boolean, default=False)
    tipo: Mapped[str] = mapped_column(String(20), default="COMENTARIO")
    minutos_invertidos: Mapped[int | None] = mapped_column(Integer)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class TicketAdjunto(Base):
    __tablename__ = "ticket_adjuntos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    comentario_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_comentarios.id"))
    nombre_original: Mapped[str] = mapped_column(Unicode(255))
    ruta_almacenamiento: Mapped[str] = mapped_column(Unicode(400))
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamano_bytes: Mapped[int] = mapped_column(BigInteger)
    hash_sha256: Mapped[str] = mapped_column(CHAR(64))
    subido_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class TicketHistorial(Base):
    __tablename__ = "ticket_historial"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(String(40))
    campo: Mapped[str | None] = mapped_column(String(60))
    valor_anterior: Mapped[str | None] = mapped_column(Unicode(500))
    valor_nuevo: Mapped[str | None] = mapped_column(Unicode(500))
    detalle: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class TicketAsignacion(Base):
    __tablename__ = "ticket_asignaciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    responsable_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    responsable_nuevo_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    asignado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(Unicode(500))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TicketEscalamiento(Base):
    __tablename__ = "ticket_escalamientos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    nivel: Mapped[int] = mapped_column(SmallInteger)
    tipo: Mapped[str] = mapped_column(String(10))
    escalado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    escalado_a: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str | None] = mapped_column(Unicode(500))
    sla_consumido_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SlaPausa(Base):
    __tablename__ = "sla_pausas"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    estado: Mapped[str] = mapped_column(String(20))
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fin: Mapped[datetime | None] = mapped_column(DateTime)
    minutos_laborables: Mapped[int | None] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


class SlaExcepcion(Base):
    __tablename__ = "sla_excepciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(15))
    minutos: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(Unicode(500))
    aprobado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SlaIncumplimiento(Base):
    __tablename__ = "sla_incumplimientos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(15))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    prioridad_id: Mapped[int] = mapped_column(ForeignKey("prioridades.id"))
    fecha_vencimiento: Mapped[datetime] = mapped_column(DateTime)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    justificacion: Mapped[str | None] = mapped_column(Unicode(1000))


# ---------------------------------------------------------- notificaciones
class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(30))
    severidad: Mapped[str] = mapped_column(String(10), default="INFO")
    titulo: Mapped[str] = mapped_column(Unicode(200))
    mensaje: Mapped[str] = mapped_column(Unicode(1000))
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_lectura: Mapped[datetime | None] = mapped_column(DateTime)


class PlantillaCorreo(Base):
    __tablename__ = "plantillas_correo"
    codigo: Mapped[str] = mapped_column(String(30), primary_key=True)
    asunto: Mapped[str] = mapped_column(Unicode(200))
    cuerpo_html: Mapped[str] = mapped_column(UnicodeText)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ColaCorreo(Base):
    __tablename__ = "cola_correos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    para: Mapped[str] = mapped_column(Unicode(500))
    cc: Mapped[str | None] = mapped_column(Unicode(500))
    asunto: Mapped[str] = mapped_column(Unicode(250))
    cuerpo_html: Mapped[str] = mapped_column(UnicodeText)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    plantilla: Mapped[str | None] = mapped_column(String(30))
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Unicode(1000))
    proximo_intento: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------- auditoría
class Auditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = {"implicit_returning": False}
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_correo: Mapped[str | None] = mapped_column(Unicode(150))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    accion: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str | None] = mapped_column(String(40))
    entidad_id: Mapped[str | None] = mapped_column(String(40))
    detalle: Mapped[str | None] = mapped_column(UnicodeText)
    ip: Mapped[str | None] = mapped_column(String(45))
    equipo: Mapped[str | None] = mapped_column(Unicode(300))
    resultado: Mapped[str] = mapped_column(String(10), default="OK")


# ------------------------------------------------------------- IA / sistema
class IaSugerencia(Base):
    __tablename__ = "ia_sugerencias"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    valor: Mapped[str] = mapped_column(UnicodeText)
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    proveedor: Mapped[str] = mapped_column(String(20))
    aceptada: Mapped[bool | None] = mapped_column(Boolean)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Configuracion(Base):
    __tablename__ = "configuracion"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Unicode(1000))
    descripcion: Mapped[str | None] = mapped_column(Unicode(300))
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actualizado_por: Mapped[int | None] = mapped_column(Integer)


class BloqueoProceso(Base):
    __tablename__ = "bloqueos_proceso"
    nombre: Mapped[str] = mapped_column(String(50), primary_key=True)
    propietario: Mapped[str] = mapped_column(String(100))
    expira: Mapped[datetime] = mapped_column(DateTime)
