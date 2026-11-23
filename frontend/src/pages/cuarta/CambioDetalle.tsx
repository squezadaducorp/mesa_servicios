import { useRef, useState, type ReactNode } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Breadcrumbs, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Link,
  MenuItem, Paper, Radio, RadioGroup, Tab, Tabs, TextField, Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import EventIcon from "@mui/icons-material/Event";
import UndoIcon from "@mui/icons-material/Undo";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFileOutlined";
import EditIcon from "@mui/icons-material/Edit";
import { Stack } from "../../components/Pila";
import { api, descargar, get, post } from "../../api/client";
import type { Cambio, OpcionesCambio, Persona } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga, Vacio } from "../../components/Comunes";
import { fechaHora, tiempoRelativo } from "../../utils/formato";
import { COLOR_CELDA, EstadoCambio, MATRIZ, RiesgoChip, TIPO_CAMBIO, aLocal, deLocal, diaHora, ventanaLarga } from "./cambiosComun";

const ddmm = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString("es-EC", { timeZone: "America/Guayaquil", day: "2-digit", month: "2-digit" }) : "");
const iniciales = (n?: string | null) => (n ?? "?").split(" ").filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
const PRIORIDAD: Record<string, { t: string; c: "error" | "warning" | "default" }> = {
  ALTA: { t: "Alta", c: "error" }, MEDIA: { t: "Media", c: "warning" }, BAJA: { t: "Baja", c: "default" },
};

// ------------------------------------------------------------------ stepper
function Pasos({ c }: { c: Cambio }) {
  const evaluado = !!c.fecha_evaluacion && !["SOLICITADO", "EN_ESPERA"].includes(c.estado);
  const ger = c.aprobaciones.find((a) => a.rol === "GERENCIA");
  const pendiente = c.aprobaciones.find((a) => a.estado === "PENDIENTE");
  const aprobado = ["PROGRAMADO", "EN_REVISION", "IMPLEMENTADO", "REVERTIDO"].includes(c.estado);
  const pasos = [
    { t: "Solicitado", x: `${c.solicitante.nombre} · ${ddmm(c.fecha_creacion)}`, ok: true },
    { t: "Evaluado por TI", x: evaluado ? `${c.evaluado_por?.nombre ?? "TI"} · ${ddmm(c.fecha_evaluacion)}` : c.estado === "EN_ESPERA" ? "En espera" : "Pendiente", ok: evaluado },
    {
      t: ger ? "Aprobación de Gerencia" : "Aprobación",
      x: pendiente ? `Pendiente · ${pendiente.aprobador?.nombre ?? ""}` : aprobado ? (c.tipo_cambio === "ESTANDAR" ? "No necesita (estándar)" : "Aprobado") : c.estado === "RECHAZADO" ? "Rechazado" : "—",
      ok: aprobado,
    },
    { t: "Implementación", x: c.fecha_implementado ? `Hecho · ${ddmm(c.fecha_implementado)}` : c.ventana_inicio ? `${diaHora(c.ventana_inicio)}${c.ventana_fin ? `-${diaHora(c.ventana_fin).slice(-5)}` : ""}` : "—", ok: !!c.fecha_implementado },
    { t: "Revisión posterior", x: c.resultado ? c.textos.resultado ?? c.resultado : c.fecha_implementado ? "Pendiente" : "—", ok: ["IMPLEMENTADO", "REVERTIDO"].includes(c.estado) },
  ];
  const actual = pasos.findIndex((p) => !p.ok);
  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 2.5, overflowX: "auto" }}>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(130px, 1fr))" }}>
        {pasos.map((p, i) => (
          <Box key={p.t} sx={{ textAlign: "center", position: "relative" }}>
            {i > 0 && <Box sx={{ position: "absolute", top: 14, right: "calc(50% + 20px)", left: "calc(-50% + 20px)", height: 2, bgcolor: "divider" }} />}
            <Box sx={{ width: 28, height: 28, borderRadius: "50%", mx: "auto", display: "grid", placeItems: "center", color: "#fff", fontSize: 13, fontWeight: 700,
              bgcolor: p.ok || i === actual ? "primary.main" : "#9AA4B2" }}>
              {p.ok ? <CheckCircleIcon sx={{ fontSize: 20 }} /> : i + 1}
            </Box>
            <Typography variant="body2" sx={{ fontWeight: 600, mt: 1, color: p.ok || i === actual ? "text.primary" : "text.secondary" }}>{p.t}</Typography>
            <Typography variant="caption" color="text.secondary">{p.x}</Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

function Fila({ k, children }: { k: string; children: ReactNode }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "200px 1fr" }, gap: { xs: 0.25, sm: 2 }, py: 1 }}>
      <Typography variant="body2" color="text.secondary">{k}</Typography>
      <Box sx={{ typography: "body2", whiteSpace: "pre-wrap" }}>{children}</Box>
    </Box>
  );
}

function Matriz({ impacto, probabilidad, onElegir }: { impacto: string; probabilidad: string; onElegir?: (i: string, p: string) => void }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">Impacto × probabilidad de falla</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "60px repeat(3, 1fr)", gap: 0.75, mt: 1, alignItems: "center" }}>
        <span />
        {["Baja", "Media", "Alta"].map((x) => <Typography key={x} variant="caption" sx={{ textAlign: "center" }}>{x}</Typography>)}
        {["ALTO", "MEDIO", "BAJO"].map((imp) => (
          <Box key={imp} sx={{ display: "contents" }}>
            <Typography variant="caption">{imp.charAt(0) + imp.slice(1).toLowerCase()}</Typography>
            {["BAJA", "MEDIA", "ALTA"].map((p) => {
              const r = MATRIZ[imp][p];
              const sel = imp === impacto && p === probabilidad;
              return (
                <Box key={p} role={onElegir ? "button" : undefined} tabIndex={onElegir ? 0 : undefined}
                  aria-label={`Impacto ${imp.toLowerCase()}, probabilidad ${p.toLowerCase()}: riesgo ${r.toLowerCase()}`}
                  onClick={() => onElegir?.(imp, p)} onKeyDown={(e) => e.key === "Enter" && onElegir?.(imp, p)}
                  sx={{ height: 30, borderRadius: 1.5, bgcolor: COLOR_CELDA[r], opacity: sel ? 1 : 0.75, cursor: onElegir ? "pointer" : "default",
                    border: sel ? "2px solid #D9480F" : "2px solid transparent", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700, color: "#B23A00" }}>
                  {sel ? r : ""}
                </Box>
              );
            })}
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ------------------------------------------------------------------ evaluación (sección 7)
function Evaluacion({ c, op, onListo }: { c: Cambio; op: OpcionesCambio; onListo: () => void }) {
  const avisar = useAviso();
  const [e, setE] = useState({
    clasificacion: c.clasificacion ?? "MEJORA", tipo_cambio: c.tipo_cambio ?? "NORMAL", impacto: c.impacto ?? "MEDIO", probabilidad: c.probabilidad ?? "BAJA",
    esfuerzo: c.esfuerzo ?? "", prioridad_ti: c.prioridad_ti ?? c.prioridad_sugerida ?? "MEDIA", evaluacion: c.evaluacion ?? "",
    plan_implementacion: c.plan_implementacion ?? "", plan_reversion: c.plan_reversion ?? "", responsable_id: c.responsable?.id ?? "",
    ventana_inicio: aLocal(c.ventana_inicio), ventana_fin: aLocal(c.ventana_fin), comentario: "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof e, v: string | number) => setE((x) => ({ ...x, [k]: v }));
  const riesgo = MATRIZ[e.impacto][e.probabilidad];
  const enviar = useMutation({
    mutationFn: (decision: string) => post<Cambio>(`/cambios/${c.id}/evaluar`, {
      ...e, decision, esfuerzo: e.esfuerzo || null, responsable_id: e.responsable_id === "" ? null : Number(e.responsable_id),
      ventana_inicio: deLocal(e.ventana_inicio), ventana_fin: deLocal(e.ventana_fin), comentario: e.comentario || null,
      evaluacion: e.evaluacion || null, plan_implementacion: e.plan_implementacion || null, plan_reversion: e.plan_reversion || null,
    }),
    onSuccess: (r) => { avisar(`${r.numero}: ${r.estado_nombre}`); onListo(); },
    onError: (x) => setError(mensajeError(x)),
  });
  const quien = e.tipo_cambio === "ESTANDAR" ? "No necesita aprobación: queda programado."
    : e.tipo_cambio === "EMERGENCIA" ? "Emergencia: solo el Jefe de TI; Gerencia recibe un aviso."
      : riesgo === "BAJO" ? "Riesgo bajo: lo aprueba solo el Jefe de TI." : `Riesgo ${riesgo.toLowerCase()}: lo aprueban el Jefe de TI y Gerencia${op.gerencia ? ` (${op.gerencia})` : ""}.`;
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 }, mt: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Evaluación TI (sección 7)</Typography>
      <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "200px 1fr" } }}>
        <Box>
          <Typography variant="caption" color="text.secondary">Tipo de cambio</Typography>
          <RadioGroup value={e.tipo_cambio} onChange={(x) => set("tipo_cambio", x.target.value)}>
            {Object.entries(TIPO_CAMBIO).map(([k, v]) => <FormControlLabel key={k} value={k} control={<Radio />} label={v} />)}
          </RadioGroup>
        </Box>
        <Matriz impacto={e.impacto} probabilidad={e.probabilidad} onElegir={(i, p) => setE((x) => ({ ...x, impacto: i, probabilidad: p }))} />
      </Box>
      <Alert severity="info" sx={{ my: 2 }}>{quien}</Alert>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" } }}>
        <TextField select size="small" label="Clasificación" value={e.clasificacion} onChange={(x) => set("clasificacion", x.target.value)}>
          {Object.entries(op.textos.clasificacion).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Esfuerzo" value={e.esfuerzo} onChange={(x) => set("esfuerzo", x.target.value)}>
          <MenuItem value="">—</MenuItem>
          {Object.entries(op.textos.esfuerzo).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Prioridad TI" value={e.prioridad_ti} onChange={(x) => set("prioridad_ti", x.target.value)}>
          <MenuItem value="ALTA">Alta</MenuItem><MenuItem value="MEDIA">Media</MenuItem><MenuItem value="BAJA">Baja</MenuItem>
        </TextField>
      </Box>
      <TextField fullWidth multiline minRows={2} label="Evaluación (análisis de TI)" value={e.evaluacion} onChange={(x) => set("evaluacion", x.target.value)} sx={{ mt: 2 }} />
      <Box sx={{ display: "grid", gap: 2, mt: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
        <TextField multiline minRows={4} label="Plan de implementación" value={e.plan_implementacion} onChange={(x) => set("plan_implementacion", x.target.value)}
          placeholder={"1. Respaldo completo\n2. Instalar…\n3. Probar…"} />
        <TextField multiline minRows={4} label="Plan de reversión" value={e.plan_reversion} onChange={(x) => set("plan_reversion", x.target.value)}
          placeholder="Si falla: cómo volver atrás, en cuánto tiempo y quién" helperText={e.tipo_cambio === "ESTANDAR" ? "Opcional en cambios estándar" : "Obligatorio"} />
      </Box>
      <Box sx={{ display: "grid", gap: 2, mt: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" } }}>
        <TextField select size="small" label="Responsable de implementar" value={e.responsable_id} onChange={(x) => set("responsable_id", x.target.value)}>
          <MenuItem value="">Quien evalúa</MenuItem>
          {op.responsables.map((u) => <MenuItem key={u.id} value={u.id}>{u.nombre}</MenuItem>)}
        </TextField>
        <TextField size="small" type="datetime-local" label="Ventana: inicio" value={e.ventana_inicio} onChange={(x) => set("ventana_inicio", x.target.value)}
          slotProps={{ inputLabel: { shrink: true } }} />
        <TextField size="small" type="datetime-local" label="Ventana: fin" value={e.ventana_fin} onChange={(x) => set("ventana_fin", x.target.value)}
          slotProps={{ inputLabel: { shrink: true } }} />
      </Box>
      <TextField fullWidth size="small" label="Comentario (obligatorio si rechaza o deja en espera)" value={e.comentario}
        onChange={(x) => set("comentario", x.target.value)} sx={{ mt: 2 }} />
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      <Stack direction="row" justifyContent="flex-end" sx={{ gap: 1, mt: 2, flexWrap: "wrap" }}>
        <Button color="error" onClick={() => { setError(null); enviar.mutate("RECHAZAR"); }} disabled={enviar.isPending}>Rechazar</Button>
        <Button onClick={() => { setError(null); enviar.mutate("EN_ESPERA"); }} disabled={enviar.isPending}>Dejar en espera</Button>
        <Button variant="contained" onClick={() => { setError(null); enviar.mutate("APROBAR"); }} disabled={enviar.isPending}>
          Aprobar evaluación
        </Button>
      </Stack>
    </Paper>
  );
}

function EvaluacionLectura({ c }: { c: Cambio }) {
  if (!c.fecha_evaluacion) return <Vacio texto="TI todavía no evalúa esta solicitud." />;
  return (
    <Box>
      <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "1fr 1.4fr" }, mb: 1 }}>
        <Box>
          <Fila k="Tipo de cambio">{TIPO_CAMBIO[c.tipo_cambio ?? ""] ?? "—"}</Fila>
          <Fila k="Riesgo"><RiesgoChip riesgo={c.riesgo} /></Fila>
          <Fila k="Clasificación">{c.textos.clasificacion ?? "—"}</Fila>
          <Fila k="Esfuerzo">{c.textos.esfuerzo ?? "—"}</Fila>
          <Fila k="Evaluó">{c.evaluado_por?.nombre ?? "—"} · {fechaHora(c.fecha_evaluacion)}</Fila>
        </Box>
        {c.impacto && c.probabilidad && <Matriz impacto={c.impacto} probabilidad={c.probabilidad} />}
      </Box>
      {c.evaluacion && <Fila k="Evaluación">{c.evaluacion}</Fila>}
      {c.motivo && <Fila k="Motivo">{c.motivo}</Fila>}
    </Box>
  );
}

// ------------------------------------------------------------------ aprobaciones
function Aprobaciones({ c, onListo }: { c: Cambio; onListo: () => void }) {
  const avisar = useAviso();
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState<string | null>(null);
  const responder = useMutation({
    mutationFn: (aprobar: boolean) => post<Cambio>(`/cambios/${c.id}/responder`, { aprobar, comentario: comentario || null }),
    onSuccess: (r, aprobar) => { avisar(aprobar ? `${r.numero} aprobado` : `${r.numero} rechazado`); setComentario(""); onListo(); },
    onError: (e) => setError(mensajeError(e)),
  });
  const filas: { p: Persona | null; rol: string; texto: string; estado: string }[] = [
    { p: c.solicitante, rol: "Solicitante", texto: `Enviado ${fechaHora(c.fecha_creacion)}`, estado: "APROBADO" },
    ...c.aprobaciones.map((a) => ({
      p: a.aprobador, rol: a.rol === "JEFE_TI" ? "Jefe de TI" : "Gerencia",
      texto: a.estado === "PENDIENTE" ? `Esperando ${tiempoRelativo(a.fecha_solicitud)}${a.recordado ? " · recordatorio enviado" : ""}`
        : `${a.estado === "APROBADO" ? "Aprobado" : "Rechazado"} ${fechaHora(a.fecha_respuesta)}${a.comentario ? ` · «${a.comentario}»` : ""}`,
      estado: a.estado,
    })),
  ];
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>Aprobaciones</Typography>
      {filas.map((f, i) => (
        <Stack key={i} direction="row" alignItems="center" sx={{ gap: 1.5, py: 1.25, borderTop: "1px solid", borderColor: "divider" }}>
          <Avatar sx={{ bgcolor: f.estado === "PENDIENTE" ? "#B7791F" : "#2E7D32", width: 36, height: 36, fontSize: 14 }}>{iniciales(f.p?.nombre)}</Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="body2"><b>{f.p?.nombre ?? "Sin asignar"}</b> <Box component="span" sx={{ color: "text.secondary" }}>· {f.rol}</Box></Typography>
            <Typography variant="caption" color="text.secondary">{f.texto}</Typography>
          </Box>
          {f.estado === "APROBADO" && <CheckCircleIcon color="success" />}
          {f.estado === "RECHAZADO" && <CancelIcon color="error" />}
          {f.estado === "PENDIENTE" && <Chip size="small" label="Pendiente" sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", fontWeight: 600 }} />}
        </Stack>
      ))}
      <Alert severity="info" sx={{ mt: 1.5 }}>
        {c.riesgo ? `Riesgo ${c.riesgo.toLowerCase()}${c.riesgo === "BAJO" ? ": lo aprueba solo el Jefe de TI." : ": lo aprueba Gerencia."} ` : ""}
        Los cambios de riesgo bajo los aprueba solo el Jefe de TI; los <b>estándar</b> (ya probados) no necesitan aprobación.
      </Alert>
      {c.acciones.includes("aprobar") && (
        <>
          <TextField fullWidth size="small" multiline minRows={2} label="Comentario (obligatorio si rechaza)" value={comentario}
            onChange={(e) => setComentario(e.target.value)} sx={{ mt: 2 }} />
          {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
          <Stack direction="row" sx={{ gap: 1.5, mt: 1.5 }}>
            <Button fullWidth variant="contained" color="success" startIcon={<CheckCircleIcon />} disabled={responder.isPending}
              onClick={() => { setError(null); responder.mutate(true); }}>Aprobar</Button>
            <Button fullWidth variant="outlined" color="error" startIcon={<CancelIcon />} disabled={responder.isPending}
              onClick={() => { setError(null); responder.mutate(false); }}>Rechazar</Button>
          </Stack>
        </>
      )}
    </Paper>
  );
}

// ------------------------------------------------------------------ ventana, implementar, revisión
function DialogoVentana({ c, onCerrar }: { c: Cambio; onCerrar: (ok: boolean) => void }) {
  const [v, setV] = useState({ ini: aLocal(c.ventana_inicio), fin: aLocal(c.ventana_fin), comentario: "" });
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => post(`/cambios/${c.id}/ventana`, { ventana_inicio: deLocal(v.ini), ventana_fin: deLocal(v.fin), comentario: v.comentario || null }),
    onSuccess: () => onCerrar(true),
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={() => onCerrar(false)} maxWidth="xs" fullWidth>
      <DialogTitle>Cambiar la ventana</DialogTitle>
      <DialogContent dividers>
        <Stack sx={{ gap: 2 }}>
          <TextField type="datetime-local" label="Inicio" value={v.ini} onChange={(e) => setV({ ...v, ini: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField type="datetime-local" label="Fin" value={v.fin} onChange={(e) => setV({ ...v, fin: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Motivo (opcional)" value={v.comentario} onChange={(e) => setV({ ...v, comentario: e.target.value })} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={() => onCerrar(false)}>Cancelar</Button><Button variant="contained" onClick={() => m.mutate()} disabled={m.isPending}>Guardar</Button></DialogActions>
    </Dialog>
  );
}

function DialogoImplementar({ c, onCerrar }: { c: Cambio; onCerrar: (ok: boolean) => void }) {
  const [v, setV] = useState({ version_ref: "", comentario: "" });
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => post(`/cambios/${c.id}/implementar`, { version_ref: v.version_ref || null, comentario: v.comentario || null }),
    onSuccess: () => onCerrar(true),
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={() => onCerrar(false)} maxWidth="sm" fullWidth>
      <DialogTitle>Marcar como implementado</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Queda «En revisión» hasta que TI registre la revisión posterior.</Typography>
        <Stack sx={{ gap: 2 }}>
          <TextField label="Versión o referencia (opcional)" value={v.version_ref} onChange={(e) => setV({ ...v, version_ref: e.target.value })} />
          <TextField label="Notas de la implementación" multiline minRows={2} value={v.comentario} onChange={(e) => setV({ ...v, comentario: e.target.value })} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={() => onCerrar(false)}>Cancelar</Button><Button variant="contained" onClick={() => m.mutate()} disabled={m.isPending}>Implementado</Button></DialogActions>
    </Dialog>
  );
}

function DialogoRevision({ c, onCerrar }: { c: Cambio; onCerrar: (ok: boolean) => void }) {
  const [v, setV] = useState({ resultado: "EXITOSO", probado: true, informado: true, observaciones: "" });
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => post(`/cambios/${c.id}/revision`, { resultado: v.resultado, probado_solicitante: v.probado, informado: v.informado, observaciones: v.observaciones || null }),
    onSuccess: () => onCerrar(true),
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={() => onCerrar(false)} maxWidth="sm" fullWidth>
      <DialogTitle>Revisión posterior</DialogTitle>
      <DialogContent dividers>
        <RadioGroup value={v.resultado} onChange={(e) => setV({ ...v, resultado: e.target.value })}>
          <FormControlLabel value="EXITOSO" control={<Radio />} label="Exitoso" />
          <FormControlLabel value="CON_PROBLEMAS" control={<Radio />} label="Con problemas (se corrigieron sin revertir)" />
          <FormControlLabel value="REVERTIDO" control={<Radio />} label="Revertido (se aplicó el plan de reversión)" />
        </RadioGroup>
        <FormControlLabel control={<Checkbox checked={v.probado} onChange={(e) => setV({ ...v, probado: e.target.checked })} />} label="El solicitante lo probó" />
        <FormControlLabel control={<Checkbox checked={v.informado} onChange={(e) => setV({ ...v, informado: e.target.checked })} />} label="Se informó a los usuarios" />
        <TextField fullWidth multiline minRows={2} label="Observaciones" value={v.observaciones} onChange={(e) => setV({ ...v, observaciones: e.target.value })} sx={{ mt: 1 }} />
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions><Button onClick={() => onCerrar(false)}>Cancelar</Button><Button variant="contained" onClick={() => m.mutate()} disabled={m.isPending}>Registrar</Button></DialogActions>
    </Dialog>
  );
}

function Ventana({ c, onListo }: { c: Cambio; onListo: () => void }) {
  const [dlg, setDlg] = useState<"ventana" | "implementar" | "revision" | null>(null);
  const cerrar = (ok: boolean) => { setDlg(null); if (ok) onListo(); };
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 1 }}>
        <EventIcon color="primary" />
        <Typography variant="h6">Ventana de cambio</Typography>
      </Stack>
      <Typography variant="body2">{ventanaLarga(c.ventana_inicio, c.ventana_fin)}</Typography>
      {c.ventana_inicio && (
        <Typography variant="body2" color={c.choques.length || c.congelado.length ? "warning.main" : "text.secondary"} sx={{ mt: 0.5 }}>
          {c.congelado.length ? `Cae en periodo congelado: ${c.congelado.join(", ")}. ` : ""}
          {c.choques.length ? `Choca con ${c.choques.map((x) => x.numero).join(", ")}.` : "Sin choque con otros cambios."}
        </Typography>
      )}
      {c.responsable && <Typography variant="body2" sx={{ mt: 1 }}><b>Responsable:</b> {c.responsable.nombre}</Typography>}
      {c.ticket_relacionado && <Typography variant="body2" sx={{ mt: 1 }}><b>Tickets relacionados:</b> {c.ticket_relacionado}</Typography>}
      {(c.acciones.includes("reprogramar") || c.acciones.includes("implementar") || c.acciones.includes("revisar")) && <Divider sx={{ my: 1.5 }} />}
      <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
        {c.acciones.includes("reprogramar") && <Button size="small" onClick={() => setDlg("ventana")}>Cambiar ventana</Button>}
        {c.acciones.includes("implementar") && <Button size="small" variant="contained" onClick={() => setDlg("implementar")}>Marcar implementado</Button>}
        {c.acciones.includes("revisar") && <Button size="small" variant="contained" onClick={() => setDlg("revision")}>Revisión posterior</Button>}
      </Stack>
      {dlg === "ventana" && <DialogoVentana c={c} onCerrar={cerrar} />}
      {dlg === "implementar" && <DialogoImplementar c={c} onCerrar={cerrar} />}
      {dlg === "revision" && <DialogoRevision c={c} onCerrar={cerrar} />}
    </Paper>
  );
}

// ------------------------------------------------------------------ página
export default function CambioDetalle() {
  const { id } = useParams();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [tab, setTab] = useState(0);
  const archivo = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ["cambios", id], queryFn: () => get<Cambio>(`/cambios/${id}`) });
  const op = useQuery({ queryKey: ["cambios", "opciones"], queryFn: () => get<OpcionesCambio>("/cambios/opciones") });
  const refrescar = () => qc.invalidateQueries({ queryKey: ["cambios"] });
  const subir = useMutation({
    mutationFn: (f: File) => { const form = new FormData(); form.append("archivo", f); return api<Cambio>("POST", `/cambios/${id}/adjuntos`, { form }); },
    onSuccess: () => { avisar("Archivo adjuntado"); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error || !q.data) return <ErrorCarga error={q.error} />;
  const c = q.data;
  const p = c.prioridad_sugerida ? PRIORIDAD[c.prioridad_sugerida] : null;

  return (
    <Box>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/cambios" underline="hover" color="inherit">Cambios</Link>
        <Typography color="text.primary" variant="body2">{c.numero}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} sx={{ gap: 1.5, mb: 2.5 }}>
        <Typography variant="h5">{c.numero} · {c.titulo}</Typography>
        <EstadoCambio estado={c.estado} nombre={c.estado_nombre} />
        {c.acciones.includes("editar") && <Button size="small" startIcon={<EditIcon />} component={RouterLink} to={`/cambios/${c.id}/editar`}>Corregir</Button>}
      </Stack>
      {c.estado === "RECHAZADO" && <Alert severity="error" sx={{ mb: 2 }}>Rechazado{c.motivo ? `: ${c.motivo}` : ""}</Alert>}
      {c.estado === "EN_ESPERA" && <Alert severity="warning" sx={{ mb: 2 }}>En espera{c.motivo ? `: ${c.motivo}` : ""}</Alert>}
      <Pasos c={c} />

      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "1.75fr 1fr" }, alignItems: "start" }}>
        <Box sx={{ minWidth: 0 }}>
          <Paper variant="outlined">
            <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ borderBottom: "1px solid", borderColor: "divider", px: 1 }}>
              <Tab label="Solicitud (secciones 1-6)" />
              <Tab label="Evaluación TI (sección 7)" />
              <Tab label="Plan y reversión" />
              <Tab label={`Historial (${c.historial.length})`} />
            </Tabs>
            <Box sx={{ p: { xs: 2, sm: 3 } }}>
              {tab === 0 && (
                <>
                  <Fila k="Formato">{c.formato === "MESA" ? "TI-FOR-001 · Mesa de Servicios" : "TI-FOR-002 · General"}</Fila>
                  <Fila k="Solicita">{[c.solicitante.nombre, c.solicitante.cargo, c.solicitante.area].filter(Boolean).join(" · ")}{c.telefono ? ` · ext. ${c.telefono}` : ""}</Fila>
                  <Fila k="Tipo de solicitud"><Chip size="small" variant="outlined" color="primary" label={c.textos.tipo_solicitud ?? c.tipo_solicitud} /></Fila>
                  <Fila k="Parte afectada">{[c.aplicacion, ...(c.partes ?? [])].filter(Boolean).join(" · ") || "—"}{c.pantalla ? ` · ${c.pantalla}` : ""}</Fila>
                  {c.desde_donde && <Fila k="Desde dónde">{c.textos.desde_donde}</Fila>}
                  <Fila k="Cómo funciona hoy">{c.situacion_actual}</Fila>
                  <Fila k="Cómo debería funcionar">{c.situacion_deseada}</Fila>
                  {c.justificacion && <Fila k="Justificación">{c.justificacion}</Fila>}
                  <Fila k="Beneficiados">{c.textos.beneficiados ?? "—"}</Fila>
                  <Fila k="Prioridad sugerida">{p ? <Chip size="small" color={p.c} label={p.t} /> : "—"}</Fila>
                  <Fila k="Adjuntos">
                    <Stack direction="row" alignItems="center" sx={{ gap: 1, flexWrap: "wrap" }}>
                      {c.adjuntos.map((a) => (
                        <Chip key={a.id} variant="outlined" icon={<InsertDriveFileIcon />} label={a.nombre} clickable
                          onClick={() => descargar(`/cambios/${c.id}/adjuntos/${a.id}`, undefined, a.nombre)} />
                      ))}
                      {c.acciones.includes("adjuntar") && (
                        <>
                          <Button size="small" startIcon={<AttachFileIcon />} onClick={() => archivo.current?.click()} disabled={subir.isPending}>Adjuntar</Button>
                          <input ref={archivo} type="file" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) subir.mutate(f); e.target.value = ""; }} />
                        </>
                      )}
                      {!c.adjuntos.length && !c.acciones.includes("adjuntar") && "—"}
                    </Stack>
                  </Fila>
                </>
              )}
              {tab === 1 && <EvaluacionLectura c={c} />}
              {tab === 2 && (
                c.plan_implementacion || c.plan_reversion ? (
                  <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
                    <Paper variant="outlined" sx={{ p: 2 }}>
                      <Typography variant="caption" color="text.secondary">Plan de implementación</Typography>
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}>{c.plan_implementacion || "—"}</Typography>
                    </Paper>
                    <Paper variant="outlined" sx={{ p: 2 }}>
                      <Typography variant="caption" color="text.secondary">Plan de reversión</Typography>
                      <Stack direction="row" sx={{ gap: 1, mt: 0.5 }}>
                        <UndoIcon color="error" fontSize="small" />
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{c.plan_reversion || "—"}</Typography>
                      </Stack>
                    </Paper>
                  </Box>
                ) : <Vacio texto="Los planes se registran en la evaluación de TI." />
              )}
              {tab === 3 && c.historial.slice().reverse().map((h) => (
                <Box key={h.id} sx={{ py: 1, borderTop: "1px solid", borderColor: "divider" }}>
                  <Typography variant="body2"><b>{h.accion}</b>{h.detalle ? ` · ${h.detalle}` : ""}</Typography>
                  <Typography variant="caption" color="text.secondary">{h.usuario ?? "Sistema"} · {fechaHora(h.fecha)}</Typography>
                </Box>
              ))}
            </Box>
          </Paper>
          {c.acciones.includes("evaluar") && op.data && <Evaluacion c={c} op={op.data} onListo={refrescar} />}
          {!c.acciones.includes("evaluar") && c.fecha_evaluacion && tab !== 1 && (
            <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 }, mt: 2.5 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>Evaluación TI</Typography>
              <EvaluacionLectura c={c} />
            </Paper>
          )}
        </Box>
        <Stack sx={{ gap: 2.5 }}>
          <Aprobaciones c={c} onListo={refrescar} />
          <Ventana c={c} onListo={refrescar} />
        </Stack>
      </Box>
    </Box>
  );
}
