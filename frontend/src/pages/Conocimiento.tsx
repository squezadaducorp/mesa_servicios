import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, InputAdornment, List, ListItemButton, ListItemText,
  MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
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

type Borrador = Partial<KbArticulo> & { titulo: string; solucion: string };

const VACIO: Borrador = { titulo: "", sintoma: "", solucion: "", nota: "", palabras_clave: "", categoria_id: null, subcategoria_id: null, estado: "BORRADOR", visibilidad: "TODOS" };

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
  const [a, setA] = useState<Borrador>(inicial);
  const [error, setError] = useState<string | null>(null);
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
            <TextField select label="Estado" sx={{ flex: 1 }} {...campo("estado")}>
              <MenuItem value="BORRADOR">Borrador (solo lo ve el equipo)</MenuItem>
              <MenuItem value="PUBLICADO">Publicado</MenuItem>
              <MenuItem value="ARCHIVADO">Archivado</MenuItem>
            </TextField>
            <TextField select label="Visible para" sx={{ flex: 1 }} {...campo("visibilidad")}>
              <MenuItem value="TODOS">Todo el personal</MenuItem>
              <MenuItem value="MESA">Solo el equipo de la mesa</MenuItem>
            </TextField>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" disabled={guardar.isPending || a.titulo.length < 5 || a.solucion.length < 10} onClick={() => guardar.mutate()}>
          Guardar
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
  const gestiona = puede(P.KB);
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

  return (
    <>
      <Encabezado
        titulo="Base de conocimiento"
        subtitulo="Soluciones a los problemas más frecuentes. Se sugieren solas al crear un ticket."
        acciones={gestiona && (
          <>
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setDesdeTicket(true)}>Crear desde un ticket resuelto</Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditando({ ...VACIO })}>Nuevo artículo</Button>
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
          <Divider />
          {lista.isLoading ? <Cargando alto={160} /> : lista.error ? <ErrorCarga error={lista.error} /> : (
            <List sx={{ py: 0 }}>
              {(lista.data ?? []).map((x) => (
                <ListItemButton key={x.id} selected={x.id === elegido} divider onClick={() => setParams({ articulo: String(x.id) })}>
                  <ListItemText
                    primary={x.titulo}
                    secondary={x.estado === "BORRADOR" ? `${x.categoria ?? "General"} · Borrador, solo lo ve el equipo`
                      : `${x.categoria ?? "General"} · ${x.vistas} vistas${x.util_pct !== null ? ` · ${x.util_pct} % útil` : ""} · evitó ${x.tickets_evitados} tickets`}
                    slotProps={{ primary: { sx: { fontWeight: 600, fontSize: 14 } } }}
                  />
                  {x.estado !== "PUBLICADO" && <Chip size="small" label={x.estado === "BORRADOR" ? "Borrador" : "Archivado"} variant="outlined" />}
                  {x.visibilidad === "MESA" && <Chip size="small" label="Interno" variant="outlined" sx={{ ml: 0.5 }} />}
                </ListItemButton>
              ))}
              {lista.data?.length === 0 && <Vacio texto={buscado ? "No hay artículos con esas palabras" : "Todavía no hay artículos"} />}
            </List>
          )}
        </Paper>

        <Paper sx={{ p: 3, minHeight: 300 }}>
          {!elegido ? <Vacio texto="Elija un artículo de la lista" /> : articulo.isLoading || !a ? <Cargando alto={200} /> : (
            <>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                <Chip size="small" label={[a.categoria ?? "General", a.subcategoria].filter(Boolean).join(" › ")} variant="outlined" />
                <Chip size="small" label={a.visibilidad === "TODOS" ? "Visible para todo el personal" : "Solo el equipo de la mesa"} color={a.visibilidad === "TODOS" ? "success" : "default"} variant="outlined" />
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
