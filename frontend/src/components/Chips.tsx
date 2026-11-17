import { Box, Chip, LinearProgress, Tooltip, Typography } from "@mui/material";
import PauseCircleOutlinedIcon from "@mui/icons-material/PauseCircleOutlined";
import type { CumplimientoSla } from "../api/types";

export const COLOR_ESTADO: Record<string, string> = {
  POR_APROBAR: "#B57400",
  NUEVO: "#1367AC",
  ASIGNADO: "#5E35B1",
  EN_PROCESO: "#0288D1",
  PENDIENTE_CLIENTE: "#F9A825",
  ESCALADO: "#E65100",
  RESUELTO: "#2E7D32",
  CERRADO: "#546E7A",
  CANCELADO: "#9E9E9E",
};

export const NOMBRE_ESTADO: Record<string, string> = {
  POR_APROBAR: "Por aprobar",
  NUEVO: "Nuevo",
  ASIGNADO: "Asignado",
  EN_PROCESO: "En Proceso",
  PENDIENTE_CLIENTE: "Pendiente Cliente",
  ESCALADO: "Escalado",
  RESUELTO: "Resuelto",
  CERRADO: "Cerrado",
  CANCELADO: "Cancelado",
};

export const COLOR_PRIORIDAD: Record<string, string> = {
  URGENTE: "#C62828",
  ALTA: "#EF6C00",
  MEDIA: "#1367AC",
  BAJA: "#607D8B",
};

export function EstadoChip({ estado, nombre }: { estado: string; nombre?: string }) {
  const c = COLOR_ESTADO[estado] ?? "#607D8B";
  return <Chip size="small" label={nombre ?? NOMBRE_ESTADO[estado] ?? estado} sx={{ bgcolor: `${c}1A`, color: c, border: `1px solid ${c}55` }} />;
}

export function PrioridadChip({ codigo, nombre }: { codigo: string; nombre: string }) {
  const c = COLOR_PRIORIDAD[codigo] ?? "#607D8B";
  return <Chip size="small" label={nombre} sx={{ bgcolor: c, color: "#fff" }} />;
}

export function colorSla(pct: number) {
  if (pct >= 100) return "#C62828";
  if (pct >= 90) return "#E65100";
  if (pct >= 75) return "#F9A825";
  return "#2E7D32";
}

export function SlaBarra({ pct, pausado, ancho = 120 }: { pct: number; pausado?: boolean; ancho?: number }) {
  const c = colorSla(pct);
  return (
    <Tooltip title={pausado ? "SLA en pausa" : `${pct.toFixed(1)} % del SLA de resolución consumido`}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: ancho }}>
        <LinearProgress
          variant="determinate"
          value={Math.min(pct, 100)}
          sx={{ flex: 1, height: 8, borderRadius: 4, bgcolor: "#E8ECF2", "& .MuiLinearProgress-bar": { bgcolor: c, borderRadius: 4 } }}
        />
        <Typography variant="caption" sx={{ fontWeight: 600, color: c, minWidth: 36, textAlign: "right" }}>
          {pct.toFixed(0)}%
        </Typography>
        {pausado && <PauseCircleOutlinedIcon fontSize="small" sx={{ color: "#F9A825" }} />}
      </Box>
    </Tooltip>
  );
}

const CUMPLIMIENTO: Record<CumplimientoSla, { texto: string; color: "success" | "error" | "default" | "info" }> = {
  CUMPLIDO: { texto: "Cumplido", color: "success" },
  INCUMPLIDO: { texto: "Incumplido", color: "error" },
  EN_CURSO: { texto: "En curso", color: "info" },
  EXCLUIDO: { texto: "Excluido", color: "default" },
};

export function CumplimientoChip({ valor }: { valor: CumplimientoSla }) {
  const c = CUMPLIMIENTO[valor] ?? CUMPLIMIENTO.EN_CURSO;
  return <Chip size="small" variant="outlined" color={c.color} label={c.texto} />;
}

/** «1 h 35 min», «2 h», «40 min» (minutos laborables). */
export function textoMinutos(n: number) {
  const m = Math.abs(Math.round(n));
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h && r) return `${h} h ${r} min`;
  if (h) return `${h} h`;
  return `${r} min`;
}

export function colorVence(min: number) {
  if (min < 0) return "#C62828";
  if (min <= 30) return "#E65100";
  if (min <= 120) return "#B57400";
  return "#2E7D32";
}

/** Tiempo laborable que falta para el próximo plazo del ticket (1.ª respuesta o resolución). */
export function VenceChip({ min, tipo }: { min: number | null | undefined; tipo?: string | null }) {
  if (min === null || min === undefined) return <Typography variant="caption" color="text.secondary">—</Typography>;
  const c = colorVence(min);
  const texto = min < 0 ? `Vencido hace ${textoMinutos(min)}` : `Faltan ${textoMinutos(min)}`;
  const titulo = (tipo === "RESPUESTA" ? "Plazo de la 1.ª respuesta" : "Plazo de resolución") + " · tiempo en horario laboral";
  return (
    <Tooltip title={titulo}>
      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
        <Chip size="small" label={texto} sx={{ height: 22, bgcolor: `${c}1A`, color: c, border: `1px solid ${c}55`, fontWeight: 700 }} />
        {tipo === "RESPUESTA" && (
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11 }}>
            1.ª resp.
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
}

export const NOMBRES_NOTA: Record<number, string> = { 1: "Muy mala", 2: "Mala", 3: "Regular", 4: "Buena", 5: "Excelente" };
