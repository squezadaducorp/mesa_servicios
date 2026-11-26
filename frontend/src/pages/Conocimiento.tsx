import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, InputAdornment, Link,
  List, ListItemButton, ListItemText, MenuItem, Paper, Stack, Tab, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import PublicIcon from "@mui/icons-material/Public";
import LockIcon from "@mui/icons-material/Lock";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import LinkIcon from "@mui/icons-material/Link";
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ThumbUpAltOutlinedIcon from "@mui/icons-material/ThumbUpAltOutlined";
import ThumbDownAltOutlinedIcon from "@mui/icons-material/ThumbDownAltOutlined";
import { del, get, post, put } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { KbArticulo, KbResumen } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../components/Comunes";
import { fecha } from "../utils/formato";
import { P } from "../utils/permisos";
import { marca } from "../theme";
import { EditorPasos, Pasos } from "../components/PasosArticulo";

type Borrador = Omit<Partial<KbArticulo>, "visibilidad"> & { titulo: string; solucion: string; visibilidad: KbArticulo["visibilidad"] | null };

// La visibilidad es obligatoria: en cada artículo quien escribe elige si es interno (todo el personal de Aducorp) o externo (35)
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
        <Typography sx={{ fontWeight: 700, color }}>{externo ? "Externo · también para los de afuera" : "Interno · personal de Aducorp"}</Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary">{externo ? "Personal de Aducorp, clientes y solicitantes externos" : "Todo el personal de Aducorp, de cualquier área"}</Typography>
      <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, fontSize: 13 }}>
        {(externo
          ? ["Aparece como sugerencia al crear un ticket", "Se puede enviar como enlace en una respuesta", "Lenguaje sencillo, paso a paso"]
          : ["Procedimientos internos de cualquier área", "Lo ve todo el personal al buscar o crear tickets", "Nunca se muestra ni se envía a clientes o solicitantes de afuera"]
        ).map((x) => <li key={x}>{x}</li>)}
      </Box>
    </Paper>
  );
}

// Los pasos (con formato e imágenes) se muestran con el componente compartido
export { Pasos } from "../components/PasosArticulo";

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
                Este artículo es interno: lo ve todo el personal de Aducorp, pero no los clientes ni los solicitantes de afuera, y no se puede enviar en una respuesta.
                Si también les sirve, cree luego una versión externa vinculada con pasos sencillos.
              </Alert>
            )}
          </Box>
          {a.ticket_origen_numero && <Alert severity="info">Borrador a partir del ticket {a.ticket_origen_numero}. Revise el texto antes de publicarlo.</Alert>}
          <TextField label="Título (como lo diría quien tiene el problema)" required {...campo("titulo")} />
          <TextField label="Síntoma" multiline minRows={2} {...campo("sintoma")} />
          <EditorPasos valor={a.solucion} onCambio={(solucion) => setA((x) => ({ ...x, solucion }))} />
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
              <MenuItem value="BORRADOR">Borrador (solo lo ven quienes escriben artículos)</MenuItem>
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
                Los artículos externos los publica un supervisor; los internos, cualquier persona que escriba artículos.
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
  const personal = !!usuario && usuario.rol !== "CLIENTE";   // personal de Aducorp: ve también los internos
  const gestiona = puede(P.KB) && personal;
  const [vista, setVista] = useState<"TODOS" | "EXTERNO" | "INTERNO">("TODOS");
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
  const copiarEnlace = async (x: KbArticulo) => {
    const enlace = window.location.origin + (x.enlace_publico ?? `/conocimiento?articulo=${x.id}`);
    try {
      await navigator.clipboard.writeText(enlace);
      avisar(x.enlace_publico ? "Enlace copiado: cualquiera puede abrirlo, sin iniciar sesión" : "Enlace copiado: solo lo abre el personal de Aducorp con su sesión");
    } catch {
      window.prompt("Copie el enlace del artículo:", enlace);
    }
  };
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
          {personal && (
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
                    secondary={x.estado === "BORRADOR" ? `${x.categoria ?? "General"} · Borrador, solo lo ven quienes escriben`
                      : `${x.categoria ?? "General"} · ${x.vistas} vistas${x.util_pct !== null ? ` · ${x.util_pct} % útil` : ""} · evitó ${x.tickets_evitados} tickets`}
                    slotProps={{ primary: { sx: { fontWeight: 600, fontSize: 14 } } }}
                  />
                  {x.estado !== "PUBLICADO" && <Chip size="small" label={x.estado === "BORRADOR" ? "Borrador" : "Archivado"} variant="outlined" />}
                  {personal && <Box sx={{ ml: 0.5 }}><ChipVisibilidad v={x.visibilidad} /></Box>}
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
                {personal && <ChipVisibilidad v={a.visibilidad} />}
                {a.estado !== "PUBLICADO" && <Chip size="small" label={a.estado === "BORRADOR" ? "Borrador" : "Archivado"} color="warning" variant="outlined" />}
                <Box sx={{ flex: 1 }} />
                {personal && (
                  <Tooltip title={a.enlace_publico ? "Para enviar a cualquier usuario: se abre sin iniciar sesión"
                    : a.visibilidad === "INTERNO" ? "Artículo interno: el enlace solo lo abre el personal de Aducorp con su sesión"
                      : "Aún no está publicado: el enlace solo lo abre quien escribe artículos"}>
                    <Button size="small" startIcon={<LinkIcon />} onClick={() => copiarEnlace(a)}>Copiar enlace</Button>
                  </Tooltip>
                )}
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
                  <b>Este artículo es interno.</b> Lo ve todo el personal de Aducorp; los clientes y solicitantes de afuera no.
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
      {desdeTicket && <DesdeTicket onCerrar={() => setDesdeTicket(false)} onListo={(b) => { setDesdeTicket(false); setEditando({ ...VACIO, ...b, estado: "BORRADOR" }); }} />}
    </>
  );
}
