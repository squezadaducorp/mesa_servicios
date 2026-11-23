/** Seguridad y cumplimiento ISO 27001: revisión de accesos (38), inactividad y retención (42). */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, MenuItem, Paper, Tab, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Tabs, TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from "@mui/material";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdfOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { descargar, get, post, put } from "../../api/client";
import {
  NOMBRE_CLASIFICACION, type CuentaInactiva, type Decision, type ItemRevision, type PendientesAcceso, type ResumenRetencion, type Revision,
} from "../../api/cumplimiento";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { Stack } from "../../components/Pila";
import { P } from "../../utils/permisos";
import { fecha, numero } from "../../utils/formato";

const DECISIONES: { valor: Decision; texto: string; color: "success" | "warning" | "error" }[] = [
  { valor: "MANTENER", texto: "Mantener", color: "success" },
  { valor: "AJUSTAR", texto: "Ajustar", color: "warning" },
  { valor: "BAJA", texto: "Dar de baja", color: "error" },
];

// ------------------------------------------------------------------ revisión de accesos
function FilaRevision({ i, abierta, alDecidir }: { i: ItemRevision; abierta: boolean; alDecidir: (i: ItemRevision, d: Decision) => void }) {
  return (
    <TableRow hover>
      <TableCell>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>{i.nombre}</Typography>
        <Typography variant="caption" color="text.secondary">{i.correo}{i.cargo ? ` · ${i.cargo}` : ""}</Typography>
      </TableCell>
      <TableCell>{i.rol}</TableCell>
      <TableCell>{i.jefe ?? <Chip size="small" label="TI" variant="outlined" />}</TableCell>
      <TableCell>{i.ultimo_login ? fecha(i.ultimo_login) : "Nunca"}</TableCell>
      <TableCell>
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
          {i.alertas.map((a) => (
            <Chip key={a.codigo} size="small" icon={<WarningAmberIcon />} label={a.texto}
              sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", "& .MuiChip-icon": { color: "#8A5A00" } }} />
          ))}
        </Stack>
      </TableCell>
      <TableCell sx={{ minWidth: 280 }}>
        {abierta ? (
          <ToggleButtonGroup size="small" exclusive value={i.decision ?? null} onChange={(_, d) => d && alDecidir(i, d)}>
            {DECISIONES.map((d) => <ToggleButton key={d.valor} value={d.valor} color={d.color}>{d.texto}</ToggleButton>)}
          </ToggleButtonGroup>
        ) : (
          <Chip size="small" color={DECISIONES.find((d) => d.valor === i.decision)?.color} label={
            `${DECISIONES.find((d) => d.valor === i.decision)?.texto ?? "Pendiente"}${i.decision === "BAJA" && i.aplicado ? " (aplicada)" : ""}`} />
        )}
        {i.comentario && <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>{i.comentario}</Typography>}
      </TableCell>
    </TableRow>
  );
}

function RevisionAccesos({ admin }: { admin: boolean }) {
  const qc = useQueryClient();
  const avisar = useAviso();
  const pend = useQuery({ queryKey: ["accesos", "pendientes"], queryFn: () => get<PendientesAcceso>("/accesos/pendientes") });
  const lista = useQuery({ queryKey: ["accesos", "revisiones"], queryFn: () => get<{ revisiones: Revision[] }>("/accesos/revisiones"), enabled: admin });
  const [sel, setSel] = useState<number | null>(null);
  const id = sel ?? pend.data?.revision_id ?? lista.data?.revisiones[0]?.id ?? null;
  const det = useQuery({ queryKey: ["accesos", "revision", id], queryFn: () => get<Revision>(`/accesos/revisiones/${id}`), enabled: !!id });
  const [motivo, setMotivo] = useState<{ i: ItemRevision; d: Decision; texto: string } | null>(null);
  const [aprobar, setAprobar] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<"PENDIENTES" | "TODOS">("PENDIENTES");
  const refrescar = () => qc.invalidateQueries({ queryKey: ["accesos"] });

  const decidir = useMutation({
    mutationFn: (x: { i: ItemRevision; d: Decision; comentario?: string }) => put(`/accesos/items/${x.i.id}`, { decision: x.d, comentario: x.comentario ?? null }),
    onSuccess: () => { setMotivo(null); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const abrir = useMutation({
    mutationFn: () => post<Revision>("/accesos/revisiones"),
    onSuccess: (r) => { setSel(r.id); avisar("Revisión abierta: los jefes recibieron el correo"); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const aprobarM = useMutation({
    mutationFn: () => post(`/accesos/revisiones/${id}/aprobar`, { observacion: aprobar || null }),
    onSuccess: () => { setAprobar(null); avisar("Acta aprobada: se aplicaron las bajas y se envió el PDF"); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const alDecidir = (i: ItemRevision, d: Decision) => {
    if (d === "MANTENER") decidir.mutate({ i, d });
    else setMotivo({ i, d, texto: i.decision === d ? i.comentario ?? "" : "" });
  };

  if (pend.isLoading || (admin && lista.isLoading)) return <Cargando />;
  if (pend.error) return <ErrorCarga error={pend.error} />;
  const r = det.data;
  const abierta = r?.estado === "ABIERTA";
  const items = (r?.items ?? []).filter((i) => filtro === "TODOS" || !i.decision);
  const hayAbierta = lista.data?.revisiones.some((x) => x.estado === "ABIERTA");

  return (
    <Stack spacing={2}>
      {admin && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
            <TextField select size="small" label="Revisión" value={id ?? ""} onChange={(e) => setSel(Number(e.target.value))} sx={{ minWidth: 220 }}>
              {(lista.data?.revisiones ?? []).map((x) => (
                <MenuItem key={x.id} value={x.id}>{x.periodo} · {x.estado === "ABIERTA" ? `${x.revisadas}/${x.total} revisadas` : "Aprobada"}</MenuItem>
              ))}
            </TextField>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
              Se abre sola el 1 de marzo, junio, septiembre y diciembre. Cada jefe revisa a su gente; las cuentas sin jefe las revisa TI.
            </Typography>
            {!hayAbierta && <Button variant="outlined" onClick={() => abrir.mutate()} disabled={abrir.isPending}>Abrir revisión ahora</Button>}
            {id && r && !abierta && (
              <Button startIcon={<PictureAsPdfIcon />} onClick={() => descargar(`/accesos/revisiones/${id}/acta`, undefined, `revision-accesos-${r.periodo}.pdf`)}>
                Acta PDF
              </Button>
            )}
          </Stack>
        </Paper>
      )}
      {!id && <Vacio texto={admin ? "Todavía no hay revisiones de accesos. La primera se abre el 1 de diciembre." : "No tiene accesos por revisar."} />}
      {det.isLoading && <Cargando />}
      {r && (
        <Paper variant="outlined">
          <Box sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Revisión de accesos {r.periodo}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {abierta ? `Plazo: ${fecha(r.fecha_limite)}. ` : `Aprobada el ${fecha(r.fecha_aprobacion)} por ${r.aprobada_por}. `}
                  {r.revisadas} de {r.total} cuentas revisadas.
                </Typography>
              </Box>
              <ToggleButtonGroup size="small" exclusive value={filtro} onChange={(_, f) => f && setFiltro(f)}>
                <ToggleButton value="PENDIENTES">Pendientes</ToggleButton>
                <ToggleButton value="TODOS">Todas</ToggleButton>
              </ToggleButtonGroup>
              {admin && abierta && (
                <Tooltip title={r.revisadas < r.total ? "Primero deben quedar revisadas todas las cuentas" : ""}>
                  <span>
                    <Button variant="contained" disabled={r.revisadas < r.total} onClick={() => setAprobar("")}>Aprobar acta</Button>
                  </span>
                </Tooltip>
              )}
            </Stack>
            <LinearProgress variant="determinate" value={r.total ? (100 * r.revisadas) / r.total : 0} sx={{ mt: 1.5, height: 6, borderRadius: 3 }} />
          </Box>
          {items.length === 0 ? (
            <Box sx={{ p: 3 }}><Vacio texto={filtro === "PENDIENTES" ? "No queda nadie por revisar." : "Sin personas."} /></Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Persona</TableCell><TableCell>Rol</TableCell><TableCell>Jefe directo</TableCell>
                    <TableCell>Último ingreso</TableCell><TableCell>Alertas</TableCell><TableCell>Decisión</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((i) => <FilaRevision key={i.id} i={i} abierta={abierta} alDecidir={alDecidir} />)}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      )}

      <Dialog open={!!motivo} onClose={() => setMotivo(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{motivo?.d === "BAJA" ? `Dar de baja a ${motivo?.i.nombre}` : `Ajustar el acceso de ${motivo?.i.nombre}`}</DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth multiline minRows={2} sx={{ mt: 1 }} value={motivo?.texto ?? ""} slotProps={{ htmlInput: { maxLength: 500 } }}
            label={motivo?.d === "BAJA" ? "¿Por qué ya no necesita acceso?" : "¿Qué hay que cambiar? (rol, permisos, área…)"}
            onChange={(e) => motivo && setMotivo({ ...motivo, texto: e.target.value })} />
          {motivo?.d === "BAJA" && (
            <Alert severity="info" sx={{ mt: 2 }}>La cuenta se desactiva cuando TI apruebe el acta. Nunca se borra: TI puede reactivarla.</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMotivo(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!motivo?.texto.trim() || decidir.isPending}
            onClick={() => motivo && decidir.mutate({ i: motivo.i, d: motivo.d, comentario: motivo.texto })}>Guardar</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={aprobar !== null} onClose={() => setAprobar(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Aprobar el acta {r?.periodo}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Se desactivarán {r?.items?.filter((i) => i.decision === "BAJA").length ?? 0} cuentas y se enviará el acta en PDF al correo configurado.
          </Typography>
          <TextField fullWidth multiline minRows={2} label="Observación (opcional)" value={aprobar ?? ""} onChange={(e) => setAprobar(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAprobar(null)}>Cancelar</Button>
          <Button variant="contained" disabled={aprobarM.isPending} onClick={() => aprobarM.mutate()}>Aprobar</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

// ------------------------------------------------------------------ inactividad
function Inactividad() {
  const q = useQuery({ queryKey: ["accesos", "inactividad"], queryFn: () => get<{ cuentas: CuentaInactiva[]; config: Record<string, string> }>("/accesos/inactividad") });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const c = q.data!.config;
  const activas = c["accesos.bajas_automaticas"]?.toLowerCase().startsWith("s");
  return (
    <Stack spacing={2}>
      <Alert severity={activas ? "info" : "warning"} variant="outlined">
        {activas
          ? `Las cuentas que no entran en ${c["accesos.dias_inactividad"]} días se desactivan solas. La persona y su jefe reciben un aviso ${c["accesos.dias_aviso_baja"]} días antes; basta con entrar para conservarla. Se cambia en Administración › Configuración (accesos.*).`
          : "Las bajas automáticas están apagadas (accesos.bajas_automaticas = no)."}
      </Alert>
      {q.data!.cuentas.length === 0 ? <Vacio texto="Ninguna cuenta se acerca al plazo de inactividad." /> : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Persona</TableCell><TableCell>Rol</TableCell><TableCell>Último ingreso</TableCell>
                <TableCell align="right">Días</TableCell><TableCell>Estado</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {q.data!.cuentas.map((u) => (
                <TableRow key={u.id} hover>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{u.nombre}</Typography>
                    <Typography variant="caption" color="text.secondary">{u.correo}</Typography>
                  </TableCell>
                  <TableCell>{u.rol}</TableCell>
                  <TableCell>{u.ultimo_login ? fecha(u.ultimo_login) : "Nunca"}</TableCell>
                  <TableCell align="right">{u.dias}</TableCell>
                  <TableCell>
                    {u.excluida ? <Chip size="small" label={u.excluida} variant="outlined" />
                      : u.aviso_enviado ? <Chip size="small" color="warning" label={`Avisada el ${fecha(u.aviso_enviado)} · baja el ${fecha(u.baja_el)}`} />
                        : <Chip size="small" label={`Baja el ${fecha(u.baja_el)}`} variant="outlined" />}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}

// ------------------------------------------------------------------ retención
function Retencion() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["retencion"], queryFn: () => get<ResumenRetencion>("/retencion") });
  const [confirmar, setConfirmar] = useState<string | null>(null);
  const depurar = useMutation({
    mutationFn: () => post<{ depurados: number; adjuntos: number; restantes: number }>("/retencion/depurar", { confirmacion: confirmar }),
    onSuccess: (r) => {
      setConfirmar(null);
      avisar(`Se depuraron ${r.depurados} tickets y ${r.adjuntos} adjuntos${r.restantes ? `; quedan ${r.restantes}` : ""}`);
      qc.invalidateQueries({ queryKey: ["retencion"] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const r = q.data!;
  const tarjeta = (titulo: string, valor: number, detalle?: string) => (
    <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 150 }}>
      <Typography variant="caption" color="text.secondary">{titulo}</Typography>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>{numero(valor)}</Typography>
      {detalle && <Typography variant="caption" color="text.secondary">{detalle}</Typography>}
    </Paper>
  );
  return (
    <Stack spacing={2}>
      <Alert severity="info" variant="outlined">
        Los tickets se conservan <b>{r.anios} años</b> desde su cierre. Después, TI puede depurarlos: se borran el texto y los adjuntos, y quedan el
        número, las fechas y las métricas. Nada se borra sin su aprobación, y un ticket con retención legal nunca se depura.
      </Alert>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ flexWrap: "wrap" }}>
        {(["PUBLICA", "INTERNA", "CONFIDENCIAL"] as const).map((n) => tarjeta(`Tickets ${NOMBRE_CLASIFICACION[n].toLowerCase()}s`, r.clasificacion[n] ?? 0))}
        {tarjeta("Con retención legal", r.retencion_legal)}
        {tarjeta("Ya depurados", r.depurados)}
      </Stack>
      <Paper variant="outlined">
        <Box sx={{ p: 2, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Listos para depurar: {numero(r.por_depurar)}</Typography>
            <Typography variant="body2" color="text.secondary">El primer día de cada mes le llega un correo si hay tickets que cumplieron el plazo.</Typography>
          </Box>
          <Button variant="contained" color="error" disabled={!r.por_depurar} onClick={() => setConfirmar("")}>Aprobar depuración</Button>
        </Box>
        {r.muestra.length > 0 && (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow><TableCell>Ticket</TableCell><TableCell>Asunto</TableCell><TableCell>Categoría</TableCell><TableCell>Cierre</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {r.muestra.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{t.numero}</TableCell><TableCell>{t.asunto}</TableCell><TableCell>{t.categoria}</TableCell>
                    <TableCell>{fecha(t.fecha_cierre)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
      <Dialog open={confirmar !== null} onClose={() => setConfirmar(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Depurar {numero(Math.min(r.por_depurar, 200))} tickets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Se borrarán para siempre el texto y los adjuntos de estos tickets (hasta 200 por vez). Queda el registro en Auditoría. Escriba <b>DEPURAR</b> para confirmar.
          </Typography>
          <TextField fullWidth autoFocus value={confirmar ?? ""} onChange={(e) => setConfirmar(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmar(null)}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={confirmar?.trim().toUpperCase() !== "DEPURAR" || depurar.isPending}
            onClick={() => depurar.mutate()}>Depurar</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

export default function Cumplimiento() {
  const { puede } = useAuth();
  const admin = puede(P.USUARIOS);
  const sistema = puede(P.SISTEMA);
  const pestanas = [
    { clave: "accesos", texto: "Revisión de accesos", ver: true },
    { clave: "inactividad", texto: "Cuentas sin uso", ver: admin },
    { clave: "retencion", texto: "Clasificación y retención", ver: sistema },
  ].filter((p) => p.ver);
  const [tab, setTab] = useState(pestanas[0].clave);
  useEffect(() => {
    if (!pestanas.some((p) => p.clave === tab)) setTab(pestanas[0].clave);
  }, [tab, pestanas]);
  return (
    <Box>
      <Encabezado titulo="Seguridad y cumplimiento"
        subtitulo={admin ? "Controles ISO 27001: revisión de accesos, cuentas sin uso, clasificación y retención" : "Confirme qué accesos necesita su equipo"} />
      {pestanas.length > 1 && (
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          {pestanas.map((p) => <Tab key={p.clave} value={p.clave} label={p.texto} />)}
        </Tabs>
      )}
      {tab === "accesos" && <RevisionAccesos admin={admin} />}
      {tab === "inactividad" && <Inactividad />}
      {tab === "retencion" && <Retencion />}
    </Box>
  );
}
