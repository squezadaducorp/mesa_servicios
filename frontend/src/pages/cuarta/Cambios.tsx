import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, InputAdornment, Link, MenuItem, Paper, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DescriptionIcon from "@mui/icons-material/DescriptionOutlined";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import AcUnitIcon from "@mui/icons-material/AcUnit";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import SearchIcon from "@mui/icons-material/Search";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import { Stack } from "../../components/Pila";
import { del, descargar, get, post } from "../../api/client";
import type { Calendario, CambioLista, OpcionesCambio, ResumenCambios } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga, Vacio } from "../../components/Comunes";
import { EstadoCambio, RiesgoChip, TipoCambio, deLocal, diaHora, hora } from "./cambiosComun";
import { fechaHora } from "../../utils/formato";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function sumarDias(isoFecha: string, n: number) {
  const d = new Date(`${isoFecha}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function tituloSemana(desde: string, hasta: string) {
  const [, m1, d1] = desde.split("-").map(Number);
  const [, m2, d2] = hasta.split("-").map(Number);
  return m1 === m2 ? `semana del ${d1} al ${d2} de ${MESES[m2 - 1]}` : `semana del ${d1} de ${MESES[m1 - 1]} al ${d2} de ${MESES[m2 - 1]}`;
}

const BORDE: Record<string, string> = { BAJO: "#2E7D32", MEDIO: "#E07B00", ALTO: "#C62828" };

function CalendarioSemana({ gestor, onCongelar }: { gestor: boolean; onCongelar: () => void }) {
  const [desde, setDesde] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["cambios", "calendario", desde], queryFn: () => get<Calendario>("/cambios/calendario", desde ? { desde } : undefined) });
  const navigate = useNavigate();
  const cal = q.data;
  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2, gap: 1, flexWrap: "wrap" }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Calendario de ventanas{cal ? ` · ${tituloSemana(cal.desde, cal.hasta)}` : ""}
        </Typography>
        <Stack direction="row" alignItems="center" sx={{ gap: 0.5 }}>
          {gestor && <Button size="small" startIcon={<AcUnitIcon />} onClick={onCongelar}>Periodos sin cambios</Button>}
          <IconButton size="small" aria-label="Semana anterior" onClick={() => cal && setDesde(sumarDias(cal.desde, -7))}><ChevronLeftIcon /></IconButton>
          <Button size="small" onClick={() => setDesde(null)}>Hoy</Button>
          <IconButton size="small" aria-label="Semana siguiente" onClick={() => cal && setDesde(sumarDias(cal.desde, 7))}><ChevronRightIcon /></IconButton>
        </Stack>
      </Stack>
      {q.isLoading ? <Cargando alto={140} /> : q.error ? <ErrorCarga error={q.error} /> : (
        <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "repeat(2, 1fr)", sm: "repeat(4, 1fr)", lg: "repeat(7, 1fr)" } }}>
          {cal!.dias.map((d, i) => (
            <Box key={d.fecha} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.25, minHeight: 130, bgcolor: i >= 5 ? "#FAFBFD" : "#fff" }}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>{DIAS[i]} {Number(d.fecha.slice(8))}</Typography>
              <Stack sx={{ gap: 0.75, mt: 1 }}>
                {d.congelamientos.map((f, j) => (
                  <Box key={`f${j}`} sx={{ bgcolor: "#FFF6E0", borderLeft: "3px solid #F2A900", borderRadius: 1, p: 0.75 }}>
                    <Typography variant="caption" sx={{ fontWeight: 700, display: "block" }}>{f.titulo}</Typography>
                    {f.motivo && <Typography variant="caption" color="text.secondary">{f.motivo}</Typography>}
                  </Box>
                ))}
                {d.cambios.map((c) => (
                  <Box key={c.id} onClick={() => navigate(`/cambios/${c.id}`)}
                    sx={{ cursor: "pointer", bgcolor: c.estado === "IMPLEMENTADO" ? "#EAF6EC" : "#FDF4E7", borderLeft: `3px solid ${BORDE[c.riesgo ?? "BAJO"] ?? "#2E7D32"}`,
                      borderRadius: 1, p: 0.75, "&:hover": { filter: "brightness(0.97)" } }}>
                    <Typography variant="caption" sx={{ fontWeight: 700, display: "block" }}>{hora(c.inicio)} · {c.numero}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {c.titulo}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
          ))}
        </Box>
      )}
    </Paper>
  );
}

function Congelamientos({ onCerrar }: { onCerrar: () => void }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const op = useQuery({ queryKey: ["cambios", "opciones"], queryFn: () => get<OpcionesCambio>("/cambios/opciones") });
  const [f, setF] = useState({ titulo: "", inicio: "", fin: "", motivo: "" });
  const [error, setError] = useState<string | null>(null);
  const refrescar = () => qc.invalidateQueries({ queryKey: ["cambios"] });
  const crear = useMutation({
    mutationFn: () => post("/cambios/congelamientos", { titulo: f.titulo, inicio: deLocal(f.inicio), fin: deLocal(f.fin), motivo: f.motivo || null }),
    onSuccess: () => { avisar("Periodo agregado"); setF({ titulo: "", inicio: "", fin: "", motivo: "" }); refrescar(); },
    onError: (e) => setError(mensajeError(e)),
  });
  const borrar = useMutation({ mutationFn: (id: number) => del(`/cambios/congelamientos/${id}`), onSuccess: refrescar });
  return (
    <Dialog open onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle>Periodos sin cambios (congelamientos)</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          No se pueden programar cambios en estos periodos, salvo los de emergencia. El último día hábil de cada mes se congela solo
          (cierre de mes) si está activo en Configuración.
        </Typography>
        {(op.data?.congelamientos ?? []).map((x, i) => (
          <Stack key={x.id ?? `a${i}`} direction="row" alignItems="center" sx={{ py: 1, borderTop: "1px solid", borderColor: "divider", gap: 1 }}>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{x.titulo}{x.automatico ? " · automático" : ""}</Typography>
              <Typography variant="caption" color="text.secondary">{fechaHora(x.inicio)} a {fechaHora(x.fin)}{x.motivo ? ` · ${x.motivo}` : ""}</Typography>
            </Box>
            {x.id && <IconButton aria-label="Quitar periodo" onClick={() => borrar.mutate(x.id!)}><DeleteIcon /></IconButton>}
          </Stack>
        ))}
        <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Agregar periodo</Typography>
        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          <TextField size="small" label="Título" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} sx={{ gridColumn: { sm: "span 2" } }} />
          <TextField size="small" type="datetime-local" label="Desde" value={f.inicio} onChange={(e) => setF({ ...f, inicio: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField size="small" type="datetime-local" label="Hasta" value={f.fin} onChange={(e) => setF({ ...f, fin: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField size="small" label="Motivo (opcional)" value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} sx={{ gridColumn: { sm: "span 2" } }} />
        </Box>
        {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cerrar</Button>
        <Button variant="contained" disabled={!f.titulo || !f.inicio || !f.fin || crear.isPending} onClick={() => { setError(null); crear.mutate(); }}>Agregar</Button>
      </DialogActions>
    </Dialog>
  );
}

function Indicador({ titulo, valor, color }: { titulo: string; valor: string | number; color: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="body2" color="text.secondary">{titulo}</Typography>
      <Typography sx={{ fontSize: 34, fontWeight: 800, color, lineHeight: 1.2 }}>{valor}</Typography>
    </Paper>
  );
}

export default function Cambios() {
  const navigate = useNavigate();
  const [estado, setEstado] = useState("");
  const [texto, setTexto] = useState("");
  const [congelar, setCongelar] = useState(false);
  const q = useQuery({
    queryKey: ["cambios", "lista", estado, texto],
    queryFn: () => get<{ cambios: CambioLista[]; resumen: ResumenCambios; gestor: boolean }>("/cambios", { estado: estado || undefined, q: texto || undefined }),
  });
  const r = q.data?.resumen;
  return (
    <Box>
      <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} justifyContent="space-between" sx={{ gap: 2, mb: 3 }}>
        <Box>
          <Typography variant="h5">Gestión de cambios</Typography>
          <Typography variant="body2" color="text.secondary">Solicitudes TI-FOR-001 / TI-FOR-002, aprobaciones y ventanas de implementación.</Typography>
        </Box>
        <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
          {q.data?.gestor && (
            <Button variant="outlined" startIcon={<DescriptionIcon />} onClick={() => descargar("/cambios/exportar", undefined, "Registro-de-Cambios.xlsx")}>
              Exportar registro (Excel)
            </Button>
          )}
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate("/cambios/nuevo")}>Solicitar cambio</Button>
        </Stack>
      </Stack>

      {r && (
        <Box sx={{ display: "grid", gap: 2, mb: 3, gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
          <Indicador titulo="Por aprobar" valor={r.por_aprobar} color="#B7791F" />
          <Indicador titulo="Programados" valor={r.programados} color="#5B2E9E" />
          <Indicador titulo={`Implementados en ${r.anio}`} valor={r.implementados_anio} color="#2E7D32" />
          <Indicador titulo="Exitosos sin reversión" valor={r.exitosos_pct === null ? "—" : `${r.exitosos_pct} %`} color="#1367AC" />
        </Box>
      )}

      <CalendarioSemana gestor={!!q.data?.gestor} onCongelar={() => setCongelar(true)} />

      <Paper variant="outlined">
        <Stack direction={{ xs: "column", sm: "row" }} sx={{ gap: 1.5, p: 2 }}>
          <TextField size="small" placeholder="Buscar por número o título" value={texto} onChange={(e) => setTexto(e.target.value)} sx={{ minWidth: 280 }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
          <TextField size="small" select label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)} sx={{ minWidth: 200 }}>
            <MenuItem value="">Todos</MenuItem>
            <MenuItem value="ABIERTOS">Abiertos</MenuItem>
            {Object.entries({ SOLICITADO: "Solicitado", EN_ESPERA: "En espera", EN_APROBACION: "En aprobación", PROGRAMADO: "Programado",
              EN_REVISION: "En revisión", IMPLEMENTADO: "Implementado", REVERTIDO: "Revertido", RECHAZADO: "Rechazado" }).map(([k, v]) => (
              <MenuItem key={k} value={k}>{v}</MenuItem>
            ))}
          </TextField>
        </Stack>
        {q.isLoading ? <Cargando /> : q.error ? <ErrorCarga error={q.error} /> : q.data!.cambios.length === 0 ? (
          <Vacio texto="No hay cambios registrados con estos filtros." />
        ) : (
          <Box sx={{ overflowX: "auto" }}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>N.º</TableCell><TableCell>Cambio</TableCell><TableCell>Tipo</TableCell><TableCell>Riesgo</TableCell>
                  <TableCell>Estado</TableCell><TableCell>Ventana</TableCell><TableCell>Solicita</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {q.data!.cambios.map((c) => (
                  <TableRow key={c.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/cambios/${c.id}`)}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      <Link component={RouterLink} to={`/cambios/${c.id}`} sx={{ fontWeight: 700 }} onClick={(e) => e.stopPropagation()}>{c.numero}</Link>
                    </TableCell>
                    <TableCell>{c.titulo}</TableCell>
                    <TableCell><TipoCambio tipo={c.tipo_cambio} /></TableCell>
                    <TableCell><RiesgoChip riesgo={c.riesgo} /></TableCell>
                    <TableCell><EstadoCambio estado={c.estado} nombre={c.estado_nombre} /></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{c.estado === "RECHAZADO" ? "—" : diaHora(c.ventana_inicio)}</TableCell>
                    <TableCell>{c.solicitante}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>

      <Alert severity="info" icon={<InfoIcon />} sx={{ mt: 3 }}>
        Reemplaza el Excel <b>Registro-de-Cambios</b>: los formatos TI-FOR-001 (Mesa) y TI-FOR-002 (general) se llenan aquí y quedan con su
        historial de aprobaciones.
      </Alert>
      {congelar && <Congelamientos onCerrar={() => setCongelar(false)} />}
    </Box>
  );
}
