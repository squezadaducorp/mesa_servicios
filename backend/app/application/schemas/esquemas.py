"""DTOs de entrada y salida de la API (Pydantic v2)."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

from app.domain.correos import normalizar_correos, separar

T = TypeVar("T")


class Modelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _utc(self, v):
        # Las fechas se guardan en UTC sin zona; se publican con sufijo Z para que el navegador las convierta.
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.isoformat() + "Z"
        return v


class Pagina(Modelo, Generic[T]):
    items: list[T]
    total: int
    pagina: int
    tamano: int


class Mensaje(Modelo):
    mensaje: str


# ------------------------------------------------------------------ auth
class LoginEntrada(BaseModel):
    correo: str = Field(examples=["admin@aducorp.com.ec"], description="Correo o usuario de dominio")
    clave: str = Field(examples=["Aducorp2026!"])
    equipo_token: str | None = Field(None, max_length=200, description="Equipo de confianza (verificación en dos pasos)")


class RefreshEntrada(BaseModel):
    refresh_token: str
    inactivo_seg: int | None = Field(None, ge=0, le=10_000_000, description="Segundos desde la última interacción del usuario")


class CambioClaveEntrada(BaseModel):
    clave_actual: str
    clave_nueva: str


class UsuarioResumen(Modelo):
    id: int
    nombre: str
    correo: str
    cargo: str | None = None


class UsuarioSesion(UsuarioResumen):
    rol: str
    rol_nombre: str
    area: str | None = None
    telefono: str | None = None
    permisos: list[str]
    debe_cambiar_clave: bool


class TokenSalida(Modelo):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    inactividad_min: int = 0
    usuario: UsuarioSesion
    equipo_token: str | None = None          # «Confiar en este equipo» (verificación en dos pasos)
    codigos_respaldo: list[str] | None = None   # al activar la verificación durante el inicio de sesión


class SegundoPaso(BaseModel):
    desafio: str
    modo: str                   # VERIFICAR | ACTIVAR
    metodo: str | None = None   # APP | CORREO
    nombre: str
    correo_mascara: str
    puede_correo: bool
    codigo_enviado: bool = False
    dias_confianza: int = 30


class SegundoPasoSalida(BaseModel):
    segundo_paso: SegundoPaso


# ------------------------------------------------------------- catálogos
class Item(Modelo):
    id: int
    nombre: str


class EstadoSalida(Modelo):
    codigo: str
    nombre: str
    color: str | None
    pausa_sla: bool
    es_final: bool


class PrioridadSalida(Modelo):
    id: int
    codigo: str
    nombre: str
    color: str | None
    sla_respuesta_min: int
    sla_resolucion_min: int


class PrioridadSlaEntrada(BaseModel):
    sla_respuesta_min: int = Field(gt=0, le=60 * 24 * 30)
    sla_resolucion_min: int = Field(gt=0, le=60 * 24 * 60)


class SubcategoriaSalida(Modelo):
    id: int
    categoria_id: int
    nombre: str
    palabras_clave: str | None = None
    respuesta_plantilla: str | None = None
    activo: bool


class ResponsableSalida(Modelo):
    usuario_id: int
    nombre: str
    es_principal: bool


class CategoriaSalida(Modelo):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    palabras_clave: str | None
    color: str | None
    orden: int
    modo_asignacion: str
    activo: bool
    supervisor: UsuarioResumen | None
    responsables: list[ResponsableSalida]
    subcategorias: list[SubcategoriaSalida]
    pide_equipo: bool = False             # el formulario pide «Equipo afectado»
    restringida_en_nombre: bool = False   # no se puede pedir en nombre de otra persona


class CategoriaEntrada(BaseModel):
    codigo: str = Field(max_length=30, pattern=r"^[A-Z0-9_]+$")
    nombre: str = Field(max_length=120)
    descripcion: str | None = None
    palabras_clave: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    orden: int = 0
    modo_asignacion: Literal["PRINCIPAL", "BALANCEO", "MANUAL"] = "PRINCIPAL"
    supervisor_id: int | None = None
    activo: bool = True
    responsables: list[ResponsableEntrada] = []
    correos_copia: list[str] = Field(default=[], description="Se agregan en copia a cada ticket nuevo de la categoría")
    pide_equipo: bool = False
    restringida_en_nombre: bool = False

    @field_validator("correos_copia")
    @classmethod
    def _correos_copia(cls, v):
        return normalizar_correos(v)


class CategoriaAdminSalida(CategoriaSalida):
    correos_copia: list[str] = []


class ResponsableEntrada(BaseModel):
    usuario_id: int
    es_principal: bool = False


class SubcategoriaEntrada(BaseModel):
    nombre: str = Field(max_length=120)
    palabras_clave: str | None = None
    respuesta_plantilla: str | None = None
    activo: bool = True


DOMINIOS_PUBLICOS = {"gmail.com", "hotmail.com", "hotmail.es", "outlook.com", "outlook.es", "live.com", "yahoo.com", "yahoo.es",
                     "icloud.com", "me.com", "msn.com", "aol.com", "protonmail.com", "proton.me", "gmx.com", "mail.com"}


def normalizar_dominios(v: list[str]) -> list[str]:
    salida = []
    for d in v or []:
        d = d.strip().lower().split("@")[-1].strip()
        if not d:
            continue
        if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d):
            raise ValueError(f"«{d}» no es un dominio válido (ejemplo: schryver.com)")
        if d in DOMINIOS_PUBLICOS:
            raise ValueError(f"«{d}» es un correo público: no identifica a una empresa")
        if d not in salida:
            salida.append(d)
    return salida


class ClienteSalida(Modelo):
    id: int
    ruc: str | None
    razon_social: str
    correo: str | None
    telefono: str | None
    es_vip: bool
    activo: bool


class ClienteEntrada(BaseModel):
    ruc: str | None = Field(default=None, pattern=r"^\d{13}$")
    razon_social: str = Field(max_length=200)
    correo: EmailStr | None = None
    telefono: str | None = None
    es_vip: bool = False
    activo: bool = True
    correos_copia: list[str] = Field(default=[], description="Se agregan en copia a cada ticket nuevo del cliente")
    dominios: list[str] = Field(default=[], max_length=10,
                                description="Dominios de correo de la empresa (p. ej. schryver.com): quien escribe desde ellos queda con este cliente")

    @field_validator("correos_copia")
    @classmethod
    def _correos_copia(cls, v):
        return normalizar_correos(v)

    @field_validator("dominios")
    @classmethod
    def _dominios(cls, v):
        return normalizar_dominios(v)


class ClienteAdminSalida(ClienteSalida):
    correos_copia: list[str] = []
    dominios: list[str] = []

    @field_validator("correos_copia", "dominios", mode="before")
    @classmethod
    def _texto(cls, v):
        return separar(v) if isinstance(v, str) or v is None else v


class CatalogosSalida(Modelo):
    categorias: list[CategoriaSalida]
    prioridades: list[PrioridadSalida]
    estados: list[EstadoSalida]
    areas: list[Item]
    clientes: list[ClienteSalida]
    responsables: list[UsuarioResumen]


# ------------------------------------------------------------------- SLA
class TramoEntrada(BaseModel):
    dia_semana: int = Field(ge=1, le=7)
    hora_inicio: time
    hora_fin: time


class HorarioSalida(Modelo):
    id: int
    nombre: str
    zona_horaria: str
    tramos: list[TramoEntrada]


class HorarioEntrada(BaseModel):
    nombre: str
    zona_horaria: str = "America/Guayaquil"
    tramos: list[TramoEntrada]


class ExcepcionCalendarioEntrada(BaseModel):
    fecha: date
    tipo: Literal["FERIADO", "HORARIO_ESPECIAL"]
    hora_inicio: time | None = None
    hora_fin: time | None = None
    descripcion: str = Field(max_length=200)


class ExcepcionCalendarioSalida(ExcepcionCalendarioEntrada, Modelo):
    id: int


class PoliticaSlaEntrada(BaseModel):
    categoria_id: int
    prioridad_id: int
    sla_respuesta_min: int = Field(gt=0)
    sla_resolucion_min: int = Field(gt=0)
    activo: bool = True


class PoliticaSlaSalida(PoliticaSlaEntrada, Modelo):
    id: int


class ExcepcionSlaEntrada(BaseModel):
    tipo: Literal["EXTENSION", "EXCLUSION"]
    minutos: int | None = Field(default=None, gt=0, description="Obligatorio para EXTENSION")
    motivo: str = Field(min_length=5, max_length=500)


# --------------------------------------------------------------- tickets
class TicketCrear(BaseModel):
    asunto: str = Field(min_length=5, max_length=200)
    descripcion: str = Field(min_length=10)
    categoria_id: int
    subcategoria_id: int
    prioridad_id: int | None = Field(default=None, description="Si se omite se usa la prioridad sugerida por la IA")
    cliente_id: int | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    canal: Literal["PORTAL", "CORREO", "TELEFONO", "PRESENCIAL", "WEB"] = "PORTAL"
    solicitante_id: int | None = Field(default=None, description="En nombre de otra persona: la mesa de servicio o quien tenga la delegación activa")
    en_nombre_motivo: str | None = Field(default=None, max_length=300, description="Obligatorio al crear en nombre de otra persona (salvo la mesa)")
    responsable_id: int | None = Field(default=None, description="Asignación directa (requiere permiso de asignar)")
    equipo_id: int | None = Field(default=None, description="Equipo afectado (inventario)")
    kb_vistos: list[int] = Field(default_factory=list, max_length=10, description="Artículos de la base de conocimiento que revisó antes de crear")
    aviso_id: int | None = Field(default=None, description="Aviso general al que pertenece (el usuario confirmó que es parte de esa caída)")


class TicketEditar(BaseModel):
    asunto: str | None = Field(default=None, min_length=5, max_length=200)
    descripcion: str | None = None
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    prioridad_id: int | None = None
    cliente_id: int | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    version: int | None = Field(default=None, description="Versión leída; si no coincide se rechaza (409)")


class AsignarEntrada(BaseModel):
    responsable_id: int
    motivo: str | None = Field(default=None, max_length=500)


class EstadoEntrada(BaseModel):
    estado: Literal["ASIGNADO", "EN_PROCESO", "PENDIENTE_CLIENTE", "ESCALADO", "RESUELTO", "CERRADO", "CANCELADO"]
    comentario: str | None = None


class EscalarEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)
    escalar_a_id: int | None = Field(default=None, description="Por defecto, el supervisor de la categoría")


class MotivoEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


class CerrarEntrada(BaseModel):
    comentario: str | None = None


class ComentarioEntrada(BaseModel):
    texto: str = Field(min_length=1)
    respuesta_rapida_id: int | None = Field(default=None, description="Respuesta rápida usada (suma un uso)")
    es_interno: bool = False
    tipo: Literal["COMENTARIO", "ACTIVIDAD"] = "COMENTARIO"
    minutos_invertidos: int | None = Field(default=None, ge=0, le=60 * 24)
    # Personas en copia de esta respuesta. None = las del ticket; [] = ninguna. Se ignora en notas internas.
    copia_a: list[str] | None = None

    @field_validator("copia_a")
    @classmethod
    def _copia_a(cls, v):
        return None if v is None else normalizar_correos(v)


class CopiasEntrada(BaseModel):
    correos: list[str] = []

    @field_validator("correos")
    @classmethod
    def _correos(cls, v):
        return normalizar_correos(v)


class CopiaSalida(BaseModel):
    correo: str
    origen: str


class ComentarioSalida(Modelo):
    id: int
    usuario: UsuarioResumen
    texto: str
    es_interno: bool
    tipo: str
    minutos_invertidos: int | None
    fecha: datetime
    copia_a: list[str] = Field(default=[], description="Correos que recibieron esta respuesta en copia")
    adjuntos: list["AdjuntoSalida"] = Field(default=[], description="Capturas y archivos enviados con este comentario")


class AdjuntoSalida(Modelo):
    id: int
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    usuario: UsuarioResumen
    fecha: datetime
    comentario_id: int | None = None


ComentarioSalida.model_rebuild()


class HistorialSalida(Modelo):
    id: int
    accion: str
    campo: str | None
    valor_anterior: str | None
    valor_nuevo: str | None
    detalle: str | None
    usuario: UsuarioResumen | None
    fecha: datetime


class EscalamientoSalida(Modelo):
    id: int
    nivel: int
    tipo: str
    motivo: str | None
    sla_consumido_pct: float | None
    fecha: datetime


class TicketListado(Modelo):
    id: int
    numero: str
    asunto: str
    fecha_creacion: datetime
    solicitante_nombre: str
    cliente: str | None
    categoria: str
    subcategoria: str
    prioridad: str
    prioridad_codigo: str
    responsable: str | None
    estado: str
    estado_nombre: str
    sla_consumido_pct: float
    sla_resolucion_vence: datetime
    sla_incumplido: bool
    cumplimiento_sla: str
    vence_tipo: str | None = Field(default=None, description="RESPUESTA o RESOLUCION: el próximo plazo del ticket abierto")
    vence_en_min: int | None = Field(default=None, description="Minutos laborables que faltan (negativo si ya venció)")


class EncuestaSalida(Modelo):
    calificacion: int
    comentario: str | None
    origen: str
    fecha: datetime


class EncuestaEntrada(BaseModel):
    calificacion: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


class EncuestaPublicaEntrada(BaseModel):
    token: str = Field(min_length=10, max_length=600)
    calificacion: int | None = Field(default=None, ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


class EncuestaPublicaSalida(BaseModel):
    numero: str
    asunto: str
    responsable: str | None
    calificacion: int | None = None
    comentario: str | None = None
    puede_comentar: bool = False


class AusenciaEntrada(BaseModel):
    usuario_id: int | None = Field(default=None, description="Vacío = el usuario actual")
    reemplazo_id: int
    motivo: Literal["VACACIONES", "PERMISO", "ENFERMEDAD", "CAPACITACION", "OTRO"] = "VACACIONES"
    desde: datetime = Field(description="Hora de Ecuador")
    hasta: datetime = Field(description="Hora de Ecuador (regreso)")
    pasar_abiertos: bool = True
    devolver: bool = True
    avisar_solicitantes: bool = True


class PersonaCorta(BaseModel):
    id: int
    nombre: str
    correo: str


class AusenciaSalida(Modelo):
    id: int
    usuario: PersonaCorta
    reemplazo: PersonaCorta
    motivo: str
    desde: datetime
    hasta: datetime
    estado: str
    pasar_abiertos: bool
    devolver: bool
    avisar_solicitantes: bool
    tickets_abiertos: int | None = None


class ReemplazoSugerido(BaseModel):
    id: int
    nombre: str
    correo: str
    tickets_abiertos: int
    categorias_comunes: list[str]
    sugerido: bool = False


class TicketCorto(BaseModel):
    id: int
    numero: str
    asunto: str


class AlertaSla(Modelo):
    id: int
    numero: str
    asunto: str
    prioridad: str
    prioridad_codigo: str
    vence_tipo: str
    vence_en_min: int
    vence: datetime


class EquipoTicket(Modelo):
    id: int
    codigo: str
    tipo: str
    marca_modelo: str
    aviso: str | None = None


class TicketDetalle(Modelo):
    id: int
    numero: str
    asunto: str
    descripcion: str
    fecha_creacion: datetime
    solicitante: UsuarioResumen
    solicitante_nombre: str
    solicitante_cargo: str | None
    area: Item | None
    cliente: Item | None
    correo: str
    telefono: str | None
    categoria: Item
    subcategoria: Item
    prioridad: PrioridadSalida
    responsable: UsuarioResumen | None
    estado: str
    estado_nombre: str
    canal: str
    fecha_asignacion: datetime | None
    fecha_primera_respuesta: datetime | None
    fecha_resolucion: datetime | None
    fecha_cierre: datetime | None
    sla_respuesta_min: int
    sla_resolucion_min: int
    sla_respuesta_vence: datetime
    sla_resolucion_vence: datetime
    sla_minutos_consumidos: int
    sla_minutos_pausa: int
    sla_minutos_extension: int
    sla_consumido_pct: float
    sla_pausado: bool
    sla_respuesta_cumplido: bool | None
    sla_resolucion_cumplido: bool | None
    sla_incumplido: bool
    sla_excluido: bool
    cumplimiento_sla: str
    reaperturas: int
    resumen_ia: str | None
    riesgo_ia: float | None
    version: int
    comentarios: list[ComentarioSalida]
    adjuntos: list[AdjuntoSalida]
    historial: list[HistorialSalida]
    escalamientos: list[EscalamientoSalida]
    copias: list[CopiaSalida] = Field(default=[], description="Personas en copia: reciben las respuestas y el cierre por correo")
    acciones: list[str] = Field(description="Acciones que el usuario actual puede ejecutar")
    solo_lectura_participante: bool = Field(default=False, description="El usuario fue responsable antes y hoy solo puede consultarlo")
    encuesta: EncuestaSalida | None = Field(default=None, description="Calificación del solicitante, si ya respondió")
    creado_por: UsuarioResumen | None = Field(default=None, description="Quien lo registró en nombre del solicitante")
    en_nombre_motivo: str | None = None
    solo_lectura_creador: bool = Field(default=False, description="Lo registró en nombre de otra persona: solo puede consultarlo")
    equipo: EquipoTicket | None = None
    recurrente_id: int | None = None
    kb_vistos: list[Item] = Field(default_factory=list, description="Artículos que el solicitante revisó antes de crear el ticket")
    aprobaciones: list[dict] = Field(default_factory=list, description="Aprobaciones del jefe pedidas para este ticket")
    aprobacion_pendiente_id: int | None = Field(default=None, description="Aprobación que espera la respuesta del usuario actual")
    vinculos: list[dict] = Field(default_factory=list, description="Tickets relacionados, duplicados o que lo bloquean")
    duplicado_de: dict | None = Field(default=None, description="Ticket principal si este se unió como duplicado")
    avisos: list[dict] = Field(default_factory=list, description="Avisos generales a los que pertenece")
    seguimiento_url: str | None = Field(default=None, description="Enlace de seguimiento sin cuenta que recibe el solicitante")
    servicio: dict | None = Field(default=None, description="Formulario del catálogo de servicios y sus tareas")


class FiltroTickets(BaseModel):
    texto: str | None = None
    estado: list[str] | None = None
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    prioridad_id: int | None = None
    responsable_id: int | None = None
    cliente_id: int | None = None
    sla: Literal["CUMPLIDO", "INCUMPLIDO", "EN_CURSO", "EN_RIESGO"] | None = None
    desde: date | None = None
    hasta: date | None = None
    solo_mios: bool = False
    participe: bool = False
    vence: Literal["HOY", "VENCIDOS"] | None = None
    orden: Literal["fecha_desc", "fecha_asc", "sla_desc", "prioridad", "vence"] = "fecha_desc"


# --------------------------------------------------------- notificaciones
class NotificacionSalida(Modelo):
    id: int
    ticket_id: int | None
    tipo: str
    severidad: str
    titulo: str
    mensaje: str
    leida: bool
    fecha: datetime


# --------------------------------------------------------------- usuarios
class UsuarioSalida(Modelo):
    id: int
    nombre: str
    correo: str
    usuario_ad: str | None
    origen_autenticacion: str
    cargo: str | None
    telefono: str | None
    area_id: int | None
    rol_id: int
    rol: str
    supervisor_id: int | None
    activo: bool
    bloqueado: bool
    ultimo_login: datetime | None


class UsuarioCrear(BaseModel):
    nombre: str = Field(max_length=150)
    correo: EmailStr
    rol_id: int
    cargo: str | None = None
    telefono: str | None = None
    area_id: int | None = None
    supervisor_id: int | None = None
    origen_autenticacion: Literal["LOCAL", "AD", "ENTRA"] = "LOCAL"
    usuario_ad: str | None = None
    clave: str | None = Field(default=None, description="Si se omite, se genera una temporal")


class UsuarioEditar(BaseModel):
    nombre: str | None = None
    cargo: str | None = None
    telefono: str | None = None
    area_id: int | None = None
    rol_id: int | None = None
    supervisor_id: int | None = None
    activo: bool | None = None
    usuario_ad: str | None = None
    origen_autenticacion: Literal["LOCAL", "AD", "ENTRA"] | None = None


class ClaveTemporalSalida(Modelo):
    clave_temporal: str


class RolSalida(Modelo):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    permisos: list[str]


class RolPermisosEntrada(BaseModel):
    permisos: list[str]


class PermisoSalida(Modelo):
    codigo: str
    modulo: str
    descripcion: str


# -------------------------------------------------------------- auditoría
class AuditoriaSalida(Modelo):
    id: int
    usuario_id: int | None
    usuario_correo: str | None
    fecha_hora: datetime
    accion: str
    entidad: str | None
    entidad_id: str | None
    detalle: str | None
    ip: str | None
    equipo: str | None
    resultado: str


# ---------------------------------------------------------------------- IA
class IaEntrada(BaseModel):
    asunto: str = ""
    descripcion: str = ""
    cliente_id: int | None = None


class SugerenciaClasificacion(Modelo):
    categoria_id: int
    categoria: str
    subcategoria_id: int
    subcategoria: str
    confianza: float
    motivos: list[str]


class SugerenciaTicketSalida(Modelo):
    proveedor: str
    clasificaciones: list[SugerenciaClasificacion]
    prioridad: str
    prioridad_id: int | None
    prioridad_confianza: float
    prioridad_motivos: list[str]
    responsable: UsuarioResumen | None


class RiesgoSalida(Modelo):
    ticket_id: int
    numero: str
    riesgo: float
    nivel: str
    motivos: list[str]


class TextoSalida(Modelo):
    proveedor: str
    texto: str


class ConfiguracionItem(Modelo):
    clave: str
    valor: str
    descripcion: str | None


class ConfiguracionEntrada(BaseModel):
    valores: dict[str, str]


CategoriaEntrada.model_rebuild()


# ------------------------------------------------------------------ formulario público
class SubcategoriaPublica(BaseModel):
    id: int
    nombre: str


class CategoriaPublica(BaseModel):
    id: int
    nombre: str
    subcategorias: list[SubcategoriaPublica]


class FormularioPublicoSalida(BaseModel):
    habilitado: bool
    empresa: str
    categorias: list[CategoriaPublica]
    token: str = Field(description="Ficha anti-spam: se devuelve al enviar el formulario")
    adjuntos_max: int = Field(0, description="Archivos que se pueden adjuntar (0 = ninguno)")
    adjuntos_max_mb: int = 0
    adjuntos_extensiones: list[str] = []


class SolicitudPublica(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    correo: EmailStr
    telefono: str | None = Field(default=None, max_length=30)
    empresa: str | None = Field(default=None, max_length=150)
    asunto: str = Field(min_length=5, max_length=200)
    descripcion: str = Field(min_length=10, max_length=4000)
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    token: str = Field(max_length=200)
    sitio_web: str | None = Field(default=None, description="Campo trampa: debe llegar vacío")


class SolicitudPublicaSalida(BaseModel):
    numero: str
    mensaje: str
    adjuntos: int = 0
