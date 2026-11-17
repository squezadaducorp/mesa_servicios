import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, Paper, Rating, Stack, TextField, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import { get, post } from "../api/client";
import type { EncuestaPublica as Datos } from "../api/types";
import { mensajeError } from "../components/Aviso";
import { NOMBRES_NOTA } from "../components/Chips";
import { Cargando } from "../components/Comunes";
import { marca } from "../theme";


/** Enlace del correo de la encuesta: /encuesta?t=<token>&nota=N. Registra la nota sin iniciar sesión y permite comentar. */
export default function EncuestaPublica() {
  const [params] = useSearchParams();
  const token = params.get("t") ?? "";
  const notaUrl = Number(params.get("nota")) || null;
  const qc = useQueryClient();
  const [elegida, setElegida] = useState<number | null>(notaUrl && notaUrl >= 1 && notaUrl <= 5 ? notaUrl : null);
  const [comentario, setComentario] = useState("");
  const [comentado, setComentado] = useState(false);

  const estado = useQuery({
    queryKey: ["encuesta", token, elegida],
    queryFn: () => (elegida ? post<Datos>("/publico/encuesta", { token, calificacion: elegida }) : get<Datos>("/publico/encuesta", { t: token })),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });
  // Si ya había otra nota (409), se muestra la registrada.
  const yaCalificado = useQuery({
    queryKey: ["encuesta", token, "actual"],
    queryFn: () => get<Datos>("/publico/encuesta", { t: token }),
    enabled: !!token && estado.isError && (estado.error as { status?: number })?.status === 409,
    retry: false,
  });
  const comentar = useMutation({
    mutationFn: () => post<Datos>("/publico/encuesta", { token, comentario }),
    onSuccess: (d) => {
      qc.setQueryData(["encuesta", token, elegida], d);
      setComentado(true);
    },
  });

  const datos = estado.data ?? yaCalificado.data;
  const nota = datos?.calificacion ?? null;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Box sx={{ color: "#fff", background: `linear-gradient(150deg, ${marca.navy} 0%, ${marca.azulOscuro} 55%, ${marca.azul} 100%)`, px: 2, pt: 4, pb: 10 }}>
        <Box sx={{ maxWidth: 620, mx: "auto" }}>
          <Typography variant="h4" sx={{ fontWeight: 800, color: "#fff", mb: 1 }}>
            ¿Cómo lo atendimos?
          </Typography>
          <Typography sx={{ color: marca.celeste, fontSize: 17 }}>Su opinión nos ayuda a mejorar la Mesa de Servicios.</Typography>
        </Box>
      </Box>
      <Box sx={{ maxWidth: 620, mx: "auto", px: 2, mt: -7, pb: 6 }}>
        <Paper sx={{ p: { xs: 2.5, sm: 4 } }}>
          <Box component="img" src="/logo-aducorp.png" alt="ADUCORP" sx={{ height: 44, mb: 3, display: "block" }} />
          {!token && <Alert severity="warning">El enlace está incompleto. Abra nuevamente el enlace del correo.</Alert>}
          {token && (estado.isLoading || yaCalificado.isLoading) && <Cargando alto={200} />}
          {estado.isError && !yaCalificado.data && !yaCalificado.isLoading && <Alert severity="warning">{mensajeError(estado.error)}</Alert>}
          {datos && (
            <Stack spacing={2.5} sx={{ alignItems: "center", textAlign: "center" }}>
              <Box>
                <Typography variant="overline" sx={{ color: "text.secondary" }}>
                  Ticket {datos.numero}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {datos.asunto}
                </Typography>
                {datos.responsable && (
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    Atendido por {datos.responsable}
                  </Typography>
                )}
              </Box>
              {nota ? (
                <>
                  {estado.isError && <Alert severity="info">Este ticket ya fue calificado. Esta es la calificación registrada.</Alert>}
                  <Rating value={nota} readOnly size="large" sx={{ fontSize: 44 }} />
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <CheckCircleIcon color="success" />
                    <Typography sx={{ fontWeight: 600 }}>
                      ¡Gracias! Calificó la atención como «{NOMBRES_NOTA[nota]}».
                    </Typography>
                  </Stack>
                  {datos.comentario && !comentado && (
                    <Typography variant="body2" sx={{ color: "text.secondary", fontStyle: "italic" }}>
                      «{datos.comentario}»
                    </Typography>
                  )}
                  {datos.puede_comentar && !comentado && (
                    <Box sx={{ width: "100%", textAlign: "left" }}>
                      <TextField
                        label={nota <= 3 ? "¿Qué podemos mejorar? (opcional)" : "¿Quiere dejarnos un comentario? (opcional)"}
                        multiline
                        minRows={3}
                        fullWidth
                        value={comentario}
                        onChange={(e) => setComentario(e.target.value)}
                        slotProps={{ htmlInput: { maxLength: 1000 } }}
                      />
                      {comentar.isError && (
                        <Alert severity="error" sx={{ mt: 1 }}>
                          {mensajeError(comentar.error)}
                        </Alert>
                      )}
                      <Button variant="contained" sx={{ mt: 1.5 }} disabled={!comentario.trim() || comentar.isPending} onClick={() => comentar.mutate()}>
                        Enviar comentario
                      </Button>
                    </Box>
                  )}
                  {comentado && <Alert severity="success">Recibimos su comentario. ¡Gracias!</Alert>}
                </>
              ) : (
                <>
                  <Typography>Elija de 1 a 5 estrellas:</Typography>
                  <Rating value={null} onChange={(_, v) => v && setElegida(v)} size="large" sx={{ fontSize: 48 }} />
                </>
              )}
            </Stack>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
