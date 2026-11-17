import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Box, Button, Card, CardActionArea, Chip, Collapse, FormControlLabel, InputAdornment, MenuItem, Paper, Stack, Switch, Tab, Table,
  TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Tabs, TextField, Typography, useMediaQuery, useTheme,
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
import { CumplimientoChip, EstadoChip, NOMBRE_ESTADO, PrioridadChip, SlaBarra, VenceChip } from "../components/Chips";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import { fechaHora } from "../utils/formato";
import { P } from "../utils/permisos";

const CLAVE_FILTRO = "aducorp.filtroTickets";

type Vista = "mios" | "HOY" | "VENCIDOS" | "todos";

function vistaDe(f: FiltroTickets): Vista | false {
  if (f.vence && f.solo_mios) return f.vence;
  if (f.vence) return false;
  return f.solo_mios ? "mios" : "todos";
}

function filtroInicial(params: URLSearchParams): FiltroTickets {
  const desdeUrl: FiltroTickets = {};
  if (params.get("estado")) desdeUrl.estado = params.getAll("estado");
  if (params.get("sla")) desdeUrl.sla = params.get("sla") as FiltroTickets["sla"];
  if (params.get("solo_mios")) desdeUrl.solo_mios = true;
  if (params.get("participe")) desdeUrl.participe = true;
  const vence = params.get("vence");
  if (vence === "HOY" || vence === "VENCIDOS") return { orden: "vence", vence, solo_mios: true };
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
  const conteo = (vence: "HOY" | "VENCIDOS") =>
    get<Pagina<TicketListado>>("/tickets", { vence, solo_mios: true, pagina: 1, tamano: 1 }).then((p) => p.total);
  const porVencer = useQuery({ queryKey: ["tickets", "conteo", "HOY"], queryFn: () => conteo("HOY"), enabled: gestor, refetchInterval: 120_000 });
  const vencidos = useQuery({ queryKey: ["tickets", "conteo", "VENCIDOS"], queryFn: () => conteo("VENCIDOS"), enabled: gestor, refetchInterval: 120_000 });
  const cambiarVista = (v: Vista) =>
    setFiltro((f) => {
      const { vence: _v, solo_mios: _m, ...resto } = f;
      if (v === "HOY" || v === "VENCIDOS") return { ...resto, vence: v, solo_mios: true, orden: "vence" };
      return { ...resto, solo_mios: v === "mios" || undefined, orden: f.orden === "vence" ? "fecha_desc" : f.orden };
    });

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
  const activos = Object.entries(filtro).filter(([k, v]) => !["orden", "texto", ...(gestor ? ["vence", "solo_mios"] : [])].includes(k) && v !== undefined && v !== false && !(Array.isArray(v) && !v.length)).length;

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

      {gestor && (
        <Tabs
          value={vistaDe(filtro)}
          onChange={(_, v) => cambiarVista(v)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
        >
          <Tab value="mios" label="Mis tickets" />
          <Tab
            value="HOY"
            label={
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                <span>Por vencer hoy</span>
                {!!porVencer.data && <Chip size="small" label={porVencer.data} sx={{ height: 20, bgcolor: "#E65100", color: "#fff", fontWeight: 700 }} />}
              </Stack>
            }
          />
          <Tab
            value="VENCIDOS"
            label={
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                <span>Vencidos</span>
                {!!vencidos.data && <Chip size="small" label={vencidos.data} sx={{ height: 20, bgcolor: "#C62828", color: "#fff", fontWeight: 700 }} />}
              </Stack>
            }
          />
          <Tab value="todos" label="Todos" />
        </Tabs>
      )}

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
        {(
          <Chip
            sx={{ mt: 1.5 }}
            color="primary"
            variant={filtro.participe ? "filled" : "outlined"}
            label="Tickets en los que participé"
            title={puede(P.VER_ASIGNADOS)
              ? "Incluye los tickets que usted atendió y hoy están con otro responsable, y los que registró en nombre de otra persona (solo lectura)"
              : "Incluye los tickets que usted registró en nombre de otra persona (solo lectura)"}
            onClick={() => set("participe", filtro.participe ? undefined : true)}
          />
        )}
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
            <TextField
              select
              label="Vencimiento"
              value={filtro.vence ?? ""}
              onChange={(e) => setFiltro((f) => ({ ...f, vence: (e.target.value || undefined) as FiltroTickets["vence"], orden: e.target.value ? "vence" : f.orden === "vence" ? "fecha_desc" : f.orden }))}
            >
              <MenuItem value="">Todos</MenuItem>
              <MenuItem value="HOY">Vencen hoy</MenuItem>
              <MenuItem value="VENCIDOS">Ya vencidos</MenuItem>
            </TextField>
            <TextField select label="Ordenar por" value={filtro.orden ?? "fecha_desc"} onChange={(e) => set("orden", e.target.value as FiltroTickets["orden"])}>
              <MenuItem value="fecha_desc">Más recientes</MenuItem>
              <MenuItem value="fecha_asc">Más antiguos</MenuItem>
              <MenuItem value="sla_desc">Mayor consumo de SLA</MenuItem>
              <MenuItem value="prioridad">Prioridad</MenuItem>
              <MenuItem value="vence">Próximo a vencer</MenuItem>
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
                  {t.vence_en_min !== null && t.vence_en_min !== undefined && <VenceChip min={t.vence_en_min} tipo={t.vence_tipo} />}
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
                  <TableCell>SLA / vence en</TableCell>
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
                    <TableCell sx={{ minWidth: 150 }}>
                      {t.cumplimiento_sla === "EN_CURSO" ? (
                        <SlaBarra pct={t.sla_consumido_pct} pausado={t.estado === "PENDIENTE_CLIENTE"} ancho={90} />
                      ) : (
                        <CumplimientoChip valor={t.cumplimiento_sla} />
                      )}
                      {t.vence_en_min !== null && t.vence_en_min !== undefined && (
                        <Box sx={{ mt: 0.5, whiteSpace: "nowrap" }}>
                          <VenceChip min={t.vence_en_min} tipo={t.vence_tipo} />
                        </Box>
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
