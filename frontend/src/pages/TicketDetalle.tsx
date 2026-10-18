import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Chip, Divider, FormControlLabel, IconButton, List, ListItem, ListItemIcon, ListItemText, Menu, MenuItem,
  Paper, Stack, Switch, Tab, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DownloadIcon from "@mui/icons-material/Download";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import LockIcon from "@mui/icons-material/Lock";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import SendIcon from "@mui/icons-material/Send";
import PauseCircleIcon from "@mui/icons-material/PauseCircle";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import { api, del, descargar, get, patch, post } from "../api/client";
import type { Riesgo, TextoIa, TicketDetalle as Ticket } from "../api/types";
import { mensajeError, useAviso } from "../components/Aviso";
import { CumplimientoChip, EstadoChip, PrioridadChip, SlaBarra, colorSla } from "../components/Chips";
import { Cargando, ErrorCarga, Vacio } from "../components/Comunes";
import { duracion, fechaHora, tamanoArchivo, tiempoRelativo } from "../utils/formato";
import TicketDialogos, { estadosDestino, type Dialogo } from "./TicketDialogos";

const ACCION_HISTORIAL: Record<string, string> = {
  CREACION: "Creó el ticket",
  CAMBIO_ESTADO: "Cambió el estado",
  ASIGNACION: "Asignó",
  REANUDACION: "Reanudó el SLA",
  ESCALAMIENTO: "Escaló",
  EDICION: "Editó",
  COMENTARIO: "Comentó",
  ADJUNTO: "Adjuntó",
  CIERRE: "Cerró",
  REAPERTURA: "Reabrió",
  SLA: "SLA",
  EXCEPCION_SLA: "Excepción de SLA",
};

function Dato({ etiqueta, valor }: { etiqueta: string; valor: React.ReactNode }) {
  return (
    <Box sx={{ py: 0.75 }}>
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
        {etiqueta}
      </Typography>
      <Typography variant="body2" component="div" sx={{ fontWeight: 500, wordBreak: "break-word" }}>
        {valor ?? "—"}
      </Typography>
    </Box>
  );
}

function iniciales(n: string) {
  return n.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export default function TicketDetalle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [tab, setTab] = useState(0);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [estadoInicial, setEstadoInicial] = useState<string>();
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [texto, setTexto] = useState("");
  const [interno, setInterno] = useState(false);
  const [resumen, setResumen] = useState<TextoIa | null>(null);
  const clave = ["ticket", id];
  const q = useQuery({ queryKey: clave, queryFn: () => get<Ticket>(`/tickets/${id}`), refetchInterval: 60_000 });
  const t = q.data;
  const puedeIa = !!t?.acciones.includes("ia");
  const riesgo = useQuery({
    queryKey: ["ticket", id, "riesgo"],
    queryFn: () => get<Riesgo>(`/tickets/${id}/ia/riesgo`),
    enabled: puedeIa && !!t && !["RESUELTO", "CERRADO", "CANCELADO"].includes(t.estado),
  });

  const actualizar = (nuevo: Ticket) => {
    qc.setQueryData(clave, nuevo);
    qc.invalidateQueries({ queryKey: ["tickets"] });
    qc.invalidateQueries({ queryKey: ["notificaciones"] });
  };

  const comentar = useMutation({
    mutationFn: () => post<Ticket>(`/tickets/${id}/comentarios`, { texto, es_interno: interno }),
    onSuccess: (n) => {
      actualizar(n);
      setTexto("");
      setInterno(false);
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const adjuntar = useMutation({
    mutationFn: async (archivos: File[]) => {
      let ultimo: Ticket | undefined;
      for (const f of archivos) {
        const form = new FormData();
        form.append("archivo", f);
        ultimo = await api<Ticket>("POST", `/tickets/${id}/adjuntos`, { form });
      }
      return ultimo;
    },
    onSuccess: (n) => {
      if (n) actualizar(n);
      avisar("Archivo adjuntado");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const sugerirRespuesta = useMutation({
    mutationFn: () => post<TextoIa>(`/tickets/${id}/ia/respuesta`),
    onSuccess: (r) => {
      setTexto(r.texto);
      setInterno(false);
      setTab(0);
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const resumir = useMutation({
    mutationFn: () => post<TextoIa>(`/tickets/${id}/ia/resumen`),
    onSuccess: setResumen,
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  if (q.isLoading) return <Cargando />;
  if (q.error || !t) return <ErrorCarga error={q.error} />;
  const a = new Set(t.acciones);

  const ejecutar = async (d: Exclude<Dialogo, null>, datos: Record<string, unknown>) => {
    const rutas: Record<string, () => Promise<Ticket | unknown>> = {
      estado: () => post<Ticket>(`/tickets/${id}/estado`, datos),
      asignar: () => post<Ticket>(`/tickets/${id}/asignar`, datos),
      escalar: () => post<Ticket>(`/tickets/${id}/escalar`, datos),
      cerrar: () => post<Ticket>(`/tickets/${id}/cerrar`, datos),
      reabrir: () => post<Ticket>(`/tickets/${id}/reabrir`, datos),
      editar: () => patch<Ticket>(`/tickets/${id}`, datos),
      excepcion: () => post<Ticket>(`/tickets/${id}/excepcion-sla`, datos),
      eliminar: () => del(`/tickets/${id}`),
    };
    try {
      const r = await rutas[d]();
      if (d === "eliminar") {
        qc.invalidateQueries({ queryKey: ["tickets"] });
        avisar("Ticket eliminado");
        navigate("/tickets", { replace: true });
        return;
      }
      actualizar(r as Ticket);
      avisar("Cambios guardados");
    } catch (e) {
      avisar(mensajeError(e), "error");
      if (e instanceof Error && "status" in e && (e as { status: number }).status === 409) q.refetch();
      throw e;
    }
  };

  const abrir = (d: Dialogo, estado?: string) => {
    setEstadoInicial(estado);
    setDialogo(d);
    setMenu(null);
  };
  const destinos = estadosDestino(t.estado).filter((e) => e !== "CANCELADO");
  const siguiente = destinos.includes("EN_PROCESO") && t.estado !== "PENDIENTE_CLIENTE" ? "EN_PROCESO" : destinos.includes("RESUELTO") ? "RESUELTO" : undefined;
  const pct = t.sla_consumido_pct;

  return (
    <>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
        <IconButton onClick={() => navigate(-1)} aria-label="Volver">
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Tickets / {t.numero}
        </Typography>
      </Stack>

      <Paper sx={{ p: { xs: 2, md: 3 }, mb: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}>
          <Box sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1, mb: 1 }}>
              <Typography variant="h6" sx={{ color: "primary.main" }}>
                {t.numero}
              </Typography>
              <EstadoChip estado={t.estado} nombre={t.estado_nombre} />
              <PrioridadChip codigo={t.prioridad.codigo} nombre={t.prioridad.nombre} />
              <CumplimientoChip valor={t.cumplimiento_sla} />
              {t.reaperturas > 0 && <Chip size="small" variant="outlined" label={`${t.reaperturas} reapertura(s)`} />}
            </Stack>
            <Typography variant="h5" sx={{ wordBreak: "break-word" }}>
              {t.asunto}
            </Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
              {t.categoria.nombre} › {t.subcategoria.nombre} · creado {fechaHora(t.fecha_creacion)} por {t.solicitante_nombre}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1, flexShrink: 0 }}>
            {a.has("cambiar_estado") && siguiente && (
              <Button variant="contained" onClick={() => abrir("estado", siguiente)}>
                {siguiente === "EN_PROCESO" ? "Iniciar atención" : "Resolver"}
              </Button>
            )}
            {a.has("cambiar_estado") && destinos.length > 0 && (
              <Button variant="outlined" onClick={() => abrir("estado")}>
                Cambiar estado
              </Button>
            )}
            {a.has("asignar") && (
              <Button variant="outlined" onClick={() => abrir("asignar")}>
                {t.responsable ? "Reasignar" : "Asignar"}
              </Button>
            )}
            {a.has("cerrar") && t.estado === "RESUELTO" && (
              <Button variant="contained" color="success" onClick={() => abrir("cerrar")}>
                Cerrar
              </Button>
            )}
            {a.has("reabrir") && (
              <Button variant="outlined" onClick={() => abrir("reabrir")}>
                Reabrir
              </Button>
            )}
            {(a.has("editar") || a.has("escalar") || a.has("excepcion_sla") || a.has("eliminar") || a.has("cerrar")) && (
              <IconButton onClick={(e) => setMenu(e.currentTarget)} aria-label="Más acciones">
                <MoreVertIcon />
              </IconButton>
            )}
            <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
              {a.has("editar") && <MenuItem onClick={() => abrir("editar")}>Editar</MenuItem>}
              {a.has("escalar") && <MenuItem onClick={() => abrir("escalar")}>Escalar</MenuItem>}
              {a.has("cerrar") && t.estado !== "RESUELTO" && <MenuItem onClick={() => abrir("cerrar")}>Cerrar directamente</MenuItem>}
              {a.has("cambiar_estado") && estadosDestino(t.estado).includes("CANCELADO") && (
                <MenuItem onClick={() => abrir("estado", "CANCELADO")}>Cancelar ticket</MenuItem>
              )}
              {a.has("excepcion_sla") && <MenuItem onClick={() => abrir("excepcion")}>Excepción de SLA</MenuItem>}
              {a.has("eliminar") && (
                <MenuItem onClick={() => abrir("eliminar")} sx={{ color: "error.main" }}>
                  Eliminar
                </MenuItem>
              )}
            </Menu>
          </Stack>
        </Stack>
      </Paper>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 2fr) minmax(320px, 1fr)" }, alignItems: "start" }}>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Paper sx={{ p: { xs: 2, md: 3 } }}>
            <Typography variant="subtitle2" sx={{ color: "text.secondary", mb: 1 }}>
              Descripción
            </Typography>
            <Typography variant="body1" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {t.descripcion}
            </Typography>
          </Paper>

          <Paper>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ px: 1, borderBottom: "1px solid #E3E8F0" }}>
              <Tab label={`Comentarios (${t.comentarios.length})`} />
              <Tab label={`Adjuntos (${t.adjuntos.length})`} />
              <Tab label="Historial" />
              <Tab label={`Escalamientos (${t.escalamientos.length})`} />
            </Tabs>
            <Box sx={{ p: { xs: 2, md: 3 } }}>
              {tab === 0 && (
                <Stack spacing={2}>
                  {t.comentarios.length === 0 && <Vacio texto="Aún no hay comentarios" />}
                  {t.comentarios.map((c) => (
                    <Stack key={c.id} direction="row" spacing={1.5}>
                      <Avatar sx={{ width: 36, height: 36, fontSize: 14, bgcolor: c.usuario.id === t.solicitante.id ? "secondary.main" : "primary.main" }}>
                        {iniciales(c.usuario.nombre)}
                      </Avatar>
                      <Box
                        sx={{
                          flex: 1,
                          minWidth: 0,
                          p: 1.5,
                          borderRadius: 2,
                          bgcolor: c.es_interno ? "#FFF8E1" : "#F5F8FC",
                          border: c.es_interno ? "1px dashed #F9A825" : "1px solid #E3E8F0",
                        }}
                      >
                        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5, flexWrap: "wrap" }}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {c.usuario.nombre}
                          </Typography>
                          {c.es_interno && <Chip size="small" icon={<LockIcon />} label="Nota interna" color="warning" variant="outlined" />}
                          {c.tipo === "ACTIVIDAD" && <Chip size="small" label={`Actividad${c.minutos_invertidos ? ` · ${duracion(c.minutos_invertidos)}` : ""}`} />}
                          <Typography variant="caption" sx={{ color: "text.secondary" }}>
                            <Tooltip title={fechaHora(c.fecha)}>
                              <span>{tiempoRelativo(c.fecha)}</span>
                            </Tooltip>
                          </Typography>
                        </Stack>
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                          {c.texto}
                        </Typography>
                      </Box>
                    </Stack>
                  ))}
                  {a.has("comentar") && (
                    <Box>
                      <Divider sx={{ mb: 2 }} />
                      {t.estado === "PENDIENTE_CLIENTE" && !a.has("nota_interna") && (
                        <Alert severity="info" sx={{ mb: 1.5 }}>
                          El equipo espera su respuesta. Al comentar, el ticket vuelve a atención y el SLA se reanuda.
                        </Alert>
                      )}
                      <TextField
                        placeholder={interno ? "Nota interna (no la ve el solicitante)" : "Escriba un comentario"}
                        value={texto}
                        onChange={(e) => setTexto(e.target.value)}
                        multiline
                        minRows={3}
                        fullWidth
                      />
                      <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                        {a.has("nota_interna") && (
                          <FormControlLabel control={<Switch checked={interno} onChange={(e) => setInterno(e.target.checked)} />} label="Nota interna" />
                        )}
                        {puedeIa && (
                          <Button startIcon={<AutoAwesomeIcon />} onClick={() => sugerirRespuesta.mutate()} disabled={sugerirRespuesta.isPending}>
                            Sugerir respuesta
                          </Button>
                        )}
                        <Box sx={{ flex: 1 }} />
                        <Button variant="contained" endIcon={<SendIcon />} disabled={!texto.trim() || comentar.isPending} onClick={() => comentar.mutate()}>
                          Enviar
                        </Button>
                      </Stack>
                    </Box>
                  )}
                </Stack>
              )}
              {tab === 1 && (
                <>
                  {t.adjuntos.length === 0 && <Vacio texto="Sin archivos adjuntos" />}
                  <List dense>
                    {t.adjuntos.map((x) => (
                      <ListItem
                        key={x.id}
                        secondaryAction={
                          <IconButton
                            onClick={() => descargar(`/tickets/${id}/adjuntos/${x.id}`, undefined, x.nombre_original).catch((e) => avisar(mensajeError(e), "error"))}
                            aria-label={`Descargar ${x.nombre_original}`}
                          >
                            <DownloadIcon />
                          </IconButton>
                        }
                      >
                        <ListItemIcon>
                          <InsertDriveFileIcon />
                        </ListItemIcon>
                        <ListItemText primary={x.nombre_original} secondary={`${tamanoArchivo(x.tamano_bytes)} · ${x.usuario.nombre} · ${fechaHora(x.fecha)}`} />
                      </ListItem>
                    ))}
                  </List>
                  {a.has("adjuntar") && (
                    <Button component="label" startIcon={<AttachFileIcon />} variant="outlined" disabled={adjuntar.isPending}>
                      {adjuntar.isPending ? "Subiendo…" : "Adjuntar archivo"}
                      <input
                        hidden
                        type="file"
                        multiple
                        onChange={(e) => {
                          const f = Array.from(e.target.files ?? []);
                          e.target.value = "";
                          if (f.length) adjuntar.mutate(f);
                        }}
                      />
                    </Button>
                  )}
                </>
              )}
              {tab === 2 && (
                <Stack spacing={0}>
                  {t.historial.map((h, i) => (
                    <Stack key={h.id} direction="row" spacing={2}>
                      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: "primary.main", mt: 0.75 }} />
                        {i < t.historial.length - 1 && <Box sx={{ width: 2, flex: 1, bgcolor: "#E3E8F0" }} />}
                      </Box>
                      <Box sx={{ pb: 2, minWidth: 0 }}>
                        <Typography variant="body2">
                          <b>{h.usuario?.nombre ?? "Sistema"}</b> · {ACCION_HISTORIAL[h.accion] ?? h.accion}
                          {h.campo && (
                            <>
                              {" "}
                              <i>{h.campo}</i>: {h.valor_anterior ?? "—"} → {h.valor_nuevo ?? "—"}
                            </>
                          )}
                        </Typography>
                        {h.detalle && (
                          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", wordBreak: "break-word" }}>
                            {h.detalle}
                          </Typography>
                        )}
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>
                          {fechaHora(h.fecha)}
                        </Typography>
                      </Box>
                    </Stack>
                  ))}
                </Stack>
              )}
              {tab === 3 && (
                <>
                  {t.escalamientos.length === 0 && <Vacio texto="El ticket no ha sido escalado" />}
                  <List dense>
                    {t.escalamientos.map((e) => (
                      <ListItem key={e.id}>
                        <ListItemIcon>
                          <TrendingUpIcon sx={{ color: e.nivel >= 100 ? "error.main" : e.nivel >= 90 ? "warning.main" : "primary.main" }} />
                        </ListItemIcon>
                        <ListItemText
                          primary={e.nivel === 0 ? "Escalamiento manual" : `Umbral ${e.nivel} % (${e.tipo.toLowerCase()})`}
                          secondary={`${e.motivo ?? ""}${e.sla_consumido_pct != null ? ` · SLA ${e.sla_consumido_pct.toFixed(0)} %` : ""} · ${fechaHora(e.fecha)}`}
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}
            </Box>
          </Paper>
        </Stack>

        <Stack spacing={2}>
          <Paper sx={{ p: 2.5 }}>
            <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
              <Typography variant="h6">SLA</Typography>
              {t.sla_pausado && <Chip size="small" icon={<PauseCircleIcon />} label="En pausa" color="warning" />}
              {t.sla_excluido && <Chip size="small" label="Excluido" />}
            </Stack>
            <SlaBarra pct={pct} pausado={t.sla_pausado} />
            <Typography variant="caption" sx={{ color: colorSla(pct), fontWeight: 600 }}>
              {pct >= 100 ? "SLA vencido" : pct >= 90 ? "Crítico: supera el 90 %" : pct >= 75 ? "Próximo a vencer" : "Dentro del plazo"}
            </Typography>
            <Divider sx={{ my: 1.5 }} />
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 2 }}>
              <Dato etiqueta="SLA respuesta" valor={duracion(t.sla_respuesta_min)} />
              <Dato etiqueta="SLA resolución" valor={duracion(t.sla_resolucion_min + t.sla_minutos_extension)} />
              <Dato
                etiqueta="Vence respuesta"
                valor={
                  <>
                    {fechaHora(t.sla_respuesta_vence)}
                    {t.sla_respuesta_cumplido === true && <Chip size="small" color="success" label="OK" sx={{ ml: 0.5 }} />}
                    {t.sla_respuesta_cumplido === false && <Chip size="small" color="error" label="Vencida" sx={{ ml: 0.5 }} />}
                  </>
                }
              />
              <Dato etiqueta="Vence resolución" valor={fechaHora(t.sla_resolucion_vence)} />
              <Dato etiqueta="Consumido" valor={duracion(t.sla_minutos_consumidos)} />
              <Dato etiqueta="En pausa" valor={duracion(t.sla_minutos_pausa)} />
              <Dato etiqueta="Primera respuesta" valor={fechaHora(t.fecha_primera_respuesta)} />
              <Dato etiqueta="Resolución" valor={fechaHora(t.fecha_resolucion)} />
            </Box>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Tiempos en horas laborables.
              {t.sla_minutos_extension > 0 && ` Incluye extensión de ${duracion(t.sla_minutos_extension)}.`}
            </Typography>
          </Paper>

          {puedeIa && (
            <Paper sx={{ p: 2.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
                <AutoAwesomeIcon color="primary" />
                <Typography variant="h6">Asistente IA</Typography>
              </Stack>
              {riesgo.data && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    Riesgo de incumplimiento
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <Typography variant="h5" sx={{ color: riesgo.data.riesgo >= 70 ? "error.main" : riesgo.data.riesgo >= 40 ? "warning.main" : "success.main" }}>
                      {Math.round(riesgo.data.riesgo)} %
                    </Typography>
                    <Chip size="small" label={riesgo.data.nivel} />
                  </Stack>
                  {riesgo.data.motivos.map((m) => (
                    <Typography key={m} variant="caption" sx={{ display: "block", color: "text.secondary" }}>
                      • {m}
                    </Typography>
                  ))}
                </Box>
              )}
              {(resumen?.texto ?? t.resumen_ia) && (
                <Alert severity="info" icon={false} sx={{ mb: 1.5, whiteSpace: "pre-wrap" }}>
                  {resumen?.texto ?? t.resumen_ia}
                </Alert>
              )}
              <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
                <Button size="small" variant="outlined" onClick={() => resumir.mutate()} disabled={resumir.isPending}>
                  {resumir.isPending ? "Resumiendo…" : "Resumir ticket"}
                </Button>
                <Button size="small" variant="outlined" onClick={() => sugerirRespuesta.mutate()} disabled={sugerirRespuesta.isPending}>
                  Sugerir respuesta
                </Button>
              </Stack>
            </Paper>
          )}

          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Información
            </Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 2 }}>
              <Dato etiqueta="Solicitante" valor={t.solicitante_nombre} />
              <Dato etiqueta="Cargo" valor={t.solicitante_cargo} />
              <Dato etiqueta="Área" valor={t.area?.nombre} />
              <Dato etiqueta="Cliente" valor={t.cliente?.nombre} />
              <Dato etiqueta="Correo" valor={t.correo} />
              <Dato etiqueta="Teléfono" valor={t.telefono} />
              <Dato etiqueta="Responsable" valor={t.responsable?.nombre ?? "Sin asignar"} />
              <Dato etiqueta="Canal" valor={t.canal} />
              <Dato etiqueta="Asignación" valor={fechaHora(t.fecha_asignacion)} />
              <Dato etiqueta="Cierre" valor={fechaHora(t.fecha_cierre)} />
            </Box>
          </Paper>
        </Stack>
      </Box>

      <TicketDialogos ticket={t} abierto={dialogo} estadoInicial={estadoInicial} onCerrar={() => setDialogo(null)} ejecutar={ejecutar} />
    </>
  );
}
