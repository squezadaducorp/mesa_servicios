import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Alert, Box, Button, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { post } from "../api/client";
import type { TokenSalida } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError } from "../components/Aviso";

/** Regreso desde Microsoft Entra ID: cambia el código de un solo uso por la sesión de la Mesa. */
export default function EntraRetorno() {
  const { aplicarToken } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const usado = useRef(false);
  const fragmento = new URLSearchParams(window.location.hash.slice(1));
  const codigo = fragmento.get("codigo");
  const destino = fragmento.get("destino") ?? "/";

  useEffect(() => {
    if (!codigo || usado.current) return;
    usado.current = true; // StrictMode monta dos veces: el código sirve una sola vez
    window.history.replaceState(null, "", window.location.pathname); // el código no queda en el historial
    post<TokenSalida>("/auth/entra/intercambio", { codigo })
      .then((t) => {
        aplicarToken(t);
        navigate(destino.startsWith("/") && !destino.startsWith("//") ? destino : "/", { replace: true });
      })
      .catch((e) => setError(mensajeError(e)));
  }, [codigo, destino, aplicarToken, navigate]);

  if (!codigo && !usado.current) return <Navigate to="/login" replace />;
  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", p: 2, bgcolor: "background.default" }}>
      <Paper sx={{ p: 4, width: "100%", maxWidth: 420, textAlign: "center" }}>
        {error ? (
          <Stack spacing={2}>
            <Alert severity="error">{error}</Alert>
            <Button variant="contained" href="/login">
              Volver a iniciar sesión
            </Button>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ alignItems: "center" }}>
            <CircularProgress />
            <Typography>Ingresando con su cuenta de Microsoft…</Typography>
          </Stack>
        )}
      </Paper>
    </Box>
  );
}
