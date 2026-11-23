/** Clasificación del ticket (Pública / Interna / Confidencial) y retención legal (ISO 27001, mejora 42). */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Switch, TextField, Tooltip,
} from "@mui/material";
import LockIcon from "@mui/icons-material/LockOutlined";
import GavelIcon from "@mui/icons-material/Gavel";
import { put } from "../api/client";
import { NOMBRE_CLASIFICACION, type Clasificacion } from "../api/cumplimiento";
import type { TicketDetalle } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "./Aviso";
import { Stack } from "./Pila";
import { P } from "../utils/permisos";

const ORDEN: Clasificacion[] = ["PUBLICA", "INTERNA", "CONFIDENCIAL"];
const AYUDA: Record<Clasificacion, string> = {
  PUBLICA: "Se puede compartir con clientes y proveedores.",
  INTERNA: "Solo para el personal de ADUCORP (por defecto).",
  CONFIDENCIAL: "Solo el solicitante, el responsable, el supervisor y TI. Los correos no llevan el contenido, solo el enlace.",
};

export function ChipClasificacion({ t }: { t: TicketDetalle }) {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [abierto, setAbierto] = useState(false);
  const actual = (t.clasificacion ?? "INTERNA") as Clasificacion;
  const [nivel, setNivel] = useState<Clasificacion>(actual);
  const [motivo, setMotivo] = useState("");
  const [legal, setLegal] = useState(!!t.retencion_legal);
  const [motivoLegal, setMotivoLegal] = useState("");
  const editable = t.acciones.includes("clasificar");
  const admin = puede(P.SISTEMA);
  const baja = ORDEN.indexOf(nivel) < ORDEN.indexOf(actual);

  const guardar = useMutation({
    mutationFn: async () => {
      if (nivel !== actual) await put(`/tickets/${t.id}/clasificacion`, { clasificacion: nivel, motivo: motivo || null });
      if (admin && legal !== !!t.retencion_legal) await put(`/tickets/${t.id}/retencion-legal`, { activa: legal, motivo: motivoLegal });
    },
    onSuccess: () => {
      setAbierto(false);
      avisar("Clasificación guardada");
      qc.invalidateQueries({ queryKey: ["ticket", String(t.id)] });
      qc.invalidateQueries({ queryKey: ["ticket"] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  if (actual === "INTERNA" && !t.retencion_legal && !editable && !admin) return null;
  const abrir = () => {
    setNivel(actual); setMotivo(""); setLegal(!!t.retencion_legal); setMotivoLegal(""); setAbierto(true);
  };
  const color = actual === "CONFIDENCIAL" ? { bgcolor: "#FDE7E7", color: "#9B1C1C", "& .MuiChip-icon": { color: "#9B1C1C" } }
    : actual === "PUBLICA" ? { bgcolor: "#E6F4EA", color: "#1E6B34" } : { bgcolor: "#EEF2F7", color: "#33415C" };
  return (
    <>
      <Tooltip title={AYUDA[actual]}>
        <Chip size="small" icon={actual === "CONFIDENCIAL" ? <LockIcon /> : undefined} label={NOMBRE_CLASIFICACION[actual]}
          onClick={editable || admin ? abrir : undefined} sx={color} />
      </Tooltip>
      {t.retencion_legal && (
        <Tooltip title="Retención legal: este ticket no se depura aunque cumpla el plazo de conservación">
          <Chip size="small" icon={<GavelIcon />} label="Retención legal" variant="outlined" onClick={admin ? abrir : undefined} />
        </Tooltip>
      )}
      <Dialog open={abierto} onClose={() => setAbierto(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Clasificación de la información</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="Clasificación" value={nivel} disabled={!editable} onChange={(e) => setNivel(e.target.value as Clasificacion)}
              helperText={AYUDA[nivel]}>
              {ORDEN.map((n) => <MenuItem key={n} value={n}>{NOMBRE_CLASIFICACION[n]}</MenuItem>)}
            </TextField>
            {baja && (
              <TextField label="Motivo para bajar la clasificación" value={motivo} onChange={(e) => setMotivo(e.target.value)} required
                multiline minRows={2} slotProps={{ htmlInput: { maxLength: 300 } }} helperText="Queda en el historial del ticket y en Auditoría." />
            )}
            {admin && (
              <>
                <FormControlLabel control={<Switch checked={legal} onChange={(e) => setLegal(e.target.checked)} />}
                  label="Retención legal (reclamo, auditoría de SENAE, proceso legal)" />
                {legal !== !!t.retencion_legal && (
                  <TextField label="Motivo" value={motivoLegal} onChange={(e) => setMotivoLegal(e.target.value)} required slotProps={{ htmlInput: { maxLength: 300 } }} />
                )}
                <Alert severity="info" variant="outlined">Con retención legal el ticket nunca se depura, aunque cumpla el plazo de conservación.</Alert>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" disabled={guardar.isPending || (baja && motivo.trim().length < 5)
            || (admin && legal !== !!t.retencion_legal && motivoLegal.trim().length < 5)} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
