import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Avatar, Box, Chip, Paper, Stack, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { SparkLineChart } from "@mui/x-charts/SparkLineChart";
import EmojiEventsIcon from "@mui/icons-material/EmojiEvents";
import { get } from "../api/client";
import type { FiltroReporte, IndicadorCategoria, IndicadorCliente, IndicadorResponsable, PuntoTendencia } from "../api/types";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import FiltroReporteBar, { filtroPorDefecto } from "../components/FiltroReporteBar";
import { horas, numero, pct } from "../utils/formato";
import { marca } from "../theme";
import { GraficoCumplimiento, GraficoTendencia } from "./Dashboard";

function colorPct(v: number | null) {
  if (v === null) return "text.secondary";
  return v >= 90 ? "success.main" : v >= 80 ? "warning.main" : "error.main";
}

const MEDALLA = ["#D4A017", "#A7A7AD", "#B87333"];

function PorCategoria({ filtro }: { filtro: FiltroReporte }) {
  const q = useQuery({ queryKey: ["rep", "cat", filtro], queryFn: () => get<IndicadorCategoria[]>("/reportes/categorias", { ...filtro }), placeholderData: keepPreviousData });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data ?? [];
  if (!d.length) return <Vacio texto="Sin datos en el período" />;
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Recibidos, resueltos y vencidos por categoría
        </Typography>
        <BarChart
          height={300}
          dataset={d.map((x) => ({ ...x }))}
          xAxis={[{ scaleType: "band", dataKey: "categoria", tickLabelStyle: { fontSize: 11 } }]}
          yAxis={[{ width: 40 }]}
          series={[
            { dataKey: "tickets_recibidos", label: "Recibidos", color: marca.celeste },
            { dataKey: "tickets_resueltos", label: "Resueltos", color: marca.azul },
            { dataKey: "tickets_vencidos", label: "Vencidos", color: "#C62828" },
          ]}
          grid={{ horizontal: true }}
        />
      </Paper>
      <Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Categoría</TableCell>
                <TableCell align="right">Recibidos</TableCell>
                <TableCell align="right">Resueltos</TableCell>
                <TableCell align="right">Pendientes</TableCell>
                <TableCell align="right">Vencidos</TableCell>
                <TableCell align="right">Cumplimiento SLA</TableCell>
                <TableCell align="right">T. prom. respuesta</TableCell>
                <TableCell align="right">T. prom. resolución</TableCell>
                <TableCell align="right">Backlog</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {d.map((c) => (
                <TableRow key={c.categoria_id} hover>
                  <TableCell>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: c.color ?? marca.azul }} />
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {c.categoria}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="right">{numero(c.tickets_recibidos)}</TableCell>
                  <TableCell align="right">{numero(c.tickets_resueltos)}</TableCell>
                  <TableCell align="right">{numero(c.tickets_pendientes)}</TableCell>
                  <TableCell align="right">{numero(c.tickets_vencidos)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, color: colorPct(c.cumplimiento_sla_pct) }}>
                    {pct(c.cumplimiento_sla_pct)}
                  </TableCell>
                  <TableCell align="right">{horas(c.tiempo_promedio_respuesta_h)}</TableCell>
                  <TableCell align="right">{horas(c.tiempo_promedio_resolucion_h)}</TableCell>
                  <TableCell align="right">{numero(c.backlog)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Stack>
  );
}

function PorResponsable({ filtro }: { filtro: FiltroReporte }) {
  const q = useQuery({ queryKey: ["rep", "resp", filtro], queryFn: () => get<IndicadorResponsable[]>("/reportes/responsables", { ...filtro }), placeholderData: keepPreviousData });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data ?? [];
  if (!d.length) return <Vacio texto="Sin datos en el período" />;
  return (
    <Stack spacing={2}>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" } }}>
        {d.slice(0, 3).map((r, i) => (
          <Paper key={r.responsable_id} sx={{ p: 2.5, display: "flex", gap: 2, alignItems: "center", borderTop: `4px solid ${MEDALLA[i]}` }}>
            <Avatar sx={{ bgcolor: MEDALLA[i], width: 48, height: 48 }}>
              <EmojiEventsIcon />
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                #{r.ranking} · puntaje {numero(r.puntaje)}
              </Typography>
              <Typography variant="h6" noWrap>
                {r.responsable}
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {numero(r.tickets_cerrados)} cerrados · SLA {pct(r.cumplimiento_sla_pct)}
              </Typography>
            </Box>
          </Paper>
        ))}
      </Box>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Cumplimiento de SLA por responsable
        </Typography>
        <BarChart
          height={Math.max(220, d.length * 38)}
          layout="horizontal"
          yAxis={[{ scaleType: "band", data: d.map((r) => r.responsable), width: 150, tickLabelStyle: { fontSize: 11 } }]}
          xAxis={[{ min: 0, max: 100, valueFormatter: (v: number) => `${v}%` }]}
          series={[{ data: d.map((r) => r.cumplimiento_sla_pct ?? 0), color: marca.azul, label: "Cumplimiento SLA %", valueFormatter: (v) => pct(v) }]}
          hideLegend
          grid={{ vertical: true }}
        />
      </Paper>
      <Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Ranking</TableCell>
                <TableCell>Responsable</TableCell>
                <TableCell align="right">Asignados</TableCell>
                <TableCell align="right">Cerrados</TableCell>
                <TableCell align="right">Abiertos</TableCell>
                <TableCell align="right">SLA cumplido</TableCell>
                <TableCell align="right">SLA incumplido</TableCell>
                <TableCell align="right">Cumplimiento</TableCell>
                <TableCell align="right">Productividad</TableCell>
                <TableCell align="right">T. prom. resolución</TableCell>
                <TableCell align="right">Puntaje</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {d.map((r) => (
                <TableRow key={r.responsable_id} hover>
                  <TableCell>
                    <Chip size="small" label={`#${r.ranking}`} sx={r.ranking <= 3 ? { bgcolor: MEDALLA[r.ranking - 1], color: "#fff" } : undefined} />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{r.responsable}</TableCell>
                  <TableCell align="right">{numero(r.tickets_asignados)}</TableCell>
                  <TableCell align="right">{numero(r.tickets_cerrados)}</TableCell>
                  <TableCell align="right">{numero(r.tickets_abiertos)}</TableCell>
                  <TableCell align="right">{numero(r.sla_cumplido)}</TableCell>
                  <TableCell align="right">{numero(r.sla_incumplido)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, color: colorPct(r.cumplimiento_sla_pct) }}>
                    {pct(r.cumplimiento_sla_pct)}
                  </TableCell>
                  <TableCell align="right">{numero(r.productividad_dia)} /día</TableCell>
                  <TableCell align="right">{horas(r.tiempo_promedio_resolucion_h)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>
                    {numero(r.puntaje)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Typography variant="caption" sx={{ display: "block", p: 1.5, color: "text.secondary" }}>
          Puntaje = 60 % cumplimiento de SLA + 40 % tickets cerrados respecto del responsable con más cierres. Productividad = cerrados por día laborable.
        </Typography>
      </Paper>
    </Stack>
  );
}

function PorCliente({ filtro }: { filtro: FiltroReporte }) {
  const q = useQuery({ queryKey: ["rep", "cli", filtro], queryFn: () => get<IndicadorCliente[]>("/reportes/clientes", { ...filtro }), placeholderData: keepPreviousData });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data ?? [];
  if (!d.length) return <Vacio texto="Sin datos en el período" />;
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Clientes con más tickets
        </Typography>
        <BarChart
          height={Math.max(240, Math.min(d.length, 12) * 34)}
          layout="horizontal"
          yAxis={[{ scaleType: "band", data: d.slice(0, 12).map((c) => c.cliente), width: 220, tickLabelStyle: { fontSize: 11 } }]}
          series={[{ data: d.slice(0, 12).map((c) => c.tickets), color: marca.azulOscuro, label: "Tickets" }]}
          hideLegend
          grid={{ vertical: true }}
        />
      </Paper>
      <Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Cliente</TableCell>
                <TableCell align="right">Tickets</TableCell>
                <TableCell align="right">Cumplimiento SLA</TableCell>
                <TableCell>Categorías más usadas</TableCell>
                <TableCell>Tendencia</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {d.map((c) => (
                <TableRow key={c.cliente_id ?? c.cliente} hover>
                  <TableCell sx={{ fontWeight: 600 }}>{c.cliente}</TableCell>
                  <TableCell align="right">{numero(c.tickets)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, color: colorPct(c.cumplimiento_sla_pct) }}>
                    {pct(c.cumplimiento_sla_pct)}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.5 }}>
                      {c.categorias.slice(0, 3).map((x) => (
                        <Chip key={x.nombre} size="small" variant="outlined" label={`${x.nombre} (${x.tickets})`} />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ width: 140 }}>
                    {c.tendencia.length > 1 ? <SparkLineChart data={c.tendencia.map((t) => t.tickets)} height={32} width={120} color={marca.azul} area /> : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Stack>
  );
}

function Historico({ filtro }: { filtro: FiltroReporte }) {
  const [agrupacion, setAgrupacion] = useState("MES");
  const q = useQuery({
    queryKey: ["rep", "tend", filtro, agrupacion],
    queryFn: () => get<PuntoTendencia[]>("/reportes/tendencia", { ...filtro, agrupacion }),
    placeholderData: keepPreviousData,
  });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data ?? [];
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1, flexWrap: "wrap", gap: 1 }}>
          <Typography variant="h6">Tickets por período</Typography>
          <ToggleButtonGroup size="small" exclusive value={agrupacion} onChange={(_, v) => v && setAgrupacion(v)}>
            <ToggleButton value="DIA">Día</ToggleButton>
            <ToggleButton value="SEMANA">Semana</ToggleButton>
            <ToggleButton value="MES">Mes</ToggleButton>
            <ToggleButton value="ANIO">Año</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        <GraficoTendencia datos={d} alto={340} />
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Tendencia histórica del cumplimiento de SLA
        </Typography>
        <GraficoCumplimiento datos={d} alto={280} />
      </Paper>
    </Stack>
  );
}

export default function Reportes() {
  const [filtro, setFiltro] = useState<FiltroReporte>(filtroPorDefecto);
  const [tab, setTab] = useState(0);
  return (
    <>
      <Encabezado titulo="Indicadores" subtitulo="Indicadores por categoría, responsable y cliente, con tendencia histórica" />
      <FiltroReporteBar filtro={filtro} onChange={setFiltro} />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ mb: 2 }}>
        <Tab label="Por categoría" />
        <Tab label="Por responsable" />
        <Tab label="Por cliente" />
        <Tab label="Histórico" />
      </Tabs>
      {tab === 0 && <PorCategoria filtro={filtro} />}
      {tab === 1 && <PorResponsable filtro={filtro} />}
      {tab === 2 && <PorCliente filtro={filtro} />}
      {tab === 3 && <Historico filtro={filtro} />}
    </>
  );
}
