/** Tipos de control de tiempo (31), proveedores (33), visualizadores (34) y artículos internos/externos (35). */

// ------------------------------------------------------------------ 31 tiempo
export interface RegistroTiempo {
  id: number;
  actividad: string;
  estado: "CORRIENDO" | "PAUSADO" | "GUARDADO";
  segundos: number;
  minutos: number;
  corriendo_desde: string | null;
  desde_texto: string | null;
  manual: boolean;
  fecha: string;
  usuario: { id: number; nombre: string };
  propio: boolean;
  editable: boolean;
  tipo: "ticket" | "problema" | "cambio";
  numero: string;
  ruta: string;
}

export interface TiempoObjeto {
  registros: RegistroTiempo[];
  total_min: number;
  activo: RegistroTiempo | null;
  estimado_min: number | null;
  facturable: boolean;
  en_atencion: boolean;
}

export interface ReporteHoras {
  desde: string;
  hasta: string;
  nombre: string;
  semanas: { desde: string; nombre: string }[];
  horas_disponibles: number;
  kpis: { minutos: number; tickets: number; promedio_min: number | null; ocupacion_pct: number | null; facturable_min: number };
  analistas: {
    id: number; nombre: string; tickets: number; minutos: number; min_incidentes: number; min_cambios: number;
    horas_por_ticket: number | null; ocupacion_pct: number | null;
  }[];
  areas: { nombre: string; minutos: number; pct: number }[];
  categorias: { nombre: string; minutos: number }[];
}

// ------------------------------------------------------------------ 33 proveedores
export type Cumplimiento = "CUMPLE" | "AL_LIMITE" | "INCUMPLE";

export interface ProveedorFila {
  id: number;
  nombre: string;
  servicio: string;
  contrato_numero: string | null;
  contrato_vence: string | null;
  dias_para_vencer: number | null;
  atencion_24x7: boolean;
  plazo_horas: number;
  plazo: string;
  multa_texto: string | null;
  contacto: string | null;
  telefono: string | null;
  correo: string | null;
  activo: boolean;
  casos_abiertos: number;
  solucion_promedio_min: number | null;
  cumplimiento: Cumplimiento;
}

export interface CasoProveedor {
  id: number;
  proveedor_id: number;
  proveedor: string;
  servicio: string;
  numero_caso: string | null;
  reporte: string;
  medio: string | null;
  contacto: string | null;
  estado: "ABIERTO" | "RESUELTO";
  fecha_reporte: string;
  vence: string;
  fecha_solucion: string | null;
  minutos_solucion: number | null;
  cumplido: boolean | null;
  vencido: boolean;
  solucion: string | null;
  correo_enviado: boolean;
  ticket_id: number;
  ticket_numero: string;
  ticket_asunto: string;
  plazo: string;
  multa: number;
}

export interface ProveedorDetalle extends ProveedorFila {
  correos_copia: string[];
  portal: string | null;
  contrato_detalle: string | null;
  valor_mensual: number | null;
  multa_pct_hora: number | null;
  notas: string | null;
  subcategorias: number[];
  subcategorias_nombres: string[];
  anio: number;
  meses: { mes: number; letra: string; casos: number; fuera: number }[];
  caidas_anio: number;
  fuera_plazo_anio: number;
  multas_anio: number;
  casos: CasoProveedor[];
}

export interface ProveedoresLista {
  proveedores: ProveedorFila[];
  alertas: { id: number; nombre: string; contrato_vence: string; dias: number; fuera_mes: number; avisado: boolean }[];
  aviso_correo: string[];
}

export interface ProveedorParaTicket extends ProveedorFila {
  sugerido: boolean;
  caida_mes: number;
  vence_caso: string;
  medios: string[];
}

// ------------------------------------------------------------------ 34 visualizadores
export type AvisosCorreo = "TODO" | "ESTADO" | "NINGUNO";

export interface Visualizador {
  usuario_id: number;
  nombre: string;
  cargo: string | null;
  area: string | null;
  avisos_correo: AvisosCorreo;
  origen: "MANUAL" | "SEGUIR" | "CATEGORIA";
  agregado_por: string | null;
  fecha: string;
  propio: boolean;
  editable: boolean;
}
