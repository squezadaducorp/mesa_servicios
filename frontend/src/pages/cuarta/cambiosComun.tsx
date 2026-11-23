import { Chip } from "@mui/material";

const ZONA = "America/Guayaquil";
const fDia = new Intl.DateTimeFormat("es-EC", { timeZone: ZONA, weekday: "short", day: "2-digit", month: "2-digit" });
const fHora = new Intl.DateTimeFormat("es-EC", { timeZone: ZONA, hour: "2-digit", minute: "2-digit", hour12: false });
const fDiaLargo = new Intl.DateTimeFormat("es-EC", { timeZone: ZONA, weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace(".", "").replace(",", "");
/** «Sáb 29/11 08:00» */
export const diaHora = (iso?: string | null) => (iso ? `${cap(fDia.format(new Date(iso)))} ${fHora.format(new Date(iso))}` : "—");
export const hora = (iso: string) => fHora.format(new Date(iso));
/** «Sábado 29/11/2026 · 08:00 a 12:00» */
export const ventanaLarga = (ini?: string | null, fin?: string | null) =>
  ini && fin ? `${cap(fDiaLargo.format(new Date(ini)))} · ${hora(ini)} a ${hora(fin)}` : "Sin ventana";

/** Valor para <input type="datetime-local"> en la hora de Ecuador. */
export function aLocal(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })
    .formatToParts(d).reduce<Record<string, string>>((a, x) => ({ ...a, [x.type]: x.value }), {});
  return `${p.year}-${p.month}-${p.day}T${p.hour === "24" ? "00" : p.hour}:${p.minute}`;
}
/** El valor de datetime-local se interpreta en hora de Ecuador (UTC−5, sin horario de verano). */
export const deLocal = (v: string) => (v ? `${v}:00-05:00` : null);

const ESTADO: Record<string, { bg: string; c: string; b: string }> = {
  SOLICITADO: { bg: "#EEF2F7", c: "#3E4A5C", b: "#CBD3DE" },
  EN_ESPERA: { bg: "#EEF2F7", c: "#3E4A5C", b: "#CBD3DE" },
  EN_APROBACION: { bg: "#FFF3D6", c: "#8A5A00", b: "#F2C14E" },
  PROGRAMADO: { bg: "#F1EAFB", c: "#5B2E9E", b: "#C9B2EC" },
  EN_REVISION: { bg: "#E6F3FB", c: "#0B6AA2", b: "#9FD0EE" },
  IMPLEMENTADO: { bg: "#E8F5E9", c: "#2E7D32", b: "#A5D6A7" },
  REVERTIDO: { bg: "#FDECEA", c: "#B3261E", b: "#F2B8B5" },
  RECHAZADO: { bg: "#F3F3F3", c: "#8A8A8A", b: "#D6D6D6" },
};

export function EstadoCambio({ estado, nombre }: { estado: string; nombre: string }) {
  const e = ESTADO[estado] ?? ESTADO.SOLICITADO;
  return <Chip size="small" label={nombre} sx={{ bgcolor: e.bg, color: e.c, border: `1px solid ${e.b}`, fontWeight: 600 }} />;
}

const RIESGO: Record<string, { t: string; bg: string; c: string; b: string }> = {
  BAJO: { t: "Riesgo bajo", bg: "#E8F5E9", c: "#2E7D32", b: "#A5D6A7" },
  MEDIO: { t: "Riesgo medio", bg: "#FFF3D6", c: "#8A5A00", b: "#F2C14E" },
  ALTO: { t: "Riesgo alto", bg: "#FDECEA", c: "#B3261E", b: "#F2B8B5" },
};

export function RiesgoChip({ riesgo }: { riesgo: string | null }) {
  if (!riesgo) return <>—</>;
  const r = RIESGO[riesgo];
  return <Chip size="small" label={r.t} sx={{ bgcolor: r.bg, color: r.c, border: `1px solid ${r.b}`, fontWeight: 600 }} />;
}

export const TIPO_CAMBIO: Record<string, string> = { ESTANDAR: "Estándar", NORMAL: "Normal", EMERGENCIA: "Emergencia" };

export function TipoCambio({ tipo }: { tipo: string | null }) {
  if (!tipo) return <>—</>;
  if (tipo === "EMERGENCIA") return <Chip size="small" color="error" label="Emergencia" sx={{ fontWeight: 600 }} />;
  return <>{TIPO_CAMBIO[tipo] ?? tipo}</>;
}

export const MATRIZ: Record<string, Record<string, string>> = {
  ALTO: { BAJA: "MEDIO", MEDIA: "MEDIO", ALTA: "ALTO" },
  MEDIO: { BAJA: "BAJO", MEDIA: "MEDIO", ALTA: "ALTO" },
  BAJO: { BAJA: "BAJO", MEDIA: "BAJO", ALTA: "MEDIO" },
};
export const COLOR_CELDA: Record<string, string> = { BAJO: "#DCEFD9", MEDIO: "#FDEBD0", ALTO: "#F7D4D2" };
