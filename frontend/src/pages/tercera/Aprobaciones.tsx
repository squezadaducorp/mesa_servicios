import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Chip, Divider, Grid, Link, Paper, TextField, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import CheckIcon from "@mui/icons-material/CheckCircle";
import CloseIcon from "@mui/icons-material/Cancel";
import HourglassIcon from "@mui/icons-material/HourglassTop";
import PauseIcon from "@mui/icons-material/PauseCircleOutlined";
import { get, post } from "../../api/client";
import type { Aprobacion, BandejaAprobaciones } from "../../api/tercera";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { duracion, fechaHora, tiempoRelativo } from "../../utils/formato";
import { marca } from "../../theme";

export const ESPERA = { bgcolor: "#FFF3D6", color: "#8A5A00", border: "1px solid #F2C14E" };

function Detalle({ a, accionInicial, onListo }: { a: Aprobacion; accionInicial: string | null; onListo: () => void }) {
  const avisar = useAviso();
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState<string | null>(null);
  const responder = useMutation({
    mutationFn: (aprobar: boolean) => post(`/aprobaciones/${a.id}/responder`, { aprobar, comentario: comentario.trim() || null }),
    onSuccess: (_, aprobar) => {
      avisar(aprobar ? `${a.ticket.numero} aprobado` : `${a.ticket.numero} rechazado`);
      setComentario("");
      onListo();
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const pendiente = a.estado === "PENDIENTE";
  const t = a.ticket;
  return (
    <Paper sx={{ p: 2.5 }}>
      <Link component={RouterLink} to={`/tickets/${t.id}`} variant="caption" sx={{ fontWeight: 700 }}>{t.numero}</Link>
      <Typography variant="h6" sx={{ mb: 1.5 }}>{t.asunto}</Typography>
      {[
        ["Pedido por", `${t.creado_por && t.creado_por !== t.solicitante ? `${t.creado_por} para ` : ""}${t.solicitante}${t.area ? ` · ${t.area}` : ""}`],
        ["Categoría", `${t.categoria} › ${t.subcategoria}`],
        ["Regla", a.regla ?? "—"],
        ["Recibido", fechaHora(a.fecha_solicitud)],
        ...(a.en_lugar_de ? [["En lugar de", a.en_lugar_de]] : []),
      ].map(([k, v]) => (
        <Stack key={k} direction="row" spacing={1.5} sx={{ py: 0.5 }}>
          <Typography variant="body2" color="text.secondary" sx={{ width: 108, flexShrink: 0 }}>{k}</Typography>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{v}</Typography>
        </Stack>
      ))}
      <Typography variant="body2" sx={{ mt: 1.5, p: 1.5, bgcolor: "#F8FAFD", borderRadius: 2, whiteSpace: "pre-wrap" }}>{t.descripcion}</Typography>
      {t.motivo && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Motivo de pedirlo en su nombre: {t.motivo}</Typography>}
      <Divider sx={{ my: 2 }} />
      {pendiente ? (
        <>
          {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
          {accionInicial === "rechazar" && <Alert severity="warning" sx={{ mb: 1.5 }}>Escriba el motivo del rechazo: el solicitante lo verá.</Alert>}
          <TextField fullWidth multiline minRows={2} label="Comentario (obligatorio si rechaza)" placeholder="Opcional al aprobar"
            value={comentario} onChange={(e) => setComentario(e.target.value)} autoFocus={accionInicial === "rechazar"} />
          <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
            <Button fullWidth variant="outlined" color="error" startIcon={<CloseIcon />} disabled={responder.isPending || comentario.trim().length < 3}
              onClick={() => responder.mutate(false)}>Rechazar</Button>
            <Button fullWidth variant="contained" color="success" startIcon={<CheckIcon />} disabled={responder.isPending}
              onClick={() => responder.mutate(true)}>Aprobar</Button>
          </Stack>
          <Alert severity="info" icon={<PauseIcon />} sx={{ mt: 2 }}>
            Mientras está «Por aprobar», el SLA del equipo está en pausa: la espera no cuenta contra el analista.
          </Alert>
        </>
      ) : (
        <Alert severity={a.estado === "APROBADO" ? "success" : a.estado === "RECHAZADO" ? "error" : "info"}>
          {a.estado === "APROBADO" ? "Aprobada" : a.estado === "RECHAZADO" ? "Rechazada" : "Ya no está pendiente"}
          {a.fecha_respuesta ? ` el ${fechaHora(a.fecha_respuesta)}` : ""}{a.comentario ? `: «${a.comentario}»` : ""}
        </Alert>
      )}
    </Paper>
  );
}

export default function Aprobaciones() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const idUrl = Number(params.get("id")) || null;
  const accion = params.get("accion");
  const [sel, setSel] = useState<number | null>(idUrl);
  const q = useQuery({ queryKey: ["aprobaciones"], queryFn: () => get<BandejaAprobaciones>("/aprobaciones") });
  const desdeCorreo = useQuery({
    queryKey: ["aprobaciones", idUrl],
    queryFn: () => get<Aprobacion>(`/aprobaciones/${idUrl}`),
    enabled: !!idUrl && !!q.data && !q.data.pendientes.some((p) => p.id === idUrl),
    retry: false,
  });
  useEffect(() => {
    if (!sel && q.data?.pendientes.length) setSel(q.data.pendientes[0].id);
  }, [q.data, sel]);
  const actual = useMemo(
    () => q.data?.pendientes.find((p) => p.id === sel) ?? q.data?.recientes.find((p) => p.id === sel) ?? (desdeCorreo.data?.id === sel ? desdeCorreo.data : undefined),
    [q.data, sel, desdeCorreo.data],
  );
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;
  const listo = () => {
    qc.invalidateQueries({ queryKey: ["aprobaciones"] });
    setSel(null);
    if (params.get("id")) setParams({}, { replace: true });
  };
  const fila = (a: Aprobacion) => (
    <Stack key={a.id} direction="row" spacing={2} alignItems="center" onClick={() => setSel(a.id)}
      sx={{ px: 2.5, py: 1.8, cursor: "pointer", borderBottom: "1px solid #EEF1F6", ...(a.id === sel ? { bgcolor: "#F2F7FC", borderLeft: `4px solid ${marca.azul}` } : {}) }}>
      <Avatar sx={{ bgcolor: "#EEF5FC", color: marca.azul }}><HourglassIcon /></Avatar>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="caption" sx={{ color: marca.azul, fontWeight: 700 }}>{a.ticket.numero}</Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{a.ticket.asunto}</Typography>
        <Typography variant="caption" color="text.secondary">
          {a.ticket.creado_por && a.ticket.creado_por !== a.ticket.solicitante ? `${a.ticket.creado_por} (la pide para ${a.ticket.solicitante})` : a.ticket.solicitante} · {a.ticket.subcategoria}
        </Typography>
      </Box>
      <Stack alignItems="flex-end" spacing={0.6}>
        {a.estado === "PENDIENTE" ? <Chip size="small" label="Por aprobar" sx={ESPERA} /> : <Chip size="small" variant="outlined" label={a.estado === "APROBADO" ? "Aprobada" : a.estado === "RECHAZADO" ? "Rechazada" : a.estado} color={a.estado === "APROBADO" ? "success" : a.estado === "RECHAZADO" ? "error" : "default"} />}
        <Typography variant="caption" color="text.secondary">{tiempoRelativo(a.fecha_solicitud)}</Typography>
      </Stack>
    </Stack>
  );
  return (
    <Box>
      <Encabezado titulo="Por aprobar" subtitulo="Solicitudes de su equipo que necesitan su visto bueno antes de que la mesa las atienda." />
      {desdeCorreo.error && <Alert severity="warning" sx={{ mb: 2 }}>Esa aprobación ya fue respondida o no le corresponde.</Alert>}
      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 7.2 }}>
          <Paper>
            {d.pendientes.length ? d.pendientes.map(fila) : <Vacio texto="No tiene aprobaciones pendientes" />}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 2.5, py: 1.3 }}>
              Últimos 30 días: {d.aprobadas_30d} aprobadas · {d.rechazadas_30d} rechazadas
              {d.minutos_respuesta_promedio !== null ? ` · tiempo medio de respuesta ${duracion(d.minutos_respuesta_promedio)}` : ""}
            </Typography>
          </Paper>
          {d.recientes.length > 0 && (
            <>
              <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>Respondidas recientemente</Typography>
              <Paper>{d.recientes.map(fila)}</Paper>
            </>
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 4.8 }}>
          {actual ? <Detalle key={actual.id} a={actual} accionInicial={actual.id === idUrl ? accion : null} onListo={listo} />
            : <Paper sx={{ p: 3 }}><Typography color="text.secondary">Elija una solicitud para ver el detalle.</Typography></Paper>}
        </Grid>
      </Grid>
    </Box>
  );
}
