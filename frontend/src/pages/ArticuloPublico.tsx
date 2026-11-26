import { Link as RouterLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Box, Button, Chip, Divider, Paper, Typography } from "@mui/material";
import { get, urlApi } from "../api/client";
import { mensajeError } from "../components/Aviso";
import { Cargando } from "../components/Comunes";
import { Pasos, type FuenteImagen } from "../components/PasosArticulo";
import { fecha } from "../utils/formato";
import { marca } from "../theme";

interface ArticuloCompartido {
  id: number;
  titulo: string;
  categoria: string | null;
  sintoma: string | null;
  solucion: string;
  nota: string | null;
  fecha_actualizacion: string;
}

/** Artículo externo abierto desde el enlace para compartir: no pide iniciar sesión. */
export default function ArticuloPublico() {
  const { id, llave } = useParams();
  const base = `/publico/articulos/${id}/${llave}`;
  const q = useQuery({ queryKey: ["articulo-publico", id, llave], queryFn: () => get<ArticuloCompartido>(base), retry: false, refetchOnWindowFocus: false });
  const fuenteImagen: FuenteImagen = async (img) => {
    const r = await fetch(urlApi(`${base}/imagenes/${img}`));
    if (!r.ok) throw new Error("Imagen no disponible");
    return r.blob();
  };
  const a = q.data;
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Box sx={{ color: "#fff", background: `linear-gradient(150deg, ${marca.navy} 0%, ${marca.azulOscuro} 55%, ${marca.azul} 100%)`, px: 2, pt: 4, pb: 10 }}>
        <Box sx={{ maxWidth: 820, mx: "auto" }}>
          <Typography sx={{ color: marca.celeste, fontSize: 15, fontWeight: 600, mb: 0.5 }}>Mesa de Servicios · Base de conocimiento</Typography>
          <Typography variant="h4" sx={{ fontWeight: 800, color: "#fff" }}>{a?.titulo ?? "Artículo de ayuda"}</Typography>
        </Box>
      </Box>
      <Box sx={{ maxWidth: 820, mx: "auto", px: 2, mt: -7, pb: 6 }}>
        <Paper sx={{ p: { xs: 2.5, sm: 4 } }}>
          <Box component="img" src="/logo-aducorp.png" alt="ADUCORP" sx={{ height: 44, mb: 2.5, display: "block" }} />
          {q.isLoading && <Cargando alto={200} />}
          {q.isError && <Alert severity="warning">{mensajeError(q.error)}. Si lo necesita, pida un enlace nuevo a la Mesa de Servicios.</Alert>}
          {a && (
            <>
              {a.categoria && <Chip size="small" variant="outlined" label={a.categoria} sx={{ mb: 1 }} />}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>Actualizado el {fecha(a.fecha_actualizacion)}</Typography>
              {a.sintoma && (
                <>
                  <Typography variant="subtitle2" sx={{ color: marca.navy, mt: 2.5, mb: 1 }}>Síntoma</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{a.sintoma}</Typography>
                </>
              )}
              <Typography variant="subtitle2" sx={{ color: marca.navy, mt: 2.5, mb: 1 }}>Solución</Typography>
              <Pasos texto={a.solucion} fuenteImagen={fuenteImagen} />
              {a.nota && <Alert severity="warning" sx={{ mt: 1.5 }}>{a.nota}</Alert>}
              <Divider sx={{ my: 3 }} />
              <Typography variant="body2" sx={{ mb: 1.5 }}>¿No se resolvió? Escríbanos y lo ayudamos.</Typography>
              <Button variant="contained" component={RouterLink} to="/solicitud">Crear una solicitud</Button>
            </>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
