import { Box, Chip, LinearProgress, Tooltip, Typography } from "@mui/material";
import PauseCircleOutlinedIcon from "@mui/icons-material/PauseCircleOutlined";
import type { CumplimientoSla } from "../api/types";

export const COLOR_ESTADO: Record<string, string> = {
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
