import { useState, type FormEvent } from "react";
import { Alert, Box, Button, Checkbox, Chip, Divider, FormControlLabel, Link, TextField, Typography } from "@mui/material";
import { Stack } from "../components/Pila";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import KeyIcon from "@mui/icons-material/Key";
import PhoneIphoneIcon from "@mui/icons-material/PhoneIphone";
import { post } from "../api/client";
import type { Activacion, SegundoPaso } from "../api/cuarta";
import type { TokenSalida } from "../api/types";
import { mensajeError } from "../components/Aviso";
import { CodigoCajas, CodigosRespaldo, PasosAuthenticator } from "../components/DosPasos";

const Nuevo = () => <Chip size="small" label="NUEVO" sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", fontWeight: 700, fontSize: 11, height: 22 }} />;

/** Segundo paso del inicio de sesión: verificar el código o, la primera vez con la política activa, configurarlo. */
export default function LoginSegundoPaso({ paso, correo, onListo, onVolver }: {
  paso: SegundoPaso; correo: string; onListo: (t: TokenSalida) => void; onVolver: () => void;
}) {
  const [codigo, setCodigo] = useState("");
  const [respaldo, setRespaldo] = useState(false);
  const [confiar, setConfiar] = useState(paso.dias_confianza > 0);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(paso.codigo_enviado ? `Enviamos un código a ${paso.correo_mascara}.` : null);
  const [enviando, setEnviando] = useState(false);
  const [metodo, setMetodo] = useState<"APP" | "CORREO">(paso.metodo ?? "APP");
  const [act, setAct] = useState<Activacion | null>(null);
  const [listo, setListo] = useState<TokenSalida | null>(null);
  const nombre = paso.nombre.split(" ")[0] ? paso.nombre : correo;

  const llamar = async <T,>(fn: () => Promise<T>) => {
    setError(null);
    setEnviando(true);
    try {
      return await fn();
    } catch (e) {
      setError(mensajeError(e));
      return null;
    } finally {
      setEnviando(false);
    }
  };

  const verificar = async (e: FormEvent) => {
    e.preventDefault();
    const t = await llamar(() => post<TokenSalida>("/auth/2fa/verificar", { desafio: paso.desafio, codigo: codigo.trim(), confiar }));
    if (t) onListo(t);
    else setCodigo("");
  };
  const enviarCorreo = async () => {
    const r = await llamar(() => post<{ enviado_a?: string }>("/auth/2fa/enviar-codigo", { desafio: paso.desafio }));
    if (r) {
      setMetodo("CORREO");
      setRespaldo(false);
      setCodigo("");
      setInfo(`Enviamos un código a ${r.enviado_a ?? paso.correo_mascara}. Vence en 10 minutos.`);
    }
  };
  const iniciarActivacion = async (m: "APP" | "CORREO") => {
    const r = await llamar(() => post<Activacion>("/auth/2fa/activar/iniciar", { desafio: paso.desafio, metodo: m }));
    if (r) { setAct(r); setMetodo(m); setCodigo(""); }
  };
  const confirmarActivacion = async (e: FormEvent) => {
    e.preventDefault();
    const t = await llamar(() => post<TokenSalida>("/auth/2fa/activar/confirmar", { desafio: paso.desafio, codigo, metodo, confiar }));
    if (t) {
      if (t.codigos_respaldo?.length) setListo(t);
      else onListo(t);
    } else setCodigo("");
  };

  // ---------- activación terminada: mostrar los códigos de respaldo antes de entrar
  if (listo) {
    return (
      <Box>
        <Typography variant="h5" sx={{ mb: 1 }}>¡Listo, {nombre}!</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          La verificación en dos pasos quedó activa. Guarde estos códigos: le sirven para entrar si no tiene el celular.
        </Typography>
        <CodigosRespaldo codigos={listo.codigos_respaldo!} cuenta={correo} />
        <Button fullWidth variant="contained" size="large" sx={{ mt: 3 }} onClick={() => onListo(listo)}>Ya los guardé, continuar</Button>
      </Box>
    );
  }

  // ---------- primera vez con la política obligatoria: configurar
  if (paso.modo === "ACTIVAR") {
    return (
      <Box component="form" onSubmit={confirmarActivacion}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <Typography variant="h5">Active la verificación en dos pasos</Typography>
          <Nuevo />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Hola, <b>{nombre}</b>. Desde ahora la Mesa pide un código además de la contraseña. Configúrelo una sola vez.
        </Typography>
        {!act ? (
          <Stack spacing={1.5}>
            <Button variant="contained" size="large" startIcon={<PhoneIphoneIcon />} onClick={() => iniciarActivacion("APP")} disabled={enviando}>
              Usar el celular (Microsoft o Google Authenticator)
            </Button>
            {paso.puede_correo && (
              <Button variant="outlined" size="large" startIcon={<MailOutlineIcon />} onClick={() => iniciarActivacion("CORREO")} disabled={enviando}>
                Recibir el código por correo
              </Button>
            )}
          </Stack>
        ) : (
          <>
            {act.metodo === "APP" ? <PasosAuthenticator a={act} /> : <Alert severity="info">Enviamos un código a {act.enviado_a}. Vence en 10 minutos.</Alert>}
            <Divider sx={{ my: 2.5 }} />
            <CodigoCajas valor={codigo} onCambio={setCodigo} autoFocus />
            {paso.dias_confianza > 0 && (
              <FormControlLabel sx={{ mt: 2 }} control={<Checkbox checked={confiar} onChange={(e) => setConfiar(e.target.checked)} />}
                label={`Confiar en este equipo por ${paso.dias_confianza} días`} />
            )}
            <Button type="submit" fullWidth variant="contained" size="large" sx={{ mt: 2 }} disabled={codigo.length !== 6 || enviando}>
              Activar e ingresar
            </Button>
          </>
        )}
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        <Link component="button" type="button" variant="body2" onClick={onVolver} sx={{ display: "block", mx: "auto", mt: 2.5 }}>Volver</Link>
      </Box>
    );
  }

  // ---------- verificar
  const textoMetodo = respaldo ? "Escriba uno de sus códigos de respaldo de 8 caracteres (cada uno sirve una sola vez)."
    : metodo === "CORREO" ? `Escriba el código de 6 dígitos que enviamos a ${paso.correo_mascara}.`
      : null;
  return (
    <Box component="form" onSubmit={verificar}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Typography variant="h5">Verificación en dos pasos</Typography>
        <Nuevo />
      </Stack>
      <Typography variant="body1" sx={{ mb: 2.5 }}>
        Hola, <b>{nombre}</b>.{" "}
        {textoMetodo ?? <>Abra <b>Microsoft Authenticator</b> en su celular y escriba el código de 6 dígitos de «Mesa ADUCORP».</>}
      </Typography>
      {info && !respaldo && <Alert severity="info" sx={{ mb: 2 }}>{info}</Alert>}
      {respaldo ? (
        <TextField fullWidth label="Código de respaldo" placeholder="XXXX-XXXX" value={codigo} autoFocus
          onChange={(e) => setCodigo(e.target.value.toUpperCase().slice(0, 9))} slotProps={{ htmlInput: { style: { fontFamily: "monospace", letterSpacing: 2 } } }} />
      ) : (
        <>
          <CodigoCajas valor={codigo} onCambio={setCodigo} autoFocus />
          {metodo === "APP" && <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 1 }}>El código cambia cada 30 segundos.</Typography>}
        </>
      )}
      {paso.dias_confianza > 0 && (
        <FormControlLabel sx={{ mt: 2 }} control={<Checkbox checked={confiar} onChange={(e) => setConfiar(e.target.checked)} />}
          label={`Confiar en este equipo por ${paso.dias_confianza} días`} />
      )}
      {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
      <Button type="submit" fullWidth variant="contained" size="large" sx={{ mt: 2 }}
        disabled={enviando || (respaldo ? codigo.replace("-", "").length !== 8 : codigo.length !== 6)}>
        {enviando ? "Verificando…" : "Verificar e ingresar"}
      </Button>
      <Divider sx={{ my: 2.5 }}><Typography variant="body2" color="text.secondary">¿No tiene el celular?</Typography></Divider>
      <Stack spacing={1.5} alignItems="center">
        {paso.puede_correo && (
          <Button fullWidth variant="outlined" startIcon={<MailOutlineIcon />} onClick={enviarCorreo} disabled={enviando}>
            {metodo === "CORREO" ? "Reenviar el código" : `Enviar un código a ${paso.correo_mascara}`}
          </Button>
        )}
        <Button startIcon={<KeyIcon />} onClick={() => { setRespaldo(!respaldo); setCodigo(""); setError(null); }}>
          {respaldo ? "Usar el código del celular" : "Usar un código de respaldo"}
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2.5 }}>
        ¿Cambió de celular? Pida a TI que restablezca su verificación (queda en Auditoría).
      </Typography>
      <Link component="button" type="button" variant="body2" onClick={onVolver} sx={{ display: "block", mx: "auto", mt: 1.5 }}>Volver</Link>
    </Box>
  );
}
