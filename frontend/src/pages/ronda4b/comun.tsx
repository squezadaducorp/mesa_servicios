import { Chip } from "@mui/material";

const ESTADO: Record<string, { bg: string; c: string; b: string }> = {
  DETECTADO: { bg: "#EEF2F7", c: "#3E4A5C", b: "#CBD3DE" },
  EN_ANALISIS: { bg: "#E6F3FB", c: "#0B6AA2", b: "#9FD0EE" },
  ERROR_CONOCIDO: { bg: "#F1EAFB", c: "#5B2E9E", b: "#C9B2EC" },
  SOLUCION_EN_CAMBIO: { bg: "#FDEEE6", c: "#C2410C", b: "#F6B999" },
  CERRADO: { bg: "#E8F5E9", c: "#2E7D32", b: "#A5D6A7" },
};

export function EstadoProblemaChip({ estado, nombre }: { estado: string; nombre: string }) {
  const e = ESTADO[estado] ?? ESTADO.DETECTADO;
  return <Chip size="small" label={nombre} sx={{ bgcolor: e.bg, color: e.c, border: `1px solid ${e.b}`, fontWeight: 600 }} />;
}

/** «1 h 37 min», «42 min», «3 días». */
export function duracionCorta(min?: number | null): string {
  if (min === null || min === undefined) return "—";
  const m = Math.round(min);
  const h = Math.floor(m / 60);
  if (h >= 48) return `${Math.floor(h / 24)} días`;
  return h ? `${h} h ${String(m % 60).padStart(2, "0")} min` : `${m} min`;
}
