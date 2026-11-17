import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, Divider, MenuItem, Stack, Switch, TextField, Typography } from "@mui/material";
import LockIcon from "@mui/icons-material/Lock";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import HistoryIcon from "@mui/icons-material/ManageHistory";
import { get, put } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { Delegacion } from "../api/types";
import { mensajeError, useAviso } from "./Aviso";
import { fechaHora } from "../utils/formato";

/** Sección «Crear tickets en nombre de otros» del usuario (apagada por defecto; queda en auditoría). */
export default function PermisoEnNombre({ usuarioId }: { usuarioId: number }) {
  const cat = useCatalogos();
  const qc = useQueryClient();
  const avisar = useAviso();
  const clave = ["admin", "en-nombre", usuarioId];
  const q = useQuery({ queryKey: clave, queryFn: () => get<Delegacion>(`/admin/usuarios/${usuarioId}/en-nombre`) });
  const [activa, setActiva] = useState(false);
  const [areas, setAreas] = useState<number[]>([]);
  const [hasta, setHasta] = useState("");
  useEffect(() => {
    if (q.data) {
      setActiva(q.data.activa);
      setAreas(q.data.areas ?? []);
      setHasta(q.data.hasta ?? "");
    }
  }, [q.data]);
  const guardar = useMutation({
    mutationFn: () => put<Delegacion>(`/admin/usuarios/${usuarioId}/en-nombre`, { activa, areas: areas.length ? areas : null, hasta: hasta || null }),
    onSuccess: (d) => {
      qc.setQueryData(clave, d);
      avisar(d.activa ? "Permiso «en nombre de» guardado" : "Permiso «en nombre de» desactivado");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const cambiado = q.data && (activa !== q.data.activa || hasta !== (q.data.hasta ?? "") || areas.join() !== (q.data.areas ?? []).join());
  const nombreArea = (id: number) => cat.data?.areas.find((a) => a.id === id)?.nombre ?? id;

  return (
    <Box>
      <Divider sx={{ mb: 2 }} />
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <Typography variant="subtitle2" sx={{ flex: 1 }}>Crear tickets en nombre de otras personas</Typography>
        <Switch checked={activa} onChange={(e) => setActiva(e.target.checked)} disabled={q.isLoading} />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Apagado por defecto. Útil para asistentes o jefes que reportan por su equipo. Lo activa un administrador y queda en la auditoría.
        {q.data?.activa && q.data.otorgado_por ? ` Otorgado por ${q.data.otorgado_por} (${fechaHora(q.data.fecha)}).` : ""}
      </Typography>
      {activa && (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <TextField select label="Puede hacerlo para personas de" value={areas}
            slotProps={{ select: { multiple: true, displayEmpty: true, renderValue: () => (areas.length ? `${areas.length} área(s) elegida(s)` : "Todas las áreas") }, inputLabel: { shrink: true } }}
            onChange={(e) => setAreas(e.target.value as unknown as number[])}>
            {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          {areas.length > 0 && (
            <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.8 }}>
              {areas.map((a) => <Chip key={a} size="small" color="primary" variant="outlined" label={nombreArea(a)} onDelete={() => setAreas(areas.filter((x) => x !== a))} />)}
            </Stack>
          )}
          <TextField label="Vigente hasta (opcional)" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} slotProps={{ inputLabel: { shrink: true } }}
            helperText="Útil para reemplazos temporales; se apaga solo." />
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.8 }}>Reglas que aplican siempre</Typography>
            {[
              [<LockIcon key="l" fontSize="small" sx={{ color: "#B57400" }} />, "Las categorías marcadas como restringidas (accesos, contraseñas, equipo nuevo) no se pueden pedir en nombre de otro."],
              [<MailOutlineIcon key="m" fontSize="small" color="primary" />, "La persona siempre recibe un correo de aviso con el motivo."],
              [<VisibilityIcon key="v" fontSize="small" color="primary" />, "Quien lo crea ve solo ese ticket, en solo lectura."],
              [<HistoryIcon key="h" fontSize="small" color="primary" />, "Todo queda en Auditoría con usuario, fecha, IP y motivo."],
            ].map(([i, t], k) => (
              <Stack key={k} direction="row" spacing={1} sx={{ mb: 0.6 }}>{i}<Typography variant="body2">{t}</Typography></Stack>
            ))}
          </Box>
        </Stack>
      )}
      {q.error && <Alert severity="error" sx={{ mt: 1 }}>{mensajeError(q.error)}</Alert>}
      <Stack direction="row" sx={{ justifyContent: "flex-end", mt: 1 }}>
        <Button size="small" variant="outlined" disabled={!cambiado || guardar.isPending} onClick={() => guardar.mutate()}>Guardar permiso</Button>
      </Stack>
    </Box>
  );
}
