/** Tipos de la ronda 4, parte 2: problemas (30), panel gerencial (32), control de tiempo (31) y proveedores (33). */

// ============================================================ 30 problemas
export type EstadoProblema = "DETECTADO" | "EN_ANALISIS" | "ERROR_CONOCIDO" | "SOLUCION_EN_CAMBIO" | "CERRADO";

export interface ProblemaCorto {
  id: number;
  numero: string;
  titulo: string;
  estado: EstadoProblema;
  estado_nombre: string;
}

export interface ProblemaLista extends ProblemaCorto {
  incidentes: number;
  responsable: string | null;
  dias_abierto: number | null;
  fecha_creacion: string;
  categoria: string | null;
}

export interface Porque {
  pregunta: string;
  respuesta: string;
}

export interface IncidenteProblema {
  id: number;
  numero: string;
  asunto: string;
  estado: string;
  estado_nombre: string;
  solicitante: string;
  fecha: string;
  con_solucion: boolean;
}

export interface ProblemaDetalle extends ProblemaLista {
  descripcion: string | null;
  origen: "MANUAL" | "PATRON";
  categoria_id: number | null;
  subcategoria_id: number | null;
  subcategoria: string | null;
  responsable_id: number | null;
  porques: Porque[];
  causa_raiz: string | null;
  solucion_definitiva: string | null;
  solucion_temporal: string | null;
  palabras_clave: string | null;
  nota_cierre: string | null;
  articulo: { id: number; titulo: string; estado: string } | null;
  cambio: { id: number; numero: string; titulo: string; estado: string; ventana_inicio: string | null } | null;
  cambio_id: number | null;
  fecha_causa: string | null;
  fecha_cierre: string | null;
  incidentes_lista: IncidenteProblema[];
  impacto: { incidentes: number; personas: number; horas: number; evitados: number };
  gestor: boolean;
}

export interface PatronDetectado {
  firma: string;
  cantidad: number;
  dias: number;
  titulo: string;
  palabras: string;
  areas: string[];
  categoria_id: number;
  subcategoria_id: number;
  subcategoria: string;
  tickets: { id: number; numero: string; asunto: string }[];
}

export interface ResumenProblemas {
  abiertos: number;
  errores_conocidos: number;
  evitados_mes: number;
  dias_hasta_causa: number | null;
}

export interface OpcionesProblema {
  responsables: { id: number; nombre: string }[];
  cambios: { id: number; numero: string; titulo: string; estado: string }[];
  estados: Record<EstadoProblema, string>;
}

export interface ProblemasDelTicket {
  problemas: ProblemaCorto[];
  coincidencias: (ProblemaCorto & { solucion_temporal: string; puntaje: number })[];
}

// ============================================================ 32 panel gerencial
export interface PanelDatos {
  anio: number;
  mes: number;
  titulo: string;
  mes_anterior: string;
  area: string | null;
  kpis: {
    recibidos: number;
    recibidos_var: number | null;
    resueltos: number;
    abiertos: number;
    cumplimiento: number | null;
    cumplimiento_var: number | null;
    satisfaccion: number | null;
    satisfaccion_var: number | null;
    encuestas: number;
    tiempo_medio_min: number | null;
    tiempo_medio_var: number | null;
  };
  serie: { anio: number; mes: number; etiqueta: string; tickets: number }[];
  tipos: { nombre: string; cantidad: number; pct: number }[];
  areas: { area: string; pct: number | null; nuevos: number; resueltos: number; vencidos: number }[];
  atencion: { titulo: string; texto: string }[];
  problemas: { numero: string; titulo: string; estado: string; incidentes: number; dias: number }[];
  cambios: { numero: string; titulo: string; resultado: string | null; fecha: string }[];
  meta_sla: number;
  puede_configurar: boolean;
}

export type SeccionPanel = "indicadores" | "tendencia" | "sla_area" | "satisfaccion" | "problemas" | "cambios" | "proveedores" | "horas";

export interface PanelEnvioConfig {
  activo: boolean;
  destinatarios: string[];
  cuando: "PRIMER_HABIL" | "DIA_1";
  hora: string;
  secciones: SeccionPanel[];
  comentario: string;
}

export interface PanelEnvioInfo {
  config: PanelEnvioConfig;
  secciones: Record<SeccionPanel, string>;
  envios: { id: number; periodo: string; archivo: string; fecha: string; destinatarios: string; es_prueba: boolean; estado: string | null }[];
  proximo: string | null;
  puede_configurar: boolean;
}
