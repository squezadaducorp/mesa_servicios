import { useNavigate } from "react-router-dom";
import { Box, LinearProgress, List, ListItemButton, ListItemText, Paper, Rating, Stack, Typography } from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { LineChart } from "@mui/x-charts/LineChart";
import type { Satisfaccion } from "../api/types";
import { numero, pct, tiempoRelativo } from "../utils/formato";
import { marca } from "../theme";
import { Vacio } from "./Comunes";

export const COLOR_NOTA: Record<number, string> = { 1: "#C62828", 2: "#EF6C00", 3: "#F9A825", 4: "#7CB342", 5: "#2E7D32" };
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const mes = (p: string) => `${MESES[Number(p.slice(5, 7)) - 1] ?? p.slice(5, 7)} ${p.slice(2, 4)}`;

function Caja({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <Paper sx={{ p: 2.5, minWidth: 0 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        {titulo}
      </Typography>
      {children}
    </Paper>
  );
}

/** Sección del dashboard con los resultados de la encuesta (1 a 5 estrellas). */
export default function SeccionSatisfaccion({ s }: { s: Satisfaccion }) {
  const navigate = useNavigate();
  const max = Math.max(1, ...Object.values(s.distribucion));
  return (
    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr", lg: "1fr 1fr 1fr" } }}>
      <Caja titulo="Satisfacción del solicitante">
        {!s.total ? (
          <Vacio texto="Aún no hay encuestas respondidas en el período" />
        ) : (
          <>
            <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 2 }}>
              <Typography sx={{ fontSize: 44, fontWeight: 800, color: marca.navy, lineHeight: 1 }}>{numero(s.promedio)}</Typography>
              <Box>
                <Rating value={s.promedio ?? 0} precision={0.1} readOnly />
                <Typography variant="caption" component="div" sx={{ color: "text.secondary" }}>
                  {s.total} respuesta(s) · {pct(s.respondidas_pct)} de {s.tickets_resueltos} resueltos
                </Typography>
              </Box>
            </Stack>
            <Stack spacing={0.75}>
              {[5, 4, 3, 2, 1].map((n) => {
                const v = s.distribucion[String(n)] ?? 0;
                return (
                  <Stack key={n} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <Typography variant="caption" sx={{ width: 22 }}>
                      {n}★
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={(v / max) * 100}
                      sx={{ flex: 1, height: 10, borderRadius: 5, bgcolor: "#EEF1F6", "& .MuiLinearProgress-bar": { bgcolor: COLOR_NOTA[n], borderRadius: 5 } }}
                    />
                    <Typography variant="caption" sx={{ width: 28, textAlign: "right" }}>
                      {v}
                    </Typography>
                  </Stack>
                );
              })}
            </Stack>
            <Stack direction="row" spacing={3} sx={{ mt: 2 }}>
              <Box>
                <Typography variant="h6" sx={{ color: COLOR_NOTA[5] }}>
                  {pct(s.satisfechos_pct)}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Satisfechos (4-5★)
                </Typography>
              </Box>
              <Box>
                <Typography variant="h6" sx={{ color: COLOR_NOTA[1] }}>
                  {pct(s.insatisfechos_pct)}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Insatisfechos (1-2★)
                </Typography>
              </Box>
            </Stack>
          </>
        )}
      </Caja>

      <Caja titulo="Promedio por responsable">
        {!s.por_responsable.length ? (
          <Vacio texto="Sin datos" />
        ) : (
          <BarChart
            height={280}
            layout="horizontal"
            xAxis={[{ min: 0, max: 5 }]}
            yAxis={[{ scaleType: "band", data: s.por_responsable.map((r) => r.nombre), width: 130, tickLabelStyle: { fontSize: 11 } }]}
            series={[
              {
                data: s.por_responsable.map((r) => r.promedio),
                color: "#F9A825",
                label: "Promedio",
                valueFormatter: (v, { dataIndex }) => `${numero(v)}★ (${s.por_responsable[dataIndex]?.encuestas ?? 0} encuestas)`,
              },
            ]}
            hideLegend
            grid={{ vertical: true }}
          />
        )}
      </Caja>

      <Caja titulo="Tendencia y últimos comentarios">
        {s.tendencia.length > 1 && (
          <LineChart
            height={140}
            xAxis={[{ scaleType: "point", data: s.tendencia.map((t) => mes(t.periodo)) }]}
            yAxis={[{ min: 1, max: 5, width: 28 }]}
            series={[{ data: s.tendencia.map((t) => t.promedio), color: "#F9A825", label: "Promedio", curve: "monotoneX" }]}
            hideLegend
          />
        )}
        {!s.comentarios.length ? (
          <Vacio texto="Sin comentarios en el período" />
        ) : (
          <List dense sx={{ maxHeight: 220, overflow: "auto" }}>
            {s.comentarios.map((c) => (
              <ListItemButton key={`${c.ticket_id}`} onClick={() => navigate(`/tickets/${c.ticket_id}`)} sx={{ alignItems: "flex-start", borderLeft: `3px solid ${COLOR_NOTA[c.calificacion]}`, mb: 0.5 }}>
                <ListItemText
                  primary={`«${c.comentario}»`}
                  secondary={`${c.calificacion}★ · ${c.numero} · ${c.responsable ?? "sin responsable"} · ${tiempoRelativo(c.fecha)}`}
                  slotProps={{ primary: { sx: { fontSize: 13 } } }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </Caja>
    </Box>
  );
}
