import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, Link, MenuItem, Paper,
  Radio, Switch, TextField, Tooltip, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import ContentCopyIcon from "@mui/icons-material/FileCopyOutlined";
import LinkIcon from "@mui/icons-material/Link";
import MergeIcon from "@mui/icons-material/MergeType";
import CloseIcon from "@mui/icons-material/Close";
import BlockIcon from "@mui/icons-material/Block";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import HourglassIcon from "@mui/icons-material/HourglassTop";
import CheckIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import ShareIcon from "@mui/icons-material/Share";
import { del, get, post } from "../../api/client";
import type { TicketDetalle as Ticket } from "../../api/types";
import type { PosibleDuplicado, TicketCorto, Vinculo } from "../../api/tercera";
import { mensajeError, useAviso } from "../../components/Aviso";
import { EstadoChip } from "../../components/Chips";
import { fechaHora, tiempoRelativo } from "../../utils/formato";
import { marca } from "../../theme";
import { ESPERA } from "./Aprobaciones";

const TERMINADOS = ["RESUELTO", "CERRADO", "CANCELADO"];

/** Diálogo para unir tickets duplicados en uno principal (desde el detalle o desde la selección de la lista). */
export function UnirDialogo({ tickets, principalInicial, onCerrar }: {
  tickets: (TicketCorto & { solicitante?: string; fecha_creacion?: string })[]; principalInicial?: number; onCerrar: (principalId?: number) => void;
}) {
  const avisar = useAviso();
  const [principal, setPrincipal] = useState<number>(principalInicial ?? tickets[0]?.id);
  const [mensaje, setMensaje] = useState("");
  const [avisarSol, setAvisarSol] = useState(true);
  const [prioridad, setPrioridad] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const p = tickets.find((x) => x.id === principal);
  const unir = useMutation({
    mutationFn: () => post<Ticket>("/tickets/unir", {
      principal_id: principal, duplicados: tickets.filter((x) => x.id !== principal).map((x) => x.id), mensaje: mensaje.trim() || null,
      avisar: avisarSol, mantener_prioridad: prioridad,
    }),
    onSuccess: (t) => {
      avisar(`Unidos en ${t.numero}`);
      onCerrar(t.id);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center"><MergeIcon color="primary" /><span>Unir {tickets.length} tickets duplicados</span></Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Elija el ticket que se queda abierto. Los demás se cancelan como duplicados (no cuentan en el SLA) y su conversación, adjuntos y solicitantes pasan al principal.
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Paper variant="outlined">
          {tickets.map((x) => (
            <Stack key={x.id} direction="row" spacing={1.5} alignItems="center" onClick={() => setPrincipal(x.id)}
              sx={{ px: 2, py: 1.2, cursor: "pointer", borderBottom: "1px solid #EEF1F6", bgcolor: x.id === principal ? "#F2F7FC" : undefined }}>
              <Radio checked={x.id === principal} size="small" />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ color: marca.azul, fontWeight: 700 }}>{x.numero}</Typography>
                <Typography variant="body2" noWrap>{x.asunto}</Typography>
                {(x.solicitante || x.fecha_creacion) && (
                  <Typography variant="caption" color="text.secondary">{[x.solicitante, x.fecha_creacion && tiempoRelativo(x.fecha_creacion)].filter(Boolean).join(" · ")}</Typography>
                )}
              </Box>
              <EstadoChip estado={x.estado} nombre={x.estado_nombre} />
              {x.id === principal && <Typography variant="caption" sx={{ fontWeight: 700, color: marca.azul }}>PRINCIPAL</Typography>}
            </Stack>
          ))}
        </Paper>
        <TextField fullWidth multiline minRows={2} sx={{ mt: 2 }} label="Mensaje para los solicitantes de los duplicados"
          placeholder={`Varias personas reportaron lo mismo. Lo atendemos en ${p?.numero ?? "el ticket principal"} y le avisaremos al resolverlo.`}
          value={mensaje} onChange={(e) => setMensaje(e.target.value)} />
        <FormControlLabel sx={{ mt: 1 }} control={<Switch checked={avisarSol} onChange={(e) => setAvisarSol(e.target.checked)} />}
          label={<Typography variant="body2">Avisar por correo a los solicitantes (y les llegarán las respuestas del principal)</Typography>} />
        <FormControlLabel control={<Switch checked={prioridad} onChange={(e) => setPrioridad(e.target.checked)} />}
          label={<Typography variant="body2">El principal toma la prioridad más alta del grupo</Typography>} />
        <Alert severity="info" sx={{ mt: 1.5 }}>La unión no se puede deshacer: los duplicados quedan cancelados con un enlace al principal.</Alert>
      </DialogContent>
      <DialogActions>
        <Button color="inherit" onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" startIcon={<MergeIcon />} disabled={unir.isPending || tickets.length < 2} onClick={() => unir.mutate()}>
          Unir en {p?.numero}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** Avisos sobre el ticket: duplicado de otro, esperando aprobación, posible duplicado. */
export function AlertasTercera({ t, onCambio }: { t: Ticket; onCambio: () => void }) {
  const navigate = useNavigate();
  const avisar = useAviso();
  const [unir, setUnir] = useState<PosibleDuplicado | null>(null);
  const gestiona = t.acciones.includes("vincular") && !TERMINADOS.includes(t.estado);
  const posibles = useQuery({
    queryKey: ["ticket", String(t.id), "posibles-duplicados"],
    queryFn: () => get<PosibleDuplicado[]>(`/tickets/${t.id}/posibles-duplicados`),
    enabled: gestiona,
  });
  const descartar = useMutation({
    mutationFn: (otro: number) => post(`/tickets/${t.id}/posibles-duplicados/${otro}/descartar`),
    onSuccess: () => posibles.refetch(),
  });
  const vincular = useMutation({
    mutationFn: (numero: string) => post(`/tickets/${t.id}/vinculos`, { relacionado: numero, tipo: "RELACIONADO" }),
    onSuccess: () => {
      avisar("Tickets vinculados");
      posibles.refetch();
      onCambio();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const pendiente = (t.aprobaciones ?? []).find((x) => x.estado === "PENDIENTE");
  const dup = posibles.data?.[0];
  return (
    <>
      {t.duplicado_de && (
        <Alert severity="info" icon={<MergeIcon />} sx={{ mb: 2 }}>
          Este ticket se unió como duplicado de{" "}
          <Link component={RouterLink} to={`/tickets/${t.duplicado_de.id}`} sx={{ fontWeight: 700 }}>{t.duplicado_de.numero}</Link>: se atiende allí.
        </Alert>
      )}
      {t.estado === "POR_APROBAR" && (
        <Alert severity="warning" icon={<HourglassIcon />} sx={{ mb: 2, ...ESPERA }}
          action={t.aprobacion_pendiente_id ? (
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="contained" color="success" startIcon={<CheckIcon />} onClick={() => navigate(`/aprobaciones?id=${t.aprobacion_pendiente_id}&accion=aprobar`)}>Aprobar</Button>
              <Button size="small" variant="outlined" color="error" startIcon={<CancelIcon />} onClick={() => navigate(`/aprobaciones?id=${t.aprobacion_pendiente_id}&accion=rechazar`)}>Rechazar</Button>
            </Stack>
          ) : undefined}>
          <b>Por aprobar.</b>{" "}
          {pendiente ? <>Esperando el visto bueno de <b>{pendiente.aprobador}</b>{pendiente.nivel > 1 ? ` (nivel ${pendiente.nivel})` : ""} desde {fechaHora(pendiente.fecha_solicitud)}.</> : "Esperando el visto bueno del aprobador."}
          {" "}Mientras tanto el SLA está en pausa y el equipo aún no lo atiende.
        </Alert>
      )}
      {dup && (
        <Alert severity="warning" icon={<ContentCopyIcon />} sx={{ mb: 2, alignItems: "center" }}
          action={
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button size="small" variant="contained" color="warning" startIcon={<MergeIcon />} onClick={() => setUnir(dup)}>Unir</Button>
              <Button size="small" color="inherit" disabled={vincular.isPending} onClick={() => vincular.mutate(dup.numero)}>Vincular</Button>
              <Button size="small" color="inherit" sx={{ whiteSpace: "nowrap" }} onClick={() => descartar.mutate(dup.id)}>No es duplicado</Button>
            </Stack>
          }>
          <b>Posible duplicado.</b> Se parece a{" "}
          <Link component={RouterLink} to={`/tickets/${dup.id}`} sx={{ fontWeight: 700 }}>{dup.numero}</Link> «{dup.asunto}» ({dup.solicitante}, {tiempoRelativo(dup.fecha_creacion)}; {dup.razones.join(", ")}).
          {posibles.data!.length > 1 && ` Hay ${posibles.data!.length - 1} más parecido(s).`}
        </Alert>
      )}
      {unir && (
        <UnirDialogo
          tickets={[
            { id: unir.id, numero: unir.numero, asunto: unir.asunto, estado: unir.estado, solicitante: unir.solicitante, fecha_creacion: unir.fecha_creacion },
            { id: t.id, numero: t.numero, asunto: t.asunto, estado: t.estado, estado_nombre: t.estado_nombre, solicitante: t.solicitante_nombre, fecha_creacion: t.fecha_creacion },
          ]}
          principalInicial={unir.id}
          onCerrar={(pid) => {
            setUnir(null);
            if (!pid) return;
            if (pid !== t.id) navigate(`/tickets/${pid}`);
            else onCambio();
          }}
        />
      )}
    </>
  );
}

const ICONO: Record<string, React.ReactNode> = {
  RELACIONADO: <LinkIcon fontSize="small" />, BLOQUEADO_POR: <BlockIcon fontSize="small" />, DUPLICADO: <MergeIcon fontSize="small" />,
};

/** Panel lateral: tickets vinculados, avisos generales, aprobaciones y enlace de seguimiento del cliente. */
export function PanelTercera({ t, onCambio }: { t: Ticket; onCambio: () => void }) {
  const avisar = useAviso();
  const [agregar, setAgregar] = useState(false);
  const [relacionado, setRelacionado] = useState("");
  const [tipo, setTipo] = useState<"RELACIONADO" | "BLOQUEADO_POR">("RELACIONADO");
  const puede = t.acciones.includes("vincular");
  const vincular = useMutation({
    mutationFn: () => post<Vinculo[]>(`/tickets/${t.id}/vinculos`, { relacionado: relacionado.trim(), tipo }),
    onSuccess: () => {
      setRelacionado("");
      setAgregar(false);
      onCambio();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const quitar = useMutation({
    mutationFn: (vid: number) => del(`/tickets/${t.id}/vinculos/${vid}`),
    onSuccess: onCambio,
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const vinculos = t.vinculos ?? [];
  const avisos = t.avisos ?? [];
  const aprob = t.aprobaciones ?? [];
  return (
    <>
      {(puede || vinculos.length > 0 || avisos.length > 0) && (
        <Paper sx={{ p: 2.5 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <LinkIcon sx={{ color: marca.azul }} />
            <Typography variant="h6" sx={{ flex: 1 }}>Tickets vinculados</Typography>
            {puede && !agregar && <Button size="small" onClick={() => setAgregar(true)}>+ Vincular</Button>}
          </Stack>
          {agregar && (
            <Stack spacing={1} sx={{ mb: 1.5 }}>
              <Stack direction="row" spacing={1}>
                <TextField size="small" select value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)} sx={{ width: 150 }}>
                  <MenuItem value="RELACIONADO">Relacionado con</MenuItem>
                  <MenuItem value="BLOQUEADO_POR">Bloqueado por</MenuItem>
                </TextField>
                <TextField size="small" fullWidth placeholder="ADU-2026-000123" value={relacionado} onChange={(e) => setRelacionado(e.target.value)} />
              </Stack>
              {tipo === "BLOQUEADO_POR" && <Typography variant="caption" color="text.secondary">Este ticket no se podrá resolver hasta que el otro termine.</Typography>}
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button size="small" color="inherit" onClick={() => setAgregar(false)}>Cancelar</Button>
                <Button size="small" variant="contained" disabled={!relacionado.trim() || vincular.isPending} onClick={() => vincular.mutate()}>Vincular</Button>
              </Stack>
            </Stack>
          )}
          {vinculos.length === 0 && avisos.length === 0 && !agregar && <Typography variant="body2" color="text.secondary">Sin vínculos.</Typography>}
          {vinculos.map((v) => (
            <Box key={v.id} sx={{ py: 1.2, borderTop: "1px solid #EEF1F6" }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Box sx={{ color: "text.secondary", display: "flex" }}>{ICONO[v.tipo]}</Box>
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>{v.etiqueta}</Typography>
                {puede && v.tipo !== "DUPLICADO" && (
                  <Tooltip title="Quitar vínculo">
                    <IconButton size="small" onClick={() => quitar.mutate(v.id)}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>
                  </Tooltip>
                )}
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Link component={RouterLink} to={`/tickets/${v.ticket.id}`} variant="body2" sx={{ fontWeight: 700 }}>{v.ticket.numero}</Link>
                <EstadoChip estado={v.ticket.estado} nombre={v.ticket.estado_nombre} />
              </Stack>
              <Typography variant="body2">{v.ticket.asunto}</Typography>
            </Box>
          ))}
          {avisos.map((a) => (
            <Box key={`a${a.id}`} sx={{ py: 1.2, borderTop: "1px solid #EEF1F6" }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <AccountTreeIcon fontSize="small" sx={{ color: "text.secondary" }} />
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>{a.maestro ? "Ticket maestro de" : "Parte de"} un aviso general</Typography>
              </Stack>
              <Typography variant="body2"><b>{a.codigo}</b> · {a.titulo} · {a.estado_nombre}</Typography>
            </Box>
          ))}
        </Paper>
      )}

      {aprob.length > 0 && (
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" sx={{ mb: 1.5 }}>Aprobación</Typography>
          {aprob.map((x) => (
            <Stack key={x.id} direction="row" spacing={1.2} alignItems="flex-start" sx={{ mb: 1.2 }}>
              <Avatar sx={{ width: 26, height: 26, fontSize: 13, bgcolor: x.estado === "PENDIENTE" ? "#F2C14E" : x.estado === "APROBADO" ? "#2E7D32" : x.estado === "RECHAZADO" ? "#C62828" : "#CFD8E3", color: x.estado === "PENDIENTE" ? "#5A3B00" : "#fff" }}>
                {x.nivel}
              </Avatar>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{x.aprobador}{x.en_lugar_de ? ` (en lugar de ${x.en_lugar_de})` : ""}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {x.estado === "PENDIENTE" ? `Pendiente desde ${fechaHora(x.fecha_solicitud)}` : `${{ APROBADO: "Aprobó", RECHAZADO: "Rechazó", REASIGNADO: "Pasó a otra persona", ANULADO: "Anulada" }[x.estado]} · ${fechaHora(x.fecha_respuesta)}`}
                </Typography>
                {x.comentario && <Typography variant="body2" sx={{ fontStyle: "italic" }}>«{x.comentario}»</Typography>}
              </Box>
            </Stack>
          ))}
        </Paper>
      )}

      {t.seguimiento_url && (
        <Paper sx={{ p: 2.5 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <ShareIcon sx={{ color: marca.azul }} />
            <Typography variant="h6">Seguimiento del cliente</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            El solicitante no tiene cuenta: cada correo le lleva este enlace para ver el estado y responder. No muestra notas internas.
          </Typography>
          <Button size="small" variant="outlined" startIcon={<ContentCopyIcon />}
            onClick={() => navigator.clipboard?.writeText(t.seguimiento_url!).then(() => avisar("Enlace copiado"), () => avisar("No se pudo copiar", "error"))}>
            Copiar enlace
          </Button>
        </Paper>
      )}
    </>
  );
}
