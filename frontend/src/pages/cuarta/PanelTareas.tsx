import { useMutation } from "@tanstack/react-query";
import { Box, Checkbox, LinearProgress, Paper, Typography } from "@mui/material";
import ChecklistIcon from "@mui/icons-material/Checklist";
import { Stack } from "../../components/Pila";
import { post } from "../../api/client";
import type { ServicioTicket } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { TituloTarjeta } from "../../components/TituloTarjeta";
import { fechaHora } from "../../utils/formato";

/** Tareas del ticket creado desde el catálogo de servicios (mejora 26). */
export default function PanelTareas({ ticketId, s, onCambio }: { ticketId: number; s: ServicioTicket; onCambio: () => void }) {
  const avisar = useAviso();
  const marcar = useMutation({
    mutationFn: ({ id, lista }: { id: number; lista: boolean }) => post(`/servicios/tickets/${ticketId}/tareas/${id}`, { lista }),
    onSuccess: onCambio,
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const listas = s.tareas.filter((x) => x.estado === "LISTA").length;
  return (
    <Paper sx={{ p: 2.5 }}>
      <TituloTarjeta icono={<ChecklistIcon />} titulo="Tareas del servicio" mb={0.5} />
      {s.servicio && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          {s.servicio} · plazo {s.plazo}
        </Typography>
      )}
      {s.tareas.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 1 }}>
            <LinearProgress variant="determinate" value={(100 * listas) / s.tareas.length} sx={{ flexGrow: 1, height: 6, borderRadius: 3 }} />
            <Typography variant="caption" color="text.secondary">{listas} de {s.tareas.length}</Typography>
          </Stack>
          {s.tareas.map((x) => (
            <Stack key={x.id} direction="row" alignItems="flex-start" sx={{ gap: 0.5, py: 0.5, borderTop: "1px solid", borderColor: "divider" }}>
              <Checkbox size="small" checked={x.estado === "LISTA"} disabled={!x.puede_marcar || marcar.isPending}
                onChange={(e) => marcar.mutate({ id: x.id, lista: e.target.checked })} sx={{ mt: -0.5 }}
                slotProps={{ input: { "aria-label": `Marcar «${x.titulo}» como lista` } }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" sx={{ textDecoration: x.estado === "LISTA" ? "line-through" : undefined,
                  color: x.estado === "LISTA" ? "text.secondary" : "text.primary" }}>{x.titulo}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {x.responsable ?? "Sin responsable"}{x.fecha_completada ? ` · lista ${fechaHora(x.fecha_completada)}` : ""}
                </Typography>
              </Box>
            </Stack>
          ))}
        </>
      )}
      {s.respuestas.length > 0 && (
        <Box sx={{ mt: 1.5, pt: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
          {s.respuestas.filter((r) => r.clave !== "observaciones").map((r) => (
            <Stack key={r.clave} direction="row" sx={{ gap: 1, py: 0.25 }}>
              <Typography variant="caption" color="text.secondary" sx={{ width: 110, flexShrink: 0 }}>{r.etiqueta}</Typography>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>{r.valor}</Typography>
            </Stack>
          ))}
        </Box>
      )}
    </Paper>
  );
}
