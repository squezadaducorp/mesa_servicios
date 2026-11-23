import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Paper, Switch, Table, TableBody, TableCell, TableHead,
  TableRow, TextField, Typography,
} from "@mui/material";
import PhoneIphoneIcon from "@mui/icons-material/PhoneIphone";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import { Stack } from "../../components/Pila";
import { get, post, put } from "../../api/client";
import type { Activacion, EstadoDosPasos, EstadoUsuarioDosPasos, PoliticaDosPasos } from "../../api/cuarta";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";
import { CodigoCajas, CodigosRespaldo, PasosAuthenticator } from "../../components/DosPasos";
import { P } from "../../utils/permisos";
import { fechaHora } from "../../utils/formato";

function MiPerfil() {
  const avisar = useAviso();
  const qc = useQueryClient();
  const { usuario } = useAuth();
  const q = useQuery({ queryKey: ["seguridad", "mi-cuenta"], queryFn: () => get<EstadoDosPasos>("/seguridad/mi-cuenta") });
  const [act, setAct] = useState<Activacion | null>(null);
  const [codigo, setCodigo] = useState("");
  const [codigos, setCodigos] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [desactivar, setDesactivar] = useState(false);
  const [clave, setClave] = useState("");
  const refrescar = () => qc.invalidateQueries({ queryKey: ["seguridad"] });
  const iniciar = useMutation({
    mutationFn: (metodo: "APP" | "CORREO") => post<Activacion>("/seguridad/mi-cuenta/iniciar", { metodo }),
    onSuccess: (a) => { setAct(a); setCodigo(""); setError(null); },
    onError: (e) => setError(mensajeError(e)),
  });
  const confirmar = useMutation({
    mutationFn: () => post<{ codigos: string[] }>("/seguridad/mi-cuenta/confirmar", { metodo: act!.metodo, codigo }),
    onSuccess: (r) => { setCodigos(r.codigos); setAct(null); avisar("Verificación en dos pasos activada"); refrescar(); },
    onError: (e) => { setError(mensajeError(e)); setCodigo(""); },
  });
  const regenerar = useMutation({
    mutationFn: () => post<{ codigos: string[] }>("/seguridad/mi-cuenta/codigos"),
    onSuccess: (r) => { setCodigos(r.codigos); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const olvidar = useMutation({
    mutationFn: () => post("/seguridad/mi-cuenta/olvidar-equipos"),
    onSuccess: () => { avisar("Sus equipos de confianza volverán a pedir el código"); refrescar(); },
  });
  const quitar = useMutation({
    mutationFn: () => post("/seguridad/mi-cuenta/desactivar", { clave }),
    onSuccess: () => { setDesactivar(false); setClave(""); setCodigos(null); avisar("Verificación desactivada"); refrescar(); },
    onError: (e) => setError(mensajeError(e)),
  });

  if (q.isLoading) return <Paper variant="outlined" sx={{ p: 3 }}><Cargando alto={200} /></Paper>;
  if (q.error) return <ErrorCarga error={q.error} />;
  const e = q.data!;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="h6">Mi perfil › Verificación en dos pasos</Typography>
      {!e.metodo && !act && !codigos && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
            Además de la contraseña, al entrar se pide un código de 6 dígitos. Así, aunque alguien obtenga su contraseña, no podrá entrar.
            {e.exigida ? " Su rol la tiene obligatoria." : ""}
          </Typography>
          {!e.local && <Alert severity="info" sx={{ mb: 2 }}>Su cuenta entra con Microsoft: la verificación la aplica Microsoft 365.</Alert>}
          <Stack direction={{ xs: "column", sm: "row" }} sx={{ gap: 1.5 }}>
            <Button variant="contained" startIcon={<PhoneIphoneIcon />} onClick={() => iniciar.mutate("APP")} disabled={iniciar.isPending}>
              Activar con el celular (Authenticator)
            </Button>
            {e.puede_correo && (
              <Button variant="outlined" startIcon={<MailOutlineIcon />} onClick={() => iniciar.mutate("CORREO")} disabled={iniciar.isPending}>
                Código por correo ({e.correo_mascara})
              </Button>
            )}
          </Stack>
          {!e.puede_correo && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              El código por correo no está disponible mientras el envío de correos de la Mesa esté apagado.
            </Typography>
          )}
        </>
      )}

      {act && (
        <Box sx={{ mt: 2 }}>
          {act.metodo === "APP" ? <PasosAuthenticator a={act} /> : (
            <Alert severity="info">Enviamos un código de 6 dígitos a {act.enviado_a}. Vence en 10 minutos.</Alert>
          )}
          <Divider sx={{ my: 2.5 }} />
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1.5, textAlign: "center" }}>Código de 6 dígitos</Typography>
          <CodigoCajas valor={codigo} onCambio={setCodigo} autoFocus />
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          <Stack direction="row" justifyContent="center" sx={{ gap: 1, mt: 2 }}>
            <Button onClick={() => { setAct(null); setError(null); }}>Cancelar</Button>
            <Button variant="contained" disabled={codigo.length !== 6 || confirmar.isPending} onClick={() => confirmar.mutate()}>Activar</Button>
          </Stack>
        </Box>
      )}

      {e.metodo && (
        <Stack direction="row" alignItems="center" sx={{ gap: 1.5, mt: 2 }}>
          <VerifiedUserIcon color="success" />
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Activa · {e.metodo === "APP" ? "app Authenticator" : `código por correo a ${e.correo_mascara}`}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Desde {fechaHora(e.fecha)} · {e.codigos_restantes} códigos de respaldo · {e.equipos_confianza} equipo(s) de confianza
            </Typography>
          </Box>
        </Stack>
      )}

      {codigos && (
        <Box sx={{ mt: 3 }}>
          <Alert severity="success" sx={{ mb: 2 }}>Guarde estos códigos: sirven para entrar si pierde el celular.</Alert>
          <CodigosRespaldo codigos={codigos} cuenta={usuario?.correo} />
        </Box>
      )}

      {e.metodo && (
        <Stack direction="row" sx={{ gap: 1, mt: 3, flexWrap: "wrap" }}>
          <Button size="small" variant="outlined" onClick={() => regenerar.mutate()} disabled={regenerar.isPending}>Nuevos códigos de respaldo</Button>
          {e.equipos_confianza > 0 && <Button size="small" onClick={() => olvidar.mutate()}>Olvidar equipos de confianza</Button>}
          {!e.exigida && <Button size="small" color="error" onClick={() => { setError(null); setDesactivar(true); }}>Desactivar</Button>}
        </Stack>
      )}
      {e.metodo && e.exigida && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          Su rol la tiene obligatoria. Si cambia de celular, pida a TI que restablezca su verificación.
        </Typography>
      )}

      <Dialog open={desactivar} onClose={() => setDesactivar(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Desactivar la verificación</DialogTitle>
        <DialogContent dividers>
          <TextField fullWidth type="password" label="Su contraseña" value={clave} onChange={(x) => setClave(x.target.value)} autoFocus />
          {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDesactivar(false)}>Cancelar</Button>
          <Button color="error" variant="contained" onClick={() => quitar.mutate()} disabled={!clave || quitar.isPending}>Desactivar</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

const INTERRUPTORES: { k: keyof PoliticaDosPasos; t: string }[] = [
  { k: "obligatoria_admin", t: "Obligatoria para Administrador y Supervisor" },
  { k: "obligatoria_analistas", t: "Obligatoria para Analistas" },
  { k: "opcional_otros", t: "Opcional para clientes internos y gerencia" },
  { k: "permitir_correo", t: "Permitir código por correo como alternativa" },
  { k: "solo_fuera_oficina", t: "Pedir el código solo al entrar desde fuera de la oficina" },
];

function Politica() {
  const avisar = useAviso();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["seguridad", "politica"], queryFn: () => get<{ politica: PoliticaDosPasos; usuarios: EstadoUsuarioDosPasos[] }>("/seguridad/politica") });
  const [p, setP] = useState<PoliticaDosPasos | null>(null);
  const [exentos, setExentos] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reset, setReset] = useState<EstadoUsuarioDosPasos | null>(null);
  useEffect(() => {
    if (q.data) { setP(q.data.politica); setExentos(q.data.politica.exentos.join(", ")); }
  }, [q.data]);
  const guardar = useMutation({
    mutationFn: () => put("/seguridad/politica", { ...p, exentos: exentos.split(",").map((x) => x.trim()).filter(Boolean) }),
    onSuccess: () => { avisar("Política guardada"); setError(null); qc.invalidateQueries({ queryKey: ["seguridad"] }); },
    onError: (e) => setError(mensajeError(e)),
  });
  const restablecer = useMutation({
    mutationFn: (id: number) => post<{ mensaje: string }>(`/seguridad/usuarios/${id}/restablecer`),
    onSuccess: (r) => { avisar(r.mensaje); setReset(null); qc.invalidateQueries({ queryKey: ["seguridad"] }); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading || !p) return <Paper variant="outlined" sx={{ p: 3 }}><Cargando alto={200} /></Paper>;
  if (q.error) return <ErrorCarga error={q.error} />;
  const usuarios = q.data!.usuarios;
  const activos = usuarios.filter((u) => u.metodo).length;

  return (
    <Stack sx={{ gap: 2.5 }}>
      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>Configuración › Política de verificación</Typography>
        {INTERRUPTORES.map((x) => (
          <Stack key={x.k} direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 0.25 }}>
            <Typography variant="body2">{x.t}</Typography>
            <Switch checked={!!p[x.k]} onChange={(e) => setP({ ...p, [x.k]: e.target.checked })} slotProps={{ input: { "aria-label": x.t } }} />
          </Stack>
        ))}
        {p.permitir_correo && !p.correo_activo && (
          <Alert severity="info" sx={{ my: 1 }}>El envío de correos está apagado: la opción por correo no se ofrece hasta activarlo. Mientras tanto se usa solo la app.</Alert>
        )}
        {p.solo_fuera_oficina && (
          <TextField fullWidth size="small" label="IP o redes de la oficina" placeholder="186.46.10.20, 192.168.1.0/24" value={p.redes_oficina}
            onChange={(e) => setP({ ...p, redes_oficina: e.target.value })} sx={{ my: 1 }} />
        )}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 1 }}>
          <Typography variant="body2">Días para recordar un equipo de confianza</Typography>
          <TextField size="small" type="number" value={p.dias_confianza} onChange={(e) => setP({ ...p, dias_confianza: Number(e.target.value) })}
            sx={{ width: 90 }} slotProps={{ htmlInput: { min: 0, max: 365, "aria-label": "Días de confianza" } }} />
        </Stack>
        <TextField fullWidth size="small" label="Cuentas de emergencia fuera de la política" value={exentos} onChange={(e) => setExentos(e.target.value)}
          helperText="Correos separados por coma" sx={{ mt: 1 }} />
        <Alert severity="warning" sx={{ mt: 2 }}>
          La cuenta de emergencia «admin» queda fuera de la política, con clave guardada en el servidor. Si alguien pierde el celular, use
          «Restablecer» abajo.
        </Alert>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2 }}>
          <Button variant="contained" onClick={() => guardar.mutate()} disabled={guardar.isPending}>Guardar política</Button>
        </Stack>
      </Paper>

      <Paper variant="outlined">
        <Typography variant="subtitle1" sx={{ p: 2, fontWeight: 600 }}>Estado por usuario · {usuarios.length} cuentas · {activos} con verificación</Typography>
        <Box sx={{ overflowX: "auto", maxHeight: 520 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow><TableCell>Usuario</TableCell><TableCell>Rol</TableCell><TableCell>Método</TableCell><TableCell align="right">Acción</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {usuarios.map((u) => (
                <TableRow key={u.id} hover>
                  <TableCell>
                    <Typography variant="body2">{u.nombre}</Typography>
                    <Typography variant="caption" color="text.secondary">{u.correo}</Typography>
                  </TableCell>
                  <TableCell>{u.rol}</TableCell>
                  <TableCell>
                    {u.metodo === "APP" && <Chip size="small" variant="outlined" color="success" icon={<PhoneIphoneIcon />} label="App" />}
                    {u.metodo === "CORREO" && <Chip size="small" variant="outlined" color="primary" icon={<MailOutlineIcon />} label="Correo" />}
                    {!u.metodo && u.exento && <Chip size="small" label="Exenta" />}
                    {!u.metodo && !u.exento && u.exigida && (
                      <Chip size="small" label={`Pendiente${u.pendiente_dias !== null ? ` · ${u.pendiente_dias} día${u.pendiente_dias === 1 ? "" : "s"}` : ""}`}
                        sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", fontWeight: 600 }} />
                    )}
                    {!u.metodo && !u.exento && !u.exigida && <Typography variant="caption" color="text.secondary">Sin activar</Typography>}
                  </TableCell>
                  <TableCell align="right">
                    {u.metodo && <Button size="small" onClick={() => setReset(u)}>Restablecer</Button>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      <Dialog open={!!reset} onClose={() => setReset(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Restablecer verificación</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            {reset?.nombre} podrá entrar con su contraseña y, si su rol la tiene obligatoria, configurará de nuevo el celular. Sus códigos de respaldo y equipos
            de confianza dejan de servir. Queda registrado en Auditoría.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReset(null)}>Cancelar</Button>
          <Button variant="contained" color="warning" onClick={() => reset && restablecer.mutate(reset.id)} disabled={restablecer.isPending}>Restablecer</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

export default function Seguridad() {
  const { puede } = useAuth();
  const admin = puede(P.USUARIOS);
  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 3 }}>Seguridad de la cuenta</Typography>
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: admin ? "1.15fr 1fr" : "minmax(0, 760px)" }, alignItems: "start" }}>
        <MiPerfil />
        {admin && <Politica />}
      </Box>
    </Box>
  );
}
