const ZONA = "America/Guayaquil";

const fFechaHora = new Intl.DateTimeFormat("es-EC", { timeZone: ZONA, dateStyle: "short", timeStyle: "short" });
const fFecha = new Intl.DateTimeFormat("es-EC", { timeZone: ZONA, dateStyle: "medium" });
const fNumero = new Intl.NumberFormat("es-EC", { maximumFractionDigits: 1 });

export const fechaHora = (iso?: string | null) => (iso ? fFechaHora.format(new Date(iso)) : "—");
export const fecha = (iso?: string | null) => (iso ? fFecha.format(new Date(iso)) : "—");
export const numero = (n?: number | null) => (n === null || n === undefined ? "—" : fNumero.format(n));
export const pct = (n?: number | null) => (n === null || n === undefined ? "—" : `${fNumero.format(n)} %`);
export const horas = (n?: number | null) => (n === null || n === undefined ? "—" : `${fNumero.format(n)} h`);

/** Minutos laborables a texto ("1 h 30 min"). */
export function duracion(min?: number | null): string {
  if (min === null || min === undefined) return "—";
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function tamanoArchivo(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export function tiempoRelativo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "hace un momento";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  if (s < 86400 * 7) return `hace ${Math.floor(s / 86400)} d`;
  return fecha(iso);
}

export const hoyIso = () => new Date().toLocaleDateString("en-CA", { timeZone: ZONA });
export function haceDias(d: number) {
  const x = new Date();
  x.setDate(x.getDate() - d);
  return x.toLocaleDateString("en-CA", { timeZone: ZONA });
}
