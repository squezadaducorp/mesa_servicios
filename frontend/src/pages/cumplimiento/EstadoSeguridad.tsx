/** Seguridad y cumplimiento: pestañas Política de acceso (37), Servidor (40) y Vulnerabilidades (41). */
import { useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, LinearProgress, Link, Paper, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ScheduleIcon from "@mui/icons-material/Schedule";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlineOutlined";
import GitHubIcon from "@mui/icons-material/GitHub";
import RefreshIcon from "@mui/icons-material/Refresh";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import { get, post, put } from "../../api/client";
import type {
  AccesoPrivilegiado, EstadoControl, EstadoServidor, EstadoVulnerabilidades, PoliticaAcceso, PoliticaClaves, Severidad,
} from "../../api/cumplimiento";
import type { PoliticaDosPasos } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";
import { Stack } from "../../components/Pila";
import { fecha, fechaHora, numero } from "../../utils/formato";

// ------------------------------------------------------------------ comunes
function Iso({ texto }: { texto: string }) {
  return <Chip size="small" variant="outlined" label={`ISO 27001 · ${texto}`} sx={{ fontWeight: 600, height: 22 }} />;
}

function Tarjeta({ titulo, valor, detalle, tono, icono, children }: {
  titulo: string; valor: ReactNode; detalle?: ReactNode; tono: "ok" | "alerta" | "neutro"; icono?: ReactNode; children?: ReactNode;
}) {
  const color = tono === "ok" ? "success.main" : tono === "alerta" ? "warning.main" : "divider";
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 200, borderLeft: 4, borderLeftColor: color }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
        {icono ?? (tono === "ok" ? <CheckCircleIcon color="success" fontSize="small" /> : tono === "alerta" ? <WarningAmberIcon color="warning" fontSize="small" /> : null)}
        <Typography variant="body2" sx={{ fontWeight: 600 }}>{titulo}</Typography>
      </Stack>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>{valor}</Typography>
      {detalle && <Typography variant="caption" color="text.secondary">{detalle}</Typography>}
      {children}
    </Paper>
  );
}

const FilaAjuste = ({ titulo, ayuda, children }: { titulo: string; ayuda?: string; children: ReactNode }) => (
  <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between", py: 1, borderBottom: 1, borderColor: "divider" }}>
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{titulo}</Typography>
      {ayuda && <Typography variant="caption" color="text.secondary">{ayuda}</Typography>}
    </Box>
    {children}
  </Stack>
);

const Numero = ({ valor, alCambiar, min, max, etiqueta }: { valor: number; alCambiar: (n: number) => void; min: number; max: number; etiqueta: string }) => (
  <TextField size="small" type="number" value={valor} onChange={(e) => alCambiar(Number(e.target.value))} sx={{ width: 96, flexShrink: 0 }}
    slotProps={{ htmlInput: { min, max, "aria-label": etiqueta } }} />
);

// ------------------------------------------------------------------ 37 política de acceso
const CHIP_2FA: Record<AccesoPrivilegiado["estado"], { texto: (f: AccesoPrivilegiado) => string; bg: string; fg: string }> = {
  ACTIVA: { texto: (f) => (f.metodo === "CORREO" ? "Correo" : "Celular"), bg: "#E4F4E8", fg: "#1E6B34" },
  PENDIENTE: { texto: (f) => `Pendiente · quedan ${f.dias_restantes} día${f.dias_restantes === 1 ? "" : "s"}`, bg: "#FFF3D6", fg: "#8A5A00" },
  VENCIDA: { texto: () => "Vencido · se exige al entrar", bg: "#FDE4E4", fg: "#9B1C1C" },
  EXENTA: { texto: () => "Exenta · cuenta de emergencia", bg: "#EEF0F4", fg: "#3D4656" },
  OPCIONAL: { texto: () => "Sin activar (opcional)", bg: "#EEF0F4", fg: "#3D4656" },
};

export function PoliticaAccesoTab() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["cumplimiento", "acceso"], queryFn: () => get<PoliticaAcceso>("/cumplimiento/acceso") });
  const [dp, setDp] = useState<PoliticaDosPasos | null>(null);
  const [claves, setClaves] = useState<PoliticaClaves | null>(null);
  useEffect(() => {
    if (q.data) { setDp(q.data.dos_pasos); setClaves(q.data.claves); }
  }, [q.data]);
  const refrescar = () => { qc.invalidateQueries({ queryKey: ["cumplimiento", "acceso"] }); qc.invalidateQueries({ queryKey: ["seguridad"] }); };
  const guardarDp = useMutation({
    mutationFn: () => put("/seguridad/politica", dp),
    onSuccess: () => { avisar("Verificación en dos pasos guardada"); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const guardarClaves = useMutation({
    mutationFn: () => put<PoliticaClaves>("/cumplimiento/acceso/claves", claves),
    onSuccess: () => { avisar("Política de contraseñas guardada"); refrescar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const recordar = useMutation({
    mutationFn: () => post<{ enviados: number }>("/cumplimiento/acceso/recordar"),
    onSuccess: (r) => avisar(r.enviados ? `Recordatorio enviado a ${r.enviados} persona${r.enviados === 1 ? "" : "s"}` : "No hay nadie pendiente"),
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading || !dp || !claves) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;
  const r = d.resumen;
  const pendientes = r.pendientes + r.vencidos;

  return (
    <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1fr) minmax(0, 1.25fr)" }, alignItems: "start" }}>
      <Stack spacing={2.5}>
        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap", gap: 1 }}>
            <Typography variant="h6">Verificación en dos pasos</Typography>
            <Iso texto="A.5.17 · A.8.5" />
          </Stack>
          <FilaAjuste titulo="Obligatoria para Administradores y Supervisores" ayuda="Se pide el código del celular (o del correo) al entrar">
            <Switch checked={dp.obligatoria_admin} onChange={(e) => setDp({ ...dp, obligatoria_admin: e.target.checked })}
              slotProps={{ input: { "aria-label": "Obligatoria para administradores" } }} />
          </FilaAjuste>
          <FilaAjuste titulo="Obligatoria para Analistas" ayuda="Quienes atienden tickets">
            <Switch checked={dp.obligatoria_analistas} onChange={(e) => setDp({ ...dp, obligatoria_analistas: e.target.checked })}
              slotProps={{ input: { "aria-label": "Obligatoria para analistas" } }} />
          </FilaAjuste>
          <FilaAjuste titulo="Plazo para configurarla" ayuda="Días desde que pasa a ser obligatoria; mientras tanto la persona entra y ve un aviso">
            <Numero valor={dp.dias_gracia ?? 7} min={0} max={90} etiqueta="Días de gracia" alCambiar={(n) => setDp({ ...dp, dias_gracia: n })} />
          </FilaAjuste>
          <Stack direction="row" spacing={1} sx={{ mt: 2, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
            <Link component={RouterLink} to="/seguridad" variant="body2">Más opciones (equipos de confianza, oficina, cuentas exentas)</Link>
            <Button variant="contained" onClick={() => guardarDp.mutate()} disabled={guardarDp.isPending}>Guardar</Button>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap", gap: 1 }}>
            <Typography variant="h6">Contraseñas y bloqueo</Typography>
            <Iso texto="A.5.17" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Mínimo {claves.min_longitud} caracteres con mayúscula, minúscula, número y símbolo; se rechazan las contraseñas obvias (nombre, correo,
            «Aducorp», secuencias). No caducan por tiempo, como recomiendan NIST e ISO cuando hay verificación en dos pasos y bloqueo.
          </Typography>
          <FilaAjuste titulo="No repetir las últimas contraseñas" ayuda="0 = sin historial">
            <Numero valor={claves.claves_previas} min={0} max={24} etiqueta="Contraseñas anteriores" alCambiar={(n) => setClaves({ ...claves, claves_previas: n })} />
          </FilaAjuste>
          <FilaAjuste titulo="Intentos fallidos antes de bloquear">
            <Numero valor={claves.max_intentos} min={3} max={20} etiqueta="Intentos" alCambiar={(n) => setClaves({ ...claves, max_intentos: n })} />
          </FilaAjuste>
          <FilaAjuste titulo="Minutos de bloqueo">
            <Numero valor={claves.bloqueo_min} min={5} max={1440} etiqueta="Minutos de bloqueo" alCambiar={(n) => setClaves({ ...claves, bloqueo_min: n })} />
          </FilaAjuste>
          <FilaAjuste titulo="Cerrar la sesión tras minutos sin uso" ayuda="0 = no cerrar">
            <Numero valor={claves.inactividad_min} min={0} max={480} etiqueta="Minutos de inactividad" alCambiar={(n) => setClaves({ ...claves, inactividad_min: n })} />
          </FilaAjuste>
          <FilaAjuste titulo="Avisar al usuario por correo cuando se bloquea su cuenta" ayuda="Con la IP y la hora, por si no reconoce el intento">
            <Switch checked={claves.aviso_bloqueo} onChange={(e) => setClaves({ ...claves, aviso_bloqueo: e.target.checked })}
              slotProps={{ input: { "aria-label": "Avisar bloqueo" } }} />
          </FilaAjuste>
          <Stack direction="row" sx={{ mt: 2, justifyContent: "flex-end" }}>
            <Button variant="contained" onClick={() => guardarClaves.mutate()} disabled={guardarClaves.isPending}>Guardar</Button>
          </Stack>
        </Paper>
      </Stack>

      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 1.5 }}>
          <Typography variant="h6">Cumplimiento de usuarios con privilegios</Typography>
          <Button variant="outlined" startIcon={<MailOutlineIcon />} disabled={!pendientes || recordar.isPending} onClick={() => recordar.mutate()}>
            Recordar a los pendientes
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}>
          <Chip label={`${r.con_verificacion} de ${r.total} con verificación`}
            sx={{ fontWeight: 700, bgcolor: r.con_verificacion === r.total ? "success.main" : "warning.main", color: "#fff" }} />
          {r.exentos > 0 && <Chip variant="outlined" label={`${r.exentos} cuenta${r.exentos === 1 ? "" : "s"} de emergencia exenta${r.exentos === 1 ? "" : "s"}`} />}
          {!dp.obligatoria_admin && <Chip color="warning" variant="outlined" label="Aún no es obligatoria para administradores" />}
        </Stack>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow><TableCell>Usuario</TableCell><TableCell>Dos pasos</TableCell><TableCell>Último ingreso</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {d.privilegiados.map((f) => {
                const c = CHIP_2FA[f.estado];
                return (
                  <TableRow key={f.id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{f.nombre}</Typography>
                      <Typography variant="caption" color="text.secondary">{f.rol} · {f.correo}</Typography>
                    </TableCell>
                    <TableCell><Chip size="small" label={c.texto(f)} sx={{ bgcolor: c.bg, color: c.fg, fontWeight: 600 }} /></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{f.ultimo_login ? fecha(f.ultimo_login) : "Nunca"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
        <Alert severity="warning" sx={{ mt: 2 }}>
          Si alguien usa una cuenta de emergencia, llega un aviso inmediato a {d.correos_alerta || "los correos de «seguridad.correos_alerta» (Configuración)"}.
          Después de usarla, cambie su contraseña.
        </Alert>
      </Paper>
    </Box>
  );
}

// ------------------------------------------------------------------ 40 servidor
const ICONO_CONTROL: Record<EstadoControl, ReactNode> = {
  ok: <CheckCircleIcon color="success" fontSize="small" />,
  alerta: <WarningAmberIcon color="warning" fontSize="small" />,
  sin_dato: <HelpOutlineIcon color="disabled" fontSize="small" />,
  opcional: <ScheduleIcon color="disabled" fontSize="small" />,
};
const CHIP_CONTROL: Record<EstadoControl, { bg: string; fg: string }> = {
  ok: { bg: "#E4F4E8", fg: "#1E6B34" }, alerta: { bg: "#FFF3D6", fg: "#8A5A00" },
  sin_dato: { bg: "#EEF0F4", fg: "#3D4656" }, opcional: { bg: "#EEF0F4", fg: "#3D4656" },
};

export function ServidorTab() {
  const q = useQuery({ queryKey: ["cumplimiento", "servidor"], queryFn: () => get<EstadoServidor>("/cumplimiento/servidor") });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;
  const comando = `sudo /opt/mesa-servicios/${d.script}`;
  if (!d.disponible) {
    return (
      <Alert severity={d.error ? "warning" : "info"} variant="outlined">
        <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>{d.error ?? "Aún no hay un informe del servidor"}</Typography>
        <Typography variant="body2">
          La Mesa corre dentro de un contenedor y no puede revisar el servidor por sí misma. En el servidor, ejecute una vez:
        </Typography>
        <Box component="pre" sx={{ my: 1, p: 1, bgcolor: "action.hover", borderRadius: 1, overflowX: "auto" }}>{comando} instalar</Box>
        <Typography variant="body2">
          Revisa el servidor y la cuenta de AWS (solo lectura), lo programa todos los días a las 06:00 y esta pestaña se llena sola.
          La guía «Endurecer el servidor» explica los permisos de AWS que necesita.
        </Typography>
      </Alert>
    );
  }
  const s = d.servidor ?? {};
  const pct = d.total ? Math.round(((d.cumplidos ?? 0) / d.total) * 100) : 0;
  const parches = d.parches ?? {};
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ flexWrap: "wrap" }}>
        <Tarjeta titulo="Controles cumplidos" valor={`${d.cumplidos} de ${d.total}`} tono={d.cumplidos === d.total ? "ok" : "alerta"}>
          <LinearProgress variant="determinate" value={pct} color={d.cumplidos === d.total ? "success" : "warning"} sx={{ mt: 1, height: 6, borderRadius: 3 }} />
        </Tarjeta>
        <Tarjeta titulo="Servidor" valor={[s.nombre, s.region].filter(Boolean).join(" · ") || "—"} tono="ok"
          detalle={[s.tipo, s.so].filter(Boolean).join(" · ")} />
        <Tarjeta titulo="Parches pendientes" valor={numero(parches.pendientes ?? 0)} tono={parches.pendientes || parches.reinicio ? "alerta" : "ok"}
          detalle={parches.reinicio ? "Kernel nuevo instalado · falta reiniciar" : "Seguridad al día"} />
        <Tarjeta titulo="Última revisión" valor={fechaHora(d.generado)} tono={d.desactualizado ? "alerta" : "ok"}
          detalle={d.desactualizado ? "Hace más de un día: revise el script programado" : "verificar-servidor.sh (diario, 06:00)"} />
      </Stack>
      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>Endurecimiento del servidor</Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow><TableCell width={36} /><TableCell>Control</TableCell><TableCell>Detalle</TableCell><TableCell>Estado</TableCell><TableCell>ISO</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {(d.controles ?? []).map((c) => (
                <TableRow key={c.clave} hover>
                  <TableCell>{ICONO_CONTROL[c.estado]}</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{c.nombre}</TableCell>
                  <TableCell>{c.detalle}</TableCell>
                  <TableCell><Chip size="small" label={c.etiqueta ?? c.estado} sx={{ bgcolor: CHIP_CONTROL[c.estado].bg, color: CHIP_CONTROL[c.estado].fg, fontWeight: 600 }} /></TableCell>
                  <TableCell>{c.iso && <Chip size="small" variant="outlined" label={c.iso} />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        {parches.reinicio && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            Hay un kernel nuevo instalado. Reinicie el servidor en la próxima ventana de mantenimiento (domingo de madrugada): son unos 3 minutos sin servicio
            y se registra como cambio estándar.
          </Alert>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          Para revisar ahora, en el servidor: <code>{comando}</code>. «Sin dato» significa que al rol del servidor le falta un permiso de lectura en AWS.
        </Typography>
      </Paper>
    </Stack>
  );
}

// ------------------------------------------------------------------ 41 vulnerabilidades
const SEV: Record<Severidad, { texto: string; bg: string; fg: string }> = {
  CRITICAL: { texto: "Crítica", bg: "#8F1D1D", fg: "#fff" }, HIGH: { texto: "Alta", bg: "#FDE4E4", fg: "#9B1C1C" },
  MEDIUM: { texto: "Media", bg: "#FFF3D6", fg: "#8A5A00" }, LOW: { texto: "Baja", bg: "#EEF0F4", fg: "#3D4656" },
};
const ChipSev = ({ s }: { s: Severidad }) => <Chip size="small" label={SEV[s].texto} sx={{ bgcolor: SEV[s].bg, color: SEV[s].fg, fontWeight: 700 }} />;
const resultadoJob = (c?: string | null) => (c === "success" ? "Sin hallazgos" : c === "failure" ? "Con hallazgos" : c ?? "—");

export function VulnerabilidadesTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cumplimiento", "vulnerabilidades"], queryFn: () => get<EstadoVulnerabilidades>("/cumplimiento/vulnerabilidades") });
  const actualizar = useMutation({
    mutationFn: () => get<EstadoVulnerabilidades>("/cumplimiento/vulnerabilidades?refrescar=true"),
    onSuccess: (d) => qc.setQueryData(["cumplimiento", "vulnerabilidades"], d),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;
  const plazos = (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Plazos de corrección</Typography>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
        <Chip label={`Crítica · ${d.plazos.CRITICAL} días`} sx={{ bgcolor: SEV.CRITICAL.bg, color: SEV.CRITICAL.fg, fontWeight: 700 }} />
        <Chip label={`Alta · ${d.plazos.HIGH} días`} sx={{ bgcolor: SEV.HIGH.bg, color: SEV.HIGH.fg, fontWeight: 600 }} />
        <Chip label={`Media · ${d.plazos.MEDIUM} días`} sx={{ bgcolor: SEV.MEDIUM.bg, color: SEV.MEDIUM.fg, fontWeight: 600 }} />
        <Chip label="Baja · siguiente versión" />
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        Herramientas: Trivy (imágenes), pip-audit y npm audit (librerías), gitleaks (secretos) y Dependabot.
      </Typography>
    </Box>
  );
  const botones = (
    <Stack direction="row" spacing={1}>
      {d.configurado && <Button startIcon={<RefreshIcon />} onClick={() => actualizar.mutate()} disabled={actualizar.isPending}>Actualizar</Button>}
      <Button variant="outlined" startIcon={<GitHubIcon />} href={`${d.enlace}/actions/workflows/seguridad.yml`} target="_blank" rel="noopener">Ver en GitHub</Button>
    </Stack>
  );
  if (!d.configurado) {
    return (
      <Stack spacing={2}>
        <Alert severity="info" variant="outlined" action={botones}>
          <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>Conecte la Mesa con GitHub para ver aquí el último escaneo</Typography>
          <Typography variant="body2">
            El escaneo ya corre en GitHub en cada cambio y todos los días a las 05:00. Para traer sus resultados, cree en GitHub un token de solo lectura
            (fine-grained, solo el repositorio {d.repo}, permisos Actions, Dependabot alerts y Pull requests en «Read») y guárdelo como
            GITHUB_TOKEN_SEGURIDAD en el secreto del servidor. La guía de despliegue tiene los pasos.
          </Typography>
        </Alert>
        <Paper variant="outlined" sx={{ p: 3 }}>{plazos}</Paper>
      </Stack>
    );
  }
  const comp = d.componentes ?? [];
  const dep = d.dependabot ?? { alertas: [], prs_abiertos: 0, por_severidad: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 } };
  const tot = d.totales ?? { CRITICAL: 0, HIGH: 0 };
  const jobs = d.escaneo?.jobs ?? [];
  const gitleaks = jobs.find((j) => j.nombre.toLowerCase().includes("gitleaks"));
  const filas = [
    ...comp.map((c) => ({ nombre: c.nombre, c: c.critica, a: c.alta, m: c.media })),
    { nombre: "Librerías (Dependabot)", c: dep.por_severidad.CRITICAL, a: dep.por_severidad.HIGH, m: dep.por_severidad.MEDIUM },
  ];
  const escaneoOk = d.escaneo?.conclusion === "success";
  return (
    <Stack spacing={2}>
      {d.error && <Alert severity="warning">{d.error}</Alert>}
      <Stack direction="row" sx={{ justifyContent: "flex-end" }}>{botones}</Stack>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ flexWrap: "wrap" }}>
        <Tarjeta titulo="Críticas abiertas" valor={numero(tot.CRITICAL)} tono={tot.CRITICAL ? "alerta" : "ok"} detalle={`Plazo: ${d.plazos.CRITICAL} días`} />
        <Tarjeta titulo="Altas abiertas" valor={numero(tot.HIGH)} tono={tot.HIGH ? "alerta" : "ok"} detalle={`Plazo: ${d.plazos.HIGH} días`} />
        <Tarjeta titulo="Actualizaciones de Dependabot" valor={`${dep.alertas.length} alertas`} tono={dep.alertas.length ? "alerta" : "ok"}
          detalle={`${dep.prs_abiertos} PR abiertos para fusionar`} />
        <Tarjeta titulo="Último escaneo" valor={d.escaneo?.fecha ? fechaHora(d.escaneo.fecha) : "—"} tono={escaneoOk ? "ok" : "alerta"}
          detalle={escaneoOk ? "GitHub Actions · también en cada PR" : `Resultado: ${d.escaneo?.conclusion ?? "sin datos"}`} />
      </Stack>
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 0.9fr) minmax(0, 1.4fr)" }, alignItems: "start" }}>
        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
            <Typography variant="h6">Por componente</Typography><Iso texto="A.8.8" />
          </Stack>
          <Table size="small">
            <TableHead><TableRow><TableCell>Componente</TableCell><TableCell align="right">Crít.</TableCell><TableCell align="right">Alta</TableCell><TableCell align="right">Media</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>
              {filas.map((f) => (
                <TableRow key={f.nombre}>
                  <TableCell>{f.nombre}</TableCell>
                  <TableCell align="right" sx={{ color: f.c ? "error.main" : undefined, fontWeight: f.c ? 700 : undefined }}>{f.c}</TableCell>
                  <TableCell align="right" sx={{ color: f.a ? "error.main" : undefined, fontWeight: f.a ? 700 : undefined }}>{f.a}</TableCell>
                  <TableCell align="right">{f.m}</TableCell>
                  <TableCell>{f.c || f.a ? <WarningAmberIcon color="warning" fontSize="small" /> : <CheckCircleIcon color="success" fontSize="small" />}</TableCell>
                </TableRow>
              ))}
              <TableRow>
                <TableCell>Secretos en el código</TableCell>
                <TableCell colSpan={3} align="right">{resultadoJob(gitleaks?.conclusion)}</TableCell>
                <TableCell>{gitleaks?.conclusion === "success" ? <CheckCircleIcon color="success" fontSize="small" /> : <WarningAmberIcon color="warning" fontSize="small" />}</TableCell>
              </TableRow>
              {d.ci && (
                <TableRow>
                  <TableCell>pip-audit y npm audit (CI)</TableCell>
                  <TableCell colSpan={3} align="right">{resultadoJob(d.ci.conclusion)}</TableCell>
                  <TableCell>{d.ci.conclusion === "success" ? <CheckCircleIcon color="success" fontSize="small" /> : <WarningAmberIcon color="warning" fontSize="small" />}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {!comp.length && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Las imágenes aparecen después del próximo escaneo diario (05:00), que guarda el resumen para la Mesa.
            </Typography>
          )}
          <Box sx={{ mt: 3 }}>{plazos}</Box>
        </Paper>

        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
            <Typography variant="h6">Hallazgos abiertos</Typography>
            <Chip size="small" variant="outlined" color="error" label="Desde riesgo medio" />
          </Stack>
          {!dep.alertas.length && !(d.hallazgos ?? []).length ? (
            <Alert severity="success">No hay vulnerabilidades abiertas de riesgo medio o mayor.</Alert>
          ) : (
            <TableContainer sx={{ maxHeight: 520 }}>
              <Table size="small" stickyHeader>
                <TableHead><TableRow><TableCell>Riesgo</TableCell><TableCell>Qué es</TableCell><TableCell>Qué se hace</TableCell><TableCell>Seguimiento</TableCell><TableCell>Plazo</TableCell></TableRow></TableHead>
                <TableBody>
                  {dep.alertas.filter((a) => a.severidad !== "LOW").map((a) => (
                    <TableRow key={`d${a.numero}`}>
                      <TableCell><ChipSev s={a.severidad} /></TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{a.paquete}</Typography>
                        <Typography variant="caption" color="text.secondary">{a.resumen}</Typography>
                      </TableCell>
                      <TableCell>{a.corregida ? `Actualizar a ${a.corregida}` : "Sin versión corregida aún"}</TableCell>
                      <TableCell><Link href={a.url} target="_blank" rel="noopener">Dependabot #{a.numero}</Link></TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{a.vence ? `Vence ${fecha(a.vence)}` : "—"}</TableCell>
                    </TableRow>
                  ))}
                  {(d.hallazgos ?? []).map((h) => (
                    <TableRow key={`${h.imagen}${h.id}${h.paquete}`}>
                      <TableCell><ChipSev s={h.severidad} /></TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{h.paquete} en {h.imagen.replace("Imagen ", "imagen ")}</Typography>
                        <Typography variant="caption" color="text.secondary">{h.titulo}</Typography>
                      </TableCell>
                      <TableCell>{h.corregida ? `Actualizar a ${h.corregida}` : "Esperar corrección"}</TableCell>
                      <TableCell><Link href={`https://avd.aquasec.com/nvd/${h.id.toLowerCase()}`} target="_blank" rel="noopener">{h.id}</Link></TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{h.severidad in d.plazos ? `${d.plazos[h.severidad as "HIGH"]} días` : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          <Box sx={{ mt: 2, p: 2, bgcolor: "action.hover", borderRadius: 2 }}>
            <Typography variant="body2">
              <b>Cómo se trabaja:</b> un PR que agrega una vulnerabilidad crítica o alta con corrección disponible, o un secreto, no se puede fusionar.
              Las correcciones que tocan producción pasan como <b>cambio estándar</b>. Si algo no se puede corregir, se registra como riesgo aceptado en
              <code> .trivyignore</code> con su fecha de revisión.
            </Typography>
          </Box>
          {d.actualizado && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Datos de GitHub leídos {fechaHora(d.actualizado)}</Typography>}
        </Paper>
      </Box>
    </Stack>
  );
}
