/** Cronómetro de la barra superior (31): el registro que corre o el último en pausa, visible en toda la Mesa. */
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import TimerIcon from "@mui/icons-material/TimerOutlined";
import PauseIcon from "@mui/icons-material/Pause";
import PlayIcon from "@mui/icons-material/PlayArrow";
import { get, post } from "../../api/client";
import type { RegistroTiempo } from "../../api/ronda4c";
import { mensajeError, useAviso } from "../../components/Aviso";
import { reloj, useSegundos } from "./TiempoTrabajado";

export default function CronometroBarra({ activo: habilitado }: { activo: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({
    queryKey: ["tiempo", "activo"],
    queryFn: () => get<{ activo: RegistroTiempo | null }>("/tiempo/activo"),
    enabled: habilitado,
    refetchInterval: 120_000,
  });
  const r = q.data?.activo ?? null;
  const segundos = useSegundos(r);
  const accion = useMutation({
    mutationFn: (a: "pausar" | "reanudar") => post<{ activo: RegistroTiempo | null }>(`/tiempo/registros/${r!.id}/${a}`),
    onSuccess: (d) => {
      qc.setQueryData(["tiempo", "activo"], { activo: d.activo });
      qc.invalidateQueries({ queryKey: ["tiempo", r!.tipo] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (!r) return null;
  const corre = r.estado === "CORRIENDO";
  return (
    <Box
      sx={{
        display: "flex", alignItems: "center", gap: 0.5, pl: 1.2, pr: 0.5, py: 0.25, borderRadius: 5,
        bgcolor: corre ? "#E8F5E9" : "#FFF8E1", border: `1px solid ${corre ? "#A5D6A7" : "#FFE082"}`,
      }}
    >
      <TimerIcon fontSize="small" sx={{ color: corre ? "#2E7D32" : "#8A5A00" }} />
      <Tooltip title={`${r.actividad || "Trabajo"} · abrir ${r.numero}`}>
        <Typography
          component="button"
          onClick={() => navigate(r.ruta)}
          sx={{ border: 0, bgcolor: "transparent", cursor: "pointer", font: "inherit", fontSize: 14, fontWeight: 700, color: "text.primary", p: 0 }}
        >
          <Box component="span" sx={{ display: { xs: "none", sm: "inline" }, fontWeight: 600, color: "primary.main", mr: 0.75 }}>{r.numero}</Box>
          <Box component="span" sx={{ fontVariantNumeric: "tabular-nums" }}>{reloj(segundos)}</Box>
        </Typography>
      </Tooltip>
      <IconButton size="small" aria-label={corre ? "Pausar cronómetro" : "Reanudar cronómetro"} disabled={accion.isPending}
        onClick={() => accion.mutate(corre ? "pausar" : "reanudar")}>
        {corre ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
      </IconButton>
    </Box>
  );
}
