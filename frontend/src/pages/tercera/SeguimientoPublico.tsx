import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Chip, Divider, Grid, Paper, Step, StepLabel, Stepper, TextField, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ScheduleIcon from "@mui/icons-material/Schedule";
import PersonIcon from "@mui/icons-material/Person";
import KeyIcon from "@mui/icons-material/VpnKey";
import SendIcon from "@mui/icons-material/Send";
import StarIcon from "@mui/icons-material/StarBorder";
import LockIcon from "@mui/icons-material/Lock";
import { api, get, post } from "../../api/client";
import type { SeguimientoVista } from "../../api/tercera";
import { mensajeError } from "../../components/Aviso";
import { EstadoChip } from "../../components/Chips";
import { Cargando } from "../../components/Comunes";
import { fechaHora } from "../../utils/formato";
import { marca } from "../../theme";

function iniciales(n: string) {
  return n.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export function BarraPublica({ titulo }: { titulo: string }) {
  return (
    <Box sx={{ bgcolor: marca.navy, px: { xs: 2, md: 5 }, py: 1.8, display: "flex", alignItems: "center", gap: 1.5 }}>
      <Box component="img" src="/isotipo.png" alt="" sx={{ width: 38, height: 38, bgcolor: "#fff", borderRadius: 2, p: 0.5 }} />
      <Box>
        <Typography sx={{ color: "#fff", fontWeight: 700, lineHeight: 1.1 }}>ADUCORP</Typography>
        <Typography variant="caption" sx={{ color: marca.celeste }}>{titulo}</Typography>
      </Box>
    </Box>
  );
}

function Reenviar() {
  const [numero, setNumero] = useState("");
  const [correo, setCorreo] = useState("");
  const enviar = useMutation({ mutationFn: () => post<{ mensaje: string }>("/publico/seguimiento/reenviar", { numero, correo }) });
  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <KeyIcon sx={{ color: marca.azul }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>¿Perdió el enlace?</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Escriba el número y el correo con que registró la solicitud. Le enviaremos un enlace nuevo a ese correo.
      </Typography>
      {enviar.data ? <Alert severity="success">{enviar.data.mensaje}</Alert> : (
        <>
          {enviar.error && <Alert severity="error" sx={{ mb: 1.5 }}>{mensajeError(enviar.error)}</Alert>}
          <TextField fullWidth size="small" label="Número de ticket" placeholder="ADU-2026-000812" value={numero} onChange={(e) => setNumero(e.target.value)} sx={{ mb: 1.5 }} />
          <TextField fullWidth size="small" label="Correo" type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} sx={{ mb: 1.5 }} />
          <Button fullWidth variant="outlined" disabled={numero.trim().length < 5 || !correo.includes("@") || enviar.isPending} onClick={() => enviar.mutate()}>
            Enviarme un enlace nuevo
          </Button>
        </>
      )}
    </Paper>
  );
}

/** Página pública de seguimiento: /seguimiento/:id/:llave (enlace de los correos). Sin enlace muestra solo «pedir uno nuevo». */
export default function SeguimientoPublico() {
  const { id, llave } = useParams();
  const qc = useQueryClient();
  const [texto, setTexto] = useState("");
  const [archivos, setArchivos] = useState<File[]>([]);
  const entrada = useRef<HTMLInputElement>(null);
  const clave = ["seguimiento", id, llave];
  const q = useQuery({
    queryKey: clave,
    queryFn: () => get<SeguimientoVista>(`/publico/seguimiento/${id}`, { t: llave }),
    enabled: !!id && !!llave,
    retry: false,
  });
  const responder = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("t", llave ?? "");
      form.append("texto", texto);
      archivos.forEach((a) => form.append("archivos", a));
      return api<SeguimientoVista>("POST", `/publico/seguimiento/${id}/responder`, { form });
    },
    onSuccess: (d) => {
      qc.setQueryData(clave, d);
      setTexto("");
      setArchivos([]);
    },
  });

  const d = q.data;
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <BarraPublica titulo="Seguimiento de solicitud" />
      <Box sx={{ px: { xs: 2, md: 5 }, py: 3, maxWidth: 1280, mx: "auto" }}>
        {q.isLoading && <Cargando />}
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 8 }}>
            {!llave && <Alert severity="info">Abra el enlace «Ver el estado de mi solicitud» de su correo, o pida uno nuevo con el número de ticket y su correo.</Alert>}
            {q.error && <Alert severity="warning">{mensajeError(q.error)}</Alert>}
            {d && (
              <>
                <Paper sx={{ p: { xs: 2, md: 3 } }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.8 }}>
                    <Typography variant="h6" sx={{ color: marca.azul, fontWeight: 700 }}>{d.numero}</Typography>
                    <EstadoChip estado={d.estado} nombre={d.estado_nombre} />
                  </Stack>
                  <Typography variant="h5" sx={{ fontSize: 21, mb: 2.5 }}>{d.asunto}</Typography>
                  {d.cancelado ? <Alert severity="info" sx={{ mb: 2 }}>Esta solicitud se canceló. Revise la conversación para ver el motivo.</Alert> : (
                    <Stepper activeStep={d.paso} alternativeLabel sx={{ mb: 3 }}>
                      {d.pasos.map((p, i) => <Step key={p} completed={i < d.paso || (i === d.paso && d.paso === d.pasos.length - 1)}><StepLabel>{p}</StepLabel></Step>)}
                    </Stepper>
                  )}
                  {d.esperando_su_respuesta && <Alert severity="warning" sx={{ mb: 2 }}>Estamos esperando su respuesta: escríbanos abajo o adjunte el documento que le pedimos.</Alert>}
                  <Grid container spacing={2}>
                    {[
                      [<PersonIcon key="p" />, "Lo atiende", d.responsable ? `${d.responsable}${d.responsable_area ? ` · ${d.responsable_area}` : ""}` : "Por asignar"],
                      [<ScheduleIcon key="s" />, "Respuesta estimada", d.respuesta_estimada ? `antes del ${fechaHora(d.respuesta_estimada)}` : "—"],
                      [<MailOutlineIcon key="m" />, "Solicitado por", d.solicitado_por],
                    ].map(([i, k, v]) => (
                      <Grid size={{ xs: 12, sm: 4 }} key={k as string}>
                        <Stack direction="row" spacing={1.2} sx={{ p: 1.5, borderRadius: 2, bgcolor: "#F4F8FC", height: "100%" }}>
                          <Box sx={{ color: marca.azul }}>{i}</Box>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="caption" color="text.secondary">{k}</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: "break-word" }}>{v}</Typography>
                          </Box>
                        </Stack>
                      </Grid>
                    ))}
                  </Grid>
                </Paper>
                <Paper sx={{ p: { xs: 2, md: 3 }, mt: 3 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>Conversación</Typography>
                  {d.conversacion.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Aún no hay respuestas.</Typography>}
                  {d.conversacion.slice().reverse().map((c, k) => (
                    <Stack key={k} direction="row" spacing={1.5} sx={{ mb: 2 }}>
                      <Avatar sx={{ width: 34, height: 34, fontSize: 13, bgcolor: c.propio ? marca.celeste : marca.azul }}>{iniciales(c.autor)}</Avatar>
                      <Box sx={{ flex: 1, p: 1.5, borderRadius: 2, bgcolor: c.propio ? "#F8FAFD" : "#EEF5FC", border: "1px solid #E3E8F0" }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {c.autor} <Typography component="span" variant="caption" color="text.secondary">· {fechaHora(c.fecha)}</Typography>
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: "pre-wrap" }}>{c.texto}</Typography>
                      </Box>
                    </Stack>
                  ))}
                  {d.adjuntos.length > 0 && (
                    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", mb: 1 }}>
                      {d.adjuntos.map((a, k) => <Chip key={k} size="small" icon={<AttachFileIcon />} label={a.nombre} variant="outlined" />)}
                    </Stack>
                  )}
                  {d.puede_responder && (
                    <>
                      <Divider sx={{ my: 2 }} />
                      {responder.error && <Alert severity="error" sx={{ mb: 1.5 }}>{mensajeError(responder.error)}</Alert>}
                      {responder.isSuccess && <Alert severity="success" sx={{ mb: 1.5 }}>Recibimos su mensaje. El analista ya fue avisado.</Alert>}
                      <TextField fullWidth multiline minRows={2} label="Agregar información" placeholder="Escriba aquí su mensaje para el analista…"
                        value={texto} onChange={(e) => setTexto(e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} />
                      {archivos.length > 0 && (
                        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", mt: 1 }}>
                          {archivos.map((a, k) => <Chip key={k} size="small" label={a.name} onDelete={() => setArchivos(archivos.filter((_, j) => j !== k))} />)}
                        </Stack>
                      )}
                      <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} justifyContent="space-between">
                        <input ref={entrada} type="file" hidden multiple onChange={(e) => { setArchivos([...archivos, ...Array.from(e.target.files ?? [])]); e.target.value = ""; }} />
                        <Button startIcon={<AttachFileIcon />} onClick={() => entrada.current?.click()}>Adjuntar documento</Button>
                        <Button variant="contained" endIcon={<SendIcon />} disabled={responder.isPending || (texto.trim().length < 2 && !archivos.length)} onClick={() => responder.mutate()}>
                          Enviar
                        </Button>
                      </Stack>
                    </>
                  )}
                </Paper>
              </>
            )}
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            {d && (
              <Paper sx={{ p: 2.5, mb: 3 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <StarIcon sx={{ color: d.encuesta_url ? marca.azul : "#B0B8C4" }} />
                  <Typography variant="subtitle2">Calificar la atención</Typography>
                </Stack>
                {d.encuesta_url ? (
                  <Button variant="contained" href={d.encuesta_url}>Calificar ahora</Button>
                ) : (
                  <Typography variant="body2" color="text.secondary">Se habilita cuando la solicitud esté resuelta.</Typography>
                )}
              </Paper>
            )}
            <Reenviar />
            <Alert severity="success" sx={{ mt: 3 }} icon={<LockIcon />}>
              Página solo de su solicitud. Las notas internas del equipo no se muestran aquí.
              {d ? ` El enlace deja de funcionar ${d.vigencia_dias} días después del cierre.` : ""}
            </Alert>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
}
