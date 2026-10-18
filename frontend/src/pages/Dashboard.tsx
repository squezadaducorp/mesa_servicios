import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Box, Card, CardActionArea, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { LineChart } from "@mui/x-charts/LineChart";
import { PieChart } from "@mui/x-charts/PieChart";
import { Gauge, gaugeClasses } from "@mui/x-charts/Gauge";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import TaskAltIcon from "@mui/icons-material/TaskAlt";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import AlarmIcon from "@mui/icons-material/Alarm";
import ReplyIcon from "@mui/icons-material/Reply";
import TimerIcon from "@mui/icons-material/Timer";
import { get } from "../api/client";
import type { Dashboard as Datos, FiltroReporte, PuntoTendencia } from "../api/types";
import { COLOR_ESTADO, COLOR_PRIORIDAD, NOMBRE_ESTADO, SlaBarra } from "../components/Chips";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import FiltroReporteBar, { filtroPorDefecto } from "../components/FiltroReporteBar";
import { fecha, fechaHora, horas, numero, pct } from "../utils/formato";
import { marca } from "../theme";

const VERDE = "#2E7D32";
const ROJO = "#C62828";
const AGRUPACIONES = [
  { v: "DIA", t: "Día" },
  { v: "SEMANA", t: "Semana" },
  { v: "MES", t: "Mes" },
  { v: "ANIO", t: "Año" },
];

function Kpi({ titulo, valor, icono, color, detalle, onClick }: { titulo: string; valor: ReactNode; icono: ReactNode; color: string; detalle?: string; onClick?: () => void }) {
  const contenido = (
    <Stack direction="row" spacing={2} sx={{ p: 2.25, alignItems: "center" }}>
      <Box sx={{ width: 48, height: 48, borderRadius: 2.5, display: "grid", placeItems: "center", bgcolor: `${color}14`, color, flexShrink: 0 }}>{icono}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" sx={{ color: "text.secondary" }} noWrap>
          {titulo}
        </Typography>
        <Typography variant="h5" sx={{ color: marca.navy, lineHeight: 1.2 }}>
          {valor}
        </Typography>
        {detalle && (
          <Typography variant="caption" sx={{ color: "text.secondary" }} noWrap component="div">
            {detalle}
          </Typography>
        )}
      </Box>
    </Stack>
  );
  return <Card variant="outlined">{onClick ? <CardActionArea onClick={onClick}>{contenido}</CardActionArea> : contenido}</Card>;
}

function Panel({ titulo, acciones, children, alto }: { titulo: string; acciones?: ReactNode; children: ReactNode; alto?: number }) {
  return (
    <Paper sx={{ p: 2.5, minWidth: 0, display: "flex", flexDirection: "column" }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1, gap: 1, flexWrap: "wrap" }}>
        <Typography variant="h6">{titulo}</Typography>
        {acciones}
      </Stack>
      <Box sx={{ flex: 1, minHeight: alto }}>{children}</Box>
    </Paper>
  );
}

export function GraficoTendencia({ datos, alto = 300 }: { datos: PuntoTendencia[]; alto?: number }) {
  if (!datos.length) return <Vacio texto="Sin datos en el período" />;
  return (
    <BarChart
      height={alto}
      dataset={datos.map((d) => ({ ...d }))}
      xAxis={[{ scaleType: "band", dataKey: "periodo", tickLabelStyle: { fontSize: 11 } }]}
      yAxis={[{ id: "n", width: 40 }]}
      series={[
        { dataKey: "sla_cumplido", label: "SLA cumplido", stack: "sla", color: VERDE, yAxisId: "n" },
        { dataKey: "sla_incumplido", label: "SLA incumplido", stack: "sla", color: ROJO, yAxisId: "n" },
        { dataKey: "tickets", label: "Recibidos", color: marca.celeste, yAxisId: "n" },
      ]}
      grid={{ horizontal: true }}
      margin={{ left: 8, right: 8 }}
    />
  );
}

export function GraficoCumplimiento({ datos, alto = 260 }: { datos: PuntoTendencia[]; alto?: number }) {
  const conDatos = datos.filter((d) => d.cumplimiento_sla_pct !== null);
  if (!conDatos.length) return <Vacio texto="Sin tickets cerrados en el período" />;
  return (
    <LineChart
      height={alto}
      xAxis={[{ scaleType: "point", data: conDatos.map((d) => d.periodo), tickLabelStyle: { fontSize: 11 } }]}
      yAxis={[{ min: Math.max(0, Math.min(...conDatos.map((d) => d.cumplimiento_sla_pct ?? 0)) - 10), max: 100, width: 44, valueFormatter: (v: number) => `${v}%` }]}
      series={[{ data: conDatos.map((d) => d.cumplimiento_sla_pct), label: "Cumplimiento SLA", color: marca.azul, area: true, showMark: true, valueFormatter: (v) => pct(v) }]}
      grid={{ horizontal: true }}
      hideLegend
      margin={{ left: 8, right: 16 }}
    />
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [filtro, setFiltro] = useState<FiltroReporte>(filtroPorDefecto);
  const [agrupacion, setAgrupacion] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["dashboard", filtro],
    queryFn: () => get<Datos>("/reportes/dashboard", { ...filtro }),
    placeholderData: keepPreviousData,
    refetchInterval: 120_000,
  });
  const tendencia = useQuery({
    queryKey: ["tendencia", filtro, agrupacion],
    queryFn: () => get<PuntoTendencia[]>("/reportes/tendencia", { ...filtro, agrupacion: agrupacion! }),
    enabled: !!agrupacion,
    placeholderData: keepPreviousData,
  });

  const d = q.data;
  const serie = agrupacion ? (tendencia.data ?? []) : (d?.tendencia ?? []);
  const w = d?.widgets;

  return (
    <>
      <Encabezado
        titulo="Dashboard ejecutivo"
        subtitulo={d ? `Del ${fecha(`${d.filtro.desde}T12:00:00Z`)} al ${fecha(`${d.filtro.hasta}T12:00:00Z`)} · actualizado ${fechaHora(new Date().toISOString())}` : " "}
      />
      <FiltroReporteBar filtro={filtro} onChange={setFiltro} />
      {q.isLoading ? (
        <Cargando alto={400} />
      ) : q.error || !d || !w ? (
        <ErrorCarga error={q.error} />
      ) : (
        <Stack spacing={2}>
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
            <Kpi titulo="Tickets totales" valor={numero(w.tickets_totales)} icono={<ConfirmationNumberIcon />} color={marca.azul} detalle="Recibidos en el período" />
            <Kpi
              titulo="Abiertos"
              valor={numero(w.tickets_abiertos)}
              icono={<PendingActionsIcon />}
              color="#0288D1"
              detalle="Nuevos, en proceso, pendientes o escalados"
              onClick={() => navigate("/tickets?estado=NUEVO&estado=ASIGNADO&estado=EN_PROCESO&estado=PENDIENTE_CLIENTE&estado=ESCALADO")}
            />
            <Kpi titulo="Cerrados" valor={numero(w.tickets_cerrados)} icono={<TaskAltIcon />} color={VERDE} detalle="Resueltos o cerrados" />
            <Kpi titulo="Escalados" valor={numero(w.tickets_escalados)} icono={<TrendingUpIcon />} color="#E65100" detalle="Al 90 %, al vencer o manualmente" />
            <Kpi titulo="Vencidos" valor={numero(w.tickets_vencidos)} icono={<AlarmIcon />} color={ROJO} detalle="SLA incumplido" onClick={() => navigate("/tickets?sla=INCUMPLIDO")} />
            <Kpi titulo="T. promedio de respuesta" valor={horas(w.tiempo_promedio_respuesta_h)} icono={<ReplyIcon />} color="#5E35B1" detalle="Horas laborables" />
            <Kpi titulo="T. promedio de resolución" valor={horas(w.tiempo_promedio_resolucion_h)} icono={<TimerIcon />} color="#00897B" detalle="Horas laborables" />
            <Card variant="outlined" sx={{ display: "flex", alignItems: "center", px: 2, gap: 1 }}>
              <Gauge
                width={96}
                height={96}
                value={w.cumplimiento_sla_pct ?? 0}
                innerRadius="72%"
                text={({ value }) => `${Math.round(value ?? 0)}%`}
                sx={{
                  [`& .${gaugeClasses.valueText}`]: { fontSize: 18, fontWeight: 700 },
                  [`& .${gaugeClasses.valueArc}`]: { fill: (w.cumplimiento_sla_pct ?? 0) >= 90 ? VERDE : (w.cumplimiento_sla_pct ?? 0) >= 80 ? "#F9A825" : ROJO },
                }}
              />
              <Box>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Cumplimiento SLA
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {numero(w.sla_cumplido)} cumplidos · {numero(w.sla_incumplido)} incumplidos
                </Typography>
              </Box>
            </Card>
          </Box>

          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" } }}>
            <Panel
              titulo="Tickets y SLA por período"
              acciones={
                <ToggleButtonGroup size="small" exclusive value={agrupacion ?? d.agrupacion} onChange={(_, v) => v && setAgrupacion(v)}>
                  {AGRUPACIONES.map((a) => (
                    <ToggleButton key={a.v} value={a.v} sx={{ px: 1.5 }}>
                      {a.t}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              }
            >
              <GraficoTendencia datos={serie} />
            </Panel>
            <Panel titulo="SLA cumplido vs incumplido">
              {w.sla_cumplido + w.sla_incumplido === 0 ? (
                <Vacio texto="Sin tickets cerrados" />
              ) : (
                <PieChart
                  height={300}
                  series={[
                    {
                      innerRadius: 60,
                      paddingAngle: 2,
                      cornerRadius: 4,
                      arcLabel: (i) => `${Math.round((i.value / (w.sla_cumplido + w.sla_incumplido)) * 100)}%`,
                      data: [
                        { id: 0, value: w.sla_cumplido, label: "Cumplido", color: VERDE },
                        { id: 1, value: w.sla_incumplido, label: "Incumplido", color: ROJO },
                      ],
                    },
                  ]}
                  sx={{ "& text": { fill: "#fff", fontWeight: 600 } }}
                  slotProps={{ legend: { direction: "horizontal", position: { vertical: "bottom", horizontal: "center" } } }}
                />
              )}
            </Panel>
          </Box>

          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr", lg: "1fr 1fr 1fr" } }}>
            <Panel titulo="Top categorías">
              <BarChart
                height={260}
                layout="horizontal"
                yAxis={[{ scaleType: "band", data: d.top_categorias.map((c) => c.nombre), width: 150, tickLabelStyle: { fontSize: 11 } }]}
                series={[{ data: d.top_categorias.map((c) => c.tickets), color: marca.azul, label: "Tickets" }]}
                hideLegend
                grid={{ vertical: true }}
              />
            </Panel>
            <Panel titulo="Top responsables">
              <BarChart
                height={260}
                layout="horizontal"
                yAxis={[{ scaleType: "band", data: d.top_responsables.map((c) => c.nombre), width: 130, tickLabelStyle: { fontSize: 11 } }]}
                series={[{ data: d.top_responsables.map((c) => c.tickets), color: marca.azulOscuro, label: "Tickets" }]}
                hideLegend
                grid={{ vertical: true }}
              />
            </Panel>
            <Panel titulo="Por estado y prioridad">
              <Stack direction={{ xs: "column", sm: "row", md: "column" }} spacing={1}>
                <PieChart
                  height={220}
                  series={[
                    {
                      innerRadius: 40,
                      data: Object.entries(d.por_estado).map(([k, v], i) => ({ id: i, value: v, label: NOMBRE_ESTADO[k] ?? k, color: COLOR_ESTADO[k] })),
                    },
                  ]}
                  slotProps={{ legend: { direction: "vertical", position: { vertical: "middle", horizontal: "end" } } }}
                />
                <PieChart
                  height={220}
                  series={[
                    {
                      innerRadius: 40,
                      data: Object.entries(d.por_prioridad).map(([k, v], i) => ({ id: i, value: v, label: k, color: COLOR_PRIORIDAD[k.toUpperCase()] })),
                    },
                  ]}
                  slotProps={{ legend: { direction: "vertical", position: { vertical: "middle", horizontal: "end" } } }}
                />
              </Stack>
            </Panel>
          </Box>

          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 2fr" } }}>
            <Panel titulo="Tendencia del cumplimiento">
              <GraficoCumplimiento datos={serie} />
            </Panel>
            <Panel titulo={`Tickets en riesgo (${d.en_riesgo.length})`}>
              {!d.en_riesgo.length ? (
                <Vacio texto="Ningún ticket abierto supera el 75 % de su SLA" />
              ) : (
                <TableContainer sx={{ maxHeight: 280 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>Ticket</TableCell>
                        <TableCell>Categoría</TableCell>
                        <TableCell>Responsable</TableCell>
                        <TableCell>Vence</TableCell>
                        <TableCell>SLA</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {d.en_riesgo.map((t) => (
                        <TableRow key={t.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/tickets/${t.id}`)}>
                          <TableCell sx={{ maxWidth: 260 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main" }}>
                              {t.numero}
                            </Typography>
                            <Typography variant="caption" noWrap component="div" sx={{ color: "text.secondary" }}>
                              {t.asunto}
                            </Typography>
                          </TableCell>
                          <TableCell>{t.categoria}</TableCell>
                          <TableCell>{t.responsable ?? "Sin asignar"}</TableCell>
                          <TableCell sx={{ whiteSpace: "nowrap" }}>{fechaHora(t.vence)}</TableCell>
                          <TableCell>
                            <SlaBarra pct={t.sla_consumido_pct} ancho={100} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Panel>
          </Box>
        </Stack>
      )}
    </>
  );
}
