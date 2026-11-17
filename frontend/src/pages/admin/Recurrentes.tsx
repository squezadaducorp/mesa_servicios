import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Dialog, DialogContent, DialogTitle, Divider, FormControlLabel, IconButton, Link, MenuItem, Paper, Stack, Switch, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EventRepeatIcon from "@mui/icons-material/EventRepeat";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import EditIcon from "@mui/icons-material/Edit";
import EventIcon from "@mui/icons-material/Event";
import { get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { Frecuencia, Recurrente } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, Vacio } from "../../components/Comunes";
import { hoyIso } from "../../utils/formato";

const FRECUENCIAS: [Frecuencia, string][] = [["DIARIA", "Diario"], ["SEMANAL", "Semanal"], ["MENSUAL", "Mensual"], ["TRIMESTRAL", "Trimestral"], ["SEMESTRAL", "Semestral"], ["ANUAL", "Anual"]];
const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const ORD: [number, string][] = [[1, "Primer"], [2, "Segundo"], [3, "Tercer"], [4, "Cuarto"], [-1, "Último"]];
const ZONA = "America/Guayaquil";
const fDia = new Intl.DateTimeFormat("es-EC", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", timeZone: ZONA });
const fHora = new Intl.DateTimeFormat("es-EC", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: ZONA });

type Form = {
  id?: number; nombre: string; asunto: string; descripcion: string; tareas: string[]; categoria_id: number | ""; subcategoria_id: number | "";
  prioridad_id: number | ""; responsable_id: number | ""; solicitante_id: number | ""; frecuencia: Frecuencia; dia_semana: number | null;
  dia_mes: number | null; semana_mes: number | null; hora: string; desde: string; hasta: string; omitir_si_abierto: boolean; activo: boolean;
};

function aForm(r: Recurrente): Form {
  return {
    ...r, tareas: (r.tareas ?? "").split("\n").filter(Boolean), responsable_id: r.responsable_id ?? "", solicitante_id: r.solicitante_id,
    hora: r.hora.slice(0, 5), hasta: r.hasta ?? "",
  };
}

function cuerpo(f: Form) {
  return {
    nombre: f.nombre, asunto: f.asunto, descripcion: f.descripcion, tareas: f.tareas.filter((t) => t.trim()).join("\n") || null,
    categoria_id: f.categoria_id, subcategoria_id: f.subcategoria_id, prioridad_id: f.prioridad_id, responsable_id: f.responsable_id || null,
    solicitante_id: f.solicitante_id || null, frecuencia: f.frecuencia, dia_semana: f.dia_semana, dia_mes: f.dia_mes, semana_mes: f.semana_mes,
    hora: `${f.hora}:00`, desde: f.desde, hasta: f.hasta || null, omitir_si_abierto: f.omitir_si_abierto, activo: f.activo,
  };
}

function Editor({ inicial, onCerrar }: { inicial: Form; onCerrar: (cambio?: boolean) => void }) {
  const cat = useCatalogos();
  const { usuario } = useAuth();
  const avisar = useAviso();
  const [f, setF] = useState<Form>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [nuevaTarea, setNuevaTarea] = useState("");
  const [previa, setPrevia] = useState<{ fechas: string[]; movidas: string[] } | null>(null);
  const categoria = cat.data?.categorias.find((c) => c.id === f.categoria_id);
  const mensual = !["DIARIA", "SEMANAL"].includes(f.frecuencia);
  const valorDia = f.semana_mes ? `s:${f.semana_mes}:${f.dia_semana ?? 1}` : `d:${f.dia_mes ?? 1}`;
  const completo = f.nombre.length >= 3 && f.asunto.length >= 5 && f.descripcion.length >= 10 && f.categoria_id && f.subcategoria_id && f.prioridad_id && f.desde;

  useEffect(() => {
    if (!completo) return;
    const t = setTimeout(() => {
      post<{ fechas: string[]; movidas: string[] }>("/recurrentes/vista-previa", cuerpo(f)).then(setPrevia).catch(() => setPrevia(null));
    }, 400);
    return () => clearTimeout(t);
  }, [f, completo]);

  const guardar = useMutation({
    mutationFn: () => (f.id ? put<Recurrente>(`/recurrentes/${f.id}`, cuerpo(f)) : post<Recurrente>("/recurrentes", cuerpo(f))),
    onSuccess: () => {
      avisar("Programación guardada");
      onCerrar(true);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const ahora = useMutation({
    mutationFn: () => post<{ numero: string }>(`/recurrentes/${f.id}/ejecutar`),
    onSuccess: (t) => {
      avisar(`Ticket ${t.numero} creado`);
      onCerrar(true);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  if (!cat.data) return null;
  const personas = [...(usuario ? [{ id: usuario.id, nombre: `${usuario.nombre} (yo)` }] : []), ...cat.data.responsables.filter((r) => r.id !== usuario?.id)];

  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="lg" fullWidth>
      <DialogTitle>{f.id ? "Editar programación" : "Nueva programación"}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "7.4fr 4.6fr" }, alignItems: "start", mt: 1 }}>
          <Box>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "primary.dark", mb: 1.5 }}>1. El ticket que se va a crear</Typography>
            <Stack spacing={2}>
              <TextField label="Nombre de la programación" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} />
              <TextField label="Asunto" value={f.asunto} onChange={(e) => setF({ ...f, asunto: e.target.value })} helperText="{mes} y {año} se reemplazan al crear: «noviembre 2026»." />
              <TextField label="Descripción" multiline minRows={2} value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Categoría" sx={{ flex: 1 }} value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: Number(e.target.value), subcategoria_id: "" })}>
                  {cat.data.categorias.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
                <TextField select label="Subcategoría" sx={{ flex: 1 }} disabled={!categoria} value={f.subcategoria_id} onChange={(e) => setF({ ...f, subcategoria_id: Number(e.target.value) })}>
                  {(categoria?.subcategorias ?? []).filter((s) => s.activo).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
                </TextField>
                <TextField select label="Prioridad" sx={{ width: { sm: 140 } }} value={f.prioridad_id} onChange={(e) => setF({ ...f, prioridad_id: Number(e.target.value) })}>
                  {cat.data.prioridades.map((p) => <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Responsable" sx={{ flex: 1 }} value={f.responsable_id} onChange={(e) => setF({ ...f, responsable_id: e.target.value ? Number(e.target.value) : "" })}>
                  <MenuItem value="">Asignación automática</MenuItem>
                  {(categoria?.responsables.length ? categoria.responsables.map((r) => ({ id: r.usuario_id, nombre: r.nombre })) : cat.data.responsables).map((r) => (
                    <MenuItem key={r.id} value={r.id}>{r.nombre}</MenuItem>
                  ))}
                </TextField>
                <TextField select label="Solicitante" sx={{ flex: 1 }} value={f.solicitante_id} onChange={(e) => setF({ ...f, solicitante_id: Number(e.target.value) })}>
                  {personas.map((r) => <MenuItem key={r.id} value={r.id}>{r.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>Lista de tareas (se copia en la descripción)</Typography>
                {f.tareas.map((t, i) => (
                  <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                    <Typography variant="body2" sx={{ flex: 1 }}>☐ {t}</Typography>
                    <Button size="small" color="inherit" onClick={() => setF({ ...f, tareas: f.tareas.filter((_, j) => j !== i) })}>Quitar</Button>
                  </Stack>
                ))}
                <Stack direction="row" spacing={1}>
                  <TextField size="small" sx={{ flex: 1 }} placeholder="Nueva tarea" value={nuevaTarea} onChange={(e) => setNuevaTarea(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && nuevaTarea.trim()) { e.preventDefault(); setF({ ...f, tareas: [...f.tareas, nuevaTarea.trim()] }); setNuevaTarea(""); } }} />
                  <Button size="small" startIcon={<AddIcon />} disabled={!nuevaTarea.trim()} onClick={() => { setF({ ...f, tareas: [...f.tareas, nuevaTarea.trim()] }); setNuevaTarea(""); }}>Agregar tarea</Button>
                </Stack>
              </Box>
            </Stack>
            <Divider sx={{ my: 2.5 }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "primary.dark", mb: 1.5 }}>2. Cada cuánto</Typography>
            <ToggleButtonGroup value={f.frecuencia} exclusive size="small" color="primary" sx={{ mb: 2, flexWrap: "wrap" }}
              onChange={(_, v: Frecuencia | null) => v && setF({ ...f, frecuencia: v, dia_semana: v === "SEMANAL" ? f.dia_semana ?? 1 : f.dia_semana, dia_mes: f.dia_mes ?? (f.semana_mes ? null : 1) })}>
              {FRECUENCIAS.map(([v, t]) => <ToggleButton key={v} value={v}>{t}</ToggleButton>)}
            </ToggleButtonGroup>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              {f.frecuencia === "SEMANAL" && (
                <TextField select label="Día" sx={{ flex: 1 }} value={f.dia_semana ?? 1} onChange={(e) => setF({ ...f, dia_semana: Number(e.target.value) })}>
                  {DIAS.map((d, i) => <MenuItem key={d} value={i + 1}>{d.charAt(0).toUpperCase() + d.slice(1)}</MenuItem>)}
                </TextField>
              )}
              {mensual && (
                <TextField select label="Qué día del mes" sx={{ flex: 1.3 }} value={valorDia}
                  onChange={(e) => {
                    const [k, a, b] = e.target.value.split(":");
                    setF(k === "d" ? { ...f, dia_mes: Number(a), semana_mes: null, dia_semana: null } : { ...f, dia_mes: null, semana_mes: Number(a), dia_semana: Number(b) });
                  }}>
                  {Array.from({ length: 28 }, (_, i) => <MenuItem key={i} value={`d:${i + 1}`}>Día {i + 1}</MenuItem>)}
                  <MenuItem value="d:-1">Último día del mes</MenuItem>
                  {ORD.flatMap(([n, o]) => DIAS.slice(0, 5).map((d, i) => <MenuItem key={`${n}-${i}`} value={`s:${n}:${i + 1}`}>{o} {d}</MenuItem>))}
                </TextField>
              )}
              <TextField label="Hora" type="time" value={f.hora} onChange={(e) => setF({ ...f, hora: e.target.value })} sx={{ width: { sm: 130 } }} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField label="Desde" type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} sx={{ width: { sm: 160 } }} slotProps={{ inputLabel: { shrink: true } }}
                helperText={f.frecuencia === "ANUAL" ? "El mes de esta fecha es el del ticket anual" : undefined} />
              <TextField label="Hasta (opcional)" type="date" value={f.hasta} onChange={(e) => setF({ ...f, hasta: e.target.value })} sx={{ width: { sm: 160 } }} slotProps={{ inputLabel: { shrink: true } }} />
            </Stack>
            <FormControlLabel sx={{ mt: 1.5 }} control={<Switch checked={f.omitir_si_abierto} onChange={(e) => setF({ ...f, omitir_si_abierto: e.target.checked })} />}
              label="No crear uno nuevo si el anterior sigue abierto (avisar al supervisor)" />
            <FormControlLabel control={<Switch checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} />} label="Activa" />
          </Box>
          <Box>
            <Paper variant="outlined" sx={{ p: 2.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
                <EventIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Próximas 6 fechas</Typography>
              </Stack>
              {!previa ? (
                <Typography variant="body2" color="text.secondary">Complete los datos para ver cuándo se crearía.</Typography>
              ) : previa.fechas.map((d, i) => (
                <Box key={d} sx={{ py: 1, borderBottom: "1px solid #EEF1F6" }}>
                  <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: previa.movidas[i] ? "#B57400" : undefined }}>{fDia.format(new Date(d))}</Typography>
                    <Typography variant="body2" color="text.secondary">{fHora.format(new Date(d))}</Typography>
                  </Stack>
                  {previa.movidas[i] && <Typography variant="caption" sx={{ color: "#B57400" }}>{previa.movidas[i]}</Typography>}
                </Box>
              ))}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                Usa el calendario de feriados de «SLA y calendario»: si la fecha cae en feriado o fin de semana, se crea el siguiente día hábil.
              </Typography>
            </Paper>
            <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", mt: 2.5, flexWrap: "wrap", gap: 1 }}>
              <Button color="inherit" onClick={() => onCerrar()}>Cancelar</Button>
              {f.id && <Button variant="outlined" startIcon={<PlayArrowIcon />} disabled={ahora.isPending} onClick={() => ahora.mutate()}>Crear uno ahora</Button>}
              <Button variant="contained" disabled={!completo || guardar.isPending} onClick={() => guardar.mutate()}>Guardar</Button>
            </Stack>
          </Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

export default function Recurrentes() {
  const { usuario } = useAuth();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [editando, setEditando] = useState<Form | null>(null);
  const lista = useQuery({ queryKey: ["recurrentes"], queryFn: () => get<Recurrente[]>("/recurrentes") });
  const refrescar = () => qc.invalidateQueries({ queryKey: ["recurrentes"] });
  const activar = useMutation({
    mutationFn: (r: Recurrente) => put(`/recurrentes/${r.id}`, cuerpo({ ...aForm(r), activo: !r.activo })),
    onSuccess: refrescar,
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const ahora = useMutation({
    mutationFn: (id: number) => post<{ numero: string }>(`/recurrentes/${id}/ejecutar`),
    onSuccess: (t) => {
      avisar(`Ticket ${t.numero} creado`);
      refrescar();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const nueva = (): Form => ({
    nombre: "", asunto: "", descripcion: "", tareas: [], categoria_id: "", subcategoria_id: "", prioridad_id: "", responsable_id: "",
    solicitante_id: usuario?.id ?? "", frecuencia: "MENSUAL", dia_semana: 1, dia_mes: null, semana_mes: 1, hora: "08:30", desde: hoyIso(), hasta: "",
    omitir_si_abierto: true, activo: true,
  });

  return (
    <>
      <Encabezado titulo="Tickets recurrentes" subtitulo="Mantenimientos y tareas que se repiten: el sistema crea el ticket solo, ya asignado y con su SLA."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditando(nueva())}>Nueva programación</Button>} />
      <Alert severity="info" icon={<EventRepeatIcon />} sx={{ mb: 2.5 }}>
        Si la fecha cae en feriado o fin de semana, el ticket se crea el siguiente día hábil.
      </Alert>
      <Paper sx={{ overflowX: "auto" }}>
        {lista.isLoading ? <Cargando /> : (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Programación</TableCell><TableCell>Se crea</TableCell><TableCell>Responsable</TableCell>
                <TableCell>Próximo</TableCell><TableCell>Último</TableCell><TableCell>Activa</TableCell><TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {(lista.data ?? []).map((r) => (
                <TableRow key={r.id} hover sx={!r.activo ? { opacity: 0.55 } : undefined}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{r.nombre}</Typography>
                    <Typography variant="caption" color="text.secondary">{r.categoria} › {r.subcategoria}</Typography>
                  </TableCell>
                  <TableCell><Stack direction="row" spacing={0.8} sx={{ alignItems: "center" }}><EventRepeatIcon fontSize="small" color="action" /><Typography variant="body2">{r.descripcion_frecuencia}</Typography></Stack></TableCell>
                  <TableCell>{r.responsable ?? "Automático"}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    {r.proxima_ejecucion ? <Typography variant="body2" sx={{ fontWeight: 600 }}>{fDia.format(new Date(r.proxima_ejecucion))} {fHora.format(new Date(r.proxima_ejecucion))}</Typography> : "—"}
                  </TableCell>
                  <TableCell>
                    {r.ultimo_ticket_id ? <Link component={RouterLink} to={`/tickets/${r.ultimo_ticket_id}`} sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{r.ultimo_ticket_numero}</Link> : "—"}
                    {r.ultimo_resultado && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{r.ultimo_resultado}</Typography>}
                  </TableCell>
                  <TableCell><Switch size="small" checked={r.activo} onChange={() => activar.mutate(r)} /></TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    <Tooltip title="Crear ahora"><IconButton size="small" onClick={() => ahora.mutate(r.id)}><PlayArrowIcon fontSize="small" /></IconButton></Tooltip>
                    <Tooltip title="Editar"><IconButton size="small" onClick={() => setEditando(aForm(r))}><EditIcon fontSize="small" /></IconButton></Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {lista.data?.length === 0 && <Vacio texto="Todavía no hay programaciones. Cree la primera, por ejemplo el mantenimiento preventivo mensual." />}
      </Paper>
      {editando && <Editor inicial={editando} onCerrar={(c) => { setEditando(null); if (c) refrescar(); }} />}
    </>
  );
}
