import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AppBar, Avatar, Badge, Box, Button, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText,
  ListSubheader, Menu, MenuItem, Popover, Toolbar, Tooltip, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import NotificationsIcon from "@mui/icons-material/Notifications";
import DashboardIcon from "@mui/icons-material/SpaceDashboard";
import AssessmentIcon from "@mui/icons-material/Assessment";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import AddCircleIcon from "@mui/icons-material/AddCircle";
import PeopleIcon from "@mui/icons-material/People";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import CategoryIcon from "@mui/icons-material/Category";
import TimerIcon from "@mui/icons-material/Timer";
import HistoryIcon from "@mui/icons-material/ManageHistory";
import SettingsIcon from "@mui/icons-material/Settings";
import LogoutIcon from "@mui/icons-material/Logout";
import KeyIcon from "@mui/icons-material/Key";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ErrorIcon from "@mui/icons-material/Error";
import InfoIcon from "@mui/icons-material/Info";
import { useAuth } from "../auth/AuthContext";
import { useConteoNotificaciones } from "../api/hooks";
import { get, post } from "../api/client";
import type { Notificacion } from "../api/types";
import { P } from "../utils/permisos";
import { tiempoRelativo } from "../utils/formato";
import { marca } from "../theme";

const ANCHO = 252;

interface ItemNav {
  a: string;
  texto: string;
  icono: ReactNode;
  permisos?: string[];
}

const PRINCIPAL: ItemNav[] = [
  { a: "/dashboard", texto: "Dashboard", icono: <DashboardIcon />, permisos: [P.DASHBOARD] },
  { a: "/reportes", texto: "Indicadores", icono: <AssessmentIcon />, permisos: [P.REPORTE] },
  { a: "/tickets", texto: "Tickets", icono: <ConfirmationNumberIcon /> },
  { a: "/tickets/nuevo", texto: "Nuevo ticket", icono: <AddCircleIcon />, permisos: [P.CREAR] },
  { a: "/notificaciones", texto: "Notificaciones", icono: <NotificationsIcon /> },
];

const ADMIN: ItemNav[] = [
  { a: "/admin/usuarios", texto: "Usuarios", icono: <PeopleIcon />, permisos: [P.USUARIOS] },
  { a: "/admin/roles", texto: "Roles y permisos", icono: <AdminPanelSettingsIcon />, permisos: [P.ROLES] },
  { a: "/admin/catalogo", texto: "Categorías y clientes", icono: <CategoryIcon />, permisos: [P.CATALOGO] },
  { a: "/admin/sla", texto: "SLA y calendario", icono: <TimerIcon />, permisos: [P.SLA] },
  { a: "/admin/auditoria", texto: "Auditoría", icono: <HistoryIcon />, permisos: [P.AUDITORIA] },
  { a: "/admin/configuracion", texto: "Configuración", icono: <SettingsIcon />, permisos: [P.SISTEMA] },
];

function iniciales(nombre: string) {
  return nombre.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export const ICONO_SEVERIDAD: Record<string, ReactNode> = {
  CRITICO: <ErrorIcon sx={{ color: "error.main" }} fontSize="small" />,
  AVISO: <WarningAmberIcon sx={{ color: "warning.main" }} fontSize="small" />,
  INFO: <InfoIcon sx={{ color: "primary.main" }} fontSize="small" />,
};

function CampanaNotificaciones() {
  const [ancla, setAncla] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const conteo = useConteoNotificaciones(true);
  const lista = useQuery({
    queryKey: ["notificaciones", "recientes"],
    queryFn: () => get<Notificacion[]>("/notificaciones", { limite: 8 }),
    enabled: !!ancla,
  });
  const marcar = useMutation({
    mutationFn: (id: number) => post(`/notificaciones/${id}/leida`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notificaciones"] }),
  });
  const n = conteo.data?.no_leidas ?? 0;
  return (
    <>
      <Tooltip title="Notificaciones">
        <IconButton color="inherit" onClick={(e) => setAncla(e.currentTarget)} aria-label={`${n} notificaciones sin leer`}>
          <Badge badgeContent={n} color="error" max={99}>
            <NotificationsIcon />
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover
        open={!!ancla}
        anchorEl={ancla}
        onClose={() => setAncla(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 380, maxWidth: "calc(100vw - 32px)" } } }}
      >
        <Box sx={{ px: 2, py: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Notificaciones
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {n} sin leer
          </Typography>
        </Box>
        <Divider />
        <List dense sx={{ maxHeight: 420, overflow: "auto", py: 0 }}>
          {(lista.data ?? []).map((x) => (
            <ListItemButton
              key={x.id}
              sx={{ alignItems: "flex-start", bgcolor: x.leida ? undefined : "#EEF5FC" }}
              onClick={() => {
                if (!x.leida) marcar.mutate(x.id);
                setAncla(null);
                if (x.ticket_id) navigate(`/tickets/${x.ticket_id}`);
              }}
            >
              <ListItemIcon sx={{ minWidth: 32, mt: 0.5 }}>{ICONO_SEVERIDAD[x.severidad] ?? ICONO_SEVERIDAD.INFO}</ListItemIcon>
              <ListItemText
                primary={x.titulo}
                secondary={`${x.mensaje} · ${tiempoRelativo(x.fecha)}`}
                slotProps={{ primary: { sx: { fontWeight: x.leida ? 400 : 600 } } }}
              />
            </ListItemButton>
          ))}
          {lista.data?.length === 0 && (
            <Typography variant="body2" sx={{ p: 3, textAlign: "center", color: "text.secondary" }}>
              No tiene notificaciones
            </Typography>
          )}
        </List>
        <Divider />
        <Box sx={{ p: 1, textAlign: "center" }}>
          <Button
            size="small"
            onClick={() => {
              setAncla(null);
              navigate("/notificaciones");
            }}
          >
            Ver todas
          </Button>
        </Box>
      </Popover>
    </>
  );
}

export default function Layout() {
  const { usuario, logout, puede } = useAuth();
  const theme = useTheme();
  const escritorio = useMediaQuery(theme.breakpoints.up("md"));
  const [abierto, setAbierto] = useState(false);
  const [menuUsuario, setMenuUsuario] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const visibles = (items: ItemNav[]) => items.filter((i) => !i.permisos || puede(...i.permisos));
  const admin = visibles(ADMIN);

  const enlace = (i: ItemNav) => {
    const activo = i.a === "/tickets" ? location.pathname === "/tickets" || /^\/tickets\/\d+/.test(location.pathname) : location.pathname.startsWith(i.a);
    return (
      <ListItemButton
        key={i.a}
        component={NavLink}
        to={i.a}
        onClick={() => setAbierto(false)}
        selected={activo}
        sx={{
          mx: 1,
          borderRadius: 2,
          mb: 0.5,
          color: "#C9D6E8",
          "& .MuiListItemIcon-root": { color: "#8FB3D9", minWidth: 40 },
          "&.Mui-selected, &.Mui-selected:hover": { bgcolor: marca.azul, color: "#fff", "& .MuiListItemIcon-root": { color: "#fff" } },
          "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
        }}
      >
        <ListItemIcon>{i.icono}</ListItemIcon>
        <ListItemText primary={i.texto} />
      </ListItemButton>
    );
  };

  const contenidoMenu = (
    <Box sx={{ height: "100%", bgcolor: marca.navy, display: "flex", flexDirection: "column" }}>
      <Box sx={{ px: 2.5, py: 2.5, display: "flex", alignItems: "center", gap: 1.5 }}>
        <Box component="img" src="/isotipo.png" alt="" sx={{ width: 40, height: 40, objectFit: "contain", bgcolor: "#fff", borderRadius: 2, p: 0.5 }} />
        <Box>
          <Typography sx={{ color: "#fff", fontWeight: 700, lineHeight: 1.1 }}>ADUCORP</Typography>
          <Typography variant="caption" sx={{ color: marca.celeste }}>
            Mesa de Servicios
          </Typography>
        </Box>
      </Box>
      <List sx={{ pt: 1 }}>{visibles(PRINCIPAL).map(enlace)}</List>
      {admin.length > 0 && (
        <List
          subheader={
            <ListSubheader sx={{ bgcolor: "transparent", color: "#7C8CA6", fontSize: 11, letterSpacing: 1, lineHeight: "32px" }}>
              ADMINISTRACIÓN
            </ListSubheader>
          }
        >
          {admin.map(enlace)}
        </List>
      )}
      <Box sx={{ flex: 1 }} />
      <Typography variant="caption" sx={{ color: "#5D6E89", px: 2.5, py: 2 }}>
        v1.0 · Agencia de Aduanas
      </Typography>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <AppBar
        position="fixed"
        color="inherit"
        sx={{ width: { md: `calc(100% - ${ANCHO}px)` }, ml: { md: `${ANCHO}px` }, bgcolor: "#fff", borderBottom: "1px solid #E3E8F0" }}
      >
        <Toolbar sx={{ gap: 1 }}>
          {!escritorio && (
            <IconButton edge="start" onClick={() => setAbierto(true)} aria-label="Abrir menú">
              <MenuIcon />
            </IconButton>
          )}
          {!escritorio && <Box component="img" src="/logo-aducorp.png" alt="ADUCORP" sx={{ height: 30 }} />}
          <Box sx={{ flex: 1 }} />
          <CampanaNotificaciones />
          <Button
            color="inherit"
            onClick={(e) => setMenuUsuario(e.currentTarget)}
            sx={{ gap: 1, px: 1 }}
            startIcon={<Avatar sx={{ width: 32, height: 32, bgcolor: marca.azul, fontSize: 14 }}>{iniciales(usuario?.nombre ?? "?")}</Avatar>}
          >
            <Box sx={{ display: { xs: "none", sm: "block" }, textAlign: "left" }}>
              <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                {usuario?.nombre}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {usuario?.rol_nombre}
              </Typography>
            </Box>
          </Button>
          <Menu anchorEl={menuUsuario} open={!!menuUsuario} onClose={() => setMenuUsuario(null)}>
            <MenuItem
              onClick={() => {
                setMenuUsuario(null);
                navigate("/cambiar-clave");
              }}
            >
              <ListItemIcon>
                <KeyIcon fontSize="small" />
              </ListItemIcon>
              Cambiar contraseña
            </MenuItem>
            <MenuItem
              onClick={async () => {
                setMenuUsuario(null);
                await logout();
                navigate("/login");
              }}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              Cerrar sesión
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Box component="nav" sx={{ width: { md: ANCHO }, flexShrink: { md: 0 } }}>
        {escritorio ? (
          <Drawer variant="permanent" open slotProps={{ paper: { sx: { width: ANCHO } } }}>
            {contenidoMenu}
          </Drawer>
        ) : (
          <Drawer variant="temporary" open={abierto} onClose={() => setAbierto(false)} slotProps={{ paper: { sx: { width: ANCHO } } }}>
            {contenidoMenu}
          </Drawer>
        )}
      </Box>
      <Box component="main" sx={{ flex: 1, minWidth: 0, p: { xs: 2, md: 3 }, mt: 8 }}>
        <Outlet />
      </Box>
    </Box>
  );
}
