import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { post } from "../api/client";
import type { TokenSalida } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";

const REGLAS = [
  { texto: "Al menos 10 caracteres", ok: (c: string) => c.length >= 10 },
  { texto: "Una mayúscula", ok: (c: string) => /[A-ZÁÉÍÓÚÑ]/.test(c) },
  { texto: "Una minúscula", ok: (c: string) => /[a-záéíóúñ]/.test(c) },
  { texto: "Un número", ok: (c: string) => /\d/.test(c) },
  { texto: "Un símbolo", ok: (c: string) => /[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]/.test(c) },
];

export default function CambiarClave() {
  const { usuario, aplicarToken } = useAuth();
  const avisar = useAviso();
  const navigate = useNavigate();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetir, setRepetir] = useState("");
  const [error, setError] = useState<string | null>(null);
  const valida = REGLAS.every((r) => r.ok(nueva)) && nueva === repetir;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const t = await post<TokenSalida>("/auth/cambiar-clave", { clave_actual: actual, clave_nueva: nueva });
      aplicarToken(t);
      avisar("Contraseña actualizada");
      navigate("/", { replace: true });
    } catch (err) {
      setError(mensajeError(err));
    }
  };

  return (
    <Box sx={{ display: "grid", placeItems: "center", py: 4 }}>
      <Paper sx={{ p: 4, width: "100%", maxWidth: 460 }}>
        <Typography variant="h5" sx={{ mb: 1 }}>
          Cambiar contraseña
        </Typography>
        {usuario?.debe_cambiar_clave && (
          <Alert severity="info" sx={{ mb: 2 }}>
            Por seguridad debe definir una contraseña nueva antes de continuar.
          </Alert>
        )}
        <form onSubmit={enviar}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField label="Contraseña actual" type="password" value={actual} onChange={(e) => setActual(e.target.value)} required autoComplete="current-password" />
            <TextField label="Contraseña nueva" type="password" value={nueva} onChange={(e) => setNueva(e.target.value)} required autoComplete="new-password" />
            <TextField
              label="Repita la contraseña nueva"
              type="password"
              value={repetir}
              onChange={(e) => setRepetir(e.target.value)}
              required
              autoComplete="new-password"
              error={!!repetir && repetir !== nueva}
              helperText={repetir && repetir !== nueva ? "No coincide" : " "}
            />
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              {REGLAS.map((r) => (
                <Typography component="li" variant="caption" key={r.texto} sx={{ color: r.ok(nueva) ? "success.main" : "text.secondary" }}>
                  {r.texto}
                </Typography>
              ))}
            </Box>
            <Button type="submit" variant="contained" disabled={!valida || !actual}>
              Guardar
            </Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  );
}
