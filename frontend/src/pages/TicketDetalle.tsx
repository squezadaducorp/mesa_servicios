import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Chip, Divider, FormControlLabel, IconButton, Link, List, ListItem, ListItemIcon, ListItemText, Menu, MenuItem,
  Paper, Rating, Stack, Switch, Tab, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import EditIcon from "@mui/icons-material/Edit";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DownloadIcon from "@mui/icons-material/Download";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import LockIcon from "@mui/icons-material/Lock";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import SendIcon from "@mui/icons-material/Send";
import PauseCircleIcon from "@mui/icons-material/PauseCircle";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import BoltIcon from "@mui/icons-material/Bolt";
import GroupIcon from "@mui/icons-material/SupervisorAccount";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import EventRepeatIcon from "@mui/icons-material/EventRepeat";
import AddPhotoIcon from "@mui/icons-material/AddPhotoAlternateOutlined";
import { api, del, descargar, get, patch, post, put } from "../api/client";
import type { RespuestaParaTicket, Riesgo, TextoIa, TicketDetalle as Ticket } from "../api/types";
import MenuRespuestas from "../components/MenuRespuestas";
import { IconoEquipo } from "./admin/Inventario";
import { mensajeError, useAviso } from "../components/Aviso";
import CampoCorreos from "../components/CampoCorreos";
import { CumplimientoChip, EstadoChip, NOMBRES_NOTA, PrioridadChip, SlaBarra, colorSla } from "../components/Chips";
import { Cargando, ErrorCarga, Vacio } from "../components/Comunes";
import { duracion, fechaHora, tamanoArchivo, tiempoRelativo } from "../utils/formato";
import TicketDialogos, { estadosDestino, type Dialogo } from "./TicketDialogos";
import { AlertasTercera, PanelTercera } from "./tercera/TicketTercera";
import PanelTareas from "./cuarta/PanelTareas";
import TicketProblemas from "./ronda4b/TicketProblemas";
import TiempoTrabajado from "./ronda4c/TiempoTrabajado";
import { ChipClasificacion } from "../components/ClasificacionTicket";
import {
  BannerProveedor, BannerSeguir, CasosProveedorTicket, ChipComentarioVisualizador, ChipVisualizadores, DialogoEscalarProveedor, PanelVisualizadores,
} from "./ronda4c/TicketRonda4c";
import { AdjuntosDeComentario, ArchivosPorEnviar, imagenesDe, nombrarCaptura } from "../components/CapturasComentario";

/** Encuesta de satisfacción: el solicitante califica (y así cierra) un ticket resuelto; luego se muestra la nota. */
function TarjetaEncuesta({ t, onListo }: { t: Ticket; onListo: (nuevo: Ticket) => void }) {
  const avisar = useAviso();
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState("");
  const enviar = useMutation({
    mutationFn: () => post<Ticket>(`/tickets/${t.id}/encuesta`, { calificacion: nota, comentario: comentario.trim() || null }),
    onSuccess: (nuevo) => {
      avisar("¡Gracias por calificar la atención!", "success");
      onListo(nuevo);
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (t.encuesta) {
    return (
      <Paper sx={{ p: 2, mb: 2, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography variant="subtitle2">Calificación del solicitante</Typography>
        <Rating value={t.encuesta.calificacion} readOnly />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {NOMBRES_NOTA[t.encuesta.calificacion]}
        </Typography>
        {t.encuesta.comentario && (
          <Typography variant="body2" sx={{ color: "text.secondary", fontStyle: "italic", flexBasis: "100%" }}>
            «{t.encuesta.comentario}»
          </Typography>
        )}
      </Paper>
    );
  }
  if (!t.acciones.includes("calificar")) return null;
  return (
    <Paper sx={{ p: { xs: 2, md: 3 }, mb: 2, border: "1px solid #F9A82555", bgcolor: "#FFFBF0" }}>
      <Typography variant="h6">¿Cómo fue la atención?</Typography>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>
        Califique de 1 a 5 estrellas. Al calificar, el ticket se cierra; si el problema sigue, use «Reabrir».
      </Typography>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", mb: 1.5 }}>
        <Rating value={nota} onChange={(_, v) => setNota(v)} size="large" sx={{ fontSize: 40 }} />
        {nota && <Typography sx={{ fontWeight: 600 }}>{NOMBRES_NOTA[nota]}</Typography>}
      </Stack>
      <TextField
        label="Comentario (opcional)"
        multiline
        minRows={2}
        fullWidth
        value={comentario}
        onChange={(e) => setComentario(e.target.value)}
        slotProps={{ htmlInput: { maxLength: 1000 } }}
      />
      <Button variant="contained" sx={{ mt: 1.5 }} disabled={!nota || enviar.isPending} onClick={() => enviar.mutate()}>
        Enviar calificación
      </Button>
    </Paper>
  );
}

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
  ENCUESTA: "Encuesta de satisfacción",
  COPIAS: "Actualizó las personas en copia",
  VISUALIZADOR: "Visualizadores",
  ESCALAMIENTO_PROVEEDOR: "Escaló a proveedor",
};

const ORIGEN_COPIA: Record<string, string> = {
  MANUAL: "Agregado manualmente",
  CATEGORIA: "Copia automática de la categoría",
  CLIENTE: "Copia automática del cliente",
  CORREO: "Venía en copia del correo original",
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
  const [escalarProv, setEscalarProv] = useState(false);
  const [texto, setTexto] = useState("");
  const [interno, setInterno] = useState(false);
  // Capturas de pantalla (Ctrl+V, arrastrar o elegir) y archivos que van con el comentario
  const [archivos, setArchivos] = useState<File[]>([]);
  const sumarArchivos = (nuevos: File[], pegados = false) =>
    setArchivos((xs) => [...xs, ...(pegados ? nuevos.map((f, i) => nombrarCaptura(f, xs.length + i)) : nuevos)].slice(0, 10));
  // null = usar las personas en copia del ticket; una lista = editada solo para este envío
  const [copiaA, setCopiaA] = useState<string[] | null>(null);
  const [editandoCopias, setEditandoCopias] = useState<string[] | null>(null);
  const [resumen, setResumen] = useState<TextoIa | null>(null);
  // Respuestas rápidas: menú ⚡ o «/» en la respuesta
  const [menuResp, setMenuResp] = useState<HTMLElement | null>(null);
  const [filtroResp, setFiltroResp] = useState("");
  const [barraEn, setBarraEn] = useState<number | null>(null);
  const [usada, setUsada] = useState<RespuestaParaTicket | null>(null);
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
    mutationFn: () => {
      const datos = {
        texto,
        es_interno: interno,
        respuesta_rapida_id: usada?.id ?? null,
        ...(!interno && t?.acciones.includes("copias") ? { copia_a: copiaA ?? t.copias.map((c) => c.correo) } : {}),
      };
      if (!archivos.length) return post<Ticket>(`/tickets/${id}/comentarios`, datos);
      const form = new FormData();
      form.append("datos", JSON.stringify(datos));
      archivos.forEach((f) => form.append("archivos", f, f.name));
      return api<Ticket>("POST", `/tickets/${id}/comentarios/con-archivos`, { form });
    },
    onSuccess: async (n) => {
      actualizar(n);
      const destino = usada?.estado_destino;
      setTexto("");
      setArchivos([]);
      setInterno(false);
      setCopiaA(null);
      setUsada(null);
      // La respuesta rápida puede además cambiar el estado (p. ej. a Pendiente Cliente)
      if (destino && destino !== n.estado && n.acciones.includes("cambiar_estado") && estadosDestino(n.estado).includes(destino)) {
        try {
          actualizar(await post<Ticket>(`/tickets/${id}/estado`, { estado: destino, comentario: null }));
          avisar(`El ticket pasó a ${destino === "PENDIENTE_CLIENTE" ? "Pendiente Cliente" : destino === "EN_PROCESO" ? "En Proceso" : "Resuelto"}`);
        } catch (e) {
          avisar(mensajeError(e), "error");
        }
      }
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const guardarCopias = useMutation({
    mutationFn: (correos: string[]) => put<Ticket>(`/tickets/${id}/copias`, { correos }),
    onSuccess: (n) => {
      actualizar(n);
      setEditandoCopias(null);
      setCopiaA(null);
      avisar("Personas en copia actualizadas");
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
  // Con un caso abierto en el proveedor, la salida es «Proveedor dio solución» (no «Iniciar atención»)
  const siguiente = t.proveedor_caso ? undefined : destinos.includes("EN_PROCESO") && t.estado !== "PENDIENTE_CLIENTE" ? "EN_PROCESO" : destinos.includes("RESUELTO") ? "RESUELTO" : undefined;
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

      {t.solo_lectura_creador && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Usted registró este ticket en nombre de {t.solicitante_nombre}. Puede seguirlo aquí en solo lectura; las respuestas del equipo le llegan a{" "}
          {t.solicitante_nombre.split(" ")[0]}.
        </Alert>
      )}

      {t.solo_lectura_participante && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Usted atendió este ticket antes. Hoy está a cargo de {t.responsable?.nombre ?? "otro responsable"} ({t.categoria.nombre}), por eso
          puede consultarlo pero no modificarlo.
        </Alert>
      )}

      <AlertasTercera t={t} onCambio={() => q.refetch()} />
      <BannerProveedor t={t} onCambio={() => { q.refetch(); qc.invalidateQueries({ queryKey: ["tickets"] }); }} />
      {t.es_visualizador && <BannerSeguir t={t} onCambio={actualizar} />}
      {a.has("nota_interna") && <TicketProblemas ticketId={t.id} onCambio={() => q.refetch()} />}

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
              <ChipVisualizadores t={t} />
              <ChipClasificacion t={t} />
              {t.recurrente_id && (
                <Chip size="small" icon={<EventRepeatIcon />} label="Recurrente" sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", "& .MuiChip-icon": { color: "#8A5A00" } }} />
              )}
            </Stack>
            <Typography variant="h5" sx={{ wordBreak: "break-word" }}>
              {t.asunto}
            </Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
              {t.categoria.nombre} › {t.subcategoria.nombre} · creado {fechaHora(t.fecha_creacion)} por {t.creado_por?.nombre ?? t.solicitante_nombre}
            </Typography>
            {t.creado_por && (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", bgcolor: "#FFF8E6", border: "1px solid #F2C14E", borderRadius: 2, p: 1.5, mt: 1.5 }}>
                <GroupIcon sx={{ color: "#8A5A00" }} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2"><b>Solicitante:</b> {t.solicitante_nombre}{t.area ? ` (${t.area.nombre})` : ""}</Typography>
                  <Typography variant="body2"><b>Creado por:</b> {t.creado_por.nombre}, en su nombre · {fechaHora(t.fecha_creacion)}</Typography>
                  {t.en_nombre_motivo && <Typography variant="caption" color="text.secondary">Motivo: {t.en_nombre_motivo}</Typography>}
                </Box>
                <Chip size="small" icon={<MailOutlineIcon />} label={`${t.solicitante_nombre.split(" ")[0]} fue avisado`} color="success" variant="outlined" />
              </Stack>
            )}
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
            {!t.es_visualizador && a.has("seguir") && <BannerSeguir t={t} onCambio={actualizar} />}
            {(a.has("editar") || a.has("escalar") || a.has("escalar_proveedor") || a.has("excepcion_sla") || a.has("eliminar") || a.has("cerrar")) && (
              <IconButton onClick={(e) => setMenu(e.currentTarget)} aria-label="Más acciones">
                <MoreVertIcon />
              </IconButton>
            )}
            <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
              {a.has("editar") && <MenuItem onClick={() => abrir("editar")}>Editar</MenuItem>}
              {a.has("escalar") && <MenuItem onClick={() => abrir("escalar")}>Escalar</MenuItem>}
              {a.has("escalar_proveedor") && <MenuItem onClick={() => { setMenu(null); setEscalarProv(true); }}>Escalar a proveedor</MenuItem>}
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

      <TarjetaEncuesta t={t} onListo={actualizar} />

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
                          {c.de_visualizador && <ChipComentarioVisualizador />}
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
                        <AdjuntosDeComentario ticketId={t.id} adjuntos={c.adjuntos} />
                        {c.copia_a?.length > 0 && (
                          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.5, wordBreak: "break-word" }}>
                            Copia a: {c.copia_a.join(", ")}
                          </Typography>
                        )}
                      </Box>
                    </Stack>
                  ))}
                  {a.has("comentar") && (
                    <Box
                      onDragOver={(e) => { if (a.has("adjuntar") && e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
                      onDrop={(e) => {
                        if (!a.has("adjuntar") || !e.dataTransfer.files.length) return;
                        e.preventDefault();
                        sumarArchivos(Array.from(e.dataTransfer.files));
                      }}
                    >
                      <Divider sx={{ mb: 2 }} />
                      {t.estado === "PENDIENTE_CLIENTE" && !a.has("nota_interna") && (
                        <Alert severity="info" sx={{ mb: 1.5 }}>
                          El equipo espera su respuesta. Al comentar, el ticket vuelve a atención y el SLA se reanuda.
                        </Alert>
                      )}
                      <TextField
                        placeholder={interno ? "Nota interna (no la ve el solicitante)" : a.has("nota_interna") ? "Escriba un comentario o «/» para una respuesta rápida" : "Escriba un comentario"}
                        value={texto}
                        onChange={(e) => {
                          const v = e.target.value;
                          setTexto(v);
                          if (!v.trim()) setUsada(null);
                          // «/» al inicio de una línea o tras un espacio abre las respuestas rápidas
                          if (a.has("nota_interna") && v.length === texto.length + 1 && /(^|\s)\/$/.test(v)) {
                            setBarraEn(v.length - 1);
                            setFiltroResp("/");
                            setMenuResp(e.target);
                          }
                        }}
                        onPaste={(e) => {
                          const imgs = a.has("adjuntar") ? imagenesDe(e.clipboardData) : [];
                          if (imgs.length) {
                            e.preventDefault();
                            sumarArchivos(imgs, true);
                          }
                        }}
                        helperText={a.has("adjuntar") ? "Para agregar una captura de pantalla, péguela aquí con Ctrl+V o arrástrela." : undefined}
                        multiline
                        minRows={3}
                        fullWidth
                      />
                      <ArchivosPorEnviar archivos={archivos} onQuitar={(i) => setArchivos((xs) => xs.filter((_, j) => j !== i))} />
                      {a.has("copias") && !interno && (
                        <Box sx={{ mt: 1.5 }}>
                          <CampoCorreos
                            etiqueta="Enviar copia a (opcional)"
                            valor={copiaA ?? t.copias.map((c) => c.correo)}
                            onCambio={setCopiaA}
                            sugerencias={t.copias.map((c) => c.correo)}
                            ayuda={
                              copiaA === null
                                ? "Viene con las personas en copia del ticket. Puede quitar o agregar correos solo para este envío."
                                : "Cambios solo para este envío; la lista del ticket no cambia."
                            }
                          />
                        </Box>
                      )}
                      <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                        {a.has("nota_interna") && (
                          <Button startIcon={<BoltIcon />} variant="outlined" color="warning"
                            onClick={(e) => { setBarraEn(null); setFiltroResp(""); setMenuResp(e.currentTarget); }}>
                            Respuestas rápidas
                          </Button>
                        )}
                        {a.has("nota_interna") && (
                          <FormControlLabel control={<Switch checked={interno} onChange={(e) => setInterno(e.target.checked)} />} label="Nota interna" />
                        )}
                        {usada?.estado_destino && (
                          <Chip size="small" color="warning" variant="outlined" onDelete={() => setUsada({ ...usada, estado_destino: null })}
                            label={`Al enviar pasa a ${usada.estado_destino === "PENDIENTE_CLIENTE" ? "Pendiente Cliente" : usada.estado_destino === "EN_PROCESO" ? "En Proceso" : "Resuelto"}`} />
                        )}
                        {puedeIa && (
                          <Button startIcon={<AutoAwesomeIcon />} onClick={() => sugerirRespuesta.mutate()} disabled={sugerirRespuesta.isPending}>
                            Sugerir respuesta
                          </Button>
                        )}
                        {a.has("adjuntar") && (
                          <Button component="label" startIcon={<AddPhotoIcon />} disabled={archivos.length >= 10}>
                            Captura o archivo
                            <input
                              hidden
                              type="file"
                              multiple
                              accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.xml,.zip,.msg,.eml"
                              onChange={(e) => {
                                const f = Array.from(e.target.files ?? []);
                                e.target.value = "";
                                if (f.length) sumarArchivos(f);
                              }}
                            />
                          </Button>
                        )}
                        <Box sx={{ flex: 1 }} />
                        <Button variant="contained" endIcon={<SendIcon />} disabled={(!texto.trim() && !archivos.length) || comentar.isPending} onClick={() => comentar.mutate()}>
                          {comentar.isPending && archivos.length ? "Enviando…" : "Enviar"}
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
                  {t.escalamientos.length === 0 && !t.proveedor_casos?.length && <Vacio texto="El ticket no ha sido escalado" />}
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
                  <CasosProveedorTicket casos={t.proveedor_casos} />
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

          {a.has("nota_interna") && <TiempoTrabajado tipo="ticket" id={t.id} />}

          {t.servicio && <PanelTareas ticketId={t.id} s={t.servicio} onCambio={() => q.refetch()} />}

          <PanelTercera t={t} onCambio={() => q.refetch()} />

          {t.equipo && (
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>Equipo</Typography>
              <Stack direction="row" spacing={1.2} sx={{ alignItems: "center" }}>
                <IconoEquipo tipo={t.equipo.tipo} />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main" }}>{t.equipo.codigo}</Typography>
                  <Typography variant="caption" color="text.secondary">{t.equipo.marca_modelo}</Typography>
                </Box>
              </Stack>
              {t.equipo.aviso && <Alert severity="warning" sx={{ mt: 1.5 }}>{t.equipo.aviso}</Alert>}
            </Paper>
          )}

          {!!t.kb_vistos?.length && (
            <Paper sx={{ p: 2.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
                <MenuBookIcon color="primary" />
                <Typography variant="h6">Ya revisó estos artículos</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary">El solicitante los leyó antes de crear el ticket y no le sirvieron.</Typography>
              {t.kb_vistos.map((k) => (
                <Typography key={k.id} variant="body2" sx={{ mt: 0.8 }}>
                  • <Link component={RouterLink} to={`/conocimiento?articulo=${k.id}`}>{k.nombre}</Link>
                </Typography>
              ))}
            </Paper>
          )}

          <PanelVisualizadores t={t} onCambio={actualizar} />

          {(a.has("copias") || t.copias.length > 0) && (
            <Paper sx={{ p: 2.5 }}>
              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                <Typography variant="h6">Personas en copia</Typography>
                {a.has("copias") && editandoCopias === null && (
                  <Button size="small" startIcon={<EditIcon />} onClick={() => setEditandoCopias(t.copias.map((c) => c.correo))}>
                    Editar
                  </Button>
                )}
              </Stack>
              {editandoCopias === null ? (
                <>
                  {t.copias.length === 0 ? (
                    <Typography variant="body2" sx={{ color: "text.secondary" }}>
                      Nadie en copia. Agregue correos para que también reciban las respuestas y el cierre del ticket.
                    </Typography>
                  ) : (
                    <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                      {t.copias.map((c) => (
                        <Tooltip key={c.correo} title={ORIGEN_COPIA[c.origen] ?? c.origen}>
                          <Chip size="small" variant="outlined" label={c.correo} />
                        </Tooltip>
                      ))}
                    </Stack>
                  )}
                </>
              ) : (
                <>
                  <CampoCorreos
                    etiqueta="Correos en copia"
                    valor={editandoCopias}
                    onCambio={setEditandoCopias}
                    ayuda="Reciben por correo las respuestas al solicitante y el cierre. No ven las notas internas."
                  />
                  <Stack direction="row" spacing={1} sx={{ mt: 1.5, justifyContent: "flex-end" }}>
                    <Button size="small" onClick={() => setEditandoCopias(null)}>
                      Cancelar
                    </Button>
                    <Button size="small" variant="contained" disabled={guardarCopias.isPending} onClick={() => guardarCopias.mutate(editandoCopias)}>
                      Guardar
                    </Button>
                  </Stack>
                </>
              )}
            </Paper>
          )}

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

      <MenuRespuestas
        ticketId={t.id}
        categoria={t.subcategoria.nombre}
        ancla={menuResp}
        filtroInicial={filtroResp}
        onCerrar={() => setMenuResp(null)}
        onElegir={(r) => {
          setTexto((x) => (barraEn !== null && x[barraEn] === "/" ? x.slice(0, barraEn) + r.texto + x.slice(barraEn + 1) : x.trim() ? `${x.trimEnd()}\n${r.texto}` : r.texto));
          setUsada(r);
          setInterno(false);
          setMenuResp(null);
        }}
      />
      {a.has("escalar_proveedor") && (
        <DialogoEscalarProveedor t={t} abierto={escalarProv} onCerrar={() => setEscalarProv(false)}
          onListo={() => { q.refetch(); qc.invalidateQueries({ queryKey: ["tickets"] }); }} />
      )}
      <TicketDialogos ticket={t} abierto={dialogo} estadoInicial={estadoInicial} onCerrar={() => setDialogo(null)} ejecutar={ejecutar} />
    </>
  );
}
