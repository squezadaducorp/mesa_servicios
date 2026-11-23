/** Tipos de la ronda 4: catálogo de servicios (26), gestión de cambios (27) y verificación en dos pasos (28). */

export type TipoCampo = "texto" | "parrafo" | "fecha" | "numero" | "cedula" | "correo" | "telefono" | "area" | "usuario" | "lista";

export interface CampoServicio {
  clave: string;
  etiqueta: string;
  tipo: TipoCampo;
  requerido: boolean;
  opciones: string[];
  ancho: number;
  aprobador: boolean;
  ayuda?: string | null;
}

export interface OpcionServicio {
  clave: string;
  etiqueta: string;
  tarea?: string | null;
  responsable_id?: number | null;
  responsable?: string | null;
  marcado: boolean;
  siempre: boolean;
  aviso?: string | null;
}

export interface Servicio {
  id: number;
  nombre: string;
  descripcion: string;
  icono: string;
  grupo: string;
  plazo_horas: number;
  plazo_texto?: string | null;
  plazo: string;
  requiere_aprobacion: boolean;
  lo_pide: string;
  orden: number;
  activo: boolean;
  categoria_id: number;
  subcategoria_id: number;
  categoria: string;
  subcategoria: string;
  titulo_campos?: string | null;
  titulo_opciones?: string | null;
  aviso?: string | null;
  campos?: CampoServicio[];
  opciones?: OpcionServicio[];
  responsable_categoria?: string | null;
}

export interface MiSolicitud {
  ticket_id: number;
  numero: string;
  servicio: string;
  detalle: string | null;
  estado: string;
  avance: string;
  tareas: number;
  tareas_listas: number;
  fecha_creacion: string;
}

export interface CatalogoRespuesta {
  servicios: Servicio[];
  grupos: string[];
  mis_solicitudes: MiSolicitud[];
}

export interface OpcionesFormulario {
  areas: { id: number; nombre: string }[];
  usuarios: { id: number; nombre: string; cargo: string | null; area: string | null }[];
}

export interface TareaTicket {
  id: number;
  titulo: string;
  estado: "PENDIENTE" | "LISTA";
  responsable: string | null;
  responsable_id: number | null;
  fecha_completada: string | null;
  completada_por?: string | null;
  puede_marcar: boolean;
}

export interface ServicioTicket {
  servicio: string;
  servicio_id: number;
  plazo: string;
  respuestas: { clave: string; etiqueta: string; valor: string }[];
  tareas: TareaTicket[];
}

// ---------------------------------------------------------------- cambios
export interface Persona {
  id: number;
  nombre: string;
  cargo: string | null;
  area: string | null;
  correo: string;
}

export interface CambioLista {
  id: number;
  numero: string;
  titulo: string;
  formato: "MESA" | "GENERAL";
  tipo_cambio: string | null;
  riesgo: string | null;
  estado: string;
  estado_nombre: string;
  ventana_inicio: string | null;
  ventana_fin: string | null;
  solicitante: string;
  aplicacion: string | null;
  fecha_creacion: string;
  prioridad_sugerida: string | null;
}

export interface ResumenCambios {
  por_aprobar: number;
  programados: number;
  implementados_anio: number;
  anio: number;
  exitosos_pct: number | null;
}

export interface Congelamiento {
  id: number | null;
  titulo: string;
  inicio?: string;
  fin?: string;
  automatico: boolean;
  motivo?: string | null;
}

export interface CambioCalendario {
  id: number;
  numero: string;
  titulo: string;
  estado: string;
  riesgo: string | null;
  tipo: string | null;
  inicio: string;
  fin: string;
}

export interface Calendario {
  desde: string;
  hasta: string;
  dias: { fecha: string; cambios: CambioCalendario[]; congelamientos: Congelamiento[] }[];
}

export interface AprobacionCambio {
  id: number;
  rol: "JEFE_TI" | "GERENCIA";
  estado: string;
  comentario: string | null;
  aprobador: Persona | null;
  fecha_solicitud: string;
  fecha_respuesta: string | null;
  recordado: boolean;
}

export interface Cambio extends Omit<CambioLista, "solicitante"> {
  telefono: string | null;
  tipo_solicitud: string;
  partes: string[] | null;
  pantalla: string | null;
  desde_donde: string | null;
  ticket_relacionado: string | null;
  situacion_actual: string;
  situacion_deseada: string;
  justificacion: string;
  beneficiados: string | null;
  clasificacion: string | null;
  impacto: string | null;
  probabilidad: string | null;
  esfuerzo: string | null;
  prioridad_ti: string | null;
  evaluacion: string | null;
  plan_implementacion: string | null;
  plan_reversion: string | null;
  version_ref: string | null;
  resultado: string | null;
  probado_solicitante: boolean | null;
  observaciones: string | null;
  motivo: string | null;
  fecha_evaluacion: string | null;
  fecha_implementado: string | null;
  fecha_informado: string | null;
  fecha_actualizacion: string | null;
  solicitante: Persona;
  responsable: Persona | null;
  evaluado_por: Persona | null;
  aprobaciones: AprobacionCambio[];
  historial: { id: number; accion: string; detalle: string | null; usuario: string | null; fecha: string }[];
  adjuntos: { id: number; nombre: string; tamano_bytes: number; fecha: string }[];
  choques: { id: number; numero: string; titulo: string }[];
  congelado: string[];
  acciones: string[];
  aprobacion_pendiente_id: number | null;
  jefe_ti: Persona | null;
  gerencia: Persona | null;
  textos: Record<string, string | null>;
}

export interface OpcionesCambio {
  aplicaciones: string[];
  responsables: { id: number; nombre: string }[];
  jefe_ti: string | null;
  gerencia: string | null;
  estados: Record<string, string>;
  textos: Record<string, Record<string, string>>;
  congelamientos: Congelamiento[];
  gestor: boolean;
}

// ---------------------------------------------------------------- 2FA
export interface SegundoPaso {
  desafio: string;
  modo: "VERIFICAR" | "ACTIVAR";
  metodo: "APP" | "CORREO" | null;
  nombre: string;
  correo_mascara: string;
  puede_correo: boolean;
  codigo_enviado: boolean;
  dias_confianza: number;
}

export interface EstadoDosPasos {
  metodo: "APP" | "CORREO" | null;
  fecha: string | null;
  exigida: boolean;
  puede_correo: boolean;
  correo_mascara: string;
  codigos_restantes: number;
  equipos_confianza: number;
  dias_confianza: number;
  local: boolean;
}

export interface Activacion {
  metodo: "APP" | "CORREO";
  clave?: string;
  uri?: string;
  qr?: string;
  enviado_a?: string;
}

export interface PoliticaDosPasos {
  obligatoria_admin: boolean;
  obligatoria_analistas: boolean;
  opcional_otros: boolean;
  permitir_correo: boolean;
  solo_fuera_oficina: boolean;
  redes_oficina: string;
  dias_confianza: number;
  exentos: string[];
  correo_activo?: boolean;
  dias_gracia?: number;
}

export interface EstadoUsuarioDosPasos {
  id: number;
  nombre: string;
  correo: string;
  rol: string;
  rol_codigo: string;
  metodo: string | null;
  fecha: string | null;
  exigida: boolean;
  exento: boolean;
  pendiente_dias: number | null;
  codigos_restantes: number | null;
}
