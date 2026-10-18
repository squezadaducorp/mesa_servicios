import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Box, Button, Card, CardActionArea, Chip, Collapse, FormControlLabel, InputAdornment, MenuItem, Paper, Stack, Switch, Table,
  TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import FilterListIcon from "@mui/icons-material/FilterList";
import AddIcon from "@mui/icons-material/Add";
import DownloadIcon from "@mui/icons-material/Download";
import { descargar, get } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { FiltroTickets, Pagina, TicketListado } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";
import { CumplimientoChip, EstadoChip, NOMBRE_ESTADO, PrioridadChip, SlaBarra } from "../components/Chips";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import { fechaHora } from "../utils/formato";
import { P } from "../utils/permisos";

const CLAVE_FILTRO = "aducorp.filtroTickets";

function filtroInicial(params: URLSearchParams): FiltroTickets {
  const desdeUrl: FiltroTickets = {};
  if (params.get("estado")) desdeUrl.estado = params.getAll("estado");
  if (params.get("sla")) desdeUrl.sla = params.get("sla") as FiltroTickets["sla"];
  if (params.get("solo_mios")) desdeUrl.solo_mios = true;
  if (Object.keys(desdeUrl).length) return { orden: "fecha_desc", ...desdeUrl };
  try {
    const g = sessionStorage.getItem(CLAVE_FILTRO);
    if (g) return JSON.parse(g);
  } catch {
    /* sin almacenamiento */
  }
  return { orden: "fecha_desc" };
}

export default function Tickets() {
  const { puede } = useAuth();
  const avisar = useAviso();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const theme = useTheme();
  const movil = useMediaQuery(theme.breakpoints.down("md"));
  const cat = useCatalogos();
  const [filtro, setFiltro] = useState<FiltroTickets>(() => filtroInicial(params));
  const [texto, setTexto] = useState(filtro.texto ?? "");
  const [pagina, setPagina] = useState(0);
  const [tamano, setTamano] = useState(20);
  const [verFiltros, setVerFiltros] = useState(false);
  const gestor = puede(P.VER_TODOS, P.VER_AREA, P.VER_ASIGNADOS);

  useEffect(() => {
    const t = setTimeout(() => setFiltro((f) => ({ ...f, texto: texto || undefined })), 350);
    return () => clearTimeout(t);
  }, [texto]);

  useEffect(() => {
    setPagina(0);
    try {
      sessionStorage.setItem(CLAVE_FILTRO, JSON.stringify(filtro));
    } catch {
      /* sin almacenamiento */
    }
  }, [filtro]);

  const q = useQuery({
    queryKey: ["tickets", filtro, pagina, tamano],
    queryFn: () => get<Pagina<TicketListado>>("/tickets", { ...filtro, pagina: pagina + 1, tamano }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });

  const set = <K extends keyof FiltroTickets>(k: K, v: FiltroTickets[K] | "" | undefined) =>
    setFiltro((f) => ({ ...f, [k]: v === "" ? undefined : v }));
  const categoria = cat.data?.categorias.find((c) => c.id === filtro.categoria_id);
  const activos = Object.entries(filtro).filter(([k, v]) => !["orden", "texto"].includes(k) && v !== undefined && v !== false && !(Array.isArray(v) && !v.length)).length;

  const exportar = async (formato: string) => {
    try {
      await descargar("/tickets/exportar", { ...filtro, formato }, `tickets.${formato}`);
    } catch (e) {
      avisar(mensajeError(e), "error");
    }
  };

  return (
    <>
      <Encabezado
        titulo="Tickets"
        subtitulo={q.data ? `${q.data.total} ticket(s) encontrados` : " "}
        acciones={
          <>
            {puede(P.EXPORTAR) &&
              ["xlsx", "pdf", "csv"].map((f) => (
                <Button key={f} variant="outlined" size="small" startIcon={<DownloadIcon />} onClick={() => exportar(f)}>
                  {f === "xlsx" ? "Excel" : f.toUpperCase()}
                </Button>
              ))}
            {puede(P.CREAR) && (
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate("/tickets/nuevo")}>
                Nuevo ticket
              </Button>
            )}
          </>
        }
      />

      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <TextField
            placeholder="Buscar por número, asunto, descripción o solicitante"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            fullWidth
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
          />
          <Button startIcon={<FilterListIcon />} onClick={() => setVerFiltros(!verFiltros)} sx={{ whiteSpace: "nowrap" }}>
            Filtros{activos ? ` (${activos})` : ""}
          </Button>
        </Stack>
        <Collapse in={verFiltros}>
          <Box sx={{ display: "grid", gap: 1.5, mt: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
            <TextField
              select
              label="Estado"
              value={filtro.estado ?? []}
              onChange={(e) => set("estado", (typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value) as string[])}
              slotProps={{ select: { multiple: true, renderValue: (v) => (v as string[]).map((x) => NOMBRE_ESTADO[x]).join(", ") } }}
            >
              {Object.entries(NOMBRE_ESTADO).map(([c, n]) => (
                <MenuItem key={c} value={c}>
                  {n}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Categoría"
              value={filtro.categoria_id ?? ""}
              onChange={(e) => setFiltro((f) => ({ ...f, categoria_id: e.target.value ? Number(e.target.value) : undefined, subcategoria_id: undefined }))}
            >
              <MenuItem value="">Todas</MenuItem>
              {(cat.data?.categorias ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Subcategoría" value={filtro.subcategoria_id ?? ""} disabled={!categoria} onChange={(e) => set("subcategoria_id", e.target.value ? Number(e.target.value) : undefined)}>
              <MenuItem value="">Todas</MenuItem>
              {(categoria?.subcategorias ?? []).map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Prioridad" value={filtro.prioridad_id ?? ""} onChange={(e) => set("prioridad_id", e.target.value ? Number(e.target.value) : undefined)}>
              <MenuItem value="">Todas</MenuItem>
              {(cat.data?.prioridades ?? []).map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.nombre}
                </MenuItem>
              ))}
            </TextField>
            {gestor && (
              <TextField select label="Responsable" value={filtro.responsable_id ?? ""} onChange={(e) => set("responsable_id", e.target.value ? Number(e.target.value) : undefined)}>
                <MenuItem value="">Todos</MenuItem>
                {(cat.data?.responsables ?? []).map((r) => (
                  <MenuItem key={r.id} value={r.id}>
                    {r.nombre}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField select label="Cliente" value={filtro.cliente_id ?? ""} onChange={(e) => set("cliente_id", e.target.value ? Number(e.target.value) : undefined)}>
              <MenuItem value="">Todos</MenuItem>
              {(cat.data?.clientes ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="SLA" value={filtro.sla ?? ""} onChange={(e) => set("sla", e.target.value as FiltroTickets["sla"])}>
              <MenuItem value="">Todos</MenuItem>
              <MenuItem value="EN_CURSO">En curso</MenuItem>
              <MenuItem value="EN_RIESGO">En riesgo (≥ 75 %)</MenuItem>
              <MenuItem value="CUMPLIDO">Cumplido</MenuItem>
              <MenuItem value="INCUMPLIDO">Incumplido</MenuItem>
            </TextField>
            <TextField select label="Ordenar por" value={filtro.orden ?? "fecha_desc"} onChange={(e) => set("orden", e.target.value as FiltroTickets["orden"])}>
              <MenuItem value="fecha_desc">Más recientes</MenuItem>
              <MenuItem value="fecha_asc">Más antiguos</MenuItem>
              <MenuItem value="sla_desc">Mayor consumo de SLA</MenuItem>
              <MenuItem value="prioridad">Prioridad</MenuItem>
            </TextField>
            <TextField type="date" label="Desde" value={filtro.desde ?? ""} onChange={(e) => set("desde", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
            <TextField type="date" label="Hasta" value={filtro.hasta ?? ""} onChange={(e) => set("hasta", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
            {gestor && (
              <FormControlLabel control={<Switch checked={!!filtro.solo_mios} onChange={(e) => set("solo_mios", e.target.checked)} />} label="Solo asignados a mí" />
            )}
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Button
                onClick={() => {
                  setTexto("");
                  setFiltro({ orden: "fecha_desc" });
                }}
              >
                Limpiar filtros
              </Button>
            </Box>
          </Box>
        </Collapse>
      </Paper>

      {q.isLoading ? (
        <Cargando />
      ) : q.error ? (
        <ErrorCarga error={q.error} />
      ) : !q.data?.items.length ? (
        <Paper>
          <Vacio texto="No hay tickets con los filtros seleccionados" />
        </Paper>
      ) : movil ? (
        <Stack spacing={1.5}>
          {q.data.items.map((t) => (
            <Card key={t.id} variant="outlined">
              <CardActionArea onClick={() => navigate(`/tickets/${t.id}`)} sx={{ p: 2 }}>
                <Stack direction="row" sx={{ justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main" }}>
                    {t.numero}
                  </Typography>
                  <EstadoChip estado={t.estado} nombre={t.estado_nombre} />
                </Stack>
                <Typography sx={{ fontWeight: 600, mb: 0.5 }}>{t.asunto}</Typography>
                <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 1 }}>
                  {t.categoria} · {t.responsable ?? "Sin responsable"} · {fechaHora(t.fecha_creacion)}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <PrioridadChip codigo={t.prioridad_codigo} nombre={t.prioridad} />
                  <Box sx={{ flex: 1 }}>
                    <SlaBarra pct={t.sla_consumido_pct} pausado={t.estado === "PENDIENTE_CLIENTE"} ancho={80} />
                  </Box>
                </Stack>
              </CardActionArea>
            </Card>
          ))}
        </Stack>
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Número</TableCell>
                  <TableCell>Asunto / Categoría</TableCell>
                  <TableCell>Solicitante / Cliente</TableCell>
                  <TableCell>Prioridad</TableCell>
                  <TableCell>Responsable</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>SLA</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {q.data.items.map((t) => (
                  <TableRow key={t.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/tickets/${t.id}`)}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main" }}>
                        {t.numero}
                      </Typography>
                      <Typography variant="caption" sx={{ color: "text.secondary" }}>
                        {fechaHora(t.fecha_creacion)}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 260 }}>
                      <Typography variant="body2" noWrap title={t.asunto} sx={{ fontWeight: 500 }}>
                        {t.asunto}
                      </Typography>
                      <Typography variant="caption" noWrap component="div" sx={{ color: "text.secondary" }}>
                        {t.categoria} › {t.subcategoria}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 170 }}>
                      <Typography variant="body2" noWrap>{t.solicitante_nombre}</Typography>
                      <Typography variant="caption" noWrap component="div" sx={{ color: "text.secondary" }}>
                        {t.cliente ?? "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <PrioridadChip codigo={t.prioridad_codigo} nombre={t.prioridad} />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{t.responsable ?? <Chip size="small" label="Sin asignar" variant="outlined" color="warning" />}</TableCell>
                    <TableCell>
                      <EstadoChip estado={t.estado} nombre={t.estado_nombre} />
                    </TableCell>
                    <TableCell sx={{ minWidth: 120 }}>
                      {t.cumplimiento_sla === "EN_CURSO" ? (
                        <SlaBarra pct={t.sla_consumido_pct} pausado={t.estado === "PENDIENTE_CLIENTE"} ancho={90} />
                      ) : (
                        <CumplimientoChip valor={t.cumplimiento_sla} />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
      {!!q.data?.total && (
        <TablePagination
          component="div"
          count={q.data.total}
          page={pagina}
          onPageChange={(_, p) => setPagina(p)}
          rowsPerPage={tamano}
          onRowsPerPageChange={(e) => {
            setTamano(Number(e.target.value));
            setPagina(0);
          }}
          rowsPerPageOptions={[10, 20, 50, 100]}
        />
      )}
    </>
  );
}
