import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, IconButton, Link, MenuItem,
  Paper, Step, StepLabel, Stepper, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import LightbulbIcon from "@mui/icons-material/LightbulbOutlined";
import LinkIcon from "@mui/icons-material/Link";
import BuildIcon from "@mui/icons-material/Build";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import CloseIcon from "@mui/icons-material/Close";
import PublishedWithChangesIcon from "@mui/icons-material/PublishedWithChanges";
import { Stack } from "../../components/Pila";
import { del, get, post, put } from "../../api/client";
import type { EstadoProblema, OpcionesProblema, Porque, ProblemaDetalle as Detalle } from "../../api/ronda4b";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";
import { fecha } from "../../utils/formato";
import { EstadoProblemaChip } from "./comun";
import TiempoTrabajado from "../ronda4c/TiempoTrabajado";

const PASOS: { e: EstadoProblema; t: string }[] = [
  { e: "DETECTADO", t: "Detectado" }, { e: "EN_ANALISIS", t: "En análisis" }, { e: "ERROR_CONOCIDO", t: "Error conocido" },
  { e: "SOLUCION_EN_CAMBIO", t: "Solución en cambio" }, { e: "CERRADO", t: "Cerrado" },
];
const PREGUNTAS = ["¿Por qué pasa?", "¿Por qué?", "¿Por qué?", "¿Por qué?", "¿Por qué?"];
const fDiaMes = new Intl.DateTimeFormat("es-EC", { timeZone: "America/Guayaquil", day: "2-digit", month: "2-digit" });
const diaMes = (iso: string) => fDiaMes.format(new Date(iso));
const vacio = (): Porque[] => PREGUNTAS.map((p) => ({ pregunta: p, respuesta: "" }));

function Recuadro({ titulo, icono, accion, children }: { titulo: string; icono?: React.ReactNode; accion?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 2 }}>
        {icono}
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1 }}>{titulo}</Typography>
        {accion}
      </Stack>
      {children}
    </Paper>
  );
}

function Cifra({ valor, texto }: { valor: string | number; texto: string }) {
  return (
    <Box sx={{ bgcolor: "#EEF4FB", borderRadius: 2, p: 1.5, textAlign: "center" }}>
      <Typography sx={{ fontSize: 28, fontWeight: 800, color: "#1367AC", lineHeight: 1.2 }}>{valor}</Typography>
      <Typography variant="caption">{texto}</Typography>
    </Box>
  );
}

export default function ProblemaDetalle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const avisar = useAviso();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["problemas", "detalle", id], queryFn: () => get<Detalle>(`/problemas/${id}`) });
  const op = useQuery({ queryKey: ["problemas", "opciones"], queryFn: () => get<OpcionesProblema>("/problemas/opciones") });
  const p = q.data;
  const [f, setF] = useState<{ porques: Porque[]; causa_raiz: string; solucion_definitiva: string; solucion_temporal: string; palabras_clave: string;
    responsable_id: number | ""; cambio_id: number | ""; titulo: string; descripcion: string } | null>(null);
  const [ticket, setTicket] = useState("");
  const [cerrar, setCerrar] = useState(false);
  const [nota, setNota] = useState("");
  const [avisarSolicitantes, setAvisarSolicitantes] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!p) return;
    const porques = p.porques.length ? [...p.porques, ...vacio().slice(p.porques.length)] : vacio();
    setF({ porques, causa_raiz: p.causa_raiz ?? "", solucion_definitiva: p.solucion_definitiva ?? "", solucion_temporal: p.solucion_temporal ?? "",
      palabras_clave: p.palabras_clave ?? "", responsable_id: p.responsable_id ?? "", cambio_id: p.cambio_id ?? "", titulo: p.titulo,
      descripcion: p.descripcion ?? "" });
  }, [p]);

  const listo = (d: Detalle) => { qc.setQueryData(["problemas", "detalle", id], d); qc.invalidateQueries({ queryKey: ["problemas", "lista"] }); };
  const fallo = (e: unknown) => { setError(mensajeError(e)); avisar(mensajeError(e), "error"); };
  const cuerpo = () => f && ({
    titulo: f.titulo, descripcion: f.descripcion || null, categoria_id: p!.categoria_id, subcategoria_id: p!.subcategoria_id,
    responsable_id: f.responsable_id || null, palabras_clave: f.palabras_clave || null,
    porques: f.porques.filter((x) => x.respuesta.trim()), causa_raiz: f.causa_raiz || null, solucion_definitiva: f.solucion_definitiva || null,
    solucion_temporal: f.solucion_temporal || null, cambio_id: f.cambio_id || null,
  });
  const guardar = useMutation({ mutationFn: () => put<Detalle>(`/problemas/${id}`, cuerpo()), onSuccess: (d) => { listo(d); avisar("Análisis guardado"); }, onError: fallo });
  const estado = useMutation({
    mutationFn: async (e: { estado: EstadoProblema; nota?: string; avisar?: boolean }) => {
      if (p!.estado !== "CERRADO") await put<Detalle>(`/problemas/${id}`, cuerpo());   // guarda lo escrito antes de avanzar
      return post<Detalle>(`/problemas/${id}/estado`, e);
    },
    onSuccess: (d) => { listo(d); setCerrar(false); avisar(`Problema: ${d.estado_nombre}`); }, onError: fallo,
  });
  const publicar = useMutation({
    mutationFn: async () => { await put<Detalle>(`/problemas/${id}`, cuerpo()); return post<Detalle>(`/problemas/${id}/publicar`); },
    onSuccess: (d) => { listo(d); avisar("Solución temporal publicada en la Base de conocimiento"); }, onError: fallo,
  });
  const vincular = useMutation({ mutationFn: () => post<Detalle>(`/problemas/${id}/tickets`, { ticket }), onSuccess: (d) => { listo(d); setTicket(""); }, onError: fallo });
  const quitar = useMutation({ mutationFn: (tid: number) => del<Detalle>(`/problemas/${id}/tickets/${tid}`), onSuccess: listo, onError: fallo });

  if (q.isLoading || !f) return q.error ? <ErrorCarga error={q.error} /> : <Cargando />;
  if (!p) return null;
  const g = p.gestor && p.estado !== "CERRADO";
  const paso = PASOS.findIndex((x) => x.e === p.estado);
  const siguiente = paso < 3 ? PASOS[paso + 1] : null;
  const ro = { readOnly: !g };

  return (
    <Box>
      <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 1 }}>
        <IconButton onClick={() => navigate("/problemas")} aria-label="Volver"><ArrowBackIcon /></IconButton>
        <Typography variant="body2" color="text.secondary">Problemas / {p.numero}</Typography>
      </Stack>
      <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 1.5, mb: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>{p.numero} · {p.titulo}</Typography>
        <EstadoProblemaChip estado={p.estado} nombre={p.estado_nombre} />
      </Stack>

      <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
        <Stepper activeStep={p.estado === "CERRADO" ? 5 : paso} alternativeLabel>
          {PASOS.map((x) => <Step key={x.e}><StepLabel>{x.t}</StepLabel></Step>)}
        </Stepper>
        {p.gestor && (
          <Stack direction="row" justifyContent="flex-end" sx={{ gap: 1, mt: 2, flexWrap: "wrap" }}>
            {p.estado === "CERRADO" ? (
              <Button onClick={() => estado.mutate({ estado: "EN_ANALISIS" })}>Reabrir</Button>
            ) : (
              <>
                <Button onClick={() => guardar.mutate()} disabled={guardar.isPending}>Guardar análisis</Button>
                {siguiente && <Button variant="outlined" onClick={() => estado.mutate({ estado: siguiente.e })} disabled={estado.isPending}>Pasar a «{siguiente.t}»</Button>}
                <Button variant="contained" onClick={() => setCerrar(true)}>Cerrar problema</Button>
              </>
            )}
          </Stack>
        )}
        {error && <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(null)}>{error}</Alert>}
      </Paper>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "3fr 2fr" }, alignItems: "start" }}>
        <Stack sx={{ gap: 2 }}>
          <Recuadro titulo="Análisis de causa raíz · 5 porqués" icono={<LightbulbIcon sx={{ color: "#F2A900" }} />}>
            {f.porques.map((x, i) => (
              <Stack key={i} direction="row" sx={{ gap: 1.5, mb: 1.5 }}>
                <Box sx={{ width: 28, height: 28, borderRadius: "50%", bgcolor: i === 4 ? "#C62828" : "#1367AC", color: "#fff", display: "grid",
                  placeItems: "center", fontWeight: 700, fontSize: 13, flexShrink: 0, mt: 0.5 }}>{i + 1}</Box>
                <Box sx={{ display: "grid", gap: 0.5, flexGrow: 1 }}>
                  <TextField size="small" variant="standard" value={x.pregunta} placeholder="Pregunta"
                    slotProps={{ input: { ...ro, disableUnderline: !g, sx: { fontWeight: 700 } } }}
                    onChange={(e) => setF({ ...f, porques: f.porques.map((y, j) => (j === i ? { ...y, pregunta: e.target.value } : y)) })} />
                  <TextField size="small" multiline value={x.respuesta} placeholder="Respuesta" slotProps={{ input: ro }}
                    onChange={(e) => setF({ ...f, porques: f.porques.map((y, j) => (j === i ? { ...y, respuesta: e.target.value } : y)) })} />
                </Box>
              </Stack>
            ))}
            <Divider sx={{ my: 2 }} />
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
              <TextField label="Causa raíz" multiline minRows={2} value={f.causa_raiz} slotProps={{ input: ro }} onChange={(e) => setF({ ...f, causa_raiz: e.target.value })} />
              <Box>
                <TextField label="Solución definitiva" multiline minRows={2} fullWidth value={f.solucion_definitiva} slotProps={{ input: ro }}
                  onChange={(e) => setF({ ...f, solucion_definitiva: e.target.value })} />
                <TextField select size="small" fullWidth label="Cambio que la aplica" value={f.cambio_id} sx={{ mt: 1.5 }} disabled={!g}
                  slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
                  onChange={(e) => setF({ ...f, cambio_id: Number(e.target.value) || "" })}>
                  <MenuItem value="">Sin cambio todavía</MenuItem>
                  {p.cambio && !(op.data?.cambios ?? []).some((c) => c.id === p.cambio!.id) && <MenuItem value={p.cambio.id}>{p.cambio.numero} · {p.cambio.titulo}</MenuItem>}
                  {(op.data?.cambios ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.numero} · {c.titulo}</MenuItem>)}
                </TextField>
                <Stack direction="row" sx={{ gap: 1, mt: 1, flexWrap: "wrap" }}>
                  {p.cambio && (
                    <Chip icon={<PublishedWithChangesIcon />} color="primary" variant="outlined" clickable component={RouterLink} to={`/cambios/${p.cambio.id}`}
                      label={`${p.cambio.numero}${p.cambio.ventana_inicio ? ` · ${fecha(p.cambio.ventana_inicio)}` : ""}`} />
                  )}
                  {g && <Button size="small" component={RouterLink} to="/cambios/nuevo" target="_blank">Solicitar un cambio</Button>}
                </Stack>
              </Box>
            </Box>
          </Recuadro>

          <Recuadro titulo="Solución temporal (mientras tanto)" icono={<BuildIcon sx={{ color: "#2E7D32" }} />}
            accion={p.articulo ? (
              <Chip size="small" color="success" variant="outlined" icon={<MenuBookIcon />} label="Publicada en Base de conocimiento"
                clickable component={RouterLink} to={`/conocimiento?articulo=${p.articulo.id}`} />
            ) : g ? <Button size="small" startIcon={<MenuBookIcon />} disabled={!f.solucion_temporal.trim() || publicar.isPending} onClick={() => publicar.mutate()}>Publicar</Button> : null}>
            <TextField fullWidth multiline minRows={3} value={f.solucion_temporal} slotProps={{ input: ro }}
              placeholder="Qué hace el analista o el usuario para seguir trabajando. Se ofrece en los tickets nuevos parecidos."
              onChange={(e) => setF({ ...f, solucion_temporal: e.target.value })} />
            <TextField fullWidth size="small" label="Palabras clave" sx={{ mt: 2 }} value={f.palabras_clave} slotProps={{ input: ro }}
              helperText="Para reconocer tickets nuevos parecidos, separadas por coma (p. ej. ecuapass lento, dai no carga)"
              onChange={(e) => setF({ ...f, palabras_clave: e.target.value })} />
          </Recuadro>
          {p.nota_cierre && <Alert severity="success">Nota de cierre: {p.nota_cierre}</Alert>}
        </Stack>

        <Stack sx={{ gap: 2 }}>
          <Recuadro titulo={`Incidentes agrupados (${p.incidentes_lista.length})`} icono={<LinkIcon color="primary" />}>
            {p.gestor && (
              <Stack direction="row" sx={{ gap: 1, mb: 1.5 }}>
                <TextField size="small" fullWidth placeholder="ADU-2026-000123" value={ticket} onChange={(e) => setTicket(e.target.value)} />
                <Button variant="outlined" disabled={!ticket.trim() || vincular.isPending} onClick={() => vincular.mutate()}>Vincular</Button>
              </Stack>
            )}
            {p.incidentes_lista.length === 0 && <Typography variant="body2" color="text.secondary">Todavía no hay tickets agrupados.</Typography>}
            {p.incidentes_lista.slice(0, 30).map((t) => (
              <Stack key={t.id} direction="row" alignItems="center" sx={{ gap: 1, py: 1, borderTop: "1px solid", borderColor: "divider" }}>
                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Link component={RouterLink} to={`/tickets/${t.id}`} sx={{ fontWeight: 700 }}>{t.numero}</Link>
                  <Typography variant="body2" noWrap>{t.asunto}</Typography>
                </Box>
                {t.con_solucion && <Chip size="small" label="Solución temporal" color="success" variant="outlined" />}
                <Chip size="small" label={t.estado_nombre} />
                <Typography variant="caption" color="text.secondary" sx={{ width: 44, textAlign: "right" }}>{diaMes(t.fecha)}</Typography>
                {p.gestor && <IconButton size="small" aria-label="Quitar" onClick={() => quitar.mutate(t.id)}><CloseIcon fontSize="small" /></IconButton>}
              </Stack>
            ))}
            {p.incidentes_lista.length > 30 && <Typography variant="caption">y {p.incidentes_lista.length - 30} más</Typography>}
            {p.estado !== "CERRADO" && p.impacto.personas > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                Al cerrar el problema se avisa a {p.impacto.personas === 1 ? "la persona afectada" : `las ${p.impacto.personas} personas afectadas`}.
              </Typography>
            )}
          </Recuadro>

          <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Impacto acumulado</Typography>
            <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(3, 1fr)" }}>
              <Cifra valor={p.impacto.incidentes} texto="incidentes" />
              <Cifra valor={p.impacto.personas} texto="personas afectadas" />
              <Cifra valor={`${String(p.impacto.horas).replace(".", ",")} h`} texto="con el incidente abierto" />
            </Box>
            <TextField select size="small" fullWidth label="Responsable" sx={{ mt: 2.5 }} value={f.responsable_id} disabled={!g}
              onChange={(e) => setF({ ...f, responsable_id: Number(e.target.value) || "" })}>
              {(op.data?.responsables ?? []).map((u) => <MenuItem key={u.id} value={u.id}>{u.nombre}</MenuItem>)}
            </TextField>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              {p.dias_abierto !== null ? `Abierto hace ${p.dias_abierto} días` : `Cerrado el ${fecha(p.fecha_cierre)}`}
              {p.impacto.evitados > 0 && ` · ${p.impacto.evitados} respondidos con la solución temporal`}
              {p.origen === "PATRON" && " · creado desde un patrón detectado"}
            </Typography>
          </Paper>
          {p.gestor && <TiempoTrabajado tipo="problema" id={p.id} />}
        </Stack>
      </Box>

      <Dialog open={cerrar} onClose={() => setCerrar(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Cerrar {p.numero}</DialogTitle>
        <DialogContent dividers>
          {!f.solucion_definitiva.trim() && <Alert severity="info" sx={{ mb: 2 }}>Sin solución definitiva escrita: indique en la nota por qué se cierra.</Alert>}
          <TextField fullWidth multiline minRows={2} label="Nota de cierre" value={nota} onChange={(e) => setNota(e.target.value)} />
          <FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={avisarSolicitantes} onChange={(e) => setAvisarSolicitantes(e.target.checked)} />}
            label={`Avisar por correo a las personas afectadas (${p.impacto.personas})`} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCerrar(false)}>Cancelar</Button>
          <Button variant="contained" disabled={estado.isPending} onClick={() => estado.mutate({ estado: "CERRADO", nota: nota || undefined, avisar: avisarSolicitantes })}>
            Cerrar problema
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
