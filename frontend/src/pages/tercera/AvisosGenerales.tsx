import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Grid, Link, ListItemText, MenuItem, Paper, Step, StepLabel, Stepper, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, ToggleButton, ToggleButtonGroup, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import CampaignIcon from "@mui/icons-material/Campaign";
import CheckIcon from "@mui/icons-material/CheckCircle";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import { descargar, get, post } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { AvisoGeneral, AvisosAdmin, EstadoAviso } from "../../api/tercera";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { fecha, fechaHora, tiempoRelativo } from "../../utils/formato";
import { marca } from "../../theme";

const PASOS: [EstadoAviso, string][] = [["INVESTIGANDO", "Investigando"], ["IDENTIFICADO", "Causa identificada"], ["MONITOREANDO", "Monitoreando"], ["RESUELTO", "Resuelto"]];
const SISTEMAS = ["ECUAPASS", "Internet", "Correo", "Servidor de archivos", "Sistema contable", "Telefonía"];

function horas(min: number) {
  const h = Math.floor(min / 60);
  return h ? `${h} h ${min % 60 ? `${min % 60} min` : ""}`.trim() : `${min} min`;
}

function NuevoAviso({ onCerrar }: { onCerrar: (creado?: boolean) => void }) {
  const cat = useCatalogos();
  const avisar = useAviso();
  const [f, setF] = useState({ titulo: "", mensaje: "", sistema: "ECUAPASS", palabras_clave: "", area_ids: [] as number[], mostrar_publico: false, ticket_maestro: "", proxima_novedad: "" });
  const [error, setError] = useState<string | null>(null);
  const crear = useMutation({
    mutationFn: () =>
      post<AvisoGeneral>("/avisos", {
        titulo: f.titulo, mensaje: f.mensaje, sistema: f.sistema, palabras_clave: f.palabras_clave || null, area_ids: f.area_ids,
        mostrar_publico: f.mostrar_publico, ticket_maestro: f.ticket_maestro.trim() || null, proxima_novedad: f.proxima_novedad || null,
      }),
    onSuccess: (a) => {
      avisar(`${a.codigo} publicado`);
      onCerrar(true);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="sm" fullWidth>
      <DialogTitle>Publicar aviso general</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="Título" placeholder="ECUAPASS no responde desde las 09:40" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} />
          <TextField label="Mensaje para las personas" multiline minRows={2} value={f.mensaje} onChange={(e) => setF({ ...f, mensaje: e.target.value })}
            placeholder="Ya lo sabemos y estamos en contacto con la mesa de ayuda del SENAE. No hace falta crear otro ticket." />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Sistema afectado" sx={{ flex: 1 }} value={SISTEMAS.includes(f.sistema) ? f.sistema : "__otro"}
              onChange={(e) => setF({ ...f, sistema: e.target.value === "__otro" ? "" : e.target.value })}>
              {SISTEMAS.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
              <MenuItem value="__otro">Otro…</MenuItem>
            </TextField>
            {!SISTEMAS.includes(f.sistema) && <TextField label="¿Cuál?" sx={{ flex: 1 }} value={f.sistema} onChange={(e) => setF({ ...f, sistema: e.target.value })} />}
          </Stack>
          <TextField label="Palabras clave (separadas por coma)" value={f.palabras_clave} onChange={(e) => setF({ ...f, palabras_clave: e.target.value })}
            helperText="Si alguien escribe estas palabras al crear un ticket, se le muestra el aviso. El nombre del sistema ya cuenta." />
          <TextField select label="A quién se muestra" slotProps={{ select: { multiple: true, renderValue: (v: unknown) => ((v as number[]).length ? (v as number[]).map((id) => cat.data?.areas.find((a) => a.id === id)?.nombre).join(", ") : "Todas las áreas") } }}
            value={f.area_ids} onChange={(e) => setF({ ...f, area_ids: e.target.value as unknown as number[] })}>
            {(cat.data?.areas ?? []).map((a) => (
              <MenuItem key={a.id} value={a.id}><Checkbox size="small" checked={f.area_ids.includes(a.id)} /><ListItemText primary={a.nombre} /></MenuItem>
            ))}
          </TextField>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Ticket maestro (opcional)" placeholder="ADU-2026-000820" sx={{ flex: 1 }} value={f.ticket_maestro} onChange={(e) => setF({ ...f, ticket_maestro: e.target.value })} />
            <TextField label="Próxima novedad" placeholder="antes de las 11:00" sx={{ flex: 1 }} value={f.proxima_novedad} onChange={(e) => setF({ ...f, proxima_novedad: e.target.value })} />
          </Stack>
          <FormControlLabel control={<Switch checked={f.mostrar_publico} onChange={(e) => setF({ ...f, mostrar_publico: e.target.checked })} />}
            label="Mostrar también a clientes en el formulario público /solicitud" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button color="inherit" onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" startIcon={<CampaignIcon />} disabled={crear.isPending || f.titulo.length < 5 || f.mensaje.length < 5 || f.sistema.length < 2} onClick={() => crear.mutate()}>Publicar</Button>
      </DialogActions>
    </Dialog>
  );
}

function Afectados({ aviso, onCerrar }: { aviso: AvisoGeneral; onCerrar: () => void }) {
  const q = useQuery({
    queryKey: ["avisos", aviso.id, "afectados"],
    queryFn: () => get<{ usuario_id: number; nombre: string; area: string | null; comentario: string | null; ticket_id: number | null; ticket_numero: string | null; fecha: string }[]>(`/avisos/${aviso.id}/afectados`),
  });
  return (
    <Dialog open onClose={onCerrar} maxWidth="md" fullWidth>
      <DialogTitle>Personas afectadas · {aviso.codigo}</DialogTitle>
      <DialogContent>
        {q.isLoading ? <Cargando alto={120} /> : !q.data?.length ? <Vacio texto="Nadie lo ha marcado todavía" /> : (
          <Table size="small">
            <TableHead><TableRow><TableCell>Persona</TableCell><TableCell>Área</TableCell><TableCell>Comentario</TableCell><TableCell>Ticket</TableCell><TableCell>Desde</TableCell></TableRow></TableHead>
            <TableBody>
              {q.data.map((p) => (
                <TableRow key={p.usuario_id}>
                  <TableCell>{p.nombre}</TableCell><TableCell>{p.area ?? "—"}</TableCell><TableCell>{p.comentario ?? "—"}</TableCell>
                  <TableCell>{p.ticket_id ? <Link component={RouterLink} to={`/tickets/${p.ticket_id}`}>{p.ticket_numero}</Link> : "—"}</TableCell>
                  <TableCell>{tiempoRelativo(p.fecha)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onCerrar}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}

function AvisoActivo({ a }: { a: AvisoGeneral }) {
  const qc = useQueryClient();
  const avisar = useAviso();
  const [estado, setEstado] = useState<EstadoAviso>(a.estado);
  const [texto, setTexto] = useState("");
  const [proxima, setProxima] = useState(a.proxima_novedad ?? "");
  const [notificar, setNotificar] = useState(true);
  const [verLista, setVerLista] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const publicar = useMutation({
    mutationFn: (resolver: boolean) => post(`/avisos/${a.id}/actualizaciones`, {
      estado: resolver ? "RESUELTO" : estado, texto: texto.trim() || (resolver ? "Servicio restablecido." : ""), proxima_novedad: proxima || null,
      avisar: notificar, resolver_tickets: true,
    }),
    onSuccess: (_, resolver) => {
      avisar(resolver ? `${a.codigo} resuelto` : "Actualización publicada");
      setTexto("");
      qc.invalidateQueries({ queryKey: ["avisos"] });
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const paso = PASOS.findIndex(([k]) => k === a.estado);
  return (
    <Paper sx={{ p: 3, mb: 2.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1, flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: marca.azul, fontWeight: 700 }}>{a.codigo} · activo {tiempoRelativo(a.inicio)} · {a.sistema}</Typography>
        <Box sx={{ flex: 1 }} />
        {a.mostrar_publico && <Chip size="small" label="Visible en /solicitud" variant="outlined" />}
        {a.ticket_maestro && <Chip size="small" label={`Ticket maestro ${a.ticket_maestro.numero}`} variant="outlined" component={RouterLink} to={`/tickets/${a.ticket_maestro.id}`} clickable />}
      </Stack>
      <Typography variant="h6" sx={{ mb: 0.5 }}>{a.titulo}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{a.mensaje}</Typography>
      <Stepper activeStep={paso} sx={{ mb: 2.5 }}>
        {PASOS.map(([, p]) => <Step key={p}><StepLabel>{p}</StepLabel></Step>)}
      </Stepper>
      {(a.actualizaciones ?? []).length > 0 && (
        <Box sx={{ mb: 2, pl: 1.5, borderLeft: `3px solid ${marca.celeste}` }}>
          {(a.actualizaciones ?? []).slice().reverse().map((x) => (
            <Typography key={x.id} variant="body2" sx={{ mb: 0.6 }}>
              <b>{fechaHora(x.fecha)}</b> · {x.estado_nombre}{x.usuario ? ` · ${x.usuario}` : ""}: {x.texto}
            </Typography>
          ))}
        </Box>
      )}
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
      <TextField fullWidth multiline minRows={2} label="Nueva actualización" value={texto} onChange={(e) => setTexto(e.target.value)}
        placeholder="SENAE confirma intermitencia en el módulo de transmisión. Estiman normalidad antes de las 12:00." />
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ mt: 1.5 }} alignItems={{ md: "center" }}>
        <ToggleButtonGroup size="small" value={estado} exclusive color="primary" onChange={(_, v) => v && setEstado(v)}>
          {PASOS.slice(0, 3).map(([k, t]) => <ToggleButton key={k} value={k}>{t}</ToggleButton>)}
        </ToggleButtonGroup>
        <TextField size="small" label="Próxima novedad" value={proxima} onChange={(e) => setProxima(e.target.value)} sx={{ width: { md: 180 } }} />
        <Box sx={{ flex: 1 }} />
        <FormControlLabel control={<Switch size="small" checked={notificar} onChange={(e) => setNotificar(e.target.checked)} />} label={<Typography variant="body2">Avisar por correo</Typography>} />
        <Button variant="outlined" startIcon={<MailOutlineIcon />} disabled={texto.trim().length < 3 || publicar.isPending} onClick={() => publicar.mutate(false)}>Publicar</Button>
      </Stack>
      <Divider sx={{ my: 2.5 }} />
      <Stack direction="row" spacing={2} alignItems="center">
        <Box sx={{ flex: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{a.afectados} personas afectadas · {a.tickets} tickets vinculados</Typography>
          {a.con_comentario > 0 && <Typography variant="caption" color="text.secondary">{a.con_comentario} dejaron comentario</Typography>}
        </Box>
        <Button size="small" onClick={() => setVerLista(true)}>Ver lista</Button>
      </Stack>
      <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2.5 }}>
        <Button variant="contained" color="success" startIcon={<CheckIcon />} disabled={publicar.isPending} onClick={() => publicar.mutate(true)}>
          Marcar resuelto{notificar && a.afectados ? ` y avisar a ${a.afectados} personas` : ""}
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
        Los tickets vinculados se marcan como resueltos con el mismo mensaje.
      </Typography>
      {verLista && <Afectados aviso={a} onCerrar={() => setVerLista(false)} />}
    </Paper>
  );
}

export default function AvisosGenerales() {
  const qc = useQueryClient();
  const [anio, setAnio] = useState(new Date().getFullYear());
  const [nuevo, setNuevo] = useState(false);
  const q = useQuery({ queryKey: ["avisos", "admin", anio], queryFn: () => get<AvisosAdmin>("/avisos", { anio }) });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;
  return (
    <Box>
      <Encabezado
        titulo="Avisos generales"
        subtitulo="Para caídas que afectan a muchos a la vez: ECUAPASS, internet, correo, servidor de archivos, sistema contable."
        acciones={<Button variant="contained" startIcon={<CampaignIcon />} onClick={() => setNuevo(true)}>Publicar aviso</Button>}
      />
      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 7.2 }}>
          {d.activos.length ? d.activos.map((a) => <AvisoActivo key={a.id} a={a} />) : (
            <Paper sx={{ p: 3 }}><Vacio texto="No hay avisos activos. Todo funciona con normalidad." /></Paper>
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 4.8 }}>
          <Paper sx={{ p: 2.5 }}>
            <Stack direction="row" alignItems="center" sx={{ mb: 1.5 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>Historial de caídas</Typography>
              <TextField select size="small" value={anio} onChange={(e) => setAnio(Number(e.target.value))}>
                {[0, 1, 2].map((k) => new Date().getFullYear() - k).map((y) => <MenuItem key={y} value={y}>{y}</MenuItem>)}
              </TextField>
            </Stack>
            {d.historial.length === 0 ? <Typography variant="body2" color="text.secondary">Sin caídas registradas en {d.anio}.</Typography> : (
              <Table size="small">
                <TableHead><TableRow><TableCell>Fecha</TableCell><TableCell>Sistema</TableCell><TableCell align="right">Duración</TableCell><TableCell /></TableRow></TableHead>
                <TableBody>
                  {d.historial.map((a) => (
                    <TableRow key={a.id} hover>
                      <TableCell>{fecha(a.inicio)}</TableCell>
                      <TableCell><Typography variant="body2">{a.sistema}</Typography><Typography variant="caption" color="text.secondary">{a.titulo}</Typography></TableCell>
                      <TableCell align="right">{a.duracion}</TableCell>
                      <TableCell align="right">
                        <Button size="small" startIcon={<PictureAsPdfIcon />} onClick={() => descargar(`/avisos/${a.id}/constancia`, undefined, `constancia-${a.codigo}.pdf`)}>
                          Constancia
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {d.resumen.length > 0 && (
              <Stack direction="row" spacing={1.5} sx={{ mt: 2, flexWrap: "wrap" }} useFlexGap>
                {d.resumen.map((r) => (
                  <Box key={r.sistema} sx={{ flex: "1 1 120px", p: 1.5, borderRadius: 2, bgcolor: "#F4F8FC" }}>
                    <Typography variant="caption" color="text.secondary">{r.sistema}</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{r.caidas} {r.caidas === 1 ? "caída" : "caídas"} · {horas(r.minutos)}</Typography>
                  </Box>
                ))}
              </Stack>
            )}
          </Paper>
          <Alert severity="info" sx={{ mt: 2.5 }}>
            La <b>constancia en PDF</b> (fecha, hora de inicio y fin, actualizaciones) sirve para explicar a un cliente por qué se retrasó su trámite el día de la caída.
          </Alert>
        </Grid>
      </Grid>
      {nuevo && <NuevoAviso onCerrar={(c) => { setNuevo(false); if (c) qc.invalidateQueries({ queryKey: ["avisos"] }); }} />}
    </Box>
  );
}
