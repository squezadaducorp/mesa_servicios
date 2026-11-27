import type { ReactNode } from "react";
import { Box, Typography } from "@mui/material";
import { Stack } from "./Pila";

/**
 * Encabezado común de las tarjetas del panel lateral del ticket:
 * ícono azul + título + acción opcional a la derecha, con el mismo tamaño y espaciado en todas.
 */
export function TituloTarjeta({ icono, titulo, accion, mb = 1.5 }: { icono: ReactNode; titulo: ReactNode; accion?: ReactNode; mb?: number }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb, minHeight: 32 }}>
      <Box sx={{ display: "flex", color: "primary.main", "& svg": { fontSize: 22 } }}>{icono}</Box>
      <Typography variant="h6" sx={{ flex: 1, fontSize: "1.05rem", lineHeight: 1.3 }}>
        {titulo}
      </Typography>
      {accion}
    </Stack>
  );
}
