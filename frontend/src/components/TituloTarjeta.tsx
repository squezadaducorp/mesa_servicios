import { useState, type ReactNode } from "react";
import { Box, ButtonBase, Collapse, Paper, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
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

const CLAVE = "mesa.panel-ticket.abiertas";
function leerAbiertas(): string[] {
  try {
    return JSON.parse(localStorage.getItem(CLAVE) ?? "[]");
  } catch {
    return [];
  }
}

/**
 * Tarjeta plegable del panel lateral del ticket: muestra solo el título (y un resumen corto)
 * y se abre al hacer clic. Los botones de acción (Editar, + Vincular) aparecen dentro, al abrirla. Recuerda en este navegador cuáles dejó abiertas el usuario.
 */
export function TarjetaDesplegable({ id, icono, titulo, resumen, accion, children }: {
  id: string; icono: ReactNode; titulo: ReactNode; resumen?: ReactNode; accion?: ReactNode; children: ReactNode;
}) {
  const [abierta, setAbierta] = useState(() => leerAbiertas().includes(id));
  const cambiar = (v: boolean) => {
    setAbierta(v);
    try {
      const l = leerAbiertas().filter((x) => x !== id);
      localStorage.setItem(CLAVE, JSON.stringify(v ? [...l, id] : l));
    } catch {
      /* sin almacenamiento: solo no se recuerda */
    }
  };
  return (
    <Paper sx={{ overflow: "hidden" }}>
      <ButtonBase
        component="div"
        onClick={() => cambiar(!abierta)}
        aria-expanded={abierta}
        sx={{ width: "100%", display: "flex", alignItems: "center", gap: 1, px: 2.5, py: 1.6, textAlign: "left", "&:hover": { bgcolor: "#F7F9FC" } }}
      >
        <Box sx={{ display: "flex", color: "primary.main", "& svg": { fontSize: 22 } }}>{icono}</Box>
        <Typography variant="h6" noWrap sx={{ flex: 1, minWidth: 0, fontSize: "1.05rem", lineHeight: 1.3 }}>{titulo}</Typography>
        {resumen != null && resumen !== false && (
          <Typography variant="caption" sx={{ color: "text.secondary", bgcolor: "#EEF2F8", px: 1, py: 0.25, borderRadius: 10, fontWeight: 600, whiteSpace: "nowrap" }}>
            {resumen}
          </Typography>
        )}
        <ExpandMoreIcon sx={{ color: "text.secondary", transition: "transform .2s", transform: abierta ? "rotate(180deg)" : "none" }} />
      </ButtonBase>
      <Collapse in={abierta} unmountOnExit>
        <Box sx={{ px: 2.5, pb: 2.5, pt: 0.5 }}>
          {accion && <Box sx={{ display: "flex", justifyContent: "flex-end", mt: -0.5, mb: 0.5 }}>{accion}</Box>}
          {children}
        </Box>
      </Collapse>
    </Paper>
  );
}
