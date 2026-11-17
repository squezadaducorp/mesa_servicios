// Tipos de la API v1 (espejo de backend/app/application/schemas/esquemas.py)

export interface Pagina<T> {
  items: T[];
  total: number;
  pagina: number;
  tamano: number;
}

export interface UsuarioResumen {
  id: number;
  nombre: string;
  correo: string;
  cargo?: string | null;
}

export interface UsuarioSesion extends UsuarioResumen {
  rol: string;
  rol_nombre: string;
  area?: string | null;
  telefono?: string | null;
  permisos: string[];
  debe_cambiar_clave: boolean;
}

export interface TokenSalida {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  inactividad_min?: number;
  usuario: UsuarioSesion;
}

export interface Item {
  id: number;
  nombre: string;
}

export interface EstadoCat {
  codigo: string;
  nombre: string;
  color: string | null;
  pausa_sla: boolean;
  es_final: boolean;
}

export interface PrioridadCat {
  id: number;
  codigo: string;
  nombre: string;
  color: string | null;
  sla_respuesta_min: number;
  sla_resolucion_min: number;
}

export interface Subcategoria {
  id: number;
  categoria_id: number;
  nombre: string;
  palabras_clave?: string | null;
  respuesta_plantilla?: string | null;
  activo: boolean;
}

export interface Categoria {
  id: number;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  palabras_clave: string | null;
  color: string | null;
  orden: number;
  modo_asignacion: "PRINCIPAL" | "BALANCEO" | "MANUAL";
  activo: boolean;
  supervisor: UsuarioResumen | null;
  responsables: { usuario_id: number; nombre: string; es_principal: boolean }[];
  subcategorias: Subcategoria[];
  correos_copia?: string[];
}

export interface Cliente {
  id: number;
  ruc: string | null;
  razon_social: string;
  correo: string | null;
  telefono: string | null;
  es_vip: boolean;
  activo: boolean;
  correos_copia?: string[];
}

export interface Catalogos {
  categorias: Categoria[];
  prioridades: PrioridadCat[];
  estados: EstadoCat[];
  areas: Item[];
  clientes: Cliente[];
  responsables: UsuarioResumen[];
}

export type CumplimientoSla = "CUMPLIDO" | "INCUMPLIDO" | "EN_CURSO" | "EXCLUIDO";

export interface TicketListado {
  id: number;
  numero: string;
  asunto: string;
  fecha_creacion: string;
  solicitante_nombre: string;
  cliente: string | null;
  categoria: string;
  subcategoria: string;
  prioridad: string;
  prioridad_codigo: string;
  responsable: string | null;
  estado: string;
  estado_nombre: string;
  sla_consumido_pct: number;
  sla_resolucion_vence: string;
  sla_incumplido: boolean;
  cumplimiento_sla: CumplimientoSla;
  /** Próximo plazo del ticket abierto: RESPUESTA (1.ª respuesta) o RESOLUCION. */
  vence_tipo?: "RESPUESTA" | "RESOLUCION" | null;
  /** Minutos laborables que faltan (negativo si ya venció). */
  vence_en_min?: number | null;
}

export interface Encuesta {
  calificacion: number;
  comentario: string | null;
  origen: "PORTAL" | "CORREO";
  fecha: string;
}

export interface EncuestaPublica {
  numero: string;
  asunto: string;
  responsable: string | null;
  calificacion: number | null;
  comentario: string | null;
  puede_comentar: boolean;
}

export interface PersonaCorta {
  id: number;
  nombre: string;
  correo: string;
}

export type MotivoAusencia = "VACACIONES" | "PERMISO" | "ENFERMEDAD" | "CAPACITACION" | "OTRO";

export interface Ausencia {
  id: number;
  usuario: PersonaCorta;
  reemplazo: PersonaCorta;
  motivo: MotivoAusencia;
  desde: string;
  hasta: string;
  estado: "PROGRAMADA" | "ACTIVA" | "FINALIZADA" | "CANCELADA";
  pasar_abiertos: boolean;
  devolver: boolean;
  avisar_solicitantes: boolean;
  tickets_abiertos: number | null;
}

export interface ReemplazoSugerido {
  id: number;
  nombre: string;
  correo: string;
  tickets_abiertos: number;
  categorias_comunes: string[];
  sugerido: boolean;
}

export interface TicketCorto {
  id: number;
  numero: string;
  asunto: string;
}

export interface AlertaSla {
  id: number;
  numero: string;
  asunto: string;
  prioridad: string;
  prioridad_codigo: string;
  vence_tipo: "RESPUESTA" | "RESOLUCION";
  vence_en_min: number;
  vence: string;
}

export interface Comentario {
  id: number;
  usuario: UsuarioResumen;
  texto: string;
  es_interno: boolean;
  tipo: string;
  minutos_invertidos: number | null;
  fecha: string;
  copia_a: string[];
}

export interface Adjunto {
  id: number;
  nombre_original: string;
  tipo_mime: string;
  tamano_bytes: number;
  usuario: UsuarioResumen;
  fecha: string;
}

export interface Historial {
  id: number;
  accion: string;
  campo: string | null;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  detalle: string | null;
  usuario: UsuarioResumen | null;
  fecha: string;
}

export interface Escalamiento {
  id: number;
  nivel: number;
  tipo: string;
  motivo: string | null;
  sla_consumido_pct: number | null;
  fecha: string;
}

export type AccionTicket =
  | "editar" | "asignar" | "cambiar_estado" | "escalar" | "cerrar" | "reabrir" | "comentar"
  | "nota_interna" | "copias" | "adjuntar" | "excepcion_sla" | "eliminar" | "ia" | "calificar";

export interface CopiaTicket {
  correo: string;
  origen: "MANUAL" | "CATEGORIA" | "CLIENTE" | "CORREO";
}

export interface TicketDetalle {
  id: number;
  numero: string;
  asunto: string;
  descripcion: string;
  fecha_creacion: string;
  solicitante: UsuarioResumen;
  solicitante_nombre: string;
  solicitante_cargo: string | null;
  area: Item | null;
  cliente: Item | null;
  correo: string;
  telefono: string | null;
  categoria: Item;
  subcategoria: Item;
  prioridad: PrioridadCat;
  responsable: UsuarioResumen | null;
  estado: string;
  estado_nombre: string;
  canal: string;
  fecha_asignacion: string | null;
  fecha_primera_respuesta: string | null;
  fecha_resolucion: string | null;
  fecha_cierre: string | null;
  sla_respuesta_min: number;
  sla_resolucion_min: number;
  sla_respuesta_vence: string;
  sla_resolucion_vence: string;
  sla_minutos_consumidos: number;
  sla_minutos_pausa: number;
  sla_minutos_extension: number;
  sla_consumido_pct: number;
  sla_pausado: boolean;
  sla_respuesta_cumplido: boolean | null;
  sla_resolucion_cumplido: boolean | null;
  sla_incumplido: boolean;
  sla_excluido: boolean;
  cumplimiento_sla: CumplimientoSla;
  reaperturas: number;
  resumen_ia: string | null;
  riesgo_ia: number | null;
  version: number;
  comentarios: Comentario[];
  adjuntos: Adjunto[];
  historial: Historial[];
  escalamientos: Escalamiento[];
  copias: CopiaTicket[];
  acciones: AccionTicket[];
  solo_lectura_participante?: boolean;
  encuesta?: Encuesta | null;
}

export interface FiltroTickets {
  texto?: string;
  estado?: string[];
  categoria_id?: number;
  subcategoria_id?: number;
  prioridad_id?: number;
  responsable_id?: number;
  cliente_id?: number;
  sla?: "CUMPLIDO" | "INCUMPLIDO" | "EN_CURSO" | "EN_RIESGO";
  desde?: string;
  hasta?: string;
  solo_mios?: boolean;
  participe?: boolean;
  vence?: "HOY" | "VENCIDOS";
  orden?: "fecha_desc" | "fecha_asc" | "sla_desc" | "prioridad" | "vence";
}

export interface Notificacion {
  id: number;
  ticket_id: number | null;
  tipo: string;
  severidad: "INFO" | "AVISO" | "CRITICO";
  titulo: string;
  mensaje: string;
  leida: boolean;
  fecha: string;
}

export interface SugerenciaTicket {
  proveedor: string;
  clasificaciones: {
    categoria_id: number;
    categoria: string;
    subcategoria_id: number;
    subcategoria: string;
    confianza: number;
    motivos: string[];
  }[];
  prioridad: string;
  prioridad_id: number | null;
  prioridad_confianza: number;
  prioridad_motivos: string[];
  responsable: UsuarioResumen | null;
}

export interface Riesgo {
  ticket_id: number;
  numero: string;
  riesgo: number;
  nivel: string;
  motivos: string[];
}

export interface TextoIa {
  proveedor: string;
  texto: string;
}

// ---------------------------------------------------------------- administración
export interface UsuarioAdmin {
  id: number;
  nombre: string;
  correo: string;
  usuario_ad: string | null;
  origen_autenticacion: "LOCAL" | "AD" | "ENTRA";
  cargo: string | null;
  telefono: string | null;
  area_id: number | null;
  rol_id: number;
  rol: string;
  supervisor_id: number | null;
  activo: boolean;
  bloqueado: boolean;
  ultimo_login: string | null;
}

export interface Rol {
  id: number;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  permisos: string[];
}

export interface PermisoCat {
  codigo: string;
  modulo: string;
  descripcion: string;
}

export interface Tramo {
  dia_semana: number;
  hora_inicio: string;
  hora_fin: string;
}

export interface Horario {
  id: number;
  nombre: string;
  zona_horaria: string;
  tramos: Tramo[];
}

export interface ExcepcionCalendario {
  id: number;
  fecha: string;
  tipo: "FERIADO" | "HORARIO_ESPECIAL";
  hora_inicio: string | null;
  hora_fin: string | null;
  descripcion: string;
}

export interface PoliticaSla {
  id: number;
  categoria_id: number;
  prioridad_id: number;
  sla_respuesta_min: number;
  sla_resolucion_min: number;
  activo: boolean;
}

export interface ConfiguracionItem {
  clave: string;
  valor: string;
  descripcion: string | null;
}

export interface Auditoria {
  id: number;
  usuario_id: number | null;
  usuario_correo: string | null;
  fecha_hora: string;
  accion: string;
  entidad: string | null;
  entidad_id: string | null;
  detalle: string | null;
  ip: string | null;
  equipo: string | null;
  resultado: string;
}

// ------------------------------------------------------------------- reportes
export interface FiltroReporte {
  desde?: string;
  hasta?: string;
  categoria_id?: number;
  responsable_id?: number;
  cliente_id?: number;
  estado?: string;
  sla?: "CUMPLIDO" | "INCUMPLIDO" | "EN_CURSO";
}

export interface PuntoTendencia {
  periodo: string;
  tickets: number;
  cerrados: number;
  sla_cumplido: number;
  sla_incumplido: number;
  cumplimiento_sla_pct: number | null;
}

export interface Dashboard {
  filtro: { desde: string; hasta: string };
  widgets: {
    tickets_totales: number;
    tickets_abiertos: number;
    tickets_cerrados: number;
    tickets_escalados: number;
    tickets_vencidos: number;
    sla_cumplido: number;
    sla_incumplido: number;
    cumplimiento_sla_pct: number | null;
    tiempo_promedio_respuesta_h: number | null;
    tiempo_promedio_resolucion_h: number | null;
  };
  por_estado: Record<string, number>;
  por_prioridad: Record<string, number>;
  tendencia: PuntoTendencia[];
  agrupacion: string;
  top_categorias: { nombre: string; tickets: number }[];
  top_responsables: { nombre: string; tickets: number }[];
  en_riesgo: {
    id: number;
    numero: string;
    asunto: string;
    categoria: string;
    responsable: string | null;
    sla_consumido_pct: number;
    vence: string;
    estado: string;
  }[];
  satisfaccion?: Satisfaccion;
}

export interface Satisfaccion {
  total: number;
  promedio: number | null;
  respondidas_pct: number | null;
  tickets_resueltos: number;
  distribucion: Record<string, number>;
  satisfechos_pct: number | null;
  insatisfechos_pct: number | null;
  por_responsable: { nombre: string; promedio: number; encuestas: number }[];
  tendencia: { periodo: string; promedio: number; encuestas: number }[];
  comentarios: { ticket_id: number; numero: string; calificacion: number; comentario: string; responsable: string | null; fecha: string }[];
}

export interface IndicadorCategoria {
  categoria_id: number;
  categoria: string;
  color: string | null;
  tickets_recibidos: number;
  tickets_resueltos: number;
  tickets_pendientes: number;
  tickets_vencidos: number;
  cumplimiento_sla_pct: number | null;
  tiempo_promedio_respuesta_h: number | null;
  tiempo_promedio_resolucion_h: number | null;
  backlog: number;
}

export interface IndicadorResponsable {
  responsable_id: number;
  responsable: string;
  tickets_asignados: number;
  tickets_cerrados: number;
  tickets_abiertos: number;
  sla_cumplido: number;
  sla_incumplido: number;
  cumplimiento_sla_pct: number | null;
  productividad_dia: number;
  tiempo_promedio_resolucion_h: number | null;
  puntaje: number;
  ranking: number;
}

export interface IndicadorCliente {
  cliente_id: number | null;
  cliente: string;
  tickets: number;
  cumplimiento_sla_pct: number | null;
  categorias: { nombre: string; tickets: number }[];
  tendencia: { periodo: string; tickets: number }[];
}
