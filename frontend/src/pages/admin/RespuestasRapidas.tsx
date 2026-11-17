import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, FormControlLabel, InputAdornment, MenuItem, Paper, Radio, RadioGroup, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import { get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { RespuestaRapida } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, Vacio } from "../../components/Comunes";
import { P } from "../../utils/permisos";

export const CHIP_ATAJO = { fontFamily: "monospace", bgcolor: "#FFF3D6", color: "#8A5A00" } as const;
const DATOS = ["{solicitante}", "{ticket}", "{asunto}", "{mi_nombre}", "{mi_area}", "{responsable}", "{vence}", "{categoria}"];
const ESTADOS: Record<string, string> = { EN_PROCESO: "En Proceso", PENDIENTE_CLIENTE: "Pendiente Cliente (pausa el SLA)", RESUELTO: "Resuelto" };
type Form = Omit<RespuestaRapida, "id" | "categoria" | "subcategoria" | "area" | "propietario_id" | "propietario" | "usos" | "puede_editar"> & { id?: number };

const NUEVA: Form = { atajo: "/", titulo: "", texto: "", categoria_id: null, subcategoria_id: null, estado_destino: null, alcance: "PERSONAL", area_id: null, activo: true };

export default function RespuestasRapidas() {
  const { puede } = useAuth();
  const gestiona = puede(P.RESPUESTAS);
  const cat = useCatalogos();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [texto, setTexto] = useState("");
  const [area, setArea] = useState<number | "">("");
  const [f, setF] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lista = useQuery({ queryKey: ["respuestas", "todas"], queryFn: () => get<RespuestaRapida[]>("/respuestas", { todas: true }) });
  const guardar = useMutation({
    mutationFn: (x: Form) => {
      const body = { ...x, categoria_id: x.categoria_id || null, subcategoria_id: x.subcategoria_id || null, area_id: x.alcance === "AREA" ? x.area_id : null };
      return x.id ? put<RespuestaRapida>(`/respuestas/${x.id}`, body) : post<RespuestaRapida>("/respuestas", body);
    },
    onSuccess: (r) => {
      avisar(r.activo ? "Respuesta guardada" : "Respuesta desactivada");
      setF(r.activo ? { ...r } : null);
      setError(null);
      qc.invalidateQueries({ queryKey: ["respuestas"] });
    },
    onError: (e) => setError(mensajeError(e)),
  });

  const filas = useMemo(() => {
    const q = texto.trim().toLowerCase();
    return (lista.data ?? []).filter((r) => (!q || `${r.atajo} ${r.titulo} ${r.texto}`.toLowerCase().includes(q)) && (!area || r.area_id === area || r.alcance === "TODOS"));
  }, [lista.data, texto, area]);
  const categoria = cat.data?.categorias.find((c) => c.id === f?.categoria_id);
  const para = (r: RespuestaRapida) => (r.alcance === "TODOS" ? "Todos" : r.alcance === "AREA" ? r.area ?? "Área" : "Solo yo");

  return (
    <>
      <Encabezado
        titulo="Respuestas rápidas"
        subtitulo="Textos guardados que el equipo inserta en la respuesta del ticket con el botón ⚡ o escribiendo «/»."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => { setError(null); setF({ ...NUEVA, alcance: gestiona ? "TODOS" : "PERSONAL" }); }}>Nueva respuesta</Button>}
      />
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "6.6fr 5.4fr" }, alignItems: "start" }}>
        <Paper>
          <Stack direction="row" spacing={1.5} sx={{ p: 2 }}>
            <TextField placeholder="Buscar" sx={{ flex: 1 }} value={texto} onChange={(e) => setTexto(e.target.value)}
              slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }} />
            <TextField select value={area} onChange={(e) => setArea(e.target.value ? Number(e.target.value) : "")} sx={{ width: 190 }}>
              <MenuItem value="">Todas las áreas</MenuItem>
              {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
            </TextField>
          </Stack>
          {lista.isLoading ? <Cargando /> : (
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Atajo</TableCell><TableCell>Título</TableCell><TableCell>Para</TableCell><TableCell align="right">Usos</TableCell></TableRow></TableHead>
                <TableBody>
                  {filas.map((r) => (
                    <TableRow key={r.id} hover selected={f?.id === r.id} sx={{ cursor: r.puede_editar ? "pointer" : undefined, opacity: r.activo ? 1 : 0.5 }}
                      onClick={() => { if (r.puede_editar) { setError(null); setF({ ...r }); } }}>
                      <TableCell><Chip size="small" label={r.atajo} sx={CHIP_ATAJO} /></TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{r.titulo}</Typography>
                        <Typography variant="caption" color="text.secondary">{[r.categoria ?? "General", r.subcategoria].filter(Boolean).join(" › ")}{r.activo ? "" : " · desactivada"}</Typography>
                      </TableCell>
                      <TableCell><Chip size="small" variant="outlined" label={para(r)} /></TableCell>
                      <TableCell align="right">{r.usos}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {filas.length === 0 && <Vacio texto="No hay respuestas" />}
            </Box>
          )}
          <Alert severity="info" sx={{ m: 2 }}>
            Las «plantillas de respuesta» que ya tenía cada subcategoría se pasaron aquí al actualizar; nada se perdió.
          </Alert>
        </Paper>

        {f ? (
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>{f.id ? "Editar respuesta" : "Nueva respuesta"}</Typography>
            <Stack spacing={2}>
              {error && <Alert severity="error">{error}</Alert>}
              <Stack direction="row" spacing={1.5}>
                <TextField label="Atajo" value={f.atajo} sx={{ width: 150 }} onChange={(e) => setF({ ...f, atajo: e.target.value.toLowerCase().replace(/[^a-z0-9_/-]/g, "") })} />
                <TextField label="Título" value={f.titulo} sx={{ flex: 1 }} onChange={(e) => setF({ ...f, titulo: e.target.value })} />
              </Stack>
              <TextField label="Texto" multiline minRows={6} value={f.texto} onChange={(e) => setF({ ...f, texto: e.target.value })} />
              <Box>
                <Typography variant="caption" color="text.secondary">Insertar dato (se llena solo con los datos del ticket):</Typography>
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.8, mt: 0.5 }}>
                  {DATOS.map((v) => <Chip key={v} size="small" variant="outlined" color="primary" label={v} onClick={() => setF({ ...f, texto: f.texto + v })} />)}
                </Stack>
              </Box>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select label="Sugerir en categoría" sx={{ flex: 1 }} value={f.categoria_id ?? ""} onChange={(e) => setF({ ...f, categoria_id: e.target.value ? Number(e.target.value) : null, subcategoria_id: null })}>
                  <MenuItem value="">(Todas)</MenuItem>
                  {(cat.data?.categorias ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
                <TextField select label="Subcategoría" sx={{ flex: 1 }} disabled={!categoria} value={f.subcategoria_id ?? ""} onChange={(e) => setF({ ...f, subcategoria_id: e.target.value ? Number(e.target.value) : null })}>
                  <MenuItem value="">(Todas)</MenuItem>
                  {(categoria?.subcategorias ?? []).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <TextField select label="Al usarla, cambiar estado a" value={f.estado_destino ?? ""} onChange={(e) => setF({ ...f, estado_destino: e.target.value || null })}
                helperText="Opcional. Ej.: una respuesta que pide datos puede pasar el ticket a Pendiente Cliente.">
                <MenuItem value="">(No cambiar)</MenuItem>
                {Object.entries(ESTADOS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
              </TextField>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>¿Quién la puede usar?</Typography>
                <RadioGroup row value={f.alcance} onChange={(e) => setF({ ...f, alcance: e.target.value as Form["alcance"] })}>
                  <FormControlLabel value="TODOS" disabled={!gestiona} control={<Radio size="small" />} label="Todo el equipo" />
                  <FormControlLabel value="AREA" disabled={!gestiona} control={<Radio size="small" />} label="Solo un área" />
                  <FormControlLabel value="PERSONAL" control={<Radio size="small" />} label="Solo yo" />
                </RadioGroup>
                {f.alcance === "AREA" && (
                  <TextField select fullWidth label="Área" value={f.area_id ?? ""} onChange={(e) => setF({ ...f, area_id: Number(e.target.value) })}>
                    {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
                  </TextField>
                )}
                {!gestiona && <Typography variant="caption" color="text.secondary">Las respuestas compartidas las crea el coordinador de la mesa.</Typography>}
              </Box>
              <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                {f.id && <Button color="error" onClick={() => guardar.mutate({ ...f, activo: false })}>Desactivar</Button>}
                <Button onClick={() => setF(null)}>Cerrar</Button>
                <Button variant="contained" disabled={guardar.isPending || f.atajo.length < 2 || f.titulo.length < 3 || f.texto.length < 3}
                  onClick={() => guardar.mutate({ ...f, activo: true })}>Guardar</Button>
              </Stack>
            </Stack>
          </Paper>
        ) : (
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Cómo funciona</Typography>
            {[
              "En el ticket, escriba «/» en la respuesta o toque el botón ⚡ para ver la lista.",
              "Primero aparecen las de la subcategoría y la categoría del ticket.",
              "Al insertarla, el nombre del solicitante, el número de ticket y su firma se completan solos.",
              "Una respuesta puede además cambiar el estado, por ejemplo pasar a Pendiente Cliente.",
            ].map((t, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ mb: 0.8 }}>
                <Typography variant="body2" sx={{ color: "primary.main", fontWeight: 700 }}>{i + 1}.</Typography>
                <Typography variant="body2">{t}</Typography>
              </Stack>
            ))}
          </Paper>
        )}
      </Box>
    </>
  );
}
