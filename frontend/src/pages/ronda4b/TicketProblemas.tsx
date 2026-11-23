import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Button, Chip, Link, Paper, Typography } from "@mui/material";
import BugReportIcon from "@mui/icons-material/BugReportOutlined";
import { Stack } from "../../components/Pila";
import { get, post } from "../../api/client";
import type { ProblemasDelTicket } from "../../api/ronda4b";
import { mensajeError, useAviso } from "../../components/Aviso";
import { EstadoProblemaChip } from "./comun";

/** En el detalle del ticket (solo equipo de TI): problemas a los que pertenece y errores conocidos que se le parecen (mejora 30). */
export default function TicketProblemas({ ticketId, onCambio }: { ticketId: number; onCambio: () => void }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const clave = ["problemas", "ticket", ticketId];
  const q = useQuery({ queryKey: clave, queryFn: () => get<ProblemasDelTicket>(`/problemas/ticket/${ticketId}`), staleTime: 60_000 });
  const aplicar = useMutation({
    mutationFn: (id: number) => post<ProblemasDelTicket>(`/problemas/${id}/aplicar/${ticketId}`, { responder: true }),
    onSuccess: (d) => { qc.setQueryData(clave, d); avisar("Ticket vinculado y respuesta enviada al solicitante"); onCambio(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const descartar = useMutation({
    mutationFn: (id: number) => post<ProblemasDelTicket>(`/problemas/${id}/descartar/${ticketId}`),
    onSuccess: (d) => qc.setQueryData(clave, d),
  });
  const d = q.data;
  if (!d || (!d.problemas.length && !d.coincidencias.length)) return null;
  return (
    <Box sx={{ mb: 2 }}>
      {d.coincidencias.map((c) => (
        <Paper key={c.id} variant="outlined" sx={{ p: 2, mb: 1.5, bgcolor: "#F7F2FD", borderColor: "#C9B2EC" }}>
          <Typography sx={{ fontWeight: 700, color: "#5B2E9E" }}>
            Coincide con <Link component={RouterLink} to={`/problemas/${c.id}`} sx={{ color: "inherit" }}>{c.numero}</Link> · {c.estado_nombre}
          </Typography>
          <Typography variant="body2" sx={{ my: 0.5 }}>{c.titulo}</Typography>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}><b>Solución temporal:</b> {c.solucion_temporal}</Typography>
          <Stack direction="row" sx={{ gap: 1, mt: 1.5, flexWrap: "wrap" }}>
            <Button variant="contained" size="small" disabled={aplicar.isPending} onClick={() => aplicar.mutate(c.id)}>Vincular y responder con la solución</Button>
            <Button size="small" onClick={() => descartar.mutate(c.id)}>No es esto</Button>
          </Stack>
        </Paper>
      ))}
      {d.problemas.length > 0 && (
        <Stack direction="row" alignItems="center" sx={{ gap: 1, flexWrap: "wrap" }}>
          <BugReportIcon fontSize="small" color="action" />
          <Typography variant="body2" color="text.secondary">Forma parte de</Typography>
          {d.problemas.map((p) => (
            <Chip key={p.id} size="small" clickable component={RouterLink} to={`/problemas/${p.id}`}
              label={<span>{p.numero} · {p.titulo}</span>} variant="outlined" />
          ))}
          {d.problemas.map((p) => <EstadoProblemaChip key={`e${p.id}`} estado={p.estado} nombre={p.estado_nombre} />)}
        </Stack>
      )}
    </Box>
  );
}
