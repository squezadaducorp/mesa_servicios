import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, InputAdornment, Link, MenuItem, Paper, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { Stack } from "../../components/Pila";
import { get, post } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { OpcionesProblema, PatronDetectado, ProblemaDetalle, ProblemaLista, ResumenProblemas } from "../../api/ronda4b";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga, Vacio } from "../../components/Comunes";
import { EstadoProblemaChip } from "./comun";

export function Indicador({ titulo, valor, color }: { titulo: string; valor: string | number; color: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="body2" color="text.secondary">{titulo}</Typography>
      <Typography sx={{ fontSize: 34, fontWeight: 800, color, lineHeight: 1.2 }}>{valor}</Typography>
    </Paper>
  );
}

/** Formulario para registrar un problema (vacío o desde un patrón detectado). */
export function NuevoProblema({ patron, onCerrar }: { patron?: PatronDetectado | null; onCerrar: () => void }) {
  const navigate = useNavigate();
  const avisar = useAviso();
  const cat = useCatalogos();
  const op = useQuery({ queryKey: ["problemas", "opciones"], queryFn: () => get<OpcionesProblema>("/problemas/opciones") });
  const [f, setF] = useState({
    titulo: patron?.titulo ?? "",
    descripcion: patron ? `Patrón detectado: ${patron.cantidad} tickets parecidos en ${patron.dias} días (${patron.subcategoria}).` : "",
    categoria_id: patron?.categoria_id ?? ("" as number | ""),
    subcategoria_id: patron?.subcategoria_id ?? ("" as number | ""),
    responsable_id: "" as number | "",
    palabras_clave: patron?.palabras ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const subcats = cat.data?.categorias.find((c) => c.id === f.categoria_id)?.subcategorias ?? [];
  const crear = useMutation({
    mutationFn: () => post<ProblemaDetalle>("/problemas", {
      titulo: f.titulo, descripcion: f.descripcion || null, categoria_id: f.categoria_id || null, subcategoria_id: f.subcategoria_id || null,
      responsable_id: f.responsable_id || null, palabras_clave: f.palabras_clave || null,
      tickets: patron?.tickets.map((t) => t.id) ?? [], desde_patron: !!patron,
    }),
    onSuccess: (p) => { avisar(`${p.numero} registrado`); navigate(`/problemas/${p.id}`); },
    onError: (e) => setError(mensajeError(e)),
  });
  return (
    <Dialog open onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle>{patron ? "Crear problema desde el patrón" : "Nuevo problema"}</DialogTitle>
      <DialogContent dividers>
        {patron && (
          <Alert severity="warning" icon={<AutoAwesomeIcon />} sx={{ mb: 2 }}>
            Se agruparán {patron.cantidad} tickets: {patron.tickets.map((t) => t.numero).join(", ")}.
          </Alert>
        )}
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          <TextField label="Problema" placeholder="Ej.: ECUAPASS se pone lento todas las mañanas" value={f.titulo} required
            onChange={(e) => setF({ ...f, titulo: e.target.value })} sx={{ gridColumn: { sm: "span 2" } }} />
          <TextField label="Descripción" multiline minRows={2} value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })}
            sx={{ gridColumn: { sm: "span 2" } }} />
          <TextField select label="Categoría" value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: Number(e.target.value) || "", subcategoria_id: "" })}>
            <MenuItem value="">Sin categoría</MenuItem>
            {(cat.data?.categorias ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
          </TextField>
          <TextField select label="Subcategoría" value={f.subcategoria_id} disabled={!subcats.length}
            onChange={(e) => setF({ ...f, subcategoria_id: Number(e.target.value) || "" })}>
            <MenuItem value="">—</MenuItem>
            {subcats.map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
          </TextField>
          <TextField select label="Responsable del análisis" value={f.responsable_id} onChange={(e) => setF({ ...f, responsable_id: Number(e.target.value) || "" })}>
            <MenuItem value="">Yo</MenuItem>
            {(op.data?.responsables ?? []).map((u) => <MenuItem key={u.id} value={u.id}>{u.nombre}</MenuItem>)}
          </TextField>
          <TextField label="Palabras clave" helperText="Para reconocer tickets nuevos parecidos (separadas por coma)" value={f.palabras_clave}
            onChange={(e) => setF({ ...f, palabras_clave: e.target.value })} />
        </Box>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" disabled={f.titulo.trim().length < 5 || crear.isPending} onClick={() => { setError(null); crear.mutate(); }}>
          Registrar problema
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Patron({ p, onCrear }: { p: PatronDetectado; onCrear: () => void }) {
  const qc = useQueryClient();
  const avisar = useAviso();
  const ignorar = useMutation({
    mutationFn: () => post("/problemas/patrones/ignorar", { firma: p.firma }),
    onSuccess: () => { avisar("Patrón ignorado por 14 días"); qc.invalidateQueries({ queryKey: ["problemas"] }); },
  });
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: "#FDF3EA", borderColor: "#F3C9A0" }}>
      <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 2 }}>
        <AutoAwesomeIcon sx={{ color: "#E07B00" }} />
        <Box sx={{ flexGrow: 1 }}>
          <Typography sx={{ fontWeight: 700, color: "#7A3E00" }}>Patrón detectado: {p.cantidad} tickets parecidos en {p.dias} días</Typography>
          <Typography variant="body2">
            «{p.titulo}» · {p.areas.length ? p.areas.join(", ") : p.subcategoria} ·{" "}
            {p.tickets.map((t, i) => (
              <span key={t.id}>{i > 0 && ", "}<Link component={RouterLink} to={`/tickets/${t.id}`}>{t.numero}</Link></span>
            ))}
            . Puede ser un solo problema de fondo.
          </Typography>
        </Box>
        <Stack direction="row" sx={{ gap: 1, flexShrink: 0 }}>
          <Button color="inherit" onClick={() => ignorar.mutate()} disabled={ignorar.isPending}>Ignorar</Button>
          <Button variant="contained" sx={{ bgcolor: "#E8590C", "&:hover": { bgcolor: "#C94C08" } }} onClick={onCrear}>Crear problema</Button>
        </Stack>
      </Stack>
    </Paper>
  );
}

export default function Problemas() {
  const navigate = useNavigate();
  const [estado, setEstado] = useState("");
  const [texto, setTexto] = useState("");
  const [nuevo, setNuevo] = useState<{ patron: PatronDetectado | null } | null>(null);
  const q = useQuery({
    queryKey: ["problemas", "lista", estado, texto],
    queryFn: () => get<{ problemas: ProblemaLista[]; resumen: ResumenProblemas; patrones: PatronDetectado[]; gestor: boolean }>(
      "/problemas", { estado: estado || undefined, q: texto || undefined }),
  });
  const r = q.data?.resumen;
  return (
    <Box>
      <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} justifyContent="space-between" sx={{ gap: 2, mb: 3 }}>
        <Box>
          <Typography variant="h5">Gestión de problemas</Typography>
          <Typography variant="body2" color="text.secondary">La causa de fondo de los incidentes que se repiten: se analiza una vez y se corrige con un cambio.</Typography>
        </Box>
        {q.data?.gestor && <Button variant="contained" startIcon={<AddIcon />} onClick={() => setNuevo({ patron: null })}>Nuevo problema</Button>}
      </Stack>

      {(q.data?.patrones ?? []).map((p) => <Patron key={p.firma} p={p} onCrear={() => setNuevo({ patron: p })} />)}

      {r && (
        <Box sx={{ display: "grid", gap: 2, mb: 3, gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4, 1fr)" } }}>
          <Indicador titulo="Abiertos" valor={r.abiertos} color="#1367AC" />
          <Indicador titulo="Errores conocidos" valor={r.errores_conocidos} color="#5B2E9E" />
          <Indicador titulo="Incidentes evitados este mes" valor={r.evitados_mes} color="#2E7D32" />
          <Indicador titulo="Tiempo medio hasta la causa" valor={r.dias_hasta_causa === null ? "—" : `${String(r.dias_hasta_causa).replace(".", ",")} días`} color="#B7791F" />
        </Box>
      )}

      <Paper variant="outlined">
        <Stack direction={{ xs: "column", sm: "row" }} sx={{ gap: 1.5, p: 2 }}>
          <TextField size="small" placeholder="Buscar por número o título" value={texto} onChange={(e) => setTexto(e.target.value)} sx={{ minWidth: 280 }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
          <TextField size="small" select label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)} sx={{ minWidth: 200 }}>
            <MenuItem value="">Todos</MenuItem>
            <MenuItem value="ABIERTOS">Abiertos</MenuItem>
            {Object.entries({ DETECTADO: "Detectado", EN_ANALISIS: "En análisis", ERROR_CONOCIDO: "Error conocido", SOLUCION_EN_CAMBIO: "Solución en cambio",
              CERRADO: "Cerrado" }).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
        </Stack>
        {q.isLoading ? <Cargando /> : q.error ? <ErrorCarga error={q.error} /> : q.data!.problemas.length === 0 ? (
          <Vacio texto="No hay problemas registrados con estos filtros." />
        ) : (
          <Box sx={{ overflowX: "auto" }}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>N.º</TableCell><TableCell>Problema</TableCell><TableCell>Estado</TableCell>
                  <TableCell align="center">Incidentes</TableCell><TableCell>Responsable</TableCell><TableCell>Abierto</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {q.data!.problemas.map((p) => (
                  <TableRow key={p.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/problemas/${p.id}`)}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      <Link component={RouterLink} to={`/problemas/${p.id}`} sx={{ fontWeight: 700 }} onClick={(e) => e.stopPropagation()}>{p.numero}</Link>
                    </TableCell>
                    <TableCell>{p.titulo}</TableCell>
                    <TableCell><EstadoProblemaChip estado={p.estado} nombre={p.estado_nombre} /></TableCell>
                    <TableCell align="center"><Chip size="small" label={p.incidentes} /></TableCell>
                    <TableCell>{p.responsable ?? "—"}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{p.dias_abierto === null ? "—" : `${p.dias_abierto} días`}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>

      <Alert severity="info" icon={<InfoIcon />} sx={{ mt: 3 }}>
        <b>Incidente</b> = algo que hoy le impide trabajar a alguien (se resuelve rápido). <b>Problema</b> = la causa de fondo que hace que se
        repita. Se analiza una vez, los analistas aplican la solución temporal en minutos y se corrige con un <b>cambio</b>.
      </Alert>
      {nuevo && <NuevoProblema patron={nuevo.patron} onCerrar={() => setNuevo(null)} />}
    </Box>
  );
}
