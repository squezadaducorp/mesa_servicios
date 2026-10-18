import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Paper, Stack, TextField } from "@mui/material";
import { get, put } from "../../api/client";
import type { ConfiguracionItem } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";

export default function Configuracion() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["admin", "configuracion"], queryFn: () => get<ConfiguracionItem[]>("/admin/configuracion") });
  const [valores, setValores] = useState<Record<string, string>>({});
  useEffect(() => {
    if (q.data) setValores(Object.fromEntries(q.data.map((c) => [c.clave, c.valor])));
  }, [q.data]);
  const cambiados = Object.fromEntries(Object.entries(valores).filter(([k, v]) => q.data?.find((c) => c.clave === k)?.valor !== v));
  const guardar = useMutation({
    mutationFn: () => put("/admin/configuracion", { valores: cambiados }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "configuracion"] });
      avisar("Configuración guardada");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  return (
    <>
      <Encabezado
        titulo="Configuración"
        subtitulo="Parámetros generales del sistema"
        acciones={
          <Button variant="contained" disabled={!Object.keys(cambiados).length || guardar.isPending} onClick={() => guardar.mutate()}>
            Guardar
          </Button>
        }
      />
      <Paper sx={{ p: 3 }}>
        <Stack spacing={2.5}>
          {q.data?.map((c) => (
            <TextField
              key={c.clave}
              label={c.clave}
              helperText={c.descripcion}
              value={valores[c.clave] ?? ""}
              onChange={(e) => setValores((v) => ({ ...v, [c.clave]: e.target.value }))}
              fullWidth
            />
          ))}
        </Stack>
      </Paper>
    </>
  );
}
