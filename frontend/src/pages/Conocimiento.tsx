import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, InputAdornment, Link,
  List, ListItemButton, ListItemText, MenuItem, Paper, Stack, Switch, Tab, Tabs, TextField, Typography,
} from "@mui/material";
import PublicIcon from "@mui/icons-material/Public";
import LockIcon from "@mui/icons-material/Lock";
import ShieldIcon from "@mui/icons-material/AdminPanelSettingsOutlined";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ThumbUpAltOutlinedIcon from "@mui/icons-material/ThumbUpAltOutlined";
import ThumbDownAltOutlinedIcon from "@mui/icons-material/ThumbDownAltOutlined";
import { del, get, patch, post, put } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { KbArticulo, KbResumen, Pagina, UsuarioAdmin } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import { fecha } from "../utils/formato";
import { P } from "../utils/permisos";
import { marca } from "../theme";

type Borrador = Omit<Partial<KbArticulo>, "visibilidad"> & { titulo: string; solucion: string; visibilidad: KbArticulo["visibilidad"] | null };

// La visibilidad es obligatoria: quien escribe elige si es para los solicitantes o solo para el equipo de TI (35)
const VACIO: Borrador = { titulo: "", sintoma: "", solucion: "", nota: "", palabras_clave: "", categoria_id: null, subcategoria_id: null, estado: "BORRADOR", visibilidad: null };
const VERDE = "#2E7D32";
const MORADO = "#5E35B1";
const ROLES_PUBLICAN = ["SUPERVISOR", "ADMIN_MESA", "SUPER_ADMIN"];

export function ChipVisibilidad({ v }: { v: KbArticulo["visibilidad"] }) {
  const externo = v === "EXTERNO";
  return (
    <Chip size="small" icon={externo ? <PublicIcon /> : <LockIcon />} label={externo ? "Externo" : "Interno"}
      sx={{ fontWeight: 600, color: externo ? VERDE : MORADO, bgcolor: externo ? "#E8F5E9" : "#EDE7F6", border: `1px solid ${externo ? "#A5D6A7" : "#C5B3E6"}`,
        "& .MuiChip-icon": { color: externo ? VERDE : MORADO } }} />
  );
}

function TarjetaVisibilidad({ valor, elegido, onElegir }: { valor: "EXTERNO" | "INTERNO"; elegido: boolean; onElegir: () => void }) {
  const externo = valor === "EXTERNO";
  const color = externo ? VERDE : MORADO;
  return (
    <Paper variant="outlined" onClick={onElegir} role="radio" aria-checked={elegido} tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onElegir()}
      sx={{ p: 2, flex: 1, cursor: "pointer", borderWidth: 2, borderColor: elegido ? color : "divider", bgcolor: elegido ? (externo ? "#F3FAF3" : "#F6F2FC") : "background.paper" }}>
      <Stack direction="row" spacing={1.2} sx={{ alignItems: "center", mb: 0.5 }}>
        {externo ? <PublicIcon sx={{ color }} /> : <LockIcon sx={{ color }} />}
        <Typography sx={{ fontWeight: 700, color }}>{externo ? "Externo · para los solicitantes" : "Interno · solo equipo de TI"}</Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary">{externo ? "Todo el personal de Aducorp" : "Personas marcadas como «Equipo de TI»"}</Typography>
      <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, fontSize: 13 }}>
        {(externo
          ? ["Aparece como sugerencia al crear un ticket", "Se puede enviar como enlace en una respuesta", "Lenguaje sencillo, paso a paso"]
          : ["Procedimientos técnicos, configuraciones y diagnósticos", "Visible al atender tickets", "Nunca se muestra ni se envía al solicitante"]
        ).map((x) => <li key={x}>{x}</li>)}
      </Box>
    </Paper>
  );
}

/** Pasos numerados: cada línea de la solución es un paso. */
export function Pasos({ texto }: { texto: string }) {
  const lineas = texto.split("\n").map((l) => l.replace(/^\s*\d+[.)-]\s*/, "").trim()).filter(Boolean);
  if (lineas.length <= 1) return <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{texto}</Typography>;
  return (
    <>
      {lineas.map((t, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ mb: 0.8 }}>
          <Typography variant="body2" sx={{ color: marca.azul, fontWeight: 700 }}>{i + 1}.</Typography>
          <Typography variant="body2">{t}</Typography>
        </Stack>
      ))}
    </>
  );
}

function Editor({ inicial, onCerrar }: { inicial: Borrador; onCerrar: (guardado?: KbArticulo) => void }) {
  const cat = useCatalogos();
  const avisar = useAviso();
  const { usuario } = useAuth();
  const [a, setA] = useState<Borrador>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState({ claves: !!inicial.id, probado: !!inicial.id });
  const publicaExterno = ROLES_PUBLICAN.includes(usuario?.rol ?? "");
  const bloqueado = a.estado === "PUBLICADO" && a.visibilidad === "EXTERNO" && !publicaExterno;
  const faltaRevision = a.estado === "PUBLICADO" && !(revision.claves && revision.probado);
  const categoria = cat.data?.categorias.find((c) => c.id === a.categoria_id);
  const guardar = useMutation({
    mutationFn: () => {
      const body = { ...a, categoria_id: a.categoria_id || null, subcategoria_id: a.subcategoria_id || null, sintoma: a.sintoma || null, nota: a.nota || null, palabras_clave: a.palabras_clave || null };
      return a.id ? put<KbArticulo>(`/conocimiento/${a.id}`, body) : post<KbArticulo>("/conocimiento", body);
    },
    onSuccess: (r) => {
      avisar("Artículo guardado");
      onCerrar(r);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const campo = (k: keyof Borrador) => ({ value: (a[k] as string | null) ?? "", onChange: (e: React.ChangeEvent<HTMLInputElement>) => setA({ ...a, [k]: e.target.value }) });
  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="md" fullWidth>
      <DialogTitle>{a.id ? "Editar artículo" : "Nuevo artículo"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>¿Para quién es este artículo? <Typography component="span" variant="caption" color="text.secondary">· obligatorio, se puede cambiar después</Typography></Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} role="radiogroup">
              <TarjetaVisibilidad valor="EXTERNO" elegido={a.visibilidad === "EXTERNO"} onElegir={() => setA({ ...a, visibilidad: "EXTERNO" })} />
              <TarjetaVisibilidad valor="INTERNO" elegido={a.visibilidad === "INTERNO"} onElegir={() => setA({ ...a, visibilidad: "INTERNO" })} />
            </Stack>
            {a.articulo_relacionado && (
              <Alert severity="info" sx={{ mt: 1.5 }}>Versión vinculada a «{a.articulo_relacionado}».</Alert>
            )}
            {a.visibilidad === "INTERNO" && (
              <Alert severity="warning" icon={<LockIcon />} sx={{ mt: 1.5 }}>
                Este artículo es interno: los solicitantes no lo verán en las sugerencias ni en la Base de conocimiento, y no se puede enviar en una respuesta.
                Si también les sirve, cree luego una versión externa vinculada con pasos sencillos.
              </Alert>
            )}
          </Box>
          {a.ticket_origen_numero && <Alert severity="info">Borrador a partir del ticket {a.ticket_origen_numero}. Revise el texto antes de publicarlo.</Alert>}
          <TextField label="Título (como lo diría quien tiene el problema)" required {...campo("titulo")} />
          <TextField label="Síntoma" multiline minRows={2} {...campo("sintoma")} />
          <TextField label="Solución" required multiline minRows={5} helperText="Escriba un paso por línea; se muestran numerados." {...campo("solucion")} />
          <TextField label="Nota o advertencia (opcional)" {...campo("nota")} />
          <TextField label="Palabras clave" helperText="Separadas por coma: ayudan a que se sugiera al crear tickets." {...campo("palabras_clave")} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Categoría" sx={{ flex: 1 }} value={a.categoria_id ?? ""} onChange={(e) => setA({ ...a, categoria_id: e.target.value ? Number(e.target.value) : null, subcategoria_id: null })}>
              <MenuItem value="">(General)</MenuItem>
              {(cat.data?.categorias ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
            </TextField>
            <TextField select label="Subcategoría" sx={{ flex: 1 }} disabled={!categoria} value={a.subcategoria_id ?? ""} onChange={(e) => setA({ ...a, subcategoria_id: e.target.value ? Number(e.target.value) : null })}>
              <MenuItem value="">(Todas)</MenuItem>
              {(categoria?.subcategorias ?? []).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
            </TextField>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Estado" sx={{ flex: 1 }} {...campo("estado")}
              helperText={bloqueado ? "Los artículos externos los publica un supervisor: guárdelo como borrador para que lo revise." : undefined}
              error={bloqueado}>
              <MenuItem value="BORRADOR">Borrador (solo lo ve el equipo de TI)</MenuItem>
              <MenuItem value="PUBLICADO">Publicado</MenuItem>
              <MenuItem value="ARCHIVADO">Archivado</MenuItem>
            </TextField>
          </Stack>
          {a.estado === "PUBLICADO" && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">Revisión antes de publicar</Typography>
              <FormControlLabel control={<Checkbox checked={revision.claves} onChange={(e) => setRevision({ ...revision, claves: e.target.checked })} />} label="No contiene contraseñas ni claves" />
              <FormControlLabel control={<Checkbox checked={revision.probado} onChange={(e) => setRevision({ ...revision, probado: e.target.checked })} />} label="Probado en un equipo real" />
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                Los artículos externos los publica un supervisor; los internos, cualquier persona del Equipo de TI.
              </Typography>
            </Paper>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" disabled={guardar.isPending || a.titulo.length < 5 || a.solucion.length < 10 || !a.visibilidad || bloqueado || faltaRevision}
          onClick={() => guardar.mutate()}>
          {a.estado === "PUBLICADO" ? "Publicar" : "Guardar"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function DesdeTicket({ onListo, onCerrar }: { onListo: (b: Borrador) => void; onCerrar: () => void }) {
  const [numero, setNumero] = useState("");
  const [error, setError] = useState<string | null>(null);
  const buscar = async () => {
    setError(null);
    try {
      const n = numero.trim();
      let id = Number(n);
      if (!/^\d+$/.test(n)) {
        const r = await get<{ items: { id: number; numero: string }[] }>("/tickets", { texto: n, tamano: 5 });
        const t = r.items.find((x) => x.numero.toUpperCase() === n.toUpperCase()) ?? r.items[0];
        if (!t) throw new Error("No se encontró el ticket");
        id = t.id;
      }
      onListo(await post<Borrador>("/conocimiento/desde-ticket", { ticket_id: id }));
    } catch (e) {
      setError(mensajeError(e));
    }
  };
  return (
    <Dialog open onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle>Crear desde un ticket resuelto</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField autoFocus fullWidth sx={{ mt: 1 }} label="Número de ticket" placeholder="ADU-2026-000612" value={numero} onChange={(e) => setNumero(e.target.value)}
          helperText="Se copian el asunto, la descripción y la última respuesta al solicitante." />
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" disabled={!numero.trim()} onClick={buscar}>Continuar</Button>
      </DialogActions>
    </Dialog>
  );
}

/** Quién es «Equipo de TI»: ve los artículos internos y, con permiso de la base de conocimiento, puede escribir en ella. */
function EquipoTi({ onCerrar }: { onCerrar: () => void }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const lista = useQuery({ queryKey: ["admin", "usuarios", "equipo-ti"], queryFn: () => get<Pagina<UsuarioAdmin>>("/admin/usuarios", { tamano: 500 }) });
  const cambiar = useMutation({
    mutationFn: ({ id, valor }: { id: number; valor: boolean }) => patch<UsuarioAdmin>(`/admin/usuarios/${id}`, { equipo_ti: valor }),
    onSuccess: (u) => {
      qc.setQueryData<Pagina<UsuarioAdmin>>(["admin", "usuarios", "equipo-ti"], (d) => d && { ...d, items: d.items.map((x) => (x.id === u.id ? u : x)) });
      avisar(u.equipo_ti ? `${u.nombre} ahora es Equipo de TI` : `${u.nombre} ya no es Equipo de TI`);
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const usuarios = (lista.data?.items ?? []).filter((u) => u.activo && (!q || `${u.nombre} ${u.cargo ?? ""}`.toLowerCase().includes(q.toLowerCase())))
    .sort((x, y) => Number(y.equipo_ti) - Number(x.equipo_ti) || x.nombre.localeCompare(y.nombre));
  const marcados = (lista.data?.items ?? []).filter((u) => u.equipo_ti).length;
  return (
    <Dialog open onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle>Equipo de TI · {marcados} persona{marcados === 1 ? "" : "s"}</DialogTitle>
      <DialogContent dividers>
        <Alert severity="info" sx={{ mb: 2 }}>
          Solo estas personas ven los artículos internos y pueden escribir en la Base de conocimiento. Como todo el personal tiene rol Analista,
          esta marca es la que de verdad separa lo interno.
        </Alert>
        <TextField fullWidth size="small" placeholder="Buscar persona" value={q} onChange={(e) => setQ(e.target.value)} sx={{ mb: 1 }} />
        {lista.isLoading ? <Cargando alto={120} /> : usuarios.map((u) => (
          <Stack key={u.id} direction="row" sx={{ alignItems: "center", py: 0.6, borderBottom: "1px solid #EEF1F5" }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{u.nombre}</Typography>
              <Typography variant="caption" color="text.secondary">{u.cargo ?? u.rol}</Typography>
            </Box>
            <Switch checked={u.equipo_ti} disabled={cambiar.isPending} onChange={(e) => cambiar.mutate({ id: u.id, valor: e.target.checked })}
              slotProps={{ input: { "aria-label": `Equipo de TI: ${u.nombre}` } }} />
          </Stack>
        ))}
      </DialogContent>
      <DialogActions><Button onClick={onCerrar}>Listo</Button></DialogActions>
    </Dialog>
  );
}

export default function Conocimiento() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [params, setParams] = useSearchParams();
  const [texto, setTexto] = useState("");
  const [buscado, setBuscado] = useState("");
  const [categoriaId, setCategoriaId] = useState<number | null>(null);
  const [editando, setEditando] = useState<Borrador | null>(null);
  const [desdeTicket, setDesdeTicket] = useState(false);
  const [votado, setVotado] = useState<Record<number, boolean>>({});
  const { usuario } = useAuth();
  const equipoTi = !!usuario?.equipo_ti;
  const gestiona = puede(P.KB) && equipoTi;
  const [vista, setVista] = useState<"TODOS" | "EXTERNO" | "INTERNO">("TODOS");
  const [equipo, setEquipo] = useState(false);
  const seleccion = Number(params.get("articulo")) || null;

  useEffect(() => {
    const t = setTimeout(() => setBuscado(texto), 300);
    return () => clearTimeout(t);
  }, [texto]);

  const lista = useQuery({ queryKey: ["kb", buscado, categoriaId], queryFn: () => get<KbResumen[]>("/conocimiento", { texto: buscado, categoria_id: categoriaId ?? undefined }) });
  const cats = useQuery({ queryKey: ["kb", "categorias"], queryFn: () => get<{ id: number | null; nombre: string; total: number }[]>("/conocimiento/categorias") });
  const elegido = seleccion ?? lista.data?.[0]?.id ?? null;
  const articulo = useQuery({ queryKey: ["kb", "articulo", elegido], queryFn: () => get<KbArticulo>(`/conocimiento/${elegido}`), enabled: !!elegido, staleTime: 5 * 60_000, refetchOnWindowFocus: false });
  const votar = useMutation({
    mutationFn: (util: boolean) => post(`/conocimiento/${elegido}/voto`, { util }),
    onSuccess: (_, util) => {
      setVotado((v) => ({ ...v, [elegido!]: util }));
      avisar("Gracias por su opinión");
    },
  });
  const eliminar = useMutation({
    mutationFn: (id: number) => del(`/conocimiento/${id}`),
    onSuccess: () => {
      avisar("Artículo eliminado");
      setParams({});
      qc.invalidateQueries({ queryKey: ["kb"] });
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const total = (cats.data ?? []).reduce((s, c) => s + c.total, 0);
  const a = articulo.data;
  const todos = lista.data ?? [];
  const visibles = vista === "TODOS" ? todos : todos.filter((x) => x.visibilidad === vista);
  const versionExterna = (x: KbArticulo) => setEditando({
    ...VACIO, titulo: x.titulo, categoria_id: x.categoria_id, subcategoria_id: x.subcategoria_id, palabras_clave: x.palabras_clave ?? "",
    sintoma: x.sintoma ?? "", visibilidad: "EXTERNO", articulo_relacionado_id: x.id, articulo_relacionado: x.titulo,
  });

  return (
    <>
      <Encabezado
        titulo="Base de conocimiento"
        subtitulo="Soluciones a los problemas más frecuentes. Se sugieren solas al crear un ticket."
        acciones={(gestiona || puede(P.USUARIOS)) && (
          <>
            {puede(P.USUARIOS) && <Button variant="outlined" startIcon={<ShieldIcon />} onClick={() => setEquipo(true)}>Equipo de TI</Button>}
            {gestiona && <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setDesdeTicket(true)}>Crear desde un ticket resuelto</Button>}
            {gestiona && <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditando({ ...VACIO })}>Nuevo artículo</Button>}
          </>
        )}
      />
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "5fr 7fr" }, alignItems: "start" }}>
        <Paper>
          <Box sx={{ p: 2 }}>
            <TextField fullWidth placeholder="Buscar: token, impresora, VPN…" value={texto} onChange={(e) => setTexto(e.target.value)}
              slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }} />
            <Stack direction="row" sx={{ mt: 1.5, flexWrap: "wrap", gap: 1 }}>
              <Chip label={`Todos (${total})`} size="small" color={categoriaId === null ? "primary" : "default"} variant={categoriaId === null ? "filled" : "outlined"} onClick={() => setCategoriaId(null)} />
              {(cats.data ?? []).filter((c) => c.id !== null).map((c) => (
                <Chip key={c.id} label={`${c.nombre} (${c.total})`} size="small" color={categoriaId === c.id ? "primary" : "default"} variant={categoriaId === c.id ? "filled" : "outlined"} onClick={() => setCategoriaId(c.id)} />
              ))}
            </Stack>
          </Box>
          {equipoTi && (
            <Tabs value={vista} onChange={(_, v) => setVista(v)} variant="fullWidth" sx={{ borderTop: "1px solid #E3E8F0" }}>
              <Tab value="TODOS" label={`Todos (${todos.length})`} />
              <Tab value="EXTERNO" icon={<PublicIcon fontSize="small" />} iconPosition="start" sx={{ color: VERDE, minHeight: 48 }}
                label={`Externos (${todos.filter((x) => x.visibilidad === "EXTERNO").length})`} />
              <Tab value="INTERNO" icon={<LockIcon fontSize="small" />} iconPosition="start" sx={{ color: MORADO, minHeight: 48 }}
                label={`Internos (${todos.filter((x) => x.visibilidad === "INTERNO").length})`} />
            </Tabs>
          )}
          <Divider />
          {lista.isLoading ? <Cargando alto={160} /> : lista.error ? <ErrorCarga error={lista.error} /> : (
            <List sx={{ py: 0 }}>
              {visibles.map((x) => (
                <ListItemButton key={x.id} selected={x.id === elegido} divider onClick={() => setParams({ articulo: String(x.id) })}>
                  <ListItemText
                    primary={x.titulo}
                    secondary={x.estado === "BORRADOR" ? `${x.categoria ?? "General"} · Borrador, solo lo ve el equipo`
                      : `${x.categoria ?? "General"} · ${x.vistas} vistas${x.util_pct !== null ? ` · ${x.util_pct} % útil` : ""} · evitó ${x.tickets_evitados} tickets`}
                    slotProps={{ primary: { sx: { fontWeight: 600, fontSize: 14 } } }}
                  />
                  {x.estado !== "PUBLICADO" && <Chip size="small" label={x.estado === "BORRADOR" ? "Borrador" : "Archivado"} variant="outlined" />}
                  {equipoTi && <Box sx={{ ml: 0.5 }}><ChipVisibilidad v={x.visibilidad} /></Box>}
                </ListItemButton>
              ))}
              {visibles.length === 0 && <Vacio texto={buscado ? "No hay artículos con esas palabras" : "Todavía no hay artículos"} />}
            </List>
          )}
        </Paper>

        <Paper sx={{ p: 3, minHeight: 300 }}>
          {!elegido ? <Vacio texto="Elija un artículo de la lista" /> : articulo.isLoading || !a ? <Cargando alto={200} /> : (
            <>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                <Chip size="small" label={[a.categoria ?? "General", a.subcategoria].filter(Boolean).join(" › ")} variant="outlined" />
                {equipoTi && <ChipVisibilidad v={a.visibilidad} />}
                {a.estado !== "PUBLICADO" && <Chip size="small" label={a.estado === "BORRADOR" ? "Borrador" : "Archivado"} color="warning" variant="outlined" />}
                <Box sx={{ flex: 1 }} />
                {a.puede_editar && (
                  <>
                    <Button size="small" startIcon={<EditIcon />} onClick={() => setEditando(a)}>Editar</Button>
                    <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => window.confirm("¿Eliminar este artículo?") && eliminar.mutate(a.id)}>Eliminar</Button>
                  </>
                )}
              </Stack>
              <Typography variant="h5" sx={{ mt: 1.5 }}>{a.titulo}</Typography>
              {a.visibilidad === "INTERNO" && (
                <Alert severity="warning" icon={<LockIcon />} sx={{ mt: 1.5 }}
                  action={a.puede_editar && !a.articulo_relacionado_id && (
                    <Button color="inherit" size="small" startIcon={<AddIcon />} onClick={() => versionExterna(a)}>Crear versión externa vinculada</Button>
                  )}>
                  <b>Este artículo es interno.</b> Los solicitantes no lo ven en las sugerencias ni en la Base de conocimiento.
                </Alert>
              )}
              {a.articulo_relacionado_id && (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  {a.visibilidad === "INTERNO" ? "Versión externa" : "Versión interna (técnica)"}:{" "}
                  <Link component="button" onClick={() => setParams({ articulo: String(a.articulo_relacionado_id) })}>{a.articulo_relacionado}</Link>
                </Typography>
              )}
              <Typography variant="caption" color="text.secondary">
                Actualizado el {fecha(a.fecha_actualizacion ?? a.fecha_creacion)}{a.actualizado_por ? ` por ${a.actualizado_por}` : ""}
                {a.ticket_origen_numero ? ` · creado a partir de ${a.ticket_origen_numero}` : ""}
              </Typography>
              <Box sx={{ mt: 2.5 }}>
                {a.sintoma && (
                  <>
                    <Typography variant="subtitle2" sx={{ color: marca.navy, mb: 1 }}>Síntoma</Typography>
                    <Typography variant="body2" sx={{ mb: 2, whiteSpace: "pre-wrap" }}>{a.sintoma}</Typography>
                  </>
                )}
                <Typography variant="subtitle2" sx={{ color: marca.navy, mb: 1 }}>Solución</Typography>
                <Pasos texto={a.solucion} />
                {a.nota && <Alert severity="warning" sx={{ mt: 1.5 }}>{a.nota}</Alert>}
              </Box>
              <Divider sx={{ my: 2.5 }} />
              <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
                <Stack direction="row" spacing={0.8} sx={{ alignItems: "center" }}><VisibilityIcon fontSize="small" color="action" /><Typography variant="body2"><b>{a.vistas}</b> vistas</Typography></Stack>
                {a.util_pct !== null && <Stack direction="row" spacing={0.8} sx={{ alignItems: "center" }}><ThumbUpAltOutlinedIcon fontSize="small" color="success" /><Typography variant="body2"><b>{a.util_pct} %</b> le sirvió</Typography></Stack>}
                <Stack direction="row" spacing={0.8} sx={{ alignItems: "center" }}><CheckCircleIcon fontSize="small" color="success" /><Typography variant="body2"><b>{a.tickets_evitados}</b> tickets evitados</Typography></Stack>
                <Box sx={{ flex: 1 }} />
                {a.estado === "PUBLICADO" && (votado[a.id] === undefined ? (
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" startIcon={<ThumbUpAltOutlinedIcon />} onClick={() => votar.mutate(true)}>Me sirvió</Button>
                    <Button size="small" variant="outlined" color="inherit" startIcon={<ThumbDownAltOutlinedIcon />} onClick={() => votar.mutate(false)}>No</Button>
                  </Stack>
                ) : <Typography variant="body2" color="text.secondary">Gracias por su opinión</Typography>)}
              </Stack>
            </>
          )}
        </Paper>
      </Box>
      {editando && (
        <Editor
          inicial={editando}
          onCerrar={(g) => {
            setEditando(null);
            if (g) {
              qc.invalidateQueries({ queryKey: ["kb"] });
              setParams({ articulo: String(g.id) });
            }
          }}
        />
      )}
      {equipo && <EquipoTi onCerrar={() => setEquipo(false)} />}
      {desdeTicket && <DesdeTicket onCerrar={() => setDesdeTicket(false)} onListo={(b) => { setDesdeTicket(false); setEditando({ ...VACIO, ...b, estado: "BORRADOR" }); }} />}
    </>
  );
}
