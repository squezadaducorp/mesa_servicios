import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, LinearProgress, MenuItem, Paper, Switch, TextField, Typography,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import ScheduleSendIcon from "@mui/icons-material/ScheduleSend";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import { Stack } from "../../components/Pila";
import { descargar, get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { PanelDatos, PanelEnvioConfig, PanelEnvioInfo, SeccionPanel } from "../../api/ronda4b";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";
import { fechaHora } from "../../utils/formato";
import { marca } from "../../theme";
import { duracionCorta } from "./comun";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const coma = (v: number, d = 1) => v.toFixed(d).replace(".", ",");

function ultimosMeses(n: number) {
  const hoy = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Guayaquil" }));
  const r: { anio: number; mes: number; texto: string }[] = [];
  let a = hoy.getFullYear(), m = hoy.getMonth() + 1;
  for (let i = 0; i < n; i++) {
    r.push({ anio: a, mes: m, texto: `${MESES[m - 1][0].toUpperCase()}${MESES[m - 1].slice(1)} ${a}` });
    if (m === 1) { a -= 1; m = 12; } else m -= 1;
  }
  return r;
}

function Kpi({ titulo, valor, variacion, bueno }: { titulo: string; valor: string; variacion?: string | null; bueno?: boolean | null }) {
  const color = bueno === null || bueno === undefined ? "text.secondary" : bueno ? "success.main" : "error.main";
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="body2" color="text.secondary">{titulo}</Typography>
      <Typography sx={{ fontSize: 34, fontWeight: 800, color: "#10203C", lineHeight: 1.25 }}>{valor}</Typography>
      {variacion && (
        <Stack direction="row" alignItems="center" sx={{ gap: 0.5, color }}>
          {bueno === false ? <TrendingDownIcon fontSize="small" /> : <TrendingUpIcon fontSize="small" />}
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{variacion}</Typography>
        </Stack>
      )}
    </Paper>
  );
}

const signo = (v: number, dec = 0) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${dec ? coma(Math.abs(v), dec) : Math.abs(Math.round(v))}`;

function EnvioMensual({ anio, mes }: { anio: number; mes: number }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["panel", "envio"], queryFn: () => get<PanelEnvioInfo>("/panel/envio") });
  const [f, setF] = useState<(PanelEnvioConfig & { para: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (q.data) setF({ ...q.data.config, para: q.data.config.destinatarios.join("; ") }); }, [q.data]);
  const guardar = useMutation({
    mutationFn: () => put("/panel/envio", {
      activo: f!.activo, destinatarios: f!.para.split(/[;,\s]+/).filter(Boolean), cuando: f!.cuando, hora: f!.hora, secciones: f!.secciones,
      comentario: f!.comentario || null,
    }),
    onSuccess: () => { avisar("Envío mensual guardado"); setError(null); qc.invalidateQueries({ queryKey: ["panel", "envio"] }); },
    onError: (e) => setError(mensajeError(e)),
  });
  const prueba = useMutation({
    mutationFn: () => post<{ mensaje: string }>(`/panel/envio/prueba?anio=${anio}&mes=${mes}`),
    onSuccess: (r) => { avisar(r.mensaje); qc.invalidateQueries({ queryKey: ["panel", "envio"] }); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (!q.data || !f) return <Paper variant="outlined" sx={{ p: 3 }}><Cargando alto={120} /></Paper>;
  const d = q.data;
  const ro = !d.puede_configurar;
  return (
    <Stack sx={{ gap: 2 }}>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 1.5 }}>
          <ScheduleSendIcon color="primary" />
          <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1 }}>Enviar el PDF cada mes</Typography>
          <Switch checked={f.activo} disabled={ro} onChange={(e) => setF({ ...f, activo: e.target.checked })} />
        </Stack>
        <Stack sx={{ gap: 2 }}>
          <TextField size="small" label="Para" value={f.para} disabled={ro} placeholder="gerencia@aducorp.com.ec; directorio@aducorp.com.ec"
            onChange={(e) => setF({ ...f, para: e.target.value })} />
          <Stack direction="row" sx={{ gap: 1.5 }}>
            <TextField select size="small" label="Cuándo" value={f.cuando} disabled={ro} sx={{ flexGrow: 1 }}
              onChange={(e) => setF({ ...f, cuando: e.target.value as PanelEnvioConfig["cuando"] })}>
              <MenuItem value="PRIMER_HABIL">Primer día hábil del mes</MenuItem>
              <MenuItem value="DIA_1">El día 1 de cada mes</MenuItem>
            </TextField>
            <TextField size="small" type="time" label="Hora" value={f.hora} disabled={ro} sx={{ width: 130 }} onChange={(e) => setF({ ...f, hora: e.target.value })}
              slotProps={{ inputLabel: { shrink: true } }} />
          </Stack>
          <Box>
            <Typography variant="body2" sx={{ mb: 1 }}>Incluye</Typography>
            <Stack direction="row" sx={{ gap: 0.75, flexWrap: "wrap" }}>
              {(Object.entries(d.secciones) as [SeccionPanel, string][]).map(([k, v]) => {
                const on = f.secciones.includes(k);
                return (
                  <Chip key={k} label={v} color={on ? "primary" : "default"} variant={on ? "filled" : "outlined"} disabled={ro}
                    onClick={() => setF({ ...f, secciones: on ? f.secciones.filter((x) => x !== k) : [...f.secciones, k] })} />
                );
              })}
            </Stack>
          </Box>
          <TextField label="Comentario de TI (opcional, sale en la portada)" multiline minRows={3} value={f.comentario} disabled={ro}
            helperText="Se borra después del envío automático para no repetirlo el mes siguiente." onChange={(e) => setF({ ...f, comentario: e.target.value })} />
          {error && <Alert severity="error">{error}</Alert>}
          {d.proximo && f.activo && <Typography variant="caption" color="text.secondary">Próximo envío: {fechaHora(d.proximo)} con el informe del mes anterior.</Typography>}
          {!ro && (
            <Stack direction="row" justifyContent="flex-end" sx={{ gap: 1 }}>
              <Button onClick={() => prueba.mutate()} disabled={prueba.isPending}>Enviármelo de prueba</Button>
              <Button variant="contained" onClick={() => guardar.mutate()} disabled={guardar.isPending}>Guardar</Button>
            </Stack>
          )}
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Envíos anteriores</Typography>
        {d.envios.length === 0 && <Typography variant="body2" color="text.secondary">Todavía no se ha enviado ningún informe.</Typography>}
        {d.envios.map((e) => (
          <Stack key={e.id} direction="row" alignItems="center" sx={{ gap: 1, py: 1, borderTop: "1px solid", borderColor: "divider" }}>
            <PictureAsPdfIcon sx={{ color: "#D32F2F" }} fontSize="small" />
            <Button size="small" sx={{ textTransform: "none", flexGrow: 1, justifyContent: "flex-start" }}
              onClick={() => descargar(`/panel/envios/${e.id}/pdf`, undefined, e.archivo)}>{e.archivo}</Button>
            {e.es_prueba && <Chip size="small" label="prueba" />}
            {e.estado === "ERROR" && <Chip size="small" color="error" label="error" />}
            <Typography variant="caption" color="text.secondary">{fechaHora(e.fecha)}</Typography>
          </Stack>
        ))}
      </Paper>
    </Stack>
  );
}

export default function PanelGerencial() {
  const meses = useMemo(() => ultimosMeses(13), []);
  const [sel, setSel] = useState(0);
  const [area, setArea] = useState<number | "">("");
  const cat = useCatalogos();
  const { anio, mes } = meses[sel];
  const q = useQuery({ queryKey: ["panel", anio, mes, area], queryFn: () => get<PanelDatos>("/panel", { anio, mes, area_id: area || undefined }) });
  const d = q.data;
  const k = d?.kpis;
  return (
    <Box>
      <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 2, mb: 3 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5">Panel gerencial</Typography>
          <Typography variant="body2" color="text.secondary">Resumen del mes para Gerencia. El mismo contenido sale en el PDF.</Typography>
        </Box>
        <TextField select size="small" value={sel} onChange={(e) => setSel(Number(e.target.value))} sx={{ minWidth: 180 }}>
          {meses.map((m, i) => <MenuItem key={m.texto} value={i}>{m.texto}</MenuItem>)}
        </TextField>
        <TextField select size="small" value={area} onChange={(e) => setArea(Number(e.target.value) || "")} sx={{ minWidth: 180 }}
          slotProps={{ select: { displayEmpty: true } }}>
          <MenuItem value="">Todas las áreas</MenuItem>
          {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
        </TextField>
        <Button variant="contained" startIcon={<PictureAsPdfIcon />}
          onClick={() => descargar("/panel/pdf", { anio, mes, area_id: area || undefined }, `Panel-Mesa-${meses[sel].texto.replace(" ", "-")}.pdf`)}>
          Descargar PDF
        </Button>
      </Stack>

      {q.isLoading ? <Cargando /> : q.error ? <ErrorCarga error={q.error} /> : d && k && (
        <>
          <Box sx={{ display: "grid", gap: 2, mb: 3, gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
            <Kpi titulo="Tickets recibidos" valor={String(k.recibidos)}
              variacion={k.recibidos_var !== null ? `${signo(k.recibidos_var)} % vs. ${d.mes_anterior}` : null} bueno={null} />
            <Kpi titulo="Cumplimiento SLA" valor={k.cumplimiento !== null ? `${coma(k.cumplimiento)} %` : "—"}
              variacion={k.cumplimiento_var !== null ? `${signo(k.cumplimiento_var, 1)} pts` : null} bueno={k.cumplimiento_var === null ? null : k.cumplimiento_var >= 0} />
            <Kpi titulo="Satisfacción" valor={k.satisfaccion !== null ? `${coma(k.satisfaccion)} / 5` : "—"}
              variacion={k.satisfaccion_var !== null ? signo(k.satisfaccion_var, 1) : null} bueno={k.satisfaccion_var === null ? null : k.satisfaccion_var >= 0} />
            <Kpi titulo="Tiempo medio de solución" valor={duracionCorta(k.tiempo_medio_min)}
              variacion={k.tiempo_medio_var !== null ? `${signo(k.tiempo_medio_var)} min` : null} bueno={k.tiempo_medio_var === null ? null : k.tiempo_medio_var <= 0} />
          </Box>

          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "3fr 2fr" }, alignItems: "start" }}>
            <Stack sx={{ gap: 2 }}>
              <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Tickets por mes (últimos 6 meses)</Typography>
                <BarChart height={260} dataset={d.serie.map((x) => ({ ...x }))}
                  xAxis={[{ scaleType: "band", dataKey: "etiqueta", colorMap: { type: "ordinal", values: d.serie.map((x) => x.etiqueta),
                    colors: d.serie.map((_, i) => (i === d.serie.length - 1 ? marca.azul : marca.celeste)) } }]}
                  yAxis={[{ width: 36 }]} series={[{ dataKey: "tickets", label: "Tickets", barLabel: "value" }]} hideLegend grid={{ horizontal: true }} />
              </Paper>
              <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Cumplimiento por área</Typography>
                {d.areas.length === 0 && <Typography variant="body2" color="text.secondary">Sin tickets en el mes.</Typography>}
                {d.areas.map((a) => (
                  <Stack key={a.area} direction="row" alignItems="center" sx={{ gap: 2, mb: 1.25 }}>
                    <Typography variant="body2" sx={{ width: 160, flexShrink: 0 }} noWrap>{a.area}</Typography>
                    <LinearProgress variant="determinate" value={a.pct ?? 0} sx={{ flexGrow: 1, height: 10, borderRadius: 5, bgcolor: "#EEF1F6",
                      "& .MuiLinearProgress-bar": { bgcolor: a.pct === null ? "#CBD3DE" : a.pct >= d.meta_sla ? "#2E7D32" : "#F5A623" } }} />
                    <Typography variant="body2" sx={{ width: 56, textAlign: "right", fontWeight: 700 }}>{a.pct === null ? "—" : `${Math.round(a.pct)} %`}</Typography>
                  </Stack>
                ))}
              </Paper>
              {d.atencion.length > 0 && (
                <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5 }}>Lo que necesita atención de Gerencia</Typography>
                  {d.atencion.map((x, i) => (
                    <Box key={i} sx={{ borderLeft: "4px solid #E8590C", pl: 1.5, mb: 1.25 }}>
                      <Typography variant="body2"><b>{x.titulo}</b> {x.texto}</Typography>
                    </Box>
                  ))}
                </Paper>
              )}
            </Stack>
            <EnvioMensual anio={anio} mes={mes} />
          </Box>
        </>
      )}
    </Box>
  );
}
