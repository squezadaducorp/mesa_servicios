import type { TokenSalida } from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "") + "/api/v1";

/** URL absoluta de un endpoint (para navegaciones del navegador, como el inicio de sesión con Microsoft). */
export const urlApi = (path: string) => `${BASE}${path}`;
const CLAVE_REFRESH = "aducorp.refresh";
const CLAVE_ACTIVIDAD = "aducorp.actividad"; // compartida entre pestañas

export class ApiError extends Error {
  status: number;
  errores?: { campo: string; mensaje: string }[];
  constructor(status: number, mensaje: string, errores?: { campo: string; mensaje: string }[]) {
    super(mensaje);
    this.status = status;
    this.errores = errores;
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

let accessToken: string | null = null;
let refreshEnCurso: Promise<TokenSalida | null> | null = null;
let alExpirarSesion: (motivo?: string) => void = () => {};
let motivoRechazo: string | undefined;
let alRenovar: (t: TokenSalida) => void = () => {};

export const sesion = {
  guardar(t: TokenSalida) {
    accessToken = t.access_token;
    try {
      localStorage.setItem(CLAVE_REFRESH, t.refresh_token);
    } catch {
      /* almacenamiento no disponible */
    }
  },
  limpiar() {
    accessToken = null;
    try {
      localStorage.removeItem(CLAVE_REFRESH);
      localStorage.removeItem(CLAVE_ACTIVIDAD);
      sessionStorage.clear(); // filtros de la sesión anterior: no deben pasar al siguiente usuario
    } catch {
      /* almacenamiento no disponible */
    }
  },
  refreshToken(): string | null {
    try {
      return localStorage.getItem(CLAVE_REFRESH);
    } catch {
      return null;
    }
  },
  /** Motivo con que el servidor rechazó la última renovación (p. ej. cierre por inactividad). */
  motivoRechazo(): string | undefined {
    return motivoRechazo;
  },
  alExpirar(fn: (motivo?: string) => void) {
    alExpirarSesion = fn;
  },
  alRenovar(fn: (t: TokenSalida) => void) {
    alRenovar = fn;
  },
};

/** Última interacción del usuario (clic, teclado, desplazamiento), compartida entre pestañas. */
export const actividad = {
  marcar(momento = Date.now()) {
    try {
      localStorage.setItem(CLAVE_ACTIVIDAD, String(momento));
    } catch {
      /* almacenamiento no disponible */
    }
  },
  ultima(): number | null {
    try {
      const v = Number(localStorage.getItem(CLAVE_ACTIVIDAD));
      return v > 0 ? v : null;
    } catch {
      return null;
    }
  },
};

export function construirQuery(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

function segundosInactivo(): number | undefined {
  const ultima = actividad.ultima();
  return ultima === null ? undefined : Math.max(0, Math.floor((Date.now() - ultima) / 1000));
}

/** Renueva el access token con el refresh token rotativo; una sola renovación concurrente. */
export async function renovar(): Promise<TokenSalida | null> {
  const rt = sesion.refreshToken();
  if (!rt) return null;
  if (!refreshEnCurso) {
    refreshEnCurso = fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt, inactivo_seg: segundosInactivo() }),
    })
      .then(async (r) => {
        if (!r.ok) {
          motivoRechazo = (await errorDesde(r)).message;
          return null;
        }
        motivoRechazo = undefined;
        const t = (await r.json()) as TokenSalida;
        sesion.guardar(t);
        alRenovar(t);
        return t;
      })
      .catch(() => null)
      .finally(() => {
        refreshEnCurso = null;
      });
  }
  return refreshEnCurso;
}

async function errorDesde(r: Response): Promise<ApiError> {
  let detalle = `Error ${r.status}`;
  let errores;
  try {
    const j = await r.json();
    if (typeof j.detail === "string") detalle = j.detail;
    errores = j.errores;
    if (errores?.length) detalle += ": " + errores.map((e: { campo: string; mensaje: string }) => `${e.campo} ${e.mensaje}`).join("; ");
  } catch {
    /* respuesta sin JSON */
  }
  if (r.status === 429) detalle = "Demasiadas solicitudes. Espere un momento.";
  return new ApiError(r.status, detalle, errores);
}

async function ejecutar(method: string, path: string, init: { body?: unknown; form?: FormData; query?: Query }, reintento = true): Promise<Response> {
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let body: BodyInit | undefined;
  if (init.form) body = init.form;
  else if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }
  const r = await fetch(`${BASE}${path}${construirQuery(init.query)}`, { method, headers, body });
  if (r.status === 401 && reintento && !path.startsWith("/auth/login") && !path.startsWith("/auth/2fa/")) {
    const t = await renovar();
    if (t) return ejecutar(method, path, init, false);
    sesion.limpiar();
    alExpirarSesion(motivoRechazo);
  }
  if (!r.ok) throw await errorDesde(r);
  return r;
}

export async function api<T>(method: string, path: string, init: { body?: unknown; form?: FormData; query?: Query } = {}): Promise<T> {
  const r = await ejecutar(method, path, init);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const get = <T>(path: string, query?: Query) => api<T>("GET", path, { query });
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, { body });
export const put = <T>(path: string, body?: unknown) => api<T>("PUT", path, { body });
export const patch = <T>(path: string, body?: unknown) => api<T>("PATCH", path, { body });
export const del = <T>(path: string) => api<T>("DELETE", path);

/** Trae un archivo autenticado como blob (vista previa de capturas). */
export async function obtenerBlob(path: string, query?: Query): Promise<Blob> {
  const r = await ejecutar("GET", path, { query });
  return r.blob();
}

/** Descarga un archivo autenticado (exportaciones, adjuntos) respetando el nombre que envía el servidor. */
export async function descargar(path: string, query?: Query, nombrePorDefecto = "archivo"): Promise<void> {
  const r = await ejecutar("GET", path, { query });
  const cd = r.headers.get("Content-Disposition") ?? "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const nombre = m ? decodeURIComponent(m[1]) : nombrePorDefecto;
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
