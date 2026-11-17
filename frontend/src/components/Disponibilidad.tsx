import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel,
  IconButton, MenuItem, Radio, RadioGroup, Stack, TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import AlarmIcon from "@mui/icons-material/AlarmOutlined";
import BeachAccessIcon from "@mui/icons-material/BeachAccessOutlined";
import { get, post } from "../api/client";
import type { AlertaSla, Ausencia, MotivoAusencia, ReemplazoSugerido, TicketCorto } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { fechaHora } from "../utils/formato";
import { mensajeError, useAviso } from "./Aviso";
import { textoMinutos } from "./Chips";

export const MOTIVOS: Record<MotivoAusencia, string> = {
  VACACIONES: "Vacaciones",
  PERMISO: "Permiso",
  ENFERMEDAD: "Enfermedad / calamidad",
  CAPACITACION: "Capacitación",
  OTRO: "Otro",
};

const ZONA = "America/Guayaquil";

/** «2026-11-23T08:30» en hora de Ecuador, para un campo datetime-local. */
function localEcuador(d: Date) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(d)
      .map((x) => [x.type, x.value]),
  );
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** Diálogo «Mi disponibilidad»: registrar una ausencia con reemplazo y ver/cancelar las vigentes. */
export function DialogoAusencia({ abierto, onCerrar, usuario }: { abierto: boolean; onCerrar: () => void; usuario?: { id: number; nombre: string } }) {
  const { usuario: yo } = useAuth();
  const avisar = useAviso();
  const qc = useQueryClient();
  const propio = !usuario || usuario.id === yo?.id;
  const usuarioId = propio ? undefined : usuario?.id;

  const [motivo, setMotivo] = useState<MotivoAusencia>("VACACIONES");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [reemplazo, setReemplazo] = useState<number | "">("");
  const [pasarAbiertos, setPasarAbiertos] = useState(true);
  const [devolver, setDevolver] = useState(true);
  const [avisarSolicitantes, setAvisarSolicitantes] = useState(true);
  const [verTickets, setVerTickets] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    const manana = new Date(Date.now() + 86_400_000);
    setDesde(localEcuador(new Date()));
    setHasta(`${localEcuador(manana).slice(0, 10)}T08:30`);
    setReemplazo("");
    setMotivo("VACACIONES");
    setPasarAbiertos(true);
    setDevolver(true);
    setAvisarSolicitantes(true);
  }, [abierto]);

  const fechasOk = !!desde && !!hasta && hasta > desde;
  const reemplazos = useQuery({
    queryKey: ["ausencias", "reemplazos", usuarioId, desde, hasta],
    queryFn: () => get<ReemplazoSugerido[]>("/ausencias/reemplazos", { usuario_id: usuarioId, desde: desde || undefined, hasta: hasta || undefined }),
    enabled: abierto && fechasOk,
  });
  useEffect(() => {
    const s = reemplazos.data?.find((r) => r.sugerido);
    if (s && reemplazo === "") setReemplazo(s.id);
  }, [reemplazos.data, reemplazo]);

  const tickets = useQuery({
    queryKey: ["ausencias", "tickets", usuarioId],
    queryFn: () => get<TicketCorto[]>("/ausencias/tickets", { usuario_id: usuarioId }),
    enabled: abierto,
  });
  const vigentes = useQuery({
    queryKey: ["ausencias", propio ? "mias" : "equipo"],
    queryFn: () => get<Ausencia[]>(propio ? "/ausencias/mias" : "/ausencias"),
    enabled: abierto,
  });
  const lista = (vigentes.data ?? []).filter((a) => a.usuario.id === (usuario?.id ?? yo?.id));

  const crear = useMutation({
    mutationFn: () =>
      post<Ausencia>("/ausencias", {
        usuario_id: usuarioId, reemplazo_id: reemplazo, motivo, desde, hasta,
        pasar_abiertos: pasarAbiertos, devolver, avisar_solicitantes: avisarSolicitantes,
      }),
    onSuccess: (a) => {
      avisar(a.estado === "ACTIVA" ? `Ausencia registrada. Los tickets pasaron a ${a.reemplazo.nombre}.` : "Ausencia programada", "success");
      qc.invalidateQueries({ queryKey: ["ausencias"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      onCerrar();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const cancelar = useMutation({
    mutationFn: (id: number) => post<Ausencia>(`/ausencias/${id}/cancelar`),
    onSuccess: (a) => {
      avisar(a.estado === "FINALIZADA" ? "Bienvenido de vuelta: sus tickets regresaron" : "Ausencia cancelada", "success");
      qc.invalidateQueries({ queryKey: ["ausencias"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const elegido = reemplazos.data?.find((r) => r.id === reemplazo);
  const n = tickets.data?.length ?? 0;

  return (
    <Dialog open={abierto} onClose={onCerrar} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <BeachAccessIcon color="primary" />
        <Box sx={{ flex: 1 }}>{propio ? "Mi disponibilidad" : `Ausencia de ${usuario?.nombre}`}</Box>
        <IconButton onClick={onCerrar} aria-label="Cerrar">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {lista.length > 0 && (
          <Stack spacing={1} sx={{ mb: 2 }}>
            {lista.map((a) => (
              <Alert
                key={a.id}
                severity={a.estado === "ACTIVA" ? "warning" : "info"}
                action={
                  <Button color="inherit" size="small" disabled={cancelar.isPending} onClick={() => cancelar.mutate(a.id)}>
                    {a.estado === "ACTIVA" ? "Volví antes" : "Cancelar"}
                  </Button>
                }
              >
                <b>{MOTIVOS[a.motivo] ?? a.motivo}</b> del {fechaHora(a.desde)} al {fechaHora(a.hasta)} · cubre {a.reemplazo.nombre}
                {a.estado === "PROGRAMADA" ? " (programada)" : " (en curso)"}
              </Alert>
            ))}
            <Divider sx={{ pt: 1 }} />
          </Stack>
        )}

        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
          Registrar una ausencia
        </Typography>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          <TextField select label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value as MotivoAusencia)} sx={{ gridColumn: { sm: "1 / -1" } }}>
            {Object.entries(MOTIVOS).map(([k, v]) => (
              <MenuItem key={k} value={k}>
                {v}
              </MenuItem>
            ))}
          </TextField>
          <TextField type="datetime-local" label="Desde" value={desde} onChange={(e) => setDesde(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField
            type="datetime-local"
            label="Regresa"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            error={!!hasta && !fechasOk}
            helperText={!!hasta && !fechasOk ? "Debe ser posterior al inicio" : " "}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            select
            label="Reemplazo"
            value={reemplazo}
            onChange={(e) => setReemplazo(Number(e.target.value))}
            disabled={!fechasOk}
            helperText={elegido?.categorias_comunes.length ? `Atiende ${elegido.categorias_comunes.join(", ")}` : "Quién recibe sus tickets mientras no está"}
            sx={{ gridColumn: { sm: "1 / -1" } }}
          >
            {(reemplazos.data ?? []).map((r) => (
              <MenuItem key={r.id} value={r.id}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
                  <Box sx={{ flex: 1 }}>{r.nombre}</Box>
                  <Typography variant="caption" color="text.secondary">
                    {r.tickets_abiertos} abiertos
                  </Typography>
                  {r.sugerido && <Chip size="small" color="success" label="Sugerido" />}
                </Box>
              </MenuItem>
            ))}
            {reemplazos.data?.length === 0 && <MenuItem disabled>No hay compañeros disponibles en esas fechas</MenuItem>}
          </TextField>
        </Box>

        <Typography variant="subtitle2" sx={{ mt: 2 }}>
          Tickets abiertos ({n})
        </Typography>
        <RadioGroup value={pasarAbiertos ? "si" : "no"} onChange={(e) => setPasarAbiertos(e.target.value === "si")}>
          <FormControlLabel value="si" control={<Radio size="small" />} label={`Pasar mis ${n} tickets abiertos al reemplazo`} />
          <FormControlLabel value="no" control={<Radio size="small" />} label="Solo los tickets nuevos que lleguen mientras no estoy" />
        </RadioGroup>
        {n > 0 && (
          <>
            <Button size="small" onClick={() => setVerTickets(!verTickets)}>
              {verTickets ? "Ocultar tickets" : "Ver qué tickets pasan"}
            </Button>
            <Collapse in={verTickets}>
              <Box sx={{ maxHeight: 160, overflow: "auto", border: "1px solid #E3E8F0", borderRadius: 1, p: 1, mt: 0.5 }}>
                {(tickets.data ?? []).map((t) => (
                  <Typography key={t.id} variant="body2" noWrap>
                    <b>{t.numero}</b> · {t.asunto}
                  </Typography>
                ))}
              </Box>
            </Collapse>
          </>
        )}
        <Stack sx={{ mt: 1 }}>
          <FormControlLabel control={<Checkbox size="small" checked={devolver} onChange={(e) => setDevolver(e.target.checked)} />} label="Devolverme los tickets cuando regrese" />
          <FormControlLabel
            control={<Checkbox size="small" checked={avisarSolicitantes} onChange={(e) => setAvisarSolicitantes(e.target.checked)} />}
            label="Avisar a los solicitantes quién los atiende"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cerrar</Button>
        <Button variant="contained" disabled={!fechasOk || reemplazo === "" || crear.isPending} onClick={() => crear.mutate()}>
          Programar ausencia
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** Avisos fijos bajo la barra superior: tickets propios a punto de vencer y reemplazos en curso. */
export function AvisosSuperiores({ gestor }: { gestor: boolean }) {
  const navigate = useNavigate();
  const { usuario } = useAuth();
  const [descartadas, setDescartadas] = useState<string>(() => {
    try {
      return sessionStorage.getItem("aducorp.alertasSla") ?? "";
    } catch {
      return "";
    }
  });
  const alertas = useQuery({
    queryKey: ["tickets", "alertas-sla"],
    queryFn: () => get<AlertaSla[]>("/tickets/alertas-sla"),
    enabled: gestor,
    refetchInterval: 60_000,
  });
  const ausencias = useQuery({
    queryKey: ["ausencias", "mias"],
    queryFn: () => get<Ausencia[]>("/ausencias/mias"),
    enabled: gestor,
    refetchInterval: 5 * 60_000,
  });
  const firma = useMemo(() => (alertas.data ?? []).map((a) => a.id).join(","), [alertas.data]);
  const visibles = (alertas.data ?? []).filter((a) => !descartadas.split(",").includes(String(a.id)));
  const cubro = (ausencias.data ?? []).filter((a) => a.estado === "ACTIVA" && a.reemplazo.id === usuario?.id);
  const ausente = (ausencias.data ?? []).find((a) => a.estado === "ACTIVA" && a.usuario.id === usuario?.id);

  const descartar = () => {
    setDescartadas(firma);
    try {
      sessionStorage.setItem("aducorp.alertasSla", firma);
    } catch {
      /* sin almacenamiento */
    }
  };

  if (!visibles.length && !cubro.length && !ausente) return null;
  const primera = visibles[0];
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {primera && (
        <Alert
          severity="error"
          icon={<AlarmIcon />}
          sx={{ alignItems: "center" }}
          action={
            <Stack direction="row" spacing={1}>
              <Button color="inherit" size="small" variant="outlined" onClick={() => navigate(visibles.length === 1 ? `/tickets/${primera.id}` : "/tickets?vence=HOY")}>
                {visibles.length === 1 ? "Abrir ticket" : "Ver tickets"}
              </Button>
              <IconButton color="inherit" size="small" onClick={descartar} aria-label="Descartar aviso">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          }
        >
          <b>{primera.numero}</b> {primera.vence_tipo === "RESPUESTA" ? "debe recibir su 1.ª respuesta" : "vence"} en{" "}
          <b>{textoMinutos(primera.vence_en_min)}</b> · {primera.asunto}
          {visibles.length > 1 && ` (y ${visibles.length - 1} más por vencer)`}
        </Alert>
      )}
      {cubro.map((a) => (
        <Alert key={a.id} severity="info" icon={<BeachAccessIcon />}>
          Usted cubre a <b>{a.usuario.nombre}</b> hasta el {fechaHora(a.hasta)}
          {a.tickets_abiertos ? ` · se le pasaron ${a.tickets_abiertos} ticket(s)` : ""}.
        </Alert>
      ))}
      {ausente && (
        <Alert severity="warning" icon={<BeachAccessIcon />}>
          Está registrado como ausente hasta el {fechaHora(ausente.hasta)}. Sus tickets nuevos van a <b>{ausente.reemplazo.nombre}</b>. Si ya volvió,
          use «Mi disponibilidad › Volví antes».
        </Alert>
      )}
    </Stack>
  );
}
