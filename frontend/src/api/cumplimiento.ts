/** ISO 27001: revisión de accesos (38) y clasificación y retención (42). */

export type Decision = "MANTENER" | "AJUSTAR" | "BAJA";
export type Clasificacion = "PUBLICA" | "INTERNA" | "CONFIDENCIAL";

export const NOMBRE_CLASIFICACION: Record<Clasificacion, string> = { PUBLICA: "Pública", INTERNA: "Interna", CONFIDENCIAL: "Confidencial" };

export interface AlertaAcceso {
  codigo: string;
  texto: string;
}

export interface ItemRevision {
  id: number;
  usuario_id: number;
  nombre: string;
  correo: string;
  cargo?: string | null;
  area?: string | null;
  rol: string;
  jefe_id?: number | null;
  jefe?: string | null;
  ultimo_login?: string | null;
  alertas: AlertaAcceso[];
  decision?: Decision | null;
  comentario?: string | null;
  decidido_por?: string | null;
  fecha_decision?: string | null;
  aplicado: boolean;
  activo: boolean;
}

export interface Revision {
  id: number;
  periodo: string;
  estado: "ABIERTA" | "APROBADA";
  fecha_creacion: string;
  fecha_limite: string;
  fecha_aprobacion?: string | null;
  aprobada_por?: string | null;
  observacion?: string | null;
  total: number;
  revisadas: number;
  items?: ItemRevision[];
}

export interface PendientesAcceso {
  revision_id: number | null;
  periodo?: string;
  fecha_limite?: string;
  pendientes: number;
}

export interface CuentaInactiva {
  id: number;
  nombre: string;
  correo: string;
  rol: string;
  ultimo_login?: string | null;
  dias: number;
  aviso_enviado?: string | null;
  baja_el?: string | null;
  excluida?: string | null;
}

export interface ResumenRetencion {
  anios: number;
  clasificacion: Record<Clasificacion, number>;
  retencion_legal: number;
  depurados: number;
  por_depurar: number;
  muestra: { id: number; numero: string; asunto: string; categoria?: string | null; estado: string; fecha_cierre?: string | null; clasificacion: Clasificacion }[];
}
