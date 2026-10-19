import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from "@mui/material";
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
      <Microsoft365 />
    </>
  );
}

interface Integraciones {
  aplicacion_configurada: boolean;
  entra: { activo: boolean; grupos_mapeados: number; rol_defecto: string | null; exigir_mfa: boolean; usuarios: number };
  buzon: {
    activo: boolean;
    correo: string;
    envio_por_graph: boolean;
    ultimos: { fecha: string; remitente: string; asunto: string; resultado: string; ticket_id: number | null; detalle: string | null }[];
  };
  teams: { activo: boolean; pendientes: number; canales: { nombre: string; categoria: string }[] };
}

const Estado = ({ activo }: { activo: boolean }) => (
  <Chip size="small" label={activo ? "Activo" : "Apagado"} color={activo ? "success" : "default"} variant={activo ? "filled" : "outlined"} />
);

/** Estado de Entra ID, el buzón de soporte y Teams. Se configuran con variables de entorno (docs/10-microsoft-365.md). */
function Microsoft365() {
  const q = useQuery({ queryKey: ["admin", "integraciones"], queryFn: () => get<Integraciones>("/admin/integraciones") });
  if (!q.data) return null;
  const d = q.data;
  return (
    <Paper sx={{ p: 3, mt: 3 }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        Microsoft 365
      </Typography>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        {d.aplicacion_configurada
          ? "Aplicación registrada en Entra ID. Estos módulos se activan en el archivo .env del servidor."
          : "Falta registrar la aplicación en Entra ID (M365_TENANT_ID, M365_CLIENT_ID y M365_CLIENT_SECRET). Vea la guía de Microsoft 365."}
      </Typography>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" } }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
            <Typography sx={{ fontWeight: 600 }}>Entra ID (SSO)</Typography>
            <Estado activo={d.entra.activo} />
          </Stack>
          <Typography variant="body2">Usuarios de Microsoft 365: {d.entra.usuarios}</Typography>
          <Typography variant="body2">Grupos con rol asignado: {d.entra.grupos_mapeados}</Typography>
          <Typography variant="body2">Rol por defecto: {d.entra.rol_defecto ?? "ninguno (acceso denegado)"}</Typography>
          <Typography variant="body2">MFA exigido por la Mesa: {d.entra.exigir_mfa ? "sí" : "no (lo exige el Acceso Condicional)"}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
            <Typography sx={{ fontWeight: 600 }}>Buzón de soporte</Typography>
            <Estado activo={d.buzon.activo} />
          </Stack>
          <Typography variant="body2">{d.buzon.correo}</Typography>
          <Typography variant="body2">Envío de avisos: {d.buzon.envio_por_graph ? "desde el buzón (Graph)" : "SMTP"}</Typography>
          <Typography variant="body2">Correos procesados recientes: {d.buzon.ultimos.length}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
            <Typography sx={{ fontWeight: 600 }}>Microsoft Teams</Typography>
            <Estado activo={d.teams.activo} />
          </Stack>
          <Typography variant="body2">Avisos pendientes: {d.teams.pendientes}</Typography>
          {d.teams.canales.length ? (
            d.teams.canales.map((c) => (
              <Typography key={c.nombre + c.categoria} variant="body2">
                #{c.nombre} · {c.categoria}
              </Typography>
            ))
          ) : (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Sin canales vinculados. En cada canal escriba «@Mesa vincular general» o «@Mesa vincular Legal Aduanero».
            </Typography>
          )}
        </Paper>
      </Box>
      {d.buzon.ultimos.length > 0 && (
        <Table size="small" sx={{ mt: 2 }}>
          <TableHead>
            <TableRow>
              <TableCell>Remitente</TableCell>
              <TableCell>Asunto</TableCell>
              <TableCell>Resultado</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {d.buzon.ultimos.map((c, i) => (
              <TableRow key={i}>
                <TableCell>{c.remitente}</TableCell>
                <TableCell>{c.asunto}</TableCell>
                <TableCell title={c.detalle ?? ""}>
                  {c.ticket_id ? <a href={`/tickets/${c.ticket_id}`}>{c.resultado.toLowerCase()}</a> : c.resultado.toLowerCase()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}
