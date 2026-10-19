import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Box, Button, Divider, IconButton, InputAdornment, Link, Paper, Stack, TextField, Typography } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import { useAuth } from "../auth/AuthContext";
import { get, urlApi } from "../api/client";
import { mensajeError } from "../components/Aviso";
import { marca } from "../theme";

export default function Login() {
  const { login, usuario } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [ver, setVer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const destino = (location.state as { desde?: string } | null)?.desde ?? "/";
  const [params] = useSearchParams();
  const errorSso = params.get("error_sso");
  const [emergencia, setEmergencia] = useState(false);
  const config = useQuery({
    queryKey: ["auth", "entra"],
    queryFn: () => get<{ activo: boolean; permitir_local: boolean }>("/auth/entra/config"),
    staleTime: Infinity,
  });
  const sso = config.data?.activo ?? false;
  const mostrarFormulario = !sso || emergencia;

  if (usuario) return <Navigate to={usuario.debe_cambiar_clave ? "/cambiar-clave" : destino} replace />;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const u = await login(correo.trim(), clave);
      navigate(u.debe_cambiar_clave ? "/cambiar-clave" : destino, { replace: true });
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", gridTemplateColumns: { xs: "1fr", md: "1.1fr 1fr" } }}>
      <Box
        sx={{
          display: { xs: "none", md: "flex" },
          flexDirection: "column",
          justifyContent: "space-between",
          p: 6,
          color: "#fff",
          background: `linear-gradient(150deg, ${marca.navy} 0%, ${marca.azulOscuro} 55%, ${marca.azul} 100%)`,
        }}
      >
        <Box component="img" src="/isotipo.png" alt="" sx={{ width: 64, bgcolor: "#fff", borderRadius: 3, p: 1 }} />
        <Box>
          <Typography variant="h3" sx={{ fontWeight: 800, color: "#fff", mb: 2 }}>
            Mesa de Servicios
          </Typography>
          <Typography sx={{ color: marca.celeste, fontSize: 18, maxWidth: 460 }}>
            Gestión de requerimientos aduaneros con control de SLA, escalamiento automático e indicadores en tiempo real.
          </Typography>
        </Box>
        <Typography variant="caption" sx={{ color: "#8FA6C5" }}>
          © {new Date().getFullYear()} ADUCORP · Agencia de Aduanas · Ecuador
        </Typography>
      </Box>
      <Box sx={{ display: "grid", placeItems: "center", p: 2, bgcolor: "background.default" }}>
        <Paper sx={{ p: { xs: 3, sm: 5 }, width: "100%", maxWidth: 440 }}>
          <Box component="img" src="/logo-aducorp.png" alt="ADUCORP" sx={{ height: 56, mb: 3, display: "block", mx: "auto" }} />
          <Typography variant="h5" sx={{ textAlign: "center", mb: 0.5 }}>
            Iniciar sesión
          </Typography>
          <Typography variant="body2" sx={{ textAlign: "center", color: "text.secondary", mb: 3 }}>
            {sso ? "Use su cuenta de Microsoft 365 de ADUCORP" : "Use su correo corporativo o usuario de dominio"}
          </Typography>
          {errorSso && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorSso}
            </Alert>
          )}
          {sso && (
            <Stack spacing={1.5} sx={{ mb: mostrarFormulario ? 3 : 0 }}>
              <Button
                variant="contained"
                size="large"
                href={urlApi(`/auth/entra/login?destino=${encodeURIComponent(destino)}`)}
                startIcon={<LogoMicrosoft />}
              >
                Iniciar sesión con Microsoft
              </Button>
              {config.data?.permitir_local && !emergencia && (
                <Link component="button" type="button" variant="caption" onClick={() => setEmergencia(true)} sx={{ alignSelf: "center" }}>
                  Acceso de emergencia
                </Link>
              )}
              {mostrarFormulario && <Divider>o con cuenta de emergencia</Divider>}
            </Stack>
          )}
          {mostrarFormulario && (
          <form onSubmit={enviar}>
            <Stack spacing={2}>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField label="Correo o usuario" value={correo} onChange={(e) => setCorreo(e.target.value)} autoComplete="username" autoFocus required fullWidth size="medium" />
              <TextField
                label="Contraseña"
                type={ver ? "text" : "password"}
                value={clave}
                onChange={(e) => setClave(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
                size="medium"
                slotProps={{
                  input: {
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setVer(!ver)} edge="end" aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"}>
                          {ver ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  },
                }}
              />
              <Button type="submit" variant={sso ? "outlined" : "contained"} size="large" disabled={enviando}>
                {enviando ? "Ingresando…" : "Ingresar"}
              </Button>
            </Stack>
          </form>
          )}
        </Paper>
      </Box>
    </Box>
  );
}

function LogoMicrosoft() {
  return (
    <Box component="svg" viewBox="0 0 21 21" sx={{ width: 18, height: 18 }} aria-hidden>
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </Box>
  );
}
