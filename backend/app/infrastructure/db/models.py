"""Modelos ORM. Reflejan exactamente database/01_tablas.sql y 07_microsoft365.sql (fuente de verdad del esquema)."""
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
    UniqueConstraint,
    UnicodeText,
    LargeBinary,
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
    entra_oid: Mapped[str | None] = mapped_column(String(36))   # objectId del usuario en Entra ID
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
    # Verificación en dos pasos (28)
    dosf_metodo: Mapped[str | None] = mapped_column(String(10))        # APP (Authenticator) | CORREO; NULL = sin activar
    dosf_secreto: Mapped[str | None] = mapped_column(String(300))      # clave TOTP cifrada
    dosf_pendiente: Mapped[str | None] = mapped_column(String(300))    # clave TOTP cifrada mientras se escanea el QR
    dosf_codigos: Mapped[str | None] = mapped_column(Unicode(1500))    # hash de los códigos de respaldo sin usar (JSON)
    dosf_fecha: Mapped[datetime | None] = mapped_column(DateTime)
    dosf_ultimo_paso: Mapped[int | None] = mapped_column(BigInteger)   # último periodo TOTP aceptado (no se reutiliza)
    dosf_exigido_desde: Mapped[datetime | None] = mapped_column(DateTime)
    equipo_ti: Mapped[bool] = mapped_column(Boolean, default=False)   # ve artículos internos y escribe en la base de conocimiento (35)

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
    correos_copia: Mapped[str | None] = mapped_column(Unicode(500))   # se copian a cada ticket nuevo del cliente
    dominios: Mapped[str | None] = mapped_column(Unicode(300))        # quien escribe desde estos dominios queda con este cliente
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
    correos_copia: Mapped[str | None] = mapped_column(Unicode(500))   # se copian a cada ticket nuevo de la categoría
    visualizadores: Mapped[str | None] = mapped_column(String(300))   # ids de usuarios que siguen cada ticket nuevo (34)
    pide_equipo: Mapped[bool] = mapped_column(Boolean, default=False)            # muestra «Equipo afectado» al crear el ticket
    restringida_en_nombre: Mapped[bool] = mapped_column(Boolean, default=False)  # no se puede pedir en nombre de otra persona
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
    sla_aviso_respuesta: Mapped[bool] = mapped_column(Boolean, default=False)   # aviso previo de 1.ª respuesta ya enviado
    minutos_respuesta: Mapped[int | None] = mapped_column(Integer)
    minutos_resolucion: Mapped[int | None] = mapped_column(Integer)
    reaperturas: Mapped[int] = mapped_column(Integer, default=0)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"))
    recurrente_id: Mapped[int | None] = mapped_column(ForeignKey("tickets_recurrentes.id"))
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))   # quien lo registró en nombre del solicitante
    en_nombre_motivo: Mapped[str | None] = mapped_column(Unicode(300))
    resumen_ia: Mapped[str | None] = mapped_column(Unicode(1000))
    riesgo_ia: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tiempo_estimado_min: Mapped[int | None] = mapped_column(Integer)   # control de tiempo (31)
    facturable: Mapped[bool] = mapped_column(Boolean, default=False)
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
    creado_por: Mapped[Usuario | None] = relationship(foreign_keys=[creado_por_id], lazy="joined")
    equipo: Mapped[Equipo | None] = relationship(lazy="joined")

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
    copia_a: Mapped[str | None] = mapped_column(Unicode(500))   # correos que recibieron este comentario en copia
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class TicketCopia(Base):
    """Personas en copia del ticket: reciben por correo las respuestas y el cierre que se envían al solicitante."""
    __tablename__ = "ticket_copias"
    __table_args__ = (UniqueConstraint("ticket_id", "correo", name="ux_ticket_copias"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    correo: Mapped[str] = mapped_column(Unicode(150))
    origen: Mapped[str] = mapped_column(String(12), default="MANUAL")   # MANUAL | CATEGORIA | CLIENTE | CORREO
    agregado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


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


class TicketEncuesta(Base):
    """Encuesta de satisfacción del solicitante (una por ticket)."""
    __tablename__ = "ticket_encuestas"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True)
    calificacion: Mapped[int] = mapped_column(SmallInteger)   # 1 a 5
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))   # NULL si respondió desde el correo sin sesión
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    origen: Mapped[str] = mapped_column(String(10), default="PORTAL")   # PORTAL | CORREO
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_comentario: Mapped[datetime | None] = mapped_column(DateTime)
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")


class UsuarioAusencia(Base):
    """Vacaciones, permisos y otras ausencias: los tickets pasan al reemplazo mientras dure."""
    __tablename__ = "usuario_ausencias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    reemplazo_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str] = mapped_column(String(15), default="VACACIONES")   # VACACIONES | PERMISO | ENFERMEDAD | CAPACITACION | OTRO
    desde: Mapped[datetime] = mapped_column(DateTime)
    hasta: Mapped[datetime] = mapped_column(DateTime)
    pasar_abiertos: Mapped[bool] = mapped_column(Boolean, default=True)
    devolver: Mapped[bool] = mapped_column(Boolean, default=True)
    avisar_solicitantes: Mapped[bool] = mapped_column(Boolean, default=True)
    estado: Mapped[str] = mapped_column(String(12), default="PROGRAMADA")   # PROGRAMADA | ACTIVA | FINALIZADA | CANCELADA
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_inicio_real: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_fin_real: Mapped[datetime | None] = mapped_column(DateTime)
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")
    reemplazo: Mapped[Usuario] = relationship(foreign_keys=[reemplazo_id], lazy="joined")


class AusenciaTicket(Base):
    """Tickets que se pasaron al reemplazo (para devolverlos al terminar la ausencia)."""
    __tablename__ = "ausencia_tickets"
    ausencia_id: Mapped[int] = mapped_column(ForeignKey("usuario_ausencias.id", ondelete="CASCADE"), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    devuelto: Mapped[bool] = mapped_column(Boolean, default=False)


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
    adjunto_nombre: Mapped[str | None] = mapped_column(Unicode(150))
    adjunto: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)


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


# ------------------------------------------------------------ Microsoft 365
class CorreoEntrante(Base):
    """Cada mensaje del buzón compartido procesado una sola vez (idempotencia y trazabilidad)."""
    __tablename__ = "correos_entrantes"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(300), unique=True)   # internetMessageId
    graph_id: Mapped[str | None] = mapped_column(String(300))
    remitente: Mapped[str] = mapped_column(Unicode(150))
    asunto: Mapped[str] = mapped_column(Unicode(250))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    resultado: Mapped[str] = mapped_column(String(20))                 # CREADO | ACTUALIZADO | IGNORADO | ERROR
    detalle: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha_recepcion: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_proceso: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TeamsCanal(Base):
    """Canal de Teams vinculado con el comando «vincular» del bot. categoria_id NULL = canal general de la mesa."""
    __tablename__ = "teams_canales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(150))
    conversation_id: Mapped[str] = mapped_column(String(300), unique=True)
    service_url: Mapped[str] = mapped_column(String(300))
    team_id: Mapped[str | None] = mapped_column(String(300))
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    vinculado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    categoria: Mapped[Categoria | None] = relationship(lazy="joined")


class ColaTeams(Base):
    """Avisos pendientes de publicar en Teams (los envía el worker, con reintentos)."""
    __tablename__ = "cola_teams"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    evento: Mapped[str] = mapped_column(String(30))
    detalle: Mapped[str | None] = mapped_column(Unicode(500))
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Unicode(1000))
    proximo_intento: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime)


# ------------------------------------------------------- segunda ronda (11)
class KbArticulo(Base):
    """Artículo de la base de conocimiento: se sugiere al crear un ticket."""
    __tablename__ = "kb_articulos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(200))
    sintoma: Mapped[str | None] = mapped_column(Unicode(1000))
    solucion: Mapped[str] = mapped_column(UnicodeText)
    nota: Mapped[str | None] = mapped_column(Unicode(500))
    palabras_clave: Mapped[str | None] = mapped_column(Unicode(500))
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int | None] = mapped_column(ForeignKey("subcategorias.id"))
    estado: Mapped[str] = mapped_column(String(10), default="BORRADOR")        # BORRADOR | PUBLICADO | ARCHIVADO
    visibilidad: Mapped[str] = mapped_column(String(10), default="EXTERNO")   # EXTERNO (todos) | INTERNO (solo equipo de TI)
    articulo_relacionado_id: Mapped[int | None] = mapped_column(ForeignKey("kb_articulos.id"))   # versión externa/interna vinculada
    ticket_origen_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    vistas: Mapped[int] = mapped_column(Integer, default=0)
    util_si: Mapped[int] = mapped_column(Integer, default=0)
    util_no: Mapped[int] = mapped_column(Integer, default=0)
    tickets_evitados: Mapped[int] = mapped_column(Integer, default=0)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria: Mapped[Categoria | None] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria | None] = relationship(lazy="joined")
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[actualizado_por], lazy="joined")


class KbTicketVisto(Base):
    __tablename__ = "kb_ticket_vistos"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("kb_articulos.id"), primary_key=True)


class RespuestaRapida(Base):
    """Texto guardado que se inserta en la respuesta de un ticket (botón ⚡ o «/atajo»)."""
    __tablename__ = "respuestas_rapidas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    atajo: Mapped[str] = mapped_column(String(30))
    titulo: Mapped[str] = mapped_column(Unicode(150))
    texto: Mapped[str] = mapped_column(Unicode(4000))
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int | None] = mapped_column(ForeignKey("subcategorias.id"))
    estado_destino: Mapped[str | None] = mapped_column(ForeignKey("estados.codigo"))
    alcance: Mapped[str] = mapped_column(String(10), default="TODOS")   # TODOS | AREA | PERSONAL
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    propietario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    categoria: Mapped[Categoria | None] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria | None] = relationship(lazy="joined")
    area: Mapped[Area | None] = relationship(lazy="joined")
    propietario: Mapped[Usuario | None] = relationship(lazy="joined")


class TicketRecurrente(Base):
    """Programación de un ticket que el worker crea solo (p. ej. mantenimiento preventivo mensual)."""
    __tablename__ = "tickets_recurrentes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(150))
    asunto: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str] = mapped_column(Unicode(4000))
    tareas: Mapped[str | None] = mapped_column(Unicode(4000))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategorias.id"))
    prioridad_id: Mapped[int] = mapped_column(ForeignKey("prioridades.id"))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    frecuencia: Mapped[str] = mapped_column(String(12))   # DIARIA | SEMANAL | MENSUAL | TRIMESTRAL | SEMESTRAL | ANUAL
    dia_semana: Mapped[int | None] = mapped_column(SmallInteger)   # 1 = lunes … 7 = domingo
    dia_mes: Mapped[int | None] = mapped_column(SmallInteger)      # 1..31, -1 = último día
    semana_mes: Mapped[int | None] = mapped_column(SmallInteger)   # 1..4, -1 = última (con dia_semana: «primer lunes»)
    hora: Mapped[time] = mapped_column(Time, default=time(8, 30))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    omitir_si_abierto: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    proxima_ejecucion: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_ejecucion: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_ticket_id: Mapped[int | None] = mapped_column(BigId)   # sin FK: evita el ciclo con tickets.recurrente_id
    ultimo_resultado: Mapped[str | None] = mapped_column(Unicode(300))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    categoria: Mapped[Categoria] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria] = relationship(lazy="joined")
    prioridad: Mapped[Prioridad] = relationship(lazy="joined")
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")
    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id], lazy="joined")


class ReporteProgramado(Base):
    """Reporte que el worker envía por correo (p. ej. resumen semanal para gerencia)."""
    __tablename__ = "reportes_programados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(150))
    destinatarios: Mapped[str] = mapped_column(Unicode(1000))
    frecuencia: Mapped[str] = mapped_column(String(10))   # DIARIA | SEMANAL | MENSUAL
    dia_semana: Mapped[int | None] = mapped_column(SmallInteger)
    dia_mes: Mapped[int | None] = mapped_column(SmallInteger)
    hora: Mapped[time] = mapped_column(Time, default=time(8, 0))
    secciones: Mapped[str] = mapped_column(String(300))
    areas: Mapped[str | None] = mapped_column(String(300))
    adjuntar_excel: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    proximo_envio: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_envio: Mapped[datetime | None] = mapped_column(DateTime)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReporteEnvio(Base):
    __tablename__ = "reporte_envios"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    reporte_id: Mapped[int] = mapped_column(ForeignKey("reportes_programados.id", ondelete="CASCADE"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    periodo: Mapped[str] = mapped_column(Unicode(100))
    destinatarios: Mapped[str] = mapped_column(Unicode(1000))
    es_prueba: Mapped[bool] = mapped_column(Boolean, default=False)
    correo_id: Mapped[int | None] = mapped_column(ForeignKey("cola_correos.id"))
    enviado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


class Equipo(Base):
    """Equipo del inventario; los tickets pueden indicar el equipo afectado (historial de fallas)."""
    __tablename__ = "equipos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    tipo: Mapped[str] = mapped_column(String(15))
    marca_modelo: Mapped[str] = mapped_column(Unicode(150))
    serie: Mapped[str | None] = mapped_column(Unicode(80))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    compartido: Mapped[bool] = mapped_column(Boolean, default=False)
    ubicacion: Mapped[str | None] = mapped_column(Unicode(150))
    estado: Mapped[str] = mapped_column(String(12), default="EN_USO")   # EN_USO | BODEGA | REPARACION | BAJA
    fecha_compra: Mapped[date | None] = mapped_column(Date)
    garantia_hasta: Mapped[date | None] = mapped_column(Date)
    sistema: Mapped[str | None] = mapped_column(Unicode(150))
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")
    area: Mapped[Area | None] = relationship(lazy="joined")


class UsuarioDelegacion(Base):
    """Permiso para crear tickets en nombre de otras personas (apagado por defecto; lo otorga un administrador)."""
    __tablename__ = "usuario_delegaciones"
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    areas: Mapped[str | None] = mapped_column(String(300))   # ids separados por coma; NULL = todas
    hasta: Mapped[date | None] = mapped_column(Date)
    otorgado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def area_ids(self) -> list[int]:
        return [int(x) for x in (self.areas or "").split(",") if x.strip().isdigit()]


# ======================================================= tercera ronda (20-24)
class ReglaAprobacion(Base):
    """Qué tickets necesitan el visto bueno de un jefe antes de atenderse (21)."""
    __tablename__ = "aprobacion_reglas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int | None] = mapped_column(ForeignKey("subcategorias.id"))   # NULL = todas las subcategorías
    nivel1_tipo: Mapped[str] = mapped_column(String(20))   # JEFE_DIRECTO | SUPERVISOR_CATEGORIA | PERSONA
    nivel1_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nivel2_tipo: Mapped[str | None] = mapped_column(String(20))
    nivel2_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    recordar_horas: Mapped[int] = mapped_column(Integer, default=4)
    escalar_horas: Mapped[int | None] = mapped_column(Integer)          # sin respuesta en estas horas pasa a escalar_a
    escalar_a_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usar_reemplazo: Mapped[bool] = mapped_column(Boolean, default=True)  # aprobador en modo ausente → su reemplazo
    auto_si_aprobador: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)

    categoria: Mapped[Categoria] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria | None] = relationship(lazy="joined")
    nivel1_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[nivel1_usuario_id], lazy="joined")
    nivel2_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[nivel2_usuario_id], lazy="joined")
    escalar_a: Mapped[Usuario | None] = relationship(foreign_keys=[escalar_a_id], lazy="joined")


class TicketAprobacion(Base):
    __tablename__ = "ticket_aprobaciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    regla_id: Mapped[int | None] = mapped_column(ForeignKey("aprobacion_reglas.id"))
    nivel: Mapped[int] = mapped_column(SmallInteger, default=1)
    aprobador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    en_lugar_de_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))   # aprobador original (ausente, escalado o traspasado)
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE")   # PENDIENTE | APROBADO | RECHAZADO | REASIGNADO | ANULADO
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_respuesta: Mapped[datetime | None] = mapped_column(DateTime)
    recordado: Mapped[bool] = mapped_column(Boolean, default=False)

    ticket: Mapped[Ticket] = relationship(lazy="joined")
    aprobador: Mapped[Usuario] = relationship(foreign_keys=[aprobador_id], lazy="joined")
    en_lugar_de: Mapped[Usuario | None] = relationship(foreign_keys=[en_lugar_de_id], lazy="joined")


class TicketVinculo(Base):
    """Relación entre dos tickets (22). Se guarda en un sentido: ticket_id «tipo» relacionado_id."""
    __tablename__ = "ticket_vinculos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    relacionado_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(15))   # RELACIONADO | DUPLICADO | BLOQUEADO_POR | NO_DUPLICADO
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    ticket: Mapped[Ticket] = relationship(foreign_keys=[ticket_id], lazy="joined")
    relacionado: Mapped[Ticket] = relationship(foreign_keys=[relacionado_id], lazy="joined")


class AvisoGeneral(Base):
    """Caída o falla que afecta a muchos a la vez (ECUAPASS, internet, correo…) (24)."""
    __tablename__ = "avisos_generales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(200))
    mensaje: Mapped[str] = mapped_column(Unicode(1000))
    sistema: Mapped[str] = mapped_column(Unicode(100))
    palabras_clave: Mapped[str | None] = mapped_column(Unicode(500))
    areas: Mapped[str | None] = mapped_column(String(300))   # ids separados por coma; NULL = todos
    mostrar_publico: Mapped[bool] = mapped_column(Boolean, default=False)   # también en /solicitud
    estado: Mapped[str] = mapped_column(String(15), default="INVESTIGANDO")  # INVESTIGANDO | IDENTIFICADO | MONITOREANDO | RESUELTO
    ticket_maestro_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fin: Mapped[datetime | None] = mapped_column(DateTime)
    proxima_novedad: Mapped[str | None] = mapped_column(Unicode(100))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)

    ticket_maestro: Mapped[Ticket | None] = relationship(lazy="joined")

    @property
    def codigo(self) -> str:
        return f"AVISO-{self.id:04d}"

    @property
    def area_ids(self) -> list[int]:
        return [int(x) for x in (self.areas or "").split(",") if x.strip().isdigit()]


class AvisoActualizacion(Base):
    __tablename__ = "aviso_actualizaciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    aviso_id: Mapped[int] = mapped_column(ForeignKey("avisos_generales.id"))
    estado: Mapped[str] = mapped_column(String(15))
    texto: Mapped[str] = mapped_column(Unicode(1000))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class AvisoAfectado(Base):
    __tablename__ = "aviso_afectados"
    aviso_id: Mapped[int] = mapped_column(ForeignKey("avisos_generales.id"), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    comentario: Mapped[str | None] = mapped_column(Unicode(500))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


# ======================================================= cuarta ronda (26-28)
class ServicioCatalogo(Base):
    """Servicio del catálogo con su propio formulario y las tareas que genera (26)."""
    __tablename__ = "servicios_catalogo"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    descripcion: Mapped[str] = mapped_column(Unicode(400))
    icono: Mapped[str] = mapped_column(String(30), default="servicio")
    grupo: Mapped[str] = mapped_column(Unicode(30), default="Accesos")
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategorias.id"))
    plazo_horas: Mapped[int] = mapped_column(Integer, default=8)              # horas hábiles; 0 = usa el SLA de la categoría
    plazo_texto: Mapped[str | None] = mapped_column(Unicode(40))              # p. ej. «El mismo día»
    requiere_aprobacion: Mapped[bool] = mapped_column(Boolean, default=False)
    lo_pide: Mapped[str | None] = mapped_column(Unicode(100))
    titulo_campos: Mapped[str | None] = mapped_column(Unicode(150))
    titulo_opciones: Mapped[str | None] = mapped_column(Unicode(150))
    aviso: Mapped[str | None] = mapped_column(Unicode(500))
    campos: Mapped[str | None] = mapped_column(UnicodeText)                   # JSON: campos del formulario
    opciones: Mapped[str | None] = mapped_column(UnicodeText)                 # JSON: casillas que generan tareas
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)

    categoria: Mapped[Categoria] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria] = relationship(lazy="joined")


class TicketSolicitudServicio(Base):
    __tablename__ = "ticket_solicitudes_servicio"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicios_catalogo.id"))
    respuestas: Mapped[str] = mapped_column(UnicodeText)                     # JSON: [{etiqueta, valor}]
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    servicio: Mapped[ServicioCatalogo] = relationship(lazy="joined")


class TicketTarea(Base):
    __tablename__ = "ticket_tareas"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    titulo: Mapped[str] = mapped_column(Unicode(200))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")     # PENDIENTE | LISTA
    orden: Mapped[int] = mapped_column(Integer, default=0)
    completada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_completada: Mapped[datetime | None] = mapped_column(DateTime)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")


class Cambio(Base):
    """Solicitud de cambio TI-FOR-001 (Mesa) o TI-FOR-002 (general) con la evaluación de TI (27)."""
    __tablename__ = "cambios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    anio: Mapped[int] = mapped_column(Integer)
    secuencia: Mapped[int] = mapped_column(Integer)
    formato: Mapped[str] = mapped_column(String(10), default="MESA")         # MESA (TI-FOR-001) | GENERAL (TI-FOR-002)
    titulo: Mapped[str] = mapped_column(Unicode(200))
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    telefono: Mapped[str | None] = mapped_column(Unicode(30))
    tipo_solicitud: Mapped[str] = mapped_column(String(15))
    aplicacion: Mapped[str | None] = mapped_column(Unicode(150))
    partes: Mapped[str | None] = mapped_column(Unicode(500))
    pantalla: Mapped[str | None] = mapped_column(Unicode(200))
    desde_donde: Mapped[str | None] = mapped_column(String(12))
    ticket_relacionado: Mapped[str | None] = mapped_column(Unicode(200))
    situacion_actual: Mapped[str] = mapped_column(UnicodeText)
    situacion_deseada: Mapped[str] = mapped_column(UnicodeText)
    justificacion: Mapped[str | None] = mapped_column(UnicodeText)
    beneficiados: Mapped[str | None] = mapped_column(String(15))
    prioridad_sugerida: Mapped[str] = mapped_column(String(5), default="MEDIA")
    # Sección 7 · uso exclusivo de TI
    clasificacion: Mapped[str | None] = mapped_column(String(15))
    tipo_cambio: Mapped[str | None] = mapped_column(String(12))              # ESTANDAR | NORMAL | EMERGENCIA
    impacto: Mapped[str | None] = mapped_column(String(5))
    probabilidad: Mapped[str | None] = mapped_column(String(5))
    riesgo: Mapped[str | None] = mapped_column(String(5))
    esfuerzo: Mapped[str | None] = mapped_column(String(10))
    prioridad_ti: Mapped[str | None] = mapped_column(String(5))
    evaluacion: Mapped[str | None] = mapped_column(UnicodeText)
    plan_implementacion: Mapped[str | None] = mapped_column(UnicodeText)
    plan_reversion: Mapped[str | None] = mapped_column(UnicodeText)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    evaluado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_evaluacion: Mapped[datetime | None] = mapped_column(DateTime)
    ventana_inicio: Mapped[datetime | None] = mapped_column(DateTime)
    ventana_fin: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_implementado: Mapped[datetime | None] = mapped_column(DateTime)
    version_ref: Mapped[str | None] = mapped_column(Unicode(100))
    resultado: Mapped[str | None] = mapped_column(String(15))                # EXITOSO | CON_PROBLEMAS | REVERTIDO
    probado_solicitante: Mapped[bool | None] = mapped_column(Boolean)
    fecha_informado: Mapped[datetime | None] = mapped_column(DateTime)
    observaciones: Mapped[str | None] = mapped_column(UnicodeText)
    motivo: Mapped[str | None] = mapped_column(Unicode(1000))                # rechazo o «en espera»
    estado: Mapped[str] = mapped_column(String(15), default="SOLICITADO")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)

    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id], lazy="joined")
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")
    evaluado_por: Mapped[Usuario | None] = relationship(foreign_keys=[evaluado_por_id], lazy="joined")


class CambioAprobacion(Base):
    __tablename__ = "cambio_aprobaciones"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    cambio_id: Mapped[int] = mapped_column(ForeignKey("cambios.id"))
    rol: Mapped[str] = mapped_column(String(10))                             # JEFE_TI | GERENCIA
    aprobador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")     # PENDIENTE | APROBADO | RECHAZADO | ANULADO
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_respuesta: Mapped[datetime | None] = mapped_column(DateTime)
    recordado: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobador: Mapped[Usuario] = relationship(lazy="joined")


class CambioHistorial(Base):
    __tablename__ = "cambio_historial"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    cambio_id: Mapped[int] = mapped_column(ForeignKey("cambios.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(String(30))
    detalle: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class CambioAdjunto(Base):
    __tablename__ = "cambio_adjuntos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    cambio_id: Mapped[int] = mapped_column(ForeignKey("cambios.id"))
    nombre_original: Mapped[str] = mapped_column(Unicode(255))
    ruta: Mapped[str] = mapped_column(Unicode(400))
    tipo_mime: Mapped[str | None] = mapped_column(String(100))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CambioCongelamiento(Base):
    """Periodo sin cambios (cierre de mes, auditoría, temporada alta…)."""
    __tablename__ = "cambio_congelamientos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(150))
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fin: Mapped[datetime] = mapped_column(DateTime)
    motivo: Mapped[str | None] = mapped_column(Unicode(500))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ------------------------------------------------------- 30 gestión de problemas
class Problema(Base):
    """Causa de fondo de varios incidentes: PRB-AAAA-NNN, 5 porqués, error conocido y solución definitiva (30)."""
    __tablename__ = "problemas"
    __table_args__ = (UniqueConstraint("anio", "secuencia", name="uq_problemas_secuencia"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    anio: Mapped[int] = mapped_column(Integer)
    secuencia: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str | None] = mapped_column(UnicodeText)
    estado: Mapped[str] = mapped_column(String(20), default="DETECTADO")      # DETECTADO | EN_ANALISIS | ERROR_CONOCIDO | SOLUCION_EN_CAMBIO | CERRADO
    origen: Mapped[str] = mapped_column(String(10), default="MANUAL")         # MANUAL | PATRON
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    subcategoria_id: Mapped[int | None] = mapped_column(ForeignKey("subcategorias.id"))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    porques: Mapped[str | None] = mapped_column(UnicodeText)                  # JSON [{pregunta, respuesta}]
    causa_raiz: Mapped[str | None] = mapped_column(Unicode(1000))
    solucion_definitiva: Mapped[str | None] = mapped_column(Unicode(1000))
    solucion_temporal: Mapped[str | None] = mapped_column(Unicode(2000))
    palabras_clave: Mapped[str | None] = mapped_column(Unicode(500))         # para reconocer tickets nuevos parecidos
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("kb_articulos.id"))
    cambio_id: Mapped[int | None] = mapped_column(ForeignKey("cambios.id"))
    nota_cierre: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_causa: Mapped[datetime | None] = mapped_column(DateTime)             # cuando pasó a «Error conocido»
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id], lazy="joined")
    categoria: Mapped[Categoria | None] = relationship(lazy="joined")
    subcategoria: Mapped[Subcategoria | None] = relationship(lazy="joined")
    cambio: Mapped[Cambio | None] = relationship(lazy="joined")


class ProblemaTicket(Base):
    """Incidente agrupado bajo un problema. `con_solucion`: se respondió con la solución temporal (incidente evitado)."""
    __tablename__ = "problema_tickets"
    __table_args__ = (UniqueConstraint("problema_id", "ticket_id", name="uq_probtick"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    problema_id: Mapped[int] = mapped_column(ForeignKey("problemas.id"))
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    con_solucion: Mapped[bool] = mapped_column(Boolean, default=False)
    vinculado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ticket: Mapped[Ticket] = relationship(lazy="joined")


class ProblemaDescarte(Base):
    """«No es esto» en un ticket (problema + ticket) o «Ignorar» un patrón detectado (firma)."""
    __tablename__ = "problema_descartes"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    problema_id: Mapped[int | None] = mapped_column(ForeignKey("problemas.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    firma: Mapped[str | None] = mapped_column(String(64))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ------------------------------------------------------- 32 panel gerencial (PDF mensual)
class PanelEnvio(Base):
    """Cada PDF del panel gerencial enviado por correo (automático el primer día hábil o de prueba)."""
    __tablename__ = "panel_envios"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    periodo: Mapped[str] = mapped_column(String(7))                          # AAAA-MM del mes informado
    archivo: Mapped[str] = mapped_column(Unicode(150))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    destinatarios: Mapped[str] = mapped_column(Unicode(1000))
    es_prueba: Mapped[bool] = mapped_column(Boolean, default=False)
    correo_id: Mapped[int | None] = mapped_column(BigId)
    enviado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


class TicketVisualizador(Base):
    """Personas de la Mesa que siguen un ticket sin atenderlo (34): lo ven, comentan en público y reciben avisos."""
    __tablename__ = "ticket_visualizadores"
    __table_args__ = (UniqueConstraint("ticket_id", "usuario_id", name="uq_ticket_visualizadores"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    avisos_correo: Mapped[str] = mapped_column(String(10), default="ESTADO")   # TODO | ESTADO | NINGUNO
    origen: Mapped[str] = mapped_column(String(10), default="MANUAL")          # MANUAL | SEGUIR | CATEGORIA
    agregado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")
    agregador: Mapped[Usuario | None] = relationship(foreign_keys=[agregado_por], lazy="joined")


class TiempoRegistro(Base):
    """Tiempo trabajado (31): cronómetro o registro a mano sobre un ticket, un problema o un cambio."""
    __tablename__ = "tiempo_registros"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    problema_id: Mapped[int | None] = mapped_column(ForeignKey("problemas.id"))
    cambio_id: Mapped[int | None] = mapped_column(ForeignKey("cambios.id"))
    actividad: Mapped[str] = mapped_column(Unicode(200))
    estado: Mapped[str] = mapped_column(String(10), default="CORRIENDO")   # CORRIENDO | PAUSADO | GUARDADO
    segundos: Mapped[int] = mapped_column(Integer, default=0)              # acumulado de los tramos cerrados
    corriendo_desde: Mapped[datetime | None] = mapped_column(DateTime)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)      # cuándo se hizo el trabajo
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime)
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class Proveedor(Base):
    """Proveedor externo con su contrato de servicio (33)."""
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    servicio: Mapped[str] = mapped_column(Unicode(150))
    telefono: Mapped[str | None] = mapped_column(Unicode(60))
    correo: Mapped[str | None] = mapped_column(Unicode(150))
    correos_copia: Mapped[str | None] = mapped_column(Unicode(500))
    portal: Mapped[str | None] = mapped_column(Unicode(200))
    contacto: Mapped[str | None] = mapped_column(Unicode(150))          # ejecutivo de cuenta y su teléfono
    contrato_numero: Mapped[str | None] = mapped_column(Unicode(60))
    contrato_vence: Mapped[date | None] = mapped_column(Date)
    contrato_detalle: Mapped[str | None] = mapped_column(Unicode(300))  # «20 Mbps simétrico», archivo, etc.
    atencion_24x7: Mapped[bool] = mapped_column(Boolean, default=False)
    plazo_horas: Mapped[int] = mapped_column(Integer, default=8)        # plazo de solución pactado
    valor_mensual: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    multa_pct_hora: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))   # % de la mensualidad por cada hora fuera de plazo
    subcategorias: Mapped[str | None] = mapped_column(String(300))     # ids de subcategorías que se escalan a este proveedor
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    aviso_vencimiento: Mapped[date | None] = mapped_column(Date)       # vencimiento ya avisado (no se repite)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProveedorCaso(Base):
    """Ticket escalado a un proveedor: n.º de caso, plazo del contrato y si lo cumplió."""
    __tablename__ = "proveedor_casos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    numero_caso: Mapped[str | None] = mapped_column(Unicode(60))
    reporte: Mapped[str] = mapped_column(Unicode(2000))
    medio: Mapped[str | None] = mapped_column(Unicode(100))
    contacto: Mapped[str | None] = mapped_column(Unicode(150))
    estado: Mapped[str] = mapped_column(String(10), default="ABIERTO")   # ABIERTO | RESUELTO
    fecha_reporte: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    vence: Mapped[datetime] = mapped_column(DateTime)
    fecha_solucion: Mapped[datetime | None] = mapped_column(DateTime)
    minutos_solucion: Mapped[int | None] = mapped_column(Integer)
    cumplido: Mapped[bool | None] = mapped_column(Boolean)
    solucion: Mapped[str | None] = mapped_column(Unicode(1000))
    aviso_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    correo_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    ticket: Mapped[Ticket] = relationship(lazy="joined")


class UsuarioClavePrevia(Base):
    """Contraseñas anteriores (hash bcrypt) para no repetirlas (ISO 27001 A.5.17, mejora 37)."""
    __tablename__ = "usuario_claves_previas"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    clave_hash: Mapped[str] = mapped_column(String(100))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DosfEquipo(Base):
    """Equipo de confianza: no pide el segundo paso durante N días (28)."""
    __tablename__ = "dosf_equipos"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    equipo: Mapped[str | None] = mapped_column(Unicode(300))
    ip: Mapped[str | None] = mapped_column(String(45))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime)
    revocado: Mapped[bool] = mapped_column(Boolean, default=False)


class DosfDesafio(Base):
    """Inicio de sesión a medias: la contraseña fue correcta y falta el código (28)."""
    __tablename__ = "dosf_desafios"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    proposito: Mapped[str] = mapped_column(String(10))                       # LOGIN | ACTIVAR
    codigo_hash: Mapped[str | None] = mapped_column(CHAR(64))                # código enviado por correo
    codigo_expira: Mapped[datetime | None] = mapped_column(DateTime)
    envios: Mapped[int] = mapped_column(Integer, default=0)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime)
    usuario: Mapped[Usuario] = relationship(lazy="joined")
