import { Box, Button, MenuItem, Paper, TextField } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { descargar } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { FiltroReporte } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { P } from "../utils/permisos";
import { haceDias, hoyIso } from "../utils/formato";
import { mensajeError, useAviso } from "./Aviso";
import { NOMBRE_ESTADO } from "./Chips";

export const PERIODOS = [
  { dias: 7, texto: "Últimos 7 días" },
  { dias: 30, texto: "Últimos 30 días" },
  { dias: 90, texto: "Últimos 90 días" },
  { dias: 180, texto: "Últimos 6 meses" },
  { dias: 365, texto: "Último año" },
];

export const filtroPorDefecto = (): FiltroReporte => ({ desde: haceDias(89), hasta: hoyIso() });

export default function FiltroReporteBar({ filtro, onChange }: { filtro: FiltroReporte; onChange: (f: FiltroReporte) => void }) {
  const cat = useCatalogos();
  const { puede } = useAuth();
  const avisar = useAviso();
  const periodo = PERIODOS.find((p) => filtro.hasta === hoyIso() && filtro.desde === haceDias(p.dias - 1))?.dias ?? "";
  const set = (k: keyof FiltroReporte, v: string) => onChange({ ...filtro, [k]: v === "" ? undefined : k.endsWith("_id") ? Number(v) : v });
  const exportar = (formato: string) =>
    descargar("/reportes/exportar", { ...filtro, formato }, `indicadores.${formato}`).catch((e) => avisar(mensajeError(e), "error"));

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" }, alignItems: "center" }}>
        <TextField
          select
          label="Período"
          value={periodo}
          onChange={(e) => onChange({ ...filtro, desde: haceDias(Number(e.target.value) - 1), hasta: hoyIso() })}
          sx={{ gridColumn: { xs: "1 / -1", sm: "auto" } }}
        >
          {PERIODOS.map((p) => (
            <MenuItem key={p.dias} value={p.dias}>
              {p.texto}
            </MenuItem>
          ))}
          <MenuItem value="" disabled>
            Personalizado
          </MenuItem>
        </TextField>
        <TextField type="date" label="Desde" value={filtro.desde ?? ""} onChange={(e) => set("desde", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <TextField type="date" label="Hasta" value={filtro.hasta ?? ""} onChange={(e) => set("hasta", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <TextField select label="Categoría" value={filtro.categoria_id ?? ""} onChange={(e) => set("categoria_id", e.target.value)}>
          <MenuItem value="">Todas</MenuItem>
          {(cat.data?.categorias ?? []).map((c) => (
            <MenuItem key={c.id} value={c.id}>
              {c.nombre}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="Responsable" value={filtro.responsable_id ?? ""} onChange={(e) => set("responsable_id", e.target.value)}>
          <MenuItem value="">Todos</MenuItem>
          {(cat.data?.responsables ?? []).map((r) => (
            <MenuItem key={r.id} value={r.id}>
              {r.nombre}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="Cliente" value={filtro.cliente_id ?? ""} onChange={(e) => set("cliente_id", e.target.value)}>
          <MenuItem value="">Todos</MenuItem>
          {(cat.data?.clientes ?? []).map((c) => (
            <MenuItem key={c.id} value={c.id}>
              {c.razon_social}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="Estado" value={filtro.estado ?? ""} onChange={(e) => set("estado", e.target.value)}>
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(NOMBRE_ESTADO).map(([c, n]) => (
            <MenuItem key={c} value={c}>
              {n}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="SLA" value={filtro.sla ?? ""} onChange={(e) => set("sla", e.target.value)}>
          <MenuItem value="">Todos</MenuItem>
          <MenuItem value="CUMPLIDO">Cumplido</MenuItem>
          <MenuItem value="INCUMPLIDO">Incumplido</MenuItem>
          <MenuItem value="EN_CURSO">En curso</MenuItem>
        </TextField>
        {puede(P.EXPORTAR) && (
          <Box sx={{ display: "flex", gap: 1, gridColumn: "1 / -1", justifyContent: "flex-end" }}>
            {["xlsx", "pdf", "csv"].map((f) => (
              <Button key={f} size="small" variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportar(f)}>
                {f === "xlsx" ? "Excel" : f.toUpperCase()}
              </Button>
            ))}
          </Box>
        )}
      </Box>
    </Paper>
  );
}
