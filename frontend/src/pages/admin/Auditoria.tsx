import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Box, Button, Chip, MenuItem, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { descargar, get } from "../../api/client";
import type { Auditoria as Registro, Pagina } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";
import { fechaHora, haceDias, hoyIso } from "../../utils/formato";

export default function Auditoria() {
  const avisar = useAviso();
  const [filtro, setFiltro] = useState({ desde: haceDias(7), hasta: hoyIso(), accion: "", texto: "" });
  const [pagina, setPagina] = useState(0);
  const [tamano, setTamano] = useState(50);
  const acciones = useQuery({ queryKey: ["auditoria", "acciones"], queryFn: () => get<string[]>("/auditoria/acciones") });
  const q = useQuery({
    queryKey: ["auditoria", filtro, pagina, tamano],
    queryFn: () => get<Pagina<Registro>>("/auditoria", { ...filtro, pagina: pagina + 1, tamano }),
    placeholderData: keepPreviousData,
  });
  const set = (k: keyof typeof filtro) => (e: { target: { value: string } }) => {
    setFiltro((f) => ({ ...f, [k]: e.target.value }));
    setPagina(0);
  };
  const exportar = (formato: string) =>
    descargar("/auditoria/exportar", { formato, desde: filtro.desde, hasta: filtro.hasta, accion: filtro.accion }).catch((e) => avisar(mensajeError(e), "error"));

  return (
    <>
      <Encabezado
        titulo="Auditoría"
        subtitulo="Registro inmutable de accesos y cambios: usuario, fecha, hora, acción, IP y equipo"
        acciones={
          <>
            <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportar("xlsx")}>
              Excel
            </Button>
            <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportar("csv")}>
              CSV
            </Button>
          </>
        }
      />
      <Paper sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "160px 160px 220px 1fr" } }}>
          <TextField type="date" label="Desde" value={filtro.desde} onChange={set("desde")} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField type="date" label="Hasta" value={filtro.hasta} onChange={set("hasta")} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField select label="Acción" value={filtro.accion} onChange={set("accion")}>
            <MenuItem value="">Todas</MenuItem>
            {(acciones.data ?? []).map((a) => (
              <MenuItem key={a} value={a}>
                {a}
              </MenuItem>
            ))}
          </TextField>
          <TextField label="Buscar (usuario, entidad, detalle, IP)" value={filtro.texto} onChange={set("texto")} />
        </Box>
      </Paper>
      {q.isLoading ? (
        <Cargando />
      ) : q.error ? (
        <ErrorCarga error={q.error} />
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Fecha y hora</TableCell>
                  <TableCell>Usuario</TableCell>
                  <TableCell>Acción</TableCell>
                  <TableCell>Entidad</TableCell>
                  <TableCell>IP</TableCell>
                  <TableCell>Equipo</TableCell>
                  <TableCell>Resultado</TableCell>
                  <TableCell>Detalle</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {q.data?.items.map((r) => (
                  <TableRow key={r.id} hover>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{fechaHora(r.fecha_hora)}</TableCell>
                    <TableCell>{r.usuario_correo ?? "Sistema"}</TableCell>
                    <TableCell>
                      <Chip size="small" label={r.accion} variant="outlined" />
                    </TableCell>
                    <TableCell>
                      {r.entidad}
                      {r.entidad_id ? ` #${r.entidad_id}` : ""}
                    </TableCell>
                    <TableCell sx={{ fontFamily: "monospace" }}>{r.ip}</TableCell>
                    <TableCell sx={{ maxWidth: 180 }}>
                      <Typography variant="caption" noWrap component="div" title={r.equipo ?? ""}>
                        {r.equipo}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip size="small" color={r.resultado === "OK" ? "success" : "error"} label={r.resultado} />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Typography variant="caption" noWrap component="div" title={r.detalle ?? ""}>
                        {r.detalle}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={q.data?.total ?? 0}
            page={pagina}
            onPageChange={(_, p) => setPagina(p)}
            rowsPerPage={tamano}
            onRowsPerPageChange={(e) => {
              setTamano(Number(e.target.value));
              setPagina(0);
            }}
            rowsPerPageOptions={[25, 50, 100, 200]}
          />
        </Paper>
      )}
    </>
  );
}
