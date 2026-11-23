/** Piezas del detalle del ticket para visualizadores (34) y escalamiento a proveedores (33). */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Avatar, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, IconButton, MenuItem, Paper,
  TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from "@mui/material";
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import CloseIcon from "@mui/icons-material/Close";
import MailIcon from "@mui/icons-material/EmailOutlined";
import BellIcon from "@mui/icons-material/NotificationsOutlined";
import HandshakeIcon from "@mui/icons-material/Handshake";
import WarningIcon from "@mui/icons-material/WarningAmber";
import { Stack } from "../../components/Pila";
import { del, get, post, put } from "../../api/client";
import type { TicketDetalle as Ticket } from "../../api/types";
import type { AvisosCorreo, CasoProveedor, ProveedorParaTicket, Visualizador } from "../../api/ronda4c";
import { mensajeError, useAviso } from "../../components/Aviso";
import { fecha, fechaHora } from "../../utils/formato";

export const NOMBRE_AVISOS: Record<AvisosCorreo, string> = { TODO: "Todo", ESTADO: "Estado y cierre", NINGUNO: "Solo campana" };
const ORIGEN: Record<Visualizador["origen"], string> = { MANUAL: "agregado por", SEGUIR: "se unió con «Seguir»", CATEGORIA: "automático por categoría" };
const iniciales = (n: string) => n.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase();
const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit", timeZone: "America/Guayaquil" });

/** Chip de la cabecera: «3 visualizadores». */
export function ChipVisualizadores({ t }: { t: Ticket }) {
  if (!t.visualizadores?.length) return null;
  const n = t.visualizadores.length;
  return (
    <Tooltip title={t.visualizadores.map((v) => v.nombre).join(", ")}>
      <Chip size="small" variant="outlined" color="primary" icon={<VisibilityIcon />} label={`${n} visualizador${n === 1 ? "" : "es"}`} />
    </Tooltip>
  );
}

/** Chip «Visualizador» de un comentario. */
export function ChipComentarioVisualizador() {
  return <Chip size="small" icon={<VisibilityIcon />} label="Visualizador" sx={{ bgcolor: "#EEF2F8" }} />;
}

/** Aviso para quien sigue el ticket, o botón «Seguir» para quien ya lo ve. */
export function BannerSeguir({ t, onCambio }: { t: Ticket; onCambio: (n: Ticket) => void }) {
  const avisar = useAviso();
  const navigate = useNavigate();
  const yo = t.visualizadores?.find((v) => v.propio);
  const seguir = useMutation({
    mutationFn: () => post<Ticket>(`/tickets/${t.id}/seguir`, { avisos_correo: "ESTADO" }),
    onSuccess: (n) => { onCambio(n); avisar("Ahora sigue este ticket"); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const dejar = useMutation({
    mutationFn: () => del<{ visible: boolean; ticket?: Ticket }>(`/tickets/${t.id}/visualizadores/${yo!.usuario_id}`),
    onSuccess: (r) => {
      avisar("Dejó de seguir el ticket");
      if (r.visible && r.ticket) onCambio(r.ticket);
      else navigate("/tickets", { replace: true });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const avisos = useMutation({
    mutationFn: (v: AvisosCorreo) => put<Ticket>(`/tickets/${t.id}/visualizadores/${yo!.usuario_id}`, { avisos_correo: v }),
    onSuccess: onCambio,
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (t.es_visualizador && yo) {
    return (
      <Alert severity="info" icon={<VisibilityIcon />} sx={{ mb: 2, alignItems: "center" }}
        action={<Button color="inherit" size="small" onClick={() => dejar.mutate()} disabled={dejar.isPending}>Dejar de seguir</Button>}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
          <span>Usted sigue este ticket como visualizador: puede verlo y comentar, pero no lo atiende.</span>
          <TextField select size="small" label="Avisos por correo" value={yo.avisos_correo} sx={{ minWidth: 170 }}
            onChange={(e) => avisos.mutate(e.target.value as AvisosCorreo)}>
            {(Object.keys(NOMBRE_AVISOS) as AvisosCorreo[]).map((k) => <MenuItem key={k} value={k}>{NOMBRE_AVISOS[k]}</MenuItem>)}
          </TextField>
        </Stack>
      </Alert>
    );
  }
  if (!t.acciones.includes("seguir")) return null;
  return (
    <Button size="small" variant="outlined" startIcon={<VisibilityIcon />} onClick={() => seguir.mutate()} disabled={seguir.isPending}>
      Seguir
    </Button>
  );
}

/** Panel «Visualizadores» (encima de «Personas en copia»). */
export function PanelVisualizadores({ t, onCambio }: { t: Ticket; onCambio: (n: Ticket) => void }) {
  const avisar = useAviso();
  const gestiona = t.acciones.includes("visualizadores");
  const [q, setQ] = useState("");
  const [nuevoAviso, setNuevoAviso] = useState<AvisosCorreo>("ESTADO");
  const candidatos = useQuery({
    queryKey: ["visualizadores", t.id, "candidatos", q],
    queryFn: () => get<{ id: number; nombre: string; cargo: string | null; area: string | null }[]>(`/tickets/${t.id}/visualizadores/candidatos`, { q }),
    enabled: gestiona,
  });
  const agregar = useMutation({
    mutationFn: (usuario_id: number) => post<Ticket>(`/tickets/${t.id}/visualizadores`, { usuario_id, avisos_correo: nuevoAviso }),
    onSuccess: (n) => { onCambio(n); setQ(""); avisar("Visualizador agregado"); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const avisos = useMutation({
    mutationFn: ({ id, v }: { id: number; v: AvisosCorreo }) => put<Ticket>(`/tickets/${t.id}/visualizadores/${id}`, { avisos_correo: v }),
    onSuccess: onCambio,
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const quitar = useMutation({
    mutationFn: (id: number) => del<{ visible: boolean; ticket?: Ticket }>(`/tickets/${t.id}/visualizadores/${id}`),
    onSuccess: (r) => { if (r.ticket) onCambio(r.ticket); avisar("Visualizador quitado"); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (!gestiona && !t.visualizadores?.length) return null;
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <VisibilityIcon color="primary" />
        <Typography variant="h6">Visualizadores</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Personas de Aducorp que siguen el ticket desde la Mesa. Lo ven y pueden comentar, pero no lo atienden.
      </Typography>
      {t.visualizadores.length === 0 && <Typography variant="body2" color="text.secondary">Nadie sigue este ticket todavía.</Typography>}
      <Stack spacing={1.2}>
        {t.visualizadores.map((v) => (
          <Stack key={v.usuario_id} direction="row" spacing={1.2} alignItems="center">
            <Avatar sx={{ width: 34, height: 34, fontSize: 13, bgcolor: v.origen === "CATEGORIA" ? "#5E35B1" : "primary.main" }}>{iniciales(v.nombre)}</Avatar>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{v.nombre}</Typography>
              <Typography variant="caption" color="text.secondary">
                {[v.cargo ?? v.area, v.origen === "MANUAL" ? `agregado por ${v.agregado_por ?? "—"}` : ORIGEN[v.origen]].filter(Boolean).join(" · ")}
              </Typography>
            </Box>
            {v.editable ? (
              <TextField select size="small" value={v.avisos_correo} sx={{ minWidth: 130, "& .MuiSelect-select": { py: 0.5, fontSize: 13 } }}
                onChange={(e) => avisos.mutate({ id: v.usuario_id, v: e.target.value as AvisosCorreo })} aria-label={`Avisos de ${v.nombre}`}>
                {(Object.keys(NOMBRE_AVISOS) as AvisosCorreo[]).map((k) => <MenuItem key={k} value={k}>{NOMBRE_AVISOS[k]}</MenuItem>)}
              </TextField>
            ) : (
              <Chip size="small" variant="outlined" icon={v.avisos_correo === "NINGUNO" ? <BellIcon /> : <MailIcon />} label={NOMBRE_AVISOS[v.avisos_correo]} />
            )}
            {v.editable && (
              <IconButton size="small" aria-label={`Quitar a ${v.nombre}`} onClick={() => quitar.mutate(v.usuario_id)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            )}
          </Stack>
        ))}
      </Stack>
      {gestiona && (
        <>
          <Autocomplete
            sx={{ mt: 2 }}
            size="small"
            options={candidatos.data ?? []}
            filterOptions={(x) => x}
            getOptionLabel={(o) => `${o.nombre}${o.area ? ` · ${o.area}` : o.cargo ? ` · ${o.cargo}` : ""}`}
            inputValue={q}
            onInputChange={(_, v, r) => { if (r !== "reset") setQ(v); }}
            value={null}
            onChange={(_, o) => o && agregar.mutate(o.id)}
            noOptionsText="Sin coincidencias"
            loading={candidatos.isFetching}
            renderInput={(p) => <TextField {...p} label="Agregar visualizador" placeholder="Nombre, correo o cargo" />}
          />
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1.2, flexWrap: "wrap", gap: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ flex: 1, minWidth: 140 }}>Avisos por correo para el nuevo visualizador:</Typography>
            <ToggleButtonGroup size="small" exclusive value={nuevoAviso} onChange={(_, v) => v && setNuevoAviso(v)}>
              <ToggleButton value="TODO">Todo</ToggleButton>
              <ToggleButton value="ESTADO">Estado y cierre</ToggleButton>
              <ToggleButton value="NINGUNO">Ninguno</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
        </>
      )}
    </Paper>
  );
}

// ------------------------------------------------------------------ 33 proveedores
/** Banner «En manos de X, caso Y» mientras el proveedor trabaja. */
export function BannerProveedor({ t, onCambio }: { t: Ticket; onCambio: () => void }) {
  const avisar = useAviso();
  const [abierto, setAbierto] = useState(false);
  const [solucion, setSolucion] = useState("");
  const c = t.proveedor_caso;
  const resolver = useMutation({
    mutationFn: () => post<CasoProveedor>(`/proveedores/casos/${c!.id}/resolver`, { solucion: solucion.trim() || null }),
    onSuccess: (r) => {
      setAbierto(false);
      setSolucion("");
      avisar(r.cumplido === false ? "Caso cerrado fuera del plazo del contrato" : "Caso cerrado dentro del plazo");
      onCambio();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (!c) return null;
  const gestiona = t.acciones.includes("nota_interna");
  return (
    <>
      <Alert severity={c.vencido ? "error" : "warning"} icon={<HandshakeIcon />} sx={{ mb: 2, alignItems: "center" }}
        action={gestiona ? <Button color="inherit" size="small" variant="outlined" onClick={() => setAbierto(true)}>Proveedor dio solución</Button> : undefined}>
        <b>En manos de {c.proveedor}{c.numero_caso ? `, caso ${c.numero_caso}` : ""}.</b>{" "}
        {gestiona
          ? <>Reportado {fechaHora(c.fecha_reporte)} · plazo {c.plazo} · {c.vencido ? "el plazo del contrato ya venció" : `debe resolver antes de ${fechaHora(c.vence)}`}. Nuestro SLA está en pausa.</>
          : <>El proveedor está trabajando en la solución; le avisaremos cuando avance.</>}
      </Alert>
      <Dialog open={abierto} onClose={() => setAbierto(false)} fullWidth maxWidth="sm">
        <DialogTitle>El proveedor dio solución</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Se cierra el caso de {c.proveedor}, se mide si cumplió el plazo del contrato y el ticket vuelve a «En proceso» con nuestro SLA corriendo.
          </Typography>
          <TextField label="Qué hizo el proveedor (opcional)" multiline minRows={3} fullWidth value={solucion}
            onChange={(e) => setSolucion(e.target.value)} slotProps={{ htmlInput: { maxLength: 1000 } }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => resolver.mutate()} disabled={resolver.isPending}>Registrar solución</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

/** Diálogo «Escalar a proveedor». */
export function DialogoEscalarProveedor({ t, abierto, onCerrar, onListo }: { t: Ticket; abierto: boolean; onCerrar: () => void; onListo: () => void }) {
  const avisar = useAviso();
  const datos = useQuery({
    queryKey: ["proveedores", "ticket", t.id],
    queryFn: () => get<{ proveedores: ProveedorParaTicket[]; mes: string }>(`/proveedores/ticket/${t.id}`),
    enabled: abierto,
  });
  const [provId, setProvId] = useState<number | "">("");
  const [caso, setCaso] = useState("");
  const [reporte, setReporte] = useState("");
  const [medio, setMedio] = useState("");
  const [contacto, setContacto] = useState("");
  const lista = useMemo(() => datos.data?.proveedores ?? [], [datos.data]);
  const elegido = lista.find((p) => p.id === provId) ?? (provId === "" ? lista.find((p) => p.sugerido) : undefined);
  const medios = elegido?.medios ?? [];
  const escalar = useMutation({
    mutationFn: (enviar_correo: boolean) => post<CasoProveedor>(`/proveedores/ticket/${t.id}/escalar`, {
      proveedor_id: elegido!.id, numero_caso: caso.trim() || null, reporte: reporte.trim(),
      medio: (medio || medios[0]) ?? null, contacto: (contacto || elegido?.contacto) ?? null, enviar_correo,
    }),
    onSuccess: (c, enviar) => {
      avisar(`Ticket escalado a ${c.proveedor}${enviar ? " y correo enviado" : ""}`);
      setCaso(""); setReporte(""); setMedio(""); setContacto(""); setProvId("");
      onListo();
      onCerrar();
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const valido = !!elegido && reporte.trim().length >= 5;
  return (
    <Dialog open={abierto} onClose={onCerrar} fullWidth maxWidth="md">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <HandshakeIcon color="primary" /> Escalar a proveedor
      </DialogTitle>
      <DialogContent dividers>
        {datos.isSuccess && lista.length === 0 && (
          <Alert severity="info">No hay proveedores registrados. Un supervisor puede registrarlos en «Proveedores y contratos».</Alert>
        )}
        {lista.length > 0 && (
          <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "minmax(0,1.3fr) minmax(0,1fr)" } }}>
            <Stack spacing={2}>
              <TextField select label="Proveedor" value={elegido?.id ?? ""} onChange={(e) => { setProvId(Number(e.target.value)); setMedio(""); setContacto(""); }}>
                {lista.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.nombre} · {p.servicio}{p.sugerido ? "  (sugerido)" : ""}
                  </MenuItem>
                ))}
              </TextField>
              <TextField label="N.º de caso del proveedor" value={caso} onChange={(e) => setCaso(e.target.value)}
                helperText="Lo da el proveedor al reportar por teléfono o portal." slotProps={{ htmlInput: { maxLength: 60 } }} />
              <TextField label="Qué se reportó" multiline minRows={3} value={reporte} onChange={(e) => setReporte(e.target.value)}
                slotProps={{ htmlInput: { maxLength: 2000 } }} />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Medio" value={medio || medios[0] || ""} onChange={(e) => setMedio(e.target.value)} sx={{ flex: 1 }}>
                  {medios.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
                </TextField>
                <TextField label="Contacto" value={contacto || elegido?.contacto || ""} onChange={(e) => setContacto(e.target.value)} sx={{ flex: 1 }}
                  slotProps={{ htmlInput: { maxLength: 150 } }} />
              </Stack>
            </Stack>
            {elegido && (
              <Stack spacing={2}>
                <Paper variant="outlined" sx={{ p: 2, bgcolor: "#F7F9FC" }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Lo que dice el contrato</Typography>
                  <Box sx={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 2, rowGap: 0.75, fontSize: 14 }}>
                    <Typography variant="body2" color="text.secondary">Contrato</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {elegido.contrato_numero ?? "—"}{elegido.contrato_vence ? ` · vence ${fecha(elegido.contrato_vence)}` : ""}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Atención</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{elegido.atencion_24x7 ? "24/7" : "Horario laboral"}</Typography>
                    <Typography variant="body2" color="text.secondary">Plazo de solución</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{elegido.plazo}</Typography>
                    <Typography variant="body2" color="text.secondary">Multa</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{elegido.multa_texto ?? "Sin multa pactada"}</Typography>
                  </Box>
                </Paper>
                <Alert severity="info">
                  Debe resolver <b>antes de {fechaHora(elegido.vence_caso)}</b> ({hora(elegido.vence_caso)}). Le avisaremos 30 min antes si sigue abierto.
                </Alert>
                {elegido.caida_mes > 1 && (
                  <Alert severity="warning" icon={<WarningIcon />}>
                    Es la <b>{elegido.caida_mes}.ª caída</b> de {elegido.nombre} en {datos.data?.mes}.
                  </Alert>
                )}
              </Stack>
            )}
          </Box>
        )}
        {elegido && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="body2">
              El ticket pasa a <b>Escalado</b>. Nuestro SLA se pausa mientras el proveedor trabaja y se mide aparte el SLA del proveedor. El solicitante
              ve «En manos de {elegido.nombre}{caso.trim() ? `, caso ${caso.trim()}` : ""}».
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions sx={{ flexWrap: "wrap", gap: 1 }}>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Tooltip title={elegido && !elegido.correo ? "El proveedor no tiene correo registrado" : ""}>
          <span>
            <Button variant="outlined" startIcon={<MailIcon />} disabled={!valido || !elegido?.correo || escalar.isPending} onClick={() => escalar.mutate(true)}>
              Escalar y enviar correo al proveedor
            </Button>
          </span>
        </Tooltip>
        <Button variant="contained" disabled={!valido || escalar.isPending} onClick={() => escalar.mutate(false)}>Escalar</Button>
      </DialogActions>
    </Dialog>
  );
}

/** Lista corta de casos anteriores con proveedores (pestaña de escalamientos). */
export function CasosProveedorTicket({ casos }: { casos: CasoProveedor[] }) {
  if (!casos?.length) return null;
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Casos con proveedores</Typography>
      <Stack spacing={1}>
        {casos.map((c) => (
          <Paper key={c.id} variant="outlined" sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: "wrap", gap: 0.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{c.proveedor}{c.numero_caso ? ` · caso ${c.numero_caso}` : ""}</Typography>
              <Chip size="small" label={c.estado === "ABIERTO" ? "Abierto" : "Resuelto"} color={c.estado === "ABIERTO" ? "warning" : "default"} />
              {c.cumplido === true && <Chip size="small" color="success" label="En plazo" />}
              {c.cumplido === false && <Chip size="small" color="error" label={`Fuera de plazo${c.multa ? ` · multa $${c.multa.toFixed(2)}` : ""}`} />}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Reportado {fechaHora(c.fecha_reporte)} · plazo {c.plazo}{c.fecha_solucion ? ` · solucionado ${fechaHora(c.fecha_solucion)}` : ""}
            </Typography>
            {c.solucion && <Typography variant="body2" sx={{ mt: 0.5 }}>{c.solucion}</Typography>}
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}
