import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, FormControlLabel, List, ListItemButton, ListItemIcon, ListItemText, Paper, Switch } from "@mui/material";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import { get, post } from "../api/client";
import type { Notificacion } from "../api/types";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import { ICONO_SEVERIDAD } from "../components/Layout";
import { fechaHora } from "../utils/formato";

export default function Notificaciones() {
  const [soloNoLeidas, setSoloNoLeidas] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["notificaciones", "lista", soloNoLeidas],
    queryFn: () => get<Notificacion[]>("/notificaciones", { solo_no_leidas: soloNoLeidas, limite: 200 }),
  });
  const invalidar = () => qc.invalidateQueries({ queryKey: ["notificaciones"] });
  const marcar = useMutation({ mutationFn: (id: number) => post(`/notificaciones/${id}/leida`), onSuccess: invalidar });
  const todas = useMutation({ mutationFn: () => post("/notificaciones/leidas"), onSuccess: invalidar });

  return (
    <>
      <Encabezado
        titulo="Notificaciones"
        subtitulo="Alertas de SLA, asignaciones, escalamientos y cambios en sus tickets"
        acciones={
          <>
            <FormControlLabel control={<Switch checked={soloNoLeidas} onChange={(e) => setSoloNoLeidas(e.target.checked)} />} label="Solo no leídas" />
            <Button startIcon={<DoneAllIcon />} onClick={() => todas.mutate()}>
              Marcar todas como leídas
            </Button>
          </>
        }
      />
      <Paper>
        {q.isLoading ? (
          <Cargando />
        ) : q.error ? (
          <ErrorCarga error={q.error} />
        ) : !q.data?.length ? (
          <Vacio texto="No hay notificaciones" />
        ) : (
          <List disablePadding>
            {q.data.map((n) => (
              <ListItemButton
                key={n.id}
                divider
                sx={{ alignItems: "flex-start", bgcolor: n.leida ? undefined : "#EEF5FC" }}
                onClick={() => {
                  if (!n.leida) marcar.mutate(n.id);
                  if (n.ticket_id) navigate(`/tickets/${n.ticket_id}`);
                }}
              >
                <ListItemIcon sx={{ minWidth: 36, mt: 0.5 }}>{ICONO_SEVERIDAD[n.severidad] ?? ICONO_SEVERIDAD.INFO}</ListItemIcon>
                <ListItemText
                  primary={n.titulo}
                  secondary={`${n.mensaje} · ${fechaHora(n.fecha)}`}
                  slotProps={{ primary: { sx: { fontWeight: n.leida ? 400 : 600 } } }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </Paper>
    </>
  );
}
