import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, MenuItem, Paper, Stack,
  Switch, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SendIcon from "@mui/icons-material/Send";
import ScheduleSendIcon from "@mui/icons-material/ScheduleSend";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import ScheduleIcon from "@mui/icons-material/Schedule";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import { del, get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { ReporteEnvio, ReporteProgramado } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import CampoCorreos from "../../components/CampoCorreos";
import { Cargando, Encabezado, Vacio } from "../../components/Comunes";
import { fechaHora } from "../../utils/formato";

const SECCIONES: [string, string][] = [
  ["totales", "Totales: nuevos, resueltos, abiertos, vencidos"], ["sla_area", "Cumplimiento del SLA por área"],
  ["vencidos", "Lista de tickets vencidos aún abiertos"], ["categorias", "Categorías más pedidas"],
  ["satisfaccion", "Satisfacción (encuestas)"], ["comparacion", "Comparación con el periodo anterior"],
  ["responsables", "Detalle por responsable"], ["recurrentes", "Tickets recurrentes no cerrados"],
];
const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const PERIODO: Record<string, string> = { DIARIA: "Día anterior", SEMANAL: "Semana anterior (lunes a domingo)", MENSUAL: "Mes anterior" };

type Form = Omit<ReporteProgramado, "id" | "proximo_envio" | "ultimo_envio" | "descripcion_frecuencia"> & { id?: number };
const NUEVO: Form = {
  nombre: "Resumen semanal para gerencia", destinatarios: [], frecuencia: "SEMANAL", dia_semana: 1, dia_mes: 1, hora: "08:00:00",
  secciones: ["totales", "sla_area", "vencidos", "categorias", "satisfaccion", "comparacion"], areas: null, adjuntar_excel: true, activo: true,
};

function Envios({ id }: { id: number }) {
  const envios = useQuery({ queryKey: ["reportes-programados", id, "envios"], queryFn: () => get<ReporteEnvio[]>(`/reportes-programados/${id}/envios`) });
  const icono = (e: ReporteEnvio) => (e.estado === "ENVIADO" ? <CheckCircleIcon fontSize="small" color="success" />
    : e.estado === "ERROR" || e.estado === "DESCARTADO" ? <ErrorIcon fontSize="small" color="error" /> : <ScheduleIcon fontSize="small" color="action" />);
  const texto = (e: ReporteEnvio) => (e.estado === "ENVIADO" ? "Enviado" : e.estado === "ERROR" ? "Reintentando" : e.estado === "DESCARTADO" ? "No se pudo enviar" : "En cola");
  return (
    <Paper>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, p: 2, pb: 1 }}>Últimos envíos</Typography>
      {(envios.data ?? []).map((e) => (
        <Stack key={e.id} direction="row" spacing={1} sx={{ alignItems: "center", px: 2, py: 1, borderTop: "1px solid #EEF1F6" }}>
          {icono(e)}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2">{fechaHora(e.fecha)}{e.es_prueba ? " · prueba" : ""}</Typography>
            <Typography variant="caption" color="text.secondary">{e.periodo}</Typography>
          </Box>
          <Tooltip title={e.destinatarios}><Typography variant="caption" color="text.secondary">{texto(e)} a {e.destinatarios.split(",").length}</Typography></Tooltip>
        </Stack>
      ))}
      {envios.data?.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>Todavía no se ha enviado.</Typography>}
    </Paper>
  );
}

export default function ReportesProgramados() {
  const cat = useCatalogos();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [f, setF] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const lista = useQuery({ queryKey: ["reportes-programados"], queryFn: () => get<ReporteProgramado[]>("/reportes-programados") });
  const refrescar = () => qc.invalidateQueries({ queryKey: ["reportes-programados"] });
  const guardar = useMutation({
    mutationFn: (x: Form) => (x.id ? put<ReporteProgramado>(`/reportes-programados/${x.id}`, x) : post<ReporteProgramado>("/reportes-programados", x)),
    onSuccess: (r) => {
      avisar("Reporte guardado");
      setError(null);
      setF({ ...r });
      refrescar();
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const prueba = useMutation({
    mutationFn: (id: number) => post<{ mensaje: string }>(`/reportes-programados/${id}/prueba`),
    onSuccess: (r) => {
      avisar(r.mensaje);
      refrescar();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const eliminar = useMutation({
    mutationFn: (id: number) => del(`/reportes-programados/${id}`),
    onSuccess: () => {
      avisar("Reporte eliminado");
      setF(null);
      refrescar();
    },
  });
  const verPrevia = async (id: number) => {
    try {
      setVista((await get<{ html: string }>(`/reportes-programados/${id}/vista-previa`)).html);
    } catch (e) {
      avisar(mensajeError(e), "error");
    }
  };
  const marcar = (k: string, v: boolean) => f && setF({ ...f, secciones: v ? [...f.secciones, k] : f.secciones.filter((x) => x !== k) });

  return (
    <>
      <Encabezado titulo="Reportes por correo" subtitulo="Resumen automático para gerencia: llega por correo con los indicadores del periodo y un Excel con el detalle."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => { setError(null); setF({ ...NUEVO }); }}>Nuevo reporte</Button>} />
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "7.2fr 4.8fr" }, alignItems: "start" }}>
        {f ? (
          <Paper sx={{ p: 3 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
              <ScheduleSendIcon color="primary" />
              <TextField variant="standard" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} sx={{ flex: 1 }}
                slotProps={{ htmlInput: { style: { fontSize: 20, fontWeight: 600 } } }} />
              <FormControlLabel control={<Switch checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} />} label="Activo" />
            </Stack>
            <Stack spacing={2}>
              {error && <Alert severity="error">{error}</Alert>}
              <CampoCorreos etiqueta="Destinatarios" valor={f.destinatarios} onCambio={(v) => setF({ ...f, destinatarios: v })} size="medium" />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Frecuencia" sx={{ flex: 1 }} value={f.frecuencia} onChange={(e) => setF({ ...f, frecuencia: e.target.value as Form["frecuencia"] })}>
                  <MenuItem value="DIARIA">Diario (días laborables)</MenuItem>
                  <MenuItem value="SEMANAL">Semanal</MenuItem>
                  <MenuItem value="MENSUAL">Mensual</MenuItem>
                </TextField>
                {f.frecuencia === "SEMANAL" && (
                  <TextField select label="Día" sx={{ flex: 1 }} value={f.dia_semana ?? 1} onChange={(e) => setF({ ...f, dia_semana: Number(e.target.value) })}>
                    {DIAS.map((d, i) => <MenuItem key={d} value={i + 1}>{d}</MenuItem>)}
                  </TextField>
                )}
                {f.frecuencia === "MENSUAL" && (
                  <TextField select label="Día del mes" sx={{ flex: 1 }} value={f.dia_mes ?? 1} onChange={(e) => setF({ ...f, dia_mes: Number(e.target.value) })}>
                    {Array.from({ length: 28 }, (_, i) => <MenuItem key={i} value={i + 1}>Día {i + 1}</MenuItem>)}
                  </TextField>
                )}
                <TextField label="Hora" type="time" sx={{ width: { sm: 130 } }} value={f.hora.slice(0, 5)} onChange={(e) => setF({ ...f, hora: `${e.target.value}:00` })} slotProps={{ inputLabel: { shrink: true } }} />
                <TextField label="Periodo que cubre" sx={{ flex: 1.4 }} value={PERIODO[f.frecuencia]} slotProps={{ input: { readOnly: true } }} />
              </Stack>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>Qué incluir</Typography>
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
                  {SECCIONES.map(([k, t]) => (
                    <FormControlLabel key={k} control={<Checkbox size="small" checked={f.secciones.includes(k)} onChange={(e) => marcar(k, e.target.checked)} />}
                      label={<Typography variant="body2">{t}</Typography>} />
                  ))}
                </Box>
              </Box>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Áreas" sx={{ flex: 1 }} value={f.areas ?? []}
                  slotProps={{ select: { multiple: true, renderValue: (v) => ((v as number[]).length ? (v as number[]).map((id) => cat.data?.areas.find((a) => a.id === id)?.nombre).join(", ") : "Todas las áreas"), displayEmpty: true }, inputLabel: { shrink: true } }}
                  onChange={(e) => { const v = e.target.value as unknown as number[]; setF({ ...f, areas: v.length ? v : null }); }}>
                  {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
                </TextField>
                <TextField select label="Adjuntar" sx={{ flex: 1 }} value={f.adjuntar_excel ? "x" : "n"} onChange={(e) => setF({ ...f, adjuntar_excel: e.target.value === "x" })}>
                  <MenuItem value="x">Excel con el detalle</MenuItem>
                  <MenuItem value="n">Nada (solo el correo)</MenuItem>
                </TextField>
              </Stack>
              <Alert severity="info">
                Se envía desde el correo de la mesa. El semanal y el mensual salen aunque ese día sea feriado; el diario solo en días laborables.
              </Alert>
              <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", flexWrap: "wrap", gap: 1 }}>
                {f.id && <Button color="error" startIcon={<DeleteIcon />} onClick={() => window.confirm("¿Eliminar este reporte?") && eliminar.mutate(f.id!)}>Eliminar</Button>}
                <Box sx={{ flex: 1 }} />
                {f.id && <Button startIcon={<VisibilityIcon />} onClick={() => verPrevia(f.id!)}>Vista previa</Button>}
                {f.id && <Button variant="outlined" startIcon={<SendIcon />} disabled={prueba.isPending} onClick={() => prueba.mutate(f.id!)}>Enviarme una prueba</Button>}
                <Button variant="contained" disabled={guardar.isPending || !f.destinatarios.length || !f.secciones.length || f.nombre.length < 3} onClick={() => guardar.mutate(f)}>Guardar</Button>
              </Stack>
            </Stack>
          </Paper>
        ) : (
          <Paper sx={{ p: 3 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Cómo funciona</Typography>
            {[
              "Elija a quién se envía, cada cuánto y qué secciones incluir.",
              "El correo trae los totales, el cumplimiento del SLA por área y los tickets vencidos, con un Excel adjunto.",
              "Use «Enviarme una prueba» para ver cómo llega antes de activarlo.",
            ].map((t, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ mb: 0.8 }}>
                <Typography variant="body2" sx={{ color: "primary.main", fontWeight: 700 }}>{i + 1}.</Typography>
                <Typography variant="body2">{t}</Typography>
              </Stack>
            ))}
          </Paper>
        )}
        <Stack spacing={2.5}>
          <Paper>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, p: 2, pb: 1 }}>Reportes configurados</Typography>
            {lista.isLoading ? <Cargando alto={100} /> : (lista.data ?? []).map((r) => (
              <Stack key={r.id} direction="row" sx={{ alignItems: "center", px: 2, py: 1.2, borderTop: "1px solid #EEF1F6", bgcolor: f?.id === r.id ? "#EEF5FC" : undefined }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{r.nombre}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {r.descripcion_frecuencia} · {r.destinatarios.length} destinatario{r.destinatarios.length === 1 ? "" : "s"}
                    {r.proximo_envio ? ` · próximo ${fechaHora(r.proximo_envio)}` : ""}
                  </Typography>
                </Box>
                <Chip size="small" label={r.activo ? "Activo" : "Pausado"} color={r.activo ? "success" : "default"} variant="outlined" />
                <IconButton size="small" onClick={() => { setError(null); setF({ ...r }); }}><EditIcon fontSize="small" /></IconButton>
              </Stack>
            ))}
            {lista.data?.length === 0 && <Vacio texto="No hay reportes programados" />}
          </Paper>
          {f?.id && <Envios id={f.id} />}
        </Stack>
      </Box>
      <Dialog open={!!vista} onClose={() => setVista(null)} maxWidth="md" fullWidth>
        <DialogTitle>Vista previa del correo</DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          {vista && <Box component="iframe" title="Vista previa" sandbox="" srcDoc={vista} sx={{ border: 0, width: "100%", height: "70vh" }} />}
        </DialogContent>
        <DialogActions><Button onClick={() => setVista(null)}>Cerrar</Button></DialogActions>
      </Dialog>
    </>
  );
}
