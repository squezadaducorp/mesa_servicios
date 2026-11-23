import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, LinearProgress, Paper,
  Switch, TextField, Tooltip, Typography,
} from "@mui/material";
import TimerIcon from "@mui/icons-material/TimerOutlined";
import PauseIcon from "@mui/icons-material/Pause";
import PlayIcon from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/EditOutlined";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { Stack } from "../../components/Pila";
import { del, post, put, get } from "../../api/client";
import type { RegistroTiempo, TiempoObjeto } from "../../api/ronda4c";
import { mensajeError, useAviso } from "../../components/Aviso";
import { duracionCorta } from "../ronda4b/comun";

export const reloj = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

/** Segundos de un registro que avanza en pantalla mientras corre (sin pedir al servidor cada segundo). */
export function useSegundos(r: RegistroTiempo | null | undefined): number {
  // Momento en que llegaron los segundos del servidor: se reinicia con cada respuesta nueva
  const [base, setBase] = useState(() => Date.now());
  const [ahora, setAhora] = useState(Date.now());
  useEffect(() => {
    const t = Date.now();
    setBase(t);
    setAhora(t);
  }, [r?.segundos, r?.id, r?.estado]);
  useEffect(() => {
    if (r?.estado !== "CORRIENDO") return;
    const id = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(id);
  }, [r?.estado, r?.id]);
  if (!r) return 0;
  return r.estado === "CORRIENDO" ? r.segundos + Math.max(0, Math.floor((ahora - base) / 1000)) : r.segundos;
}

const iniciales = (n: string) => n.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase();

function DialogoRegistro({ inicial, onGuardar, onCerrar }: {
  inicial?: RegistroTiempo; onGuardar: (actividad: string, minutos: number) => void; onCerrar: () => void;
}) {
  const [actividad, setActividad] = useState(inicial?.actividad ?? "");
  const [horas, setHoras] = useState(inicial ? String(Math.floor(inicial.minutos / 60)) : "0");
  const [mins, setMins] = useState(inicial ? String(inicial.minutos % 60) : "30");
  const total = (Number(horas) || 0) * 60 + (Number(mins) || 0);
  return (
    <Dialog open onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle>{inicial ? "Corregir tiempo" : "Agregar tiempo a mano"}</DialogTitle>
      <DialogContent>
        <TextField autoFocus fullWidth label="Actividad" sx={{ mt: 1 }} value={actividad} onChange={(e) => setActividad(e.target.value)}
          placeholder="Revisión del firewall" slotProps={{ htmlInput: { maxLength: 200 } }} />
        <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
          <TextField label="Horas" type="number" value={horas} onChange={(e) => setHoras(e.target.value)} slotProps={{ htmlInput: { min: 0, max: 24 } }} />
          <TextField label="Minutos" type="number" value={mins} onChange={(e) => setMins(e.target.value)} slotProps={{ htmlInput: { min: 0, max: 59 } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" disabled={actividad.trim().length < 2 || total < 1 || total > 1440} onClick={() => onGuardar(actividad.trim(), total)}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** Tiempo trabajado (mejora 31): cronómetro, registros del equipo, estimado y facturable. Para tickets, problemas y cambios. */
export default function TiempoTrabajado({ tipo, id }: { tipo: "ticket" | "problema" | "cambio"; id: number }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const clave = ["tiempo", tipo, id];
  const q = useQuery({ queryKey: clave, queryFn: () => get<TiempoObjeto>(`/tiempo/${tipo}/${id}`), refetchInterval: 60_000 });
  const [actividad, setActividad] = useState("");
  const [dialogo, setDialogo] = useState<RegistroTiempo | "nuevo" | null>(null);
  const [estimando, setEstimando] = useState<string | null>(null);
  const d = q.data;
  const activo = d?.activo ?? null;
  const seg = useSegundos(activo);
  const refrescar = (nuevo?: TiempoObjeto) => {
    if (nuevo) qc.setQueryData(clave, nuevo);
    else qc.invalidateQueries({ queryKey: clave });
    qc.invalidateQueries({ queryKey: ["tiempo", "activo"] });
  };
  const err = (e: unknown) => avisar(mensajeError(e), "error");
  const iniciar = useMutation({
    mutationFn: () => post<TiempoObjeto>(`/tiempo/${tipo}/${id}/iniciar`, { actividad }),
    onSuccess: (n) => { refrescar(n); setActividad(""); }, onError: err,
  });
  const accion = useMutation({
    mutationFn: ({ r, a }: { r: number; a: "pausar" | "reanudar" | "detener" }) => post(`/tiempo/registros/${r}/${a}`),
    onSuccess: (_, v) => { refrescar(); if (v.a === "detener") avisar("Tiempo guardado"); }, onError: err,
  });
  const manual = useMutation({
    mutationFn: (x: { actividad: string; minutos: number }) => post<TiempoObjeto>(`/tiempo/${tipo}/${id}/manual`, x),
    onSuccess: (n) => { refrescar(n); setDialogo(null); avisar("Tiempo agregado"); }, onError: err,
  });
  const editar = useMutation({
    mutationFn: (x: { id: number; actividad: string; minutos: number }) => put(`/tiempo/registros/${x.id}`, { actividad: x.actividad, minutos: x.minutos }),
    onSuccess: () => { refrescar(); setDialogo(null); }, onError: err,
  });
  const borrar = useMutation({ mutationFn: (r: number) => del(`/tiempo/registros/${r}`), onSuccess: () => refrescar(), onError: err });
  const ajustes = useMutation({
    mutationFn: (x: { estimado_min?: number | null; facturable?: boolean }) => put<TiempoObjeto>(`/tiempo/ticket/${id}/ajustes`, x),
    onSuccess: (n) => { refrescar(n); setEstimando(null); }, onError: err,
  });
  if (!d) return null;

  const totalSeg = d.registros.reduce((s, r) => s + (r.id === activo?.id ? seg : r.segundos), 0);
  const totalMin = Math.round(totalSeg / 60);
  const pctEst = d.estimado_min ? Math.round((100 * totalMin) / d.estimado_min) : null;
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <TimerIcon color="primary" />
        <Typography variant="h6" sx={{ flex: 1 }}>Tiempo trabajado</Typography>
      </Stack>

      <Box sx={{ bgcolor: "#F2F5FA", borderRadius: 3, p: 2, textAlign: "center" }}>
        {activo ? (
          <>
            <Typography sx={{ fontSize: 38, fontWeight: 800, letterSpacing: 1, color: "#10203C", fontVariantNumeric: "tabular-nums" }}>{reloj(seg)}</Typography>
            <Typography variant="body2" color="text.secondary">
              {activo.estado === "CORRIENDO" ? `corriendo desde las ${activo.desde_texto}` : "en pausa"} · {activo.actividad}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ justifyContent: "center", mt: 1.5 }}>
              {activo.estado === "CORRIENDO" ? (
                <Button variant="outlined" startIcon={<PauseIcon />} onClick={() => accion.mutate({ r: activo.id, a: "pausar" })}>Pausar</Button>
              ) : (
                <Button variant="outlined" startIcon={<PlayIcon />} disabled={!d.en_atencion} onClick={() => accion.mutate({ r: activo.id, a: "reanudar" })}>Reanudar</Button>
              )}
              <Button variant="contained" color="error" startIcon={<StopIcon />} onClick={() => accion.mutate({ r: activo.id, a: "detener" })}>Detener y guardar</Button>
            </Stack>
          </>
        ) : (
          <Stack spacing={1.2}>
            <TextField size="small" placeholder="¿Qué va a hacer? (p. ej. Diagnóstico en sitio)" value={actividad} onChange={(e) => setActividad(e.target.value)}
              disabled={!d.en_atencion} slotProps={{ htmlInput: { maxLength: 200 } }} sx={{ bgcolor: "#fff" }} />
            <Button variant="contained" startIcon={<PlayIcon />} disabled={!d.en_atencion || iniciar.isPending} onClick={() => iniciar.mutate()}>
              Iniciar cronómetro
            </Button>
            {!d.en_atencion && <Typography variant="caption" color="text.secondary">El ticket no está en atención: el cronómetro se usa con el ticket en proceso.</Typography>}
          </Stack>
        )}
      </Box>

      <Stack direction="row" sx={{ alignItems: "baseline", mt: 2 }}>
        <Typography variant="body2" sx={{ flex: 1 }}>
          Total <b>{duracionCorta(totalMin)}</b>
          {tipo === "ticket" && (estimando !== null ? null : d.estimado_min
            ? <> de <b>{duracionCorta(d.estimado_min)}</b> estimadas</>
            : <> · <Button size="small" sx={{ p: 0, minWidth: 0 }} onClick={() => setEstimando("")}>poner estimado</Button></>)}
        </Typography>
        {pctEst !== null && <Typography variant="body2" sx={{ fontWeight: 700, color: pctEst > 100 ? "error.main" : "#B57400" }}>{pctEst} %</Typography>}
        {tipo === "ticket" && d.estimado_min && estimando === null && (
          <IconButton size="small" aria-label="Cambiar estimado" onClick={() => setEstimando(String(d.estimado_min! / 60))}><EditIcon fontSize="small" /></IconButton>
        )}
      </Stack>
      {estimando !== null && (
        <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: "center" }}>
          <TextField size="small" type="number" label="Horas estimadas" value={estimando} onChange={(e) => setEstimando(e.target.value)} sx={{ width: 150 }}
            slotProps={{ htmlInput: { min: 0, step: 0.5 } }} />
          <Button size="small" variant="contained" onClick={() => ajustes.mutate({ estimado_min: Math.round((Number(estimando) || 0) * 60) })}>Guardar</Button>
          <Button size="small" onClick={() => setEstimando(null)}>Cancelar</Button>
        </Stack>
      )}
      {pctEst !== null && (
        <LinearProgress variant="determinate" value={Math.min(pctEst, 100)} sx={{ mt: 0.8, height: 8, borderRadius: 4, bgcolor: "#C9DDF0",
          "& .MuiLinearProgress-bar": { bgcolor: pctEst > 100 ? "error.main" : "#F9A825" } }} />
      )}

      <Box sx={{ mt: 1.5 }}>
        {d.registros.length === 0 && <Typography variant="body2" color="text.secondary">Todavía no hay tiempo registrado.</Typography>}
        {d.registros.map((r) => (
          <Stack key={r.id} direction="row" spacing={1.2} sx={{ alignItems: "center", py: 1, borderBottom: "1px solid #EEF1F5" }}>
            <Tooltip title={r.usuario.nombre}><Avatar sx={{ width: 30, height: 30, fontSize: 12, bgcolor: r.propio ? "primary.main" : "#6A4BC4" }}>{iniciales(r.usuario.nombre)}</Avatar></Tooltip>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ wordBreak: "break-word" }}>{r.actividad}</Typography>
              {r.estado !== "GUARDADO" && (
                <Chip size="small" label={r.estado === "CORRIENDO" ? "en curso" : "en pausa"} sx={{ height: 18, fontSize: 11, fontWeight: 700,
                  bgcolor: r.estado === "CORRIENDO" ? "#2E7D32" : "#E0E5EC", color: r.estado === "CORRIENDO" ? "#fff" : "#3E4A5C" }} />
              )}
              {r.manual && <Typography variant="caption" color="text.secondary"> a mano</Typography>}
            </Box>
            <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{duracionCorta(Math.round((r.id === activo?.id ? seg : r.segundos) / 60))}</Typography>
            {r.editable && r.estado === "GUARDADO" && (
              <>
                <IconButton size="small" aria-label="Corregir" onClick={() => setDialogo(r)}><EditIcon fontSize="small" /></IconButton>
                <IconButton size="small" aria-label="Borrar" onClick={() => window.confirm("¿Borrar este registro de tiempo?") && borrar.mutate(r.id)}><DeleteIcon fontSize="small" /></IconButton>
              </>
            )}
          </Stack>
        ))}
        <Button startIcon={<AddIcon />} sx={{ mt: 1 }} onClick={() => setDialogo("nuevo")}>Agregar tiempo a mano</Button>
      </Box>

      {tipo === "ticket" && (
        <>
          <FormControlLabel sx={{ mt: 1, display: "flex", justifyContent: "space-between", ml: 0 }} labelPlacement="start"
            control={<Switch checked={d.facturable} onChange={(e) => ajustes.mutate({ facturable: e.target.checked })} />} label="Facturable al cliente" />
          <Alert severity="info" icon={false} sx={{ mt: 0.5, py: 0, bgcolor: "transparent", px: 0, color: "text.secondary", fontSize: 13 }}>
            El cronómetro se pausa solo al pasar el ticket a «Pendiente cliente», al resolverlo o al cerrar sesión.
          </Alert>
        </>
      )}
      {dialogo && (
        <DialogoRegistro
          inicial={dialogo === "nuevo" ? undefined : dialogo}
          onCerrar={() => setDialogo(null)}
          onGuardar={(a, m) => (dialogo === "nuevo" ? manual.mutate({ actividad: a, minutos: m }) : editar.mutate({ id: dialogo.id, actividad: a, minutos: m }))}
        />
      )}
    </Paper>
  );
}
