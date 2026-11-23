import { useMemo, useState, type ReactNode } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Box, Button, Chip, InputAdornment, Link, Paper, TextField, Typography } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ScheduleIcon from "@mui/icons-material/Schedule";
import TaskAltIcon from "@mui/icons-material/TaskAlt";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import PersonOffIcon from "@mui/icons-material/PersonOff";
import VpnKeyIcon from "@mui/icons-material/VpnKey";
import UsbIcon from "@mui/icons-material/Usb";
import LaptopIcon from "@mui/icons-material/Laptop";
import FolderSharedIcon from "@mui/icons-material/FolderShared";
import AlternateEmailIcon from "@mui/icons-material/AlternateEmail";
import VpnLockIcon from "@mui/icons-material/VpnLock";
import RoomServiceIcon from "@mui/icons-material/RoomServiceOutlined";
import { Stack } from "../../components/Pila";
import { get } from "../../api/client";
import type { CatalogoRespuesta, Servicio } from "../../api/cuarta";
import { useAuth } from "../../auth/AuthContext";
import { Cargando, ErrorCarga, Vacio } from "../../components/Comunes";
import { P } from "../../utils/permisos";

export const ICONOS: Record<string, ReactNode> = {
  alta: <PersonAddIcon />, baja: <PersonOffIcon />, llave: <VpnKeyIcon />, token: <UsbIcon />, equipo: <LaptopIcon />,
  carpeta: <FolderSharedIcon />, buzon: <AlternateEmailIcon />, vpn: <VpnLockIcon />, servicio: <RoomServiceIcon />,
};
export const ESPERA_JEFE = { bgcolor: "#FFF3D6", color: "#8A5A00", fontWeight: 600 };

export function IconoServicio({ icono, tam = 44 }: { icono: string; tam?: number }) {
  return (
    <Box sx={{ width: tam, height: tam, borderRadius: "50%", bgcolor: "#E8F1FA", color: "primary.main", display: "grid", placeItems: "center" }}>
      {ICONOS[icono] ?? ICONOS.servicio}
    </Box>
  );
}

function Tarjeta({ s }: { s: Servicio }) {
  const navigate = useNavigate();
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2.5, display: "flex", flexDirection: "column", height: "100%", cursor: "pointer", transition: "border-color .15s, box-shadow .15s",
        "&:hover": { borderColor: "primary.main", boxShadow: "0 0 0 1px #1367AC" } }}
      onClick={() => navigate(`/catalogo/${s.id}`)}
    >
      <IconoServicio icono={s.icono} />
      <Typography variant="h6" sx={{ fontSize: 17, mt: 2 }}>{s.nombre}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, flexGrow: 1 }}>{s.descripcion}</Typography>
      <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1, mt: 2 }}>
        <Chip size="small" variant="outlined" icon={<ScheduleIcon />} label={s.plazo} sx={{ fontWeight: 600 }} />
        {s.requiere_aprobacion && <Chip size="small" icon={<TaskAltIcon sx={{ color: "#8A5A00 !important" }} />} label="Aprueba su jefe" sx={ESPERA_JEFE} />}
      </Stack>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 2 }}>
        <Typography variant="caption" color="text.secondary">Lo pide: {s.lo_pide}</Typography>
        <Button size="small" endIcon={<ArrowForwardIcon />} onClick={(e) => { e.stopPropagation(); navigate(`/catalogo/${s.id}`); }}>
          Solicitar
        </Button>
      </Stack>
    </Paper>
  );
}

export default function Catalogo() {
  const { puede } = useAuth();
  const [texto, setTexto] = useState("");
  const [grupo, setGrupo] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["servicios"], queryFn: () => get<CatalogoRespuesta>("/servicios") });

  const visibles = useMemo(() => {
    const t = texto.trim().toLowerCase();
    return (q.data?.servicios ?? []).filter(
      (s) => (!grupo || s.grupo === grupo) && (!t || `${s.nombre} ${s.descripcion} ${s.grupo}`.toLowerCase().includes(t)),
    );
  }, [q.data, texto, grupo]);

  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const d = q.data!;

  return (
    <Box>
      <Typography variant="h5">Catálogo de servicios</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 3 }}>
        Elija lo que necesita. Cada servicio trae su propio formulario, así TI recibe todo lo necesario desde el primer momento.
      </Typography>

      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 1.5 }}>
          <TextField
            size="small" placeholder="¿Qué necesita? Ej.: ECUAPASS, portátil, carpeta" value={texto} onChange={(e) => setTexto(e.target.value)}
            sx={{ minWidth: { md: 340 } }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }}
          />
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1, flexGrow: 1 }}>
            {[null, ...d.grupos].map((g) => (
              <Chip key={g ?? "todos"} label={g ?? "Todos"} clickable color={grupo === g ? "primary" : "default"}
                variant={grupo === g ? "filled" : "outlined"} onClick={() => setGrupo(g)} sx={{ fontWeight: 600 }} />
            ))}
          </Stack>
          {puede(P.CREAR) && (
            <Link component={RouterLink} to="/tickets/nuevo" sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>¿No está su caso? Ticket libre</Link>
          )}
        </Stack>
      </Paper>

      {visibles.length === 0 ? (
        <Paper variant="outlined"><Vacio texto="No hay servicios que coincidan. Pruebe otra palabra o cree un ticket libre." /></Paper>
      ) : (
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
          {visibles.map((s) => <Tarjeta key={s.id} s={s} />)}
        </Box>
      )}

      <Box sx={{ display: "grid", gap: 2, mt: 3, gridTemplateColumns: { xs: "1fr", lg: "2.6fr 1fr" } }}>
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Mis solicitudes de servicio en curso</Typography>
          {d.mis_solicitudes.length === 0 ? (
            <Typography variant="body2" color="text.secondary">No tiene solicitudes del catálogo abiertas.</Typography>
          ) : (
            d.mis_solicitudes.map((x) => (
              <Stack key={x.ticket_id} direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }}
                sx={{ gap: { xs: 0.5, sm: 2 }, py: 1.25, borderTop: "1px solid", borderColor: "divider" }}>
                <Link component={RouterLink} to={`/tickets/${x.ticket_id}`} sx={{ fontWeight: 700, minWidth: 150, whiteSpace: "nowrap" }}>{x.numero}</Link>
                <Typography variant="body2" sx={{ flexGrow: 1 }}>{x.servicio}{x.detalle ? ` · ${x.detalle}` : ""}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: { sm: "right" } }}>{x.avance}</Typography>
              </Stack>
            ))
          )}
        </Paper>
        <Paper variant="outlined" sx={{ p: 2.5, bgcolor: "#EAF4FB", borderColor: "#CFE3F2" }}>
          <Stack direction="row" sx={{ gap: 1.5 }}>
            <InfoIcon color="primary" />
            <Typography variant="body2">
              Los servicios los define TI en <b>Administración › Catálogo de servicios</b>: campos del formulario, quién aprueba, tareas que se
              generan y tiempo comprometido.
            </Typography>
          </Stack>
        </Paper>
      </Box>
    </Box>
  );
}
