import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Paper, Stack, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import { del, get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { ExcepcionCalendario, Horario, PoliticaSla, Tramo } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado } from "../../components/Comunes";
import { PrioridadChip } from "../../components/Chips";
import { fecha } from "../../utils/formato";

const DIAS = ["", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const h = (min: number) => +(min / 60).toFixed(2);
const hhmm = (t: string) => t.slice(0, 5);

function Prioridades() {
  const cat = useCatalogos();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [edit, setEdit] = useState<Record<number, { r: number; s: number }>>({});
  const guardar = useMutation({
    mutationFn: async () => {
      for (const [id, v] of Object.entries(edit)) await put(`/admin/sla/prioridades/${id}`, { sla_respuesta_min: Math.round(v.r * 60), sla_resolucion_min: Math.round(v.s * 60) });
    },
    onSuccess: () => {
      setEdit({});
      qc.invalidateQueries({ queryKey: ["catalogos"] });
      avisar("SLA actualizado. Aplica a los tickets nuevos y a los que cambien de prioridad.");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography variant="h6">SLA por prioridad</Typography>
        <Button variant="contained" size="small" disabled={!Object.keys(edit).length || guardar.isPending} onClick={() => guardar.mutate()}>
          Guardar
        </Button>
      </Stack>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Prioridad</TableCell>
              <TableCell>Primera respuesta (h)</TableCell>
              <TableCell>Resolución (h)</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(cat.data?.prioridades ?? []).map((p) => {
              const v = edit[p.id] ?? { r: h(p.sla_respuesta_min), s: h(p.sla_resolucion_min) };
              return (
                <TableRow key={p.id}>
                  <TableCell>
                    <PrioridadChip codigo={p.codigo} nombre={p.nombre} />
                  </TableCell>
                  <TableCell>
                    <TextField type="number" value={v.r} onChange={(e) => setEdit({ ...edit, [p.id]: { ...v, r: Number(e.target.value) } })} slotProps={{ htmlInput: { min: 0.25, step: 0.25 } }} sx={{ width: 120 }} />
                  </TableCell>
                  <TableCell>
                    <TextField type="number" value={v.s} onChange={(e) => setEdit({ ...edit, [p.id]: { ...v, s: Number(e.target.value) } })} slotProps={{ htmlInput: { min: 0.5, step: 0.5 } }} sx={{ width: 120 }} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography variant="caption" sx={{ color: "text.secondary" }}>
        Horas laborables según el horario configurado. Avisos automáticos al 75 % y 90 %; al 100 % el ticket queda incumplido y se escala.
      </Typography>
    </Paper>
  );
}

function Politicas() {
  const cat = useCatalogos();
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["admin", "politicas"], queryFn: () => get<PoliticaSla[]>("/admin/sla/politicas") });
  const [f, setF] = useState<{ categoria_id: number | ""; prioridad_id: number | ""; r: number; s: number } | null>(null);
  const guardar = useMutation({
    mutationFn: (p: { categoria_id: number; prioridad_id: number; sla_respuesta_min: number; sla_resolucion_min: number; activo: boolean }) => post("/admin/sla/politicas", p),
    onSuccess: () => {
      setF(null);
      qc.invalidateQueries({ queryKey: ["admin", "politicas"] });
      avisar("Política guardada");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const nombreCat = (id: number) => cat.data?.categorias.find((c) => c.id === id)?.nombre ?? id;
  const prio = (id: number) => cat.data?.prioridades.find((p) => p.id === id);
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography variant="h6">SLA específicos por categoría</Typography>
        <Button size="small" startIcon={<AddIcon />} onClick={() => setF({ categoria_id: "", prioridad_id: "", r: 2, s: 8 })}>
          Agregar
        </Button>
      </Stack>
      {!q.data?.length ? (
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Sin excepciones: todas las categorías usan el SLA por prioridad.
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Categoría</TableCell>
              <TableCell>Prioridad</TableCell>
              <TableCell>Respuesta</TableCell>
              <TableCell>Resolución</TableCell>
              <TableCell>Estado</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {q.data.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{nombreCat(p.categoria_id)}</TableCell>
                <TableCell>{prio(p.prioridad_id)?.nombre}</TableCell>
                <TableCell>{h(p.sla_respuesta_min)} h</TableCell>
                <TableCell>{h(p.sla_resolucion_min)} h</TableCell>
                <TableCell>{p.activo ? <Chip size="small" color="success" label="Activa" /> : <Chip size="small" label="Inactiva" />}</TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    onClick={() => guardar.mutate({ categoria_id: p.categoria_id, prioridad_id: p.prioridad_id, sla_respuesta_min: p.sla_respuesta_min, sla_resolucion_min: p.sla_resolucion_min, activo: !p.activo })}
                  >
                    {p.activo ? "Desactivar" : "Activar"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={!!f} onClose={() => setF(null)} fullWidth maxWidth="xs">
        <DialogTitle>SLA por categoría</DialogTitle>
        {f && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField select label="Categoría" value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: Number(e.target.value) })}>
                {(cat.data?.categorias ?? []).map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Prioridad" value={f.prioridad_id} onChange={(e) => setF({ ...f, prioridad_id: Number(e.target.value) })}>
                {(cat.data?.prioridades ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField type="number" label="Respuesta (h)" value={f.r} onChange={(e) => setF({ ...f, r: Number(e.target.value) })} />
              <TextField type="number" label="Resolución (h)" value={f.s} onChange={(e) => setF({ ...f, s: Number(e.target.value) })} />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setF(null)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!f?.categoria_id || !f?.prioridad_id}
            onClick={() =>
              f &&
              guardar.mutate({
                categoria_id: Number(f.categoria_id),
                prioridad_id: Number(f.prioridad_id),
                sla_respuesta_min: Math.round(f.r * 60),
                sla_resolucion_min: Math.round(f.s * 60),
                activo: true,
              })
            }
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

function HorarioLaboral() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["admin", "horario"], queryFn: () => get<Horario | null>("/admin/sla/horario") });
  const [tramos, setTramos] = useState<Tramo[]>([]);
  useEffect(() => {
    if (q.data) setTramos(q.data.tramos.map((t) => ({ ...t, hora_inicio: hhmm(t.hora_inicio), hora_fin: hhmm(t.hora_fin) })));
  }, [q.data]);
  const guardar = useMutation({
    mutationFn: () => put("/admin/sla/horario", { nombre: q.data?.nombre ?? "Horario ADUCORP", zona_horaria: q.data?.zona_horaria ?? "America/Guayaquil", tramos }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "horario"] });
      avisar("Horario guardado");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const totalMin = tramos.reduce((s, t) => {
    const [a, b] = [t.hora_inicio, t.hora_fin].map((x) => Number(x.slice(0, 2)) * 60 + Number(x.slice(3, 5)));
    return s + Math.max(0, b - a);
  }, 0);
  if (q.isLoading) return <Cargando alto={120} />;
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Box>
          <Typography variant="h6">Horario laboral</Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {q.data?.zona_horaria ?? "America/Guayaquil"} · {h(totalMin)} h laborables por semana
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button size="small" startIcon={<AddIcon />} onClick={() => setTramos([...tramos, { dia_semana: 1, hora_inicio: "08:30", hora_fin: "13:00" }])}>
            Tramo
          </Button>
          <Button variant="contained" size="small" disabled={guardar.isPending} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </Stack>
      </Stack>
      <Stack spacing={1}>
        {tramos
          .map((t, i) => ({ t, i }))
          .sort((a, b) => a.t.dia_semana - b.t.dia_semana || a.t.hora_inicio.localeCompare(b.t.hora_inicio))
          .map(({ t, i }) => (
            <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <TextField select value={t.dia_semana} onChange={(e) => setTramos(tramos.map((x, j) => (j === i ? { ...x, dia_semana: Number(e.target.value) } : x)))} sx={{ width: 140 }}>
                {DIAS.slice(1).map((d, k) => (
                  <MenuItem key={d} value={k + 1}>
                    {d}
                  </MenuItem>
                ))}
              </TextField>
              <TextField type="time" value={t.hora_inicio} onChange={(e) => setTramos(tramos.map((x, j) => (j === i ? { ...x, hora_inicio: e.target.value } : x)))} sx={{ width: 150 }} />
              <Typography>a</Typography>
              <TextField type="time" value={t.hora_fin} onChange={(e) => setTramos(tramos.map((x, j) => (j === i ? { ...x, hora_fin: e.target.value } : x)))} sx={{ width: 150 }} />
              <IconButton size="small" onClick={() => setTramos(tramos.filter((_, j) => j !== i))} aria-label="Quitar tramo">
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
      </Stack>
    </Paper>
  );
}

function Calendario() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["admin", "calendario"], queryFn: () => get<ExcepcionCalendario[]>("/admin/sla/calendario") });
  const [f, setF] = useState<{ fecha: string; tipo: "FERIADO" | "HORARIO_ESPECIAL"; hora_inicio: string; hora_fin: string; descripcion: string } | null>(null);
  const crear = useMutation({
    mutationFn: () =>
      post("/admin/sla/calendario", {
        ...f,
        hora_inicio: f?.tipo === "HORARIO_ESPECIAL" ? f.hora_inicio : null,
        hora_fin: f?.tipo === "HORARIO_ESPECIAL" ? f.hora_fin : null,
      }),
    onSuccess: () => {
      setF(null);
      qc.invalidateQueries({ queryKey: ["admin", "calendario"] });
      avisar("Fecha registrada");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const borrar = useMutation({
    mutationFn: (id: number) => del(`/admin/sla/calendario/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "calendario"] }),
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography variant="h6">Feriados y jornadas especiales</Typography>
        <Button size="small" startIcon={<AddIcon />} onClick={() => setF({ fecha: "", tipo: "FERIADO", hora_inicio: "08:30", hora_fin: "13:00", descripcion: "" })}>
          Agregar fecha
        </Button>
      </Stack>
      <Alert severity="info" sx={{ mb: 1.5 }}>
        Los feriados nacionales cargados son referenciales; confírmelos con el decreto ejecutivo de cada año.
      </Alert>
      <TableContainer sx={{ maxHeight: 420 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Fecha</TableCell>
              <TableCell>Tipo</TableCell>
              <TableCell>Horario</TableCell>
              <TableCell>Descripción</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {q.data?.map((x) => (
              <TableRow key={x.id} hover>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{fecha(`${x.fecha}T12:00:00Z`)}</TableCell>
                <TableCell>
                  <Chip size="small" label={x.tipo === "FERIADO" ? "Feriado" : "Jornada especial"} color={x.tipo === "FERIADO" ? "error" : "warning"} variant="outlined" />
                </TableCell>
                <TableCell>{x.hora_inicio ? `${hhmm(x.hora_inicio)} – ${hhmm(x.hora_fin ?? "")}` : "—"}</TableCell>
                <TableCell>{x.descripcion}</TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => borrar.mutate(x.id)} aria-label="Eliminar">
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Dialog open={!!f} onClose={() => setF(null)} fullWidth maxWidth="xs">
        <DialogTitle>Nueva fecha</DialogTitle>
        {f && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField type="date" label="Fecha" value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField select label="Tipo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as "FERIADO" | "HORARIO_ESPECIAL" })}>
                <MenuItem value="FERIADO">Feriado (no laborable)</MenuItem>
                <MenuItem value="HORARIO_ESPECIAL">Jornada especial (horario reducido)</MenuItem>
              </TextField>
              {f.tipo === "HORARIO_ESPECIAL" && (
                <Stack direction="row" spacing={1}>
                  <TextField type="time" label="Desde" value={f.hora_inicio} onChange={(e) => setF({ ...f, hora_inicio: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
                  <TextField type="time" label="Hasta" value={f.hora_fin} onChange={(e) => setF({ ...f, hora_fin: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
                </Stack>
              )}
              <TextField label="Descripción" value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setF(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!f?.fecha || !f?.descripcion || crear.isPending} onClick={() => crear.mutate()}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

export default function Sla() {
  return (
    <>
      <Encabezado titulo="SLA y calendario" subtitulo="Tiempos de atención, horario laboral y días no laborables que usa el motor de SLA" />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" }, alignItems: "start" }}>
        <Stack spacing={2}>
          <Prioridades />
          <Politicas />
        </Stack>
        <Stack spacing={2}>
          <HorarioLaboral />
          <Calendario />
        </Stack>
      </Box>
    </>
  );
}
