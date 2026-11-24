/** ISO 27001: política de acceso (37), revisión de accesos (38), servidor (40), vulnerabilidades (41), clasificación y retención (42). */
import type { PoliticaDosPasos } from "./cuarta";

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

// ------------------------------------------------------------ 37 política de acceso
export type EstadoDosPasosPriv = "ACTIVA" | "PENDIENTE" | "VENCIDA" | "EXENTA" | "OPCIONAL";

export interface PoliticaClaves {
  min_longitud: number;
  claves_previas: number;
  max_intentos: number;
  bloqueo_min: number;
  inactividad_min: number;
  aviso_bloqueo: boolean;
}

export interface AccesoPrivilegiado {
  id: number;
  nombre: string;
  correo: string;
  rol: string;
  estado: EstadoDosPasosPriv;
  metodo?: "APP" | "CORREO" | null;
  dias_restantes?: number | null;
  ultimo_login?: string | null;
}

export interface PoliticaAcceso {
  dos_pasos: PoliticaDosPasos;
  claves: PoliticaClaves;
  privilegiados: AccesoPrivilegiado[];
  resumen: { total: number; con_verificacion: number; pendientes: number; vencidos: number; exentos: number };
  correos_alerta: string;
}

// ------------------------------------------------------------ 40 servidor
export type EstadoControl = "ok" | "alerta" | "sin_dato" | "opcional";

export interface ControlServidor {
  clave: string;
  nombre: string;
  detalle?: string;
  estado: EstadoControl;
  etiqueta?: string;
  iso?: string;
}

export interface EstadoServidor {
  disponible: boolean;
  archivo: string;
  script: string;
  error?: string;
  generado?: string | null;
  antiguedad_horas?: number | null;
  desactualizado?: boolean;
  servidor?: { nombre?: string; instancia?: string; tipo?: string; region?: string; zona?: string; so?: string; kernel?: string };
  parches?: { pendientes?: number; reinicio?: boolean };
  controles?: ControlServidor[];
  cumplidos?: number;
  total?: number;
}

// ------------------------------------------------------------ 41 vulnerabilidades
export type Severidad = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface Hallazgo {
  imagen: string;
  id: string;
  severidad: Severidad;
  paquete: string;
  instalada?: string;
  corregida?: string;
  titulo?: string;
}

export interface AlertaDependabot {
  numero: number;
  severidad: Severidad;
  paquete?: string;
  ecosistema?: string;
  resumen?: string;
  manifiesto?: string;
  corregida?: string | null;
  creada?: string | null;
  vence?: string | null;
  url?: string;
}

export interface EstadoVulnerabilidades {
  configurado: boolean;
  repo: string;
  enlace: string;
  plazos: Record<"CRITICAL" | "HIGH" | "MEDIUM", number>;
  error?: string;
  actualizado?: string;
  escaneo?: { fecha?: string | null; estado?: string; conclusion?: string | null; url?: string; evento?: string; jobs: { nombre: string; conclusion?: string | null }[] };
  ci?: { conclusion?: string | null; fecha?: string | null; url?: string } | null;
  componentes?: { imagen: string; nombre: string; critica: number; alta: number; media: number; hallazgos: Hallazgo[] }[];
  dependabot?: { alertas: AlertaDependabot[]; prs_abiertos: number; por_severidad: Record<Severidad, number> };
  totales?: { CRITICAL: number; HIGH: number };
  hallazgos?: Hallazgo[];
}
