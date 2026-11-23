/** Tipos de la tercera ronda: aprobaciones (21), vínculos (22), lote y traspaso (23), avisos generales (24) y seguimiento (20). */

export interface AprobacionTicket {
  id: number;
  nivel: number;
  estado: "PENDIENTE" | "APROBADO" | "RECHAZADO" | "REASIGNADO" | "ANULADO";
  comentario: string | null;
  fecha_solicitud: string;
  fecha_respuesta: string | null;
  aprobador: string;
  aprobador_id: number;
  en_lugar_de: string | null;
  regla: string | null;
}

export interface Aprobacion extends AprobacionTicket {
  ticket: {
    id: number; numero: string; asunto: string; descripcion: string; categoria: string; subcategoria: string; estado: string;
    solicitante: string; area: string | null; creado_por: string | null; motivo: string | null; fecha_creacion: string;
  };
}

export interface BandejaAprobaciones {
  pendientes: Aprobacion[];
  aprobadas_30d: number;
  rechazadas_30d: number;
  minutos_respuesta_promedio: number | null;
  recientes: Aprobacion[];
}

export type TipoAprobador = "JEFE_DIRECTO" | "SUPERVISOR_CATEGORIA" | "PERSONA";

export interface ReglaAprobacion {
  id: number;
  categoria_id: number;
  categoria: string;
  subcategoria_id: number | null;
  subcategoria: string | null;
  nivel1_tipo: TipoAprobador;
  nivel1_usuario_id: number | null;
  nivel1: string;
  nivel2_tipo: TipoAprobador | null;
  nivel2_usuario_id: number | null;
  nivel2: string | null;
  recordar_horas: number;
  escalar_horas: number | null;
  escalar_a_id: number | null;
  escalar_a: string | null;
  usar_reemplazo: boolean;
  auto_si_aprobador: boolean;
  activo: boolean;
  restringida_en_nombre: boolean;
}

export interface JefesDirectos {
  total: number;
  completos: number;
  faltan: { id: number; nombre: string; area: string | null }[];
}

export interface TicketCorto {
  id: number;
  numero: string;
  asunto: string;
  estado: string;
  estado_nombre?: string;
}

export interface Vinculo {
  id: number;
  tipo: "RELACIONADO" | "DUPLICADO" | "BLOQUEADO_POR";
  etiqueta: string;
  desde_este: boolean;
  ticket: TicketCorto;
  fecha: string;
}

export interface PosibleDuplicado {
  id: number;
  numero: string;
  asunto: string;
  solicitante: string;
  estado: string;
  fecha_creacion: string;
  puntaje: number;
  razones: string[];
}

export interface AvisoDeTicket {
  id: number;
  codigo: string;
  titulo: string;
  estado: string;
  estado_nombre: string;
  maestro: boolean;
}

export interface ExtrasTercera {
  aprobaciones?: AprobacionTicket[];
  aprobacion_pendiente_id?: number | null;
  vinculos?: Vinculo[];
  duplicado_de?: { id: number; numero: string } | null;
  avisos?: AvisoDeTicket[];
  seguimiento_url?: string | null;
  servicio?: import("./cuarta").ServicioTicket | null;
}

export interface LoteResultado {
  ok: string[];
  sin_cambio: string[];
  errores: { numero: string; error: string }[];
}

export interface PlanTraspaso {
  origen: { id: number; nombre: string; abiertos: number };
  tickets: { id: number; numero: string; asunto: string; estado: string; categoria: string; vence: string; destino_id: number | null; destino: string }[];
  destinos: { id: number; nombre: string; tiene: number; recibe: number }[];
  recurrentes: number;
  aprobaciones: number;
  jefe: { id: number; nombre: string } | null;
}

export type EstadoAviso = "INVESTIGANDO" | "IDENTIFICADO" | "MONITOREANDO" | "RESUELTO";

export interface AvisoGeneral {
  id: number;
  codigo: string;
  titulo: string;
  mensaje: string;
  sistema: string;
  palabras_clave: string | null;
  area_ids: number[];
  mostrar_publico: boolean;
  estado: EstadoAviso;
  estado_nombre: string;
  inicio: string;
  fin: string | null;
  duracion: string;
  proxima_novedad: string | null;
  ticket_maestro: { id: number; numero: string } | null;
  afectados: number;
  tickets: number;
  con_comentario: number;
  ultima_actualizacion: string;
  me_afecta: boolean;
  actualizaciones?: { id: number; estado: EstadoAviso; estado_nombre: string; texto: string; usuario: string | null; fecha: string }[];
}

export interface AvisosAdmin {
  activos: AvisoGeneral[];
  historial: AvisoGeneral[];
  resumen: { sistema: string; caidas: number; minutos: number }[];
  anio: number;
}

export interface AvisoPublico {
  id: number;
  titulo: string;
  mensaje: string;
  estado_nombre: string;
  inicio: string;
  ultima_actualizacion: string;
}

export interface SeguimientoVista {
  numero: string;
  asunto: string;
  estado: string;
  estado_nombre: string;
  pasos: string[];
  paso: number;
  cancelado: boolean;
  responsable: string | null;
  responsable_area: string | null;
  respuesta_estimada: string | null;
  solicitado_por: string;
  fecha_creacion: string;
  esperando_su_respuesta: boolean;
  conversacion: { autor: string; propio: boolean; texto: string; fecha: string }[];
  adjuntos: { nombre: string; propio: boolean; fecha: string }[];
  puede_responder: boolean;
  encuesta_url: string | null;
  vigencia_dias: number;
}

export const COLOR_AVISO: Record<EstadoAviso, string> = {
  INVESTIGANDO: "#C62828",
  IDENTIFICADO: "#E65100",
  MONITOREANDO: "#B57400",
  RESUELTO: "#2E7D32",
};
