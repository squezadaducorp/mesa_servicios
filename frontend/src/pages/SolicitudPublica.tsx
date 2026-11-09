import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Box, Button, Link, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import { get, post } from "../api/client";
import { mensajeError } from "../components/Aviso";
import { Cargando } from "../components/Comunes";
import { marca } from "../theme";

type Formulario = {
  habilitado: boolean;
  empresa: string;
  token: string;
  categorias: { id: number; nombre: string; subcategorias: { id: number; nombre: string }[] }[];
};

const VACIO = { nombre: "", correo: "", telefono: "", empresa: "", asunto: "", descripcion: "" };

/** Formulario público: clientes y personas externas registran una solicitud sin tener cuenta en la Mesa. */
export default function SolicitudPublica() {
  const form = useQuery({ queryKey: ["publico", "formulario"], queryFn: () => get<Formulario>("/publico/formulario"), staleTime: 30 * 60_000, retry: 1 });
  const [datos, setDatos] = useState(VACIO);
  const [categoriaId, setCategoriaId] = useState<number | "">("");
  const [subId, setSubId] = useState<number | "">("");
  const [trampa, setTrampa] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [registrado, setRegistrado] = useState<{ numero: string; mensaje: string } | null>(null);

  const campo = (k: keyof typeof VACIO) => ({
    value: datos[k],
    onChange: (e: { target: { value: string } }) => setDatos({ ...datos, [k]: e.target.value }),
  });
  const categoria = form.data?.categorias.find((c) => c.id === categoriaId);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.data) return;
    setError(null);
    setEnviando(true);
    try {
      const r = await post<{ numero: string; mensaje: string }>("/publico/tickets", {
        ...datos,
        telefono: datos.telefono || null,
        empresa: datos.empresa || null,
        categoria_id: categoriaId || null,
        subcategoria_id: subId || null,
        token: form.data.token,
        sitio_web: trampa,
      });
      setRegistrado(r);
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  const nueva = () => {
    setRegistrado(null);
    setDatos({ ...VACIO, nombre: datos.nombre, correo: datos.correo, telefono: datos.telefono, empresa: datos.empresa });
    setCategoriaId("");
    setSubId("");
    form.refetch();
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Box sx={{ color: "#fff", background: `linear-gradient(150deg, ${marca.navy} 0%, ${marca.azulOscuro} 55%, ${marca.azul} 100%)`, px: 2, pt: 4, pb: 10 }}>
        <Box sx={{ maxWidth: 760, mx: "auto" }}>
          <Typography variant="h4" sx={{ fontWeight: 800, color: "#fff", mb: 1 }}>
            Mesa de Servicios
          </Typography>
          <Typography sx={{ color: marca.celeste, fontSize: 17 }}>
            Registre su solicitud y le responderemos por correo. No necesita una cuenta.
          </Typography>
        </Box>
      </Box>
      <Box sx={{ maxWidth: 760, mx: "auto", px: 2, mt: -7, pb: 6 }}>
        <Paper sx={{ p: { xs: 2.5, sm: 4 } }}>
          <Box component="img" src="/logo-aducorp.png" alt="ADUCORP" sx={{ height: 48, mb: 3, display: "block" }} />
          {form.isLoading && <Cargando alto={240} />}
          {form.isError && (
            <Alert severity="warning">
              El formulario no está disponible en este momento. Escríbanos a <b>soporte@aducorp.com.ec</b>.
            </Alert>
          )}
          {registrado && (
            <Stack spacing={2} sx={{ alignItems: "center", textAlign: "center", py: 3 }}>
              <CheckCircleIcon color="success" sx={{ fontSize: 64 }} />
              <Typography variant="h5">Solicitud registrada</Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, color: marca.azul }}>
                {registrado.numero}
              </Typography>
              <Typography sx={{ color: "text.secondary", maxWidth: 480 }}>{registrado.mensaje} Guarde este número para cualquier consulta.</Typography>
              <Button variant="outlined" onClick={nueva}>
                Registrar otra solicitud
              </Button>
            </Stack>
          )}
          {form.data && !registrado && (
            <form onSubmit={enviar}>
              <Stack spacing={2}>
                <Typography variant="h6">Sus datos</Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <TextField label="Nombre y apellido" required fullWidth autoComplete="name" slotProps={{ htmlInput: { minLength: 3, maxLength: 120 } }} {...campo("nombre")} />
                  <TextField label="Correo electrónico" type="email" required fullWidth autoComplete="email" {...campo("correo")} />
                </Stack>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <TextField label="Empresa (opcional)" fullWidth autoComplete="organization" slotProps={{ htmlInput: { maxLength: 150 } }} {...campo("empresa")} />
                  <TextField label="Teléfono (opcional)" fullWidth autoComplete="tel" slotProps={{ htmlInput: { maxLength: 30 } }} {...campo("telefono")} />
                </Stack>
                {/* Campo trampa para robots: las personas no lo ven */}
                <Box aria-hidden sx={{ position: "absolute", left: -10000, width: 1, height: 1, overflow: "hidden" }}>
                  <label>
                    Sitio web
                    <input tabIndex={-1} autoComplete="off" value={trampa} onChange={(e) => setTrampa(e.target.value)} />
                  </label>
                </Box>
                <Typography variant="h6" sx={{ pt: 1 }}>
                  Su solicitud
                </Typography>
                <TextField label="Asunto" required fullWidth slotProps={{ htmlInput: { minLength: 5, maxLength: 200 } }} {...campo("asunto")} />
                <TextField
                  label="Describa lo que necesita"
                  required
                  fullWidth
                  multiline
                  minRows={5}
                  helperText="Incluya números de trámite, DAI, factura o referencia si los tiene."
                  slotProps={{ htmlInput: { minLength: 10, maxLength: 4000 } }}
                  {...campo("descripcion")}
                />
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <TextField
                    select
                    label="Tipo de solicitud (opcional)"
                    fullWidth
                    value={categoriaId}
                    onChange={(e) => {
                      const id = e.target.value === "" ? "" : Number(e.target.value);
                      setCategoriaId(id);
                      setSubId(id === "" ? "" : form.data.categorias.find((c) => c.id === id)?.subcategorias[0]?.id ?? "");
                    }}
                    helperText="Si no está seguro, déjelo en blanco y lo clasificamos nosotros."
                  >
                    <MenuItem value="">No estoy seguro</MenuItem>
                    {form.data.categorias.map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.nombre}
                      </MenuItem>
                    ))}
                  </TextField>
                  {categoria && categoria.subcategorias.length > 1 && (
                    <TextField select label="Detalle" fullWidth value={subId} onChange={(e) => setSubId(Number(e.target.value))}>
                      {categoria.subcategorias.map((x) => (
                        <MenuItem key={x.id} value={x.id}>
                          {x.nombre}
                        </MenuItem>
                      ))}
                    </TextField>
                  )}
                </Stack>
                {error && <Alert severity="error">{error}</Alert>}
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Usaremos sus datos solo para atender esta solicitud.
                </Typography>
                <Button type="submit" variant="contained" size="large" disabled={enviando}>
                  {enviando ? "Enviando…" : "Enviar solicitud"}
                </Button>
              </Stack>
            </form>
          )}
        </Paper>
        <Typography variant="body2" sx={{ textAlign: "center", mt: 3, color: "text.secondary" }}>
          ¿Trabaja en ADUCORP?{" "}
          <Link component={RouterLink} to="/login" state={{ desde: "/tickets/nuevo" }}>
            Ingrese con su cuenta
          </Link>
        </Typography>
      </Box>
    </Box>
  );
}
