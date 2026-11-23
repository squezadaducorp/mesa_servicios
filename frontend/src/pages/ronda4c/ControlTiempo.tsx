/** Control de tiempo (31): reporte semanal de horas por analista, área y categoría. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Box, Button, MenuItem, Paper, Table, TableBody, TableCell, TableRow, TextField, Typography } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { Stack } from "../../components/Pila";
import { descargar, get } from "../../api/client";
import type { ReporteHoras } from "../../api/ronda4c";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { duracionCorta } from "../ronda4b/comun";

const OSCURO = "#1565C0";
const CLARO = "#6FA8D6";
const h = (min: number) => {
  const x = min / 60;
  return `${x >= 10 || Number.isInteger(x) ? Math.round(x) : x.toFixed(1).replace(".", ",")} h`;
};

function Kpi({ titulo, valor, ayuda }: { titulo: string; valor: string; ayuda?: string }) {
  return (
    <Paper sx={{ p: 2.5 }}>
      <Typography variant="body2" color="text.secondary">{titulo}</Typography>
      <Typography variant="h4" sx={{ fontWeight: 700, mt: 0.5 }}>{valor}</Typography>
      {ayuda && <Typography variant="caption" color="text.secondary">{ayuda}</Typography>}
    </Paper>
  );
}

export default function ControlTiempo() {
  const avisar = useAviso();
  const [desde, setDesde] = useState<string | undefined>();
  const q = useQuery({
    queryKey: ["tiempo", "reporte", desde ?? "actual"],
    queryFn: () => get<ReporteHoras>("/tiempo/reporte", desde ? { desde } : undefined),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error || !q.data) return <ErrorCarga error={q.error} />;
  const r = q.data;
  const disponibleMin = r.horas_disponibles * 60;
  return (
    <>
      <Encabezado
        titulo="Control de tiempo"
        subtitulo="Horas que el equipo registró con el cronómetro o a mano en tickets, problemas y cambios."
        acciones={
          <>
            <TextField select size="small" value={r.desde} onChange={(e) => setDesde(e.target.value)} sx={{ minWidth: 250 }} aria-label="Semana">
              {r.semanas.map((s) => <MenuItem key={s.desde} value={s.desde}>{s.nombre}</MenuItem>)}
            </TextField>
            <Button variant="outlined" startIcon={<DownloadIcon />}
              onClick={() => descargar("/tiempo/reporte/excel", { desde: r.desde }, "horas.xlsx").catch((e) => avisar(mensajeError(e), "error"))}>
              Excel
            </Button>
          </>
        }
      />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4, 1fr)" }, mb: 2 }}>
        <Kpi titulo="Horas registradas" valor={h(r.kpis.minutos)} ayuda={r.kpis.facturable_min ? `${h(r.kpis.facturable_min)} facturables` : undefined} />
        <Kpi titulo="Tickets con tiempo" valor={String(r.kpis.tickets)} />
        <Kpi titulo="Promedio por ticket" valor={r.kpis.promedio_min != null ? duracionCorta(r.kpis.promedio_min) : "—"} />
        <Kpi titulo="Ocupación del equipo" valor={r.kpis.ocupacion_pct != null ? `${Math.round(r.kpis.ocupacion_pct)} %` : "—"} ayuda={`Sobre ${r.horas_disponibles} h por persona`} />
      </Box>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.6fr) minmax(0, 1fr)" }, alignItems: "start" }}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Horas por analista (de {r.horas_disponibles} h disponibles)</Typography>
          {r.analistas.length === 0 && <Vacio texto="Nadie registró tiempo esta semana" />}
          <Stack spacing={2.2}>
            {r.analistas.map((a) => {
              const base = Math.max(disponibleMin, a.minutos);
              return (
                <Box key={a.id}>
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.6, gap: 1, flexWrap: "wrap" }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{a.nombre}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {a.tickets} ticket{a.tickets === 1 ? "" : "s"}
                      {a.horas_por_ticket != null ? ` · ${a.horas_por_ticket.toString().replace(".", ",")} h/ticket` : ""} · <b style={{ color: "#1a2433" }}>{h(a.minutos)}</b>
                      {a.ocupacion_pct != null ? ` · ${Math.round(a.ocupacion_pct)} %` : ""}
                    </Typography>
                  </Stack>
                  <Box sx={{ display: "flex", height: 22, borderRadius: 11, overflow: "hidden", bgcolor: "#EDF1F6" }}
                    aria-label={`${a.nombre}: ${h(a.min_incidentes)} en incidentes y solicitudes, ${h(a.min_cambios)} en cambios y problemas`}>
                    <Box sx={{ width: `${(a.min_incidentes / base) * 100}%`, bgcolor: OSCURO }} />
                    <Box sx={{ width: `${(a.min_cambios / base) * 100}%`, bgcolor: CLARO }} />
                  </Box>
                </Box>
              );
            })}
          </Stack>
          {r.analistas.length > 0 && (
            <Stack direction="row" spacing={2.5} sx={{ mt: 2.5, flexWrap: "wrap" }}>
              {[[OSCURO, "Incidentes y solicitudes"], [CLARO, "Cambios y problemas"]].map(([c, t]) => (
                <Stack key={t} direction="row" spacing={0.8} alignItems="center">
                  <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: c }} />
                  <Typography variant="caption">{t}</Typography>
                </Stack>
              ))}
            </Stack>
          )}
        </Paper>
        <Stack spacing={2}>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Por área solicitante</Typography>
            {r.areas.length === 0 ? <Vacio texto="Sin datos" /> : (
              <Table size="small">
                <TableBody>
                  {r.areas.map((x) => (
                    <TableRow key={x.nombre}>
                      <TableCell sx={{ pl: 0 }}>{x.nombre}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700 }}>{h(x.minutos)}</TableCell>
                      <TableCell align="right" sx={{ color: "text.secondary", pr: 0 }}>{Math.round(x.pct)} %</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Paper>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Categorías que más tiempo consumen</Typography>
            {r.categorias.length === 0 ? <Vacio texto="Sin datos" /> : (
              <Table size="small">
                <TableBody>
                  {r.categorias.map((x) => (
                    <TableRow key={x.nombre}>
                      <TableCell sx={{ pl: 0 }}>{x.nombre}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, pr: 0 }}>{h(x.minutos)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Paper>
        </Stack>
      </Box>
    </>
  );
}
