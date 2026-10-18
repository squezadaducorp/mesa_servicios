import type { ReactNode } from "react";
import { Alert, Box, CircularProgress, Stack, Typography } from "@mui/material";

export function Cargando({ alto = 240 }: { alto?: number }) {
  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: alto }}>
      <CircularProgress />
    </Box>
  );
}

export function ErrorCarga({ error }: { error: unknown }) {
  return <Alert severity="error">{error instanceof Error ? error.message : "No se pudo cargar la información"}</Alert>;
}

export function Encabezado({ titulo, subtitulo, acciones }: { titulo: string; subtitulo?: ReactNode; acciones?: ReactNode }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 3, alignItems: { sm: "center" }, justifyContent: "space-between" }}>
      <Box>
        <Typography variant="h5">{titulo}</Typography>
        {subtitulo && (
          <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
            {subtitulo}
          </Typography>
        )}
      </Box>
      {acciones && <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>{acciones}</Stack>}
    </Stack>
  );
}

export function Vacio({ texto }: { texto: string }) {
  return (
    <Box sx={{ py: 6, textAlign: "center", color: "text.secondary" }}>
      <Typography variant="body2">{texto}</Typography>
    </Box>
  );
}
