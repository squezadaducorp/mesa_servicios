import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, AlertTitle, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField, Typography,
} from "@mui/material";
import { Stack } from "./Pila";
import CampaignIcon from "@mui/icons-material/Campaign";
import GroupAddIcon from "@mui/icons-material/GroupAdd";
import CheckIcon from "@mui/icons-material/Check";
import { del, get, post } from "../api/client";
import type { AvisoGeneral } from "../api/tercera";
import { mensajeError, useAviso } from "./Aviso";
import { fechaHora } from "../utils/formato";

export function useAvisosActivos() {
  return useQuery({ queryKey: ["avisos", "activos"], queryFn: () => get<AvisoGeneral[]>("/avisos/activos"), refetchInterval: 60_000 });
}

function BotonAfecta({ a }: { a: AvisoGeneral }) {
  const qc = useQueryClient();
  const avisar = useAviso();
  const [abierto, setAbierto] = useState(false);
  const [comentario, setComentario] = useState("");
  const marcar = useMutation({
    mutationFn: () => post(`/avisos/${a.id}/afecta`, { comentario: comentario.trim() || null }),
    onSuccess: () => {
      avisar("Listo: le avisaremos por correo cuando se resuelva");
      setAbierto(false);
      qc.invalidateQueries({ queryKey: ["avisos"] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const quitar = useMutation({
    mutationFn: () => del(`/avisos/${a.id}/afecta`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["avisos"] }),
  });
  return (
    <Stack spacing={0.5} alignItems={{ xs: "flex-start", sm: "flex-end" }} sx={{ flexShrink: 0 }}>
      {a.me_afecta ? (
        <Button size="small" variant="outlined" color="inherit" startIcon={<CheckIcon />} onClick={() => quitar.mutate()}>Ya no me afecta</Button>
      ) : (
        <Button variant="contained" color="error" startIcon={<GroupAddIcon />} onClick={() => setAbierto(true)}>A mí también me afecta</Button>
      )}
      <Typography variant="caption" color="text.secondary">
        {a.afectados === 1 ? "1 persona lo reportó" : `${a.afectados} personas ya lo reportaron`}
      </Typography>
      <Dialog open={abierto} onClose={() => setAbierto(false)} maxWidth="xs" fullWidth>
        <DialogTitle>A mí también me afecta</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Queda registrado sin crear otro ticket, y le llega un correo con cada novedad y cuando se resuelva.
          </Typography>
          <TextField fullWidth multiline minRows={2} label="Comentario (opcional)" placeholder="p. ej. tengo una DAI que vence hoy"
            value={comentario} onChange={(e) => setComentario(e.target.value)} slotProps={{ htmlInput: { maxLength: 500 } }} />
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" color="error" disabled={marcar.isPending} onClick={() => marcar.mutate()}>Confirmar</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

export function TarjetaAviso({ a, sx }: { a: AvisoGeneral; sx?: object }) {
  const resuelto = a.estado === "RESUELTO";
  return (
    <Alert severity={resuelto ? "success" : a.estado === "MONITOREANDO" ? "warning" : "error"} icon={<CampaignIcon fontSize="large" />}
      sx={{ border: "1px solid #E9A6A6", alignItems: "center", "& .MuiAlert-message": { flex: 1 }, ...sx }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
        <Box sx={{ flex: 1 }}>
          <AlertTitle sx={{ fontWeight: 700, mb: 0.3 }}>{a.titulo}</AlertTitle>
          {a.mensaje} {!resuelto && <b>No hace falta crear otro ticket.</b>}
          <Box sx={{ mt: 0.6 }}>
            <Typography variant="caption">
              Última actualización {fechaHora(a.ultima_actualizacion)} · {a.estado_nombre}
              {a.proxima_novedad ? ` · próxima novedad ${a.proxima_novedad}` : ""}
            </Typography>
          </Box>
        </Box>
        {!resuelto && <BotonAfecta a={a} />}
      </Stack>
    </Alert>
  );
}

/** Banner superior: avisos generales vigentes para el área de la persona. */
export function BannerAvisosGenerales() {
  const q = useAvisosActivos();
  if (!q.data?.length) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {q.data.map((a) => <TarjetaAviso key={a.id} a={a} />)}
    </Stack>
  );
}
