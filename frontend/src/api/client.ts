import type { TokenSalida } from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "") + "/api/v1";
const CLAVE_REFRESH = "aducorp.refresh";

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
let alExpirarSesion: () => void = () => {};
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
  alExpirar(fn: () => void) {
    alExpirarSesion = fn;
  },
  alRenovar(fn: (t: TokenSalida) => void) {
    alRenovar = fn;
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

/** Renueva el access token con el refresh token rotativo; una sola renovación concurrente. */
export async function renovar(): Promise<TokenSalida | null> {
  const rt = sesion.refreshToken();
  if (!rt) return null;
  if (!refreshEnCurso) {
    refreshEnCurso = fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    })
      .then(async (r) => {
        if (!r.ok) return null;
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
  if (r.status === 401 && reintento && !path.startsWith("/auth/login")) {
    const t = await renovar();
    if (t) return ejecutar(method, path, init, false);
    sesion.limpiar();
    alExpirarSesion();
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
