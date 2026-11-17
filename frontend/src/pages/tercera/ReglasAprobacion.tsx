import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, Collapse, FormControlLabel, Grid, Link, MenuItem, Paper, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import ArrowIcon from "@mui/icons-material/ArrowForward";
import EditIcon from "@mui/icons-material/EditOutlined";
import AddIcon from "@mui/icons-material/Add";
import { get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { Pagina, UsuarioAdmin } from "../../api/types";
import type { JefesDirectos, ReglaAprobacion, TipoAprobador } from "../../api/tercera";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { marca } from "../../theme";

type Form = {
  id?: number; categoria_id: number | ""; subcategoria_id: number | ""; nivel1_tipo: TipoAprobador; nivel1_usuario_id: number | "";
  nivel2_tipo: TipoAprobador | ""; nivel2_usuario_id: number | ""; recordar_horas: number; escalar_horas: number | ""; escalar_a_id: number | "";
  usar_reemplazo: boolean; auto_si_aprobador: boolean; activo: boolean;
};

const VACIO: Form = {
  categoria_id: "", subcategoria_id: "", nivel1_tipo: "JEFE_DIRECTO", nivel1_usuario_id: "", nivel2_tipo: "", nivel2_usuario_id: "",
  recordar_horas: 4, escalar_horas: "", escalar_a_id: "", usar_reemplazo: true, auto_si_aprobador: true, activo: true,
};

const TIPOS: [TipoAprobador, string][] = [["JEFE_DIRECTO", "Jefe directo del solicitante"], ["SUPERVISOR_CATEGORIA", "Supervisor de la categoría"], ["PERSONA", "Una persona fija"]];

function aForm(r: ReglaAprobacion): Form {
  return {
    id: r.id, categoria_id: r.categoria_id, subcategoria_id: r.subcategoria_id ?? "", nivel1_tipo: r.nivel1_tipo, nivel1_usuario_id: r.nivel1_usuario_id ?? "",
    nivel2_tipo: r.nivel2_tipo ?? "", nivel2_usuario_id: r.nivel2_usuario_id ?? "", recordar_horas: r.recordar_horas, escalar_horas: r.escalar_horas ?? "",
    escalar_a_id: r.escalar_a_id ?? "", usar_reemplazo: r.usar_reemplazo, auto_si_aprobador: r.auto_si_aprobador, activo: r.activo,
  };
}

function cuerpo(f: Form) {
  return {
    categoria_id: f.categoria_id, subcategoria_id: f.subcategoria_id || null, nivel1_tipo: f.nivel1_tipo, nivel1_usuario_id: f.nivel1_usuario_id || null,
    nivel2_tipo: f.nivel2_tipo || null, nivel2_usuario_id: f.nivel2_usuario_id || null, recordar_horas: f.recordar_horas,
    escalar_horas: f.escalar_horas || null, escalar_a_id: f.escalar_horas ? f.escalar_a_id || null : null, usar_reemplazo: f.usar_reemplazo,
    auto_si_aprobador: f.auto_si_aprobador, activo: f.activo,
  };
}

export default function ReglasAprobacion() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const cat = useCatalogos();
  const q = useQuery({ queryKey: ["aprobaciones", "reglas"], queryFn: () => get<{ reglas: ReglaAprobacion[]; jefes: JefesDirectos }>("/aprobaciones/admin/reglas") });
  const personas = useQuery({
    queryKey: ["admin", "usuarios", "todos"],
    queryFn: () => get<Pagina<UsuarioAdmin>>("/admin/usuarios", { tamano: 500 }),
    retry: false,
  });
  const [f, setF] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verFaltan, setVerFaltan] = useState(false);
  const guardar = useMutation({
    mutationFn: (x: Form) => (x.id ? put(`/aprobaciones/admin/reglas/${x.id}`, cuerpo(x)) : post("/aprobaciones/admin/reglas", cuerpo(x))),
    onSuccess: () => {
      avisar("Regla guardada");
      setF(null);
      qc.invalidateQueries({ queryKey: ["aprobaciones", "reglas"] });
    },
    onError: (e) => setError(mensajeError(e)),
  });
  if (q.isLoading || !cat.data) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  const { reglas, jefes } = q.data!;
  const gente = (personas.data?.items ?? cat.data.responsables.map((r) => ({ id: r.id, nombre: r.nombre, activo: true } as UsuarioAdmin)))
    .filter((u) => u.activo).sort((a, b) => a.nombre.localeCompare(b.nombre));
  const categoria = cat.data.categorias.find((c) => c.id === f?.categoria_id);
  const pct = jefes.total ? Math.round((jefes.completos / jefes.total) * 100) : 0;

  const selectorPersona = (valor: number | "", cambiar: (v: number | "") => void, etiqueta = "Persona") => (
    <TextField select fullWidth size="small" label={etiqueta} value={valor} onChange={(e) => cambiar(e.target.value ? Number(e.target.value) : "")}>
      {gente.map((u) => <MenuItem key={u.id} value={u.id}>{u.nombre}</MenuItem>)}
    </TextField>
  );

  return (
    <Box>
      <Encabezado
        titulo="Reglas de aprobación"
        subtitulo="Qué tickets necesitan visto bueno antes de atenderse, sin importar si el solicitante los crea él mismo o alguien en su nombre."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => { setError(null); setF({ ...VACIO }); }}>Nueva regla</Button>}
      />
      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: f ? 7.2 : 12 }}>
          <Paper sx={{ overflowX: "auto" }}>
            {reglas.length === 0 ? <Vacio texto="Aún no hay reglas: ningún ticket necesita aprobación." /> : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Categoría</TableCell><TableCell>Cuándo</TableCell><TableCell>Aprueba (nivel 1)</TableCell><TableCell>Nivel 2</TableCell>
                    <TableCell>Si no responde</TableCell><TableCell>Estado</TableCell><TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {reglas.map((r) => (
                    <TableRow key={r.id} selected={f?.id === r.id} hover>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{r.categoria}</Typography>
                        {r.restringida_en_nombre && <Typography variant="caption" color="text.secondary">También se puede pedir en nombre de otra persona</Typography>}
                      </TableCell>
                      <TableCell>{r.subcategoria ?? "Todas"}</TableCell>
                      <TableCell>{r.nivel1}</TableCell>
                      <TableCell>{r.nivel2 ?? "—"}</TableCell>
                      <TableCell>
                        <Typography variant="body2">{r.recordar_horas ? `Recordar a las ${r.recordar_horas} h` : "Sin recordatorio"}</Typography>
                        {r.escalar_a && <Typography variant="caption" color="text.secondary">Pasa a {r.escalar_a} a las {r.escalar_horas} h</Typography>}
                      </TableCell>
                      <TableCell><Chip size="small" variant="outlined" label={r.activo ? "Activa" : "Inactiva"} color={r.activo ? "success" : "default"} /></TableCell>
                      <TableCell align="right">
                        <Button size="small" startIcon={<EditIcon />} onClick={() => { setError(null); setF(aForm(r)); }}>Editar</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Paper>
          <Paper sx={{ p: 2.5, mt: 2.5 }}>
            <Typography variant="subtitle2">Usuarios › campo «Jefe directo»</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Lo usan las reglas de «Jefe directo». Se completa en <Link component={RouterLink} to="/admin/usuarios">Usuarios</Link> (o con la carga desde Excel).
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center">
              <Box sx={{ flex: 1, height: 10, borderRadius: 5, bgcolor: "#E3E8F0", overflow: "hidden" }}>
                <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: marca.azul }} />
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{jefes.completos} de {jefes.total} completos</Typography>
              {jefes.faltan.length > 0 && <Button size="small" onClick={() => setVerFaltan(!verFaltan)}>{verFaltan ? "Ocultar" : `Ver los ${jefes.faltan.length} que faltan`}</Button>}
            </Stack>
            <Collapse in={verFaltan}>
              <Stack direction="row" useFlexGap spacing={1} sx={{ mt: 1.5, flexWrap: "wrap" }}>
                {jefes.faltan.map((u) => <Chip key={u.id} size="small" label={`${u.nombre}${u.area ? ` · ${u.area}` : ""}`} />)}
              </Stack>
            </Collapse>
          </Paper>
        </Grid>
        {f && (
          <Grid size={{ xs: 12, md: 4.8 }}>
            <Paper sx={{ p: 2.5 }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <EditIcon sx={{ color: marca.azul }} />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{f.id ? "Editar regla" : "Nueva regla"}</Typography>
              </Stack>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              <Stack direction="row" spacing={1.5}>
                <TextField select fullWidth size="small" label="Categoría" value={f.categoria_id}
                  onChange={(e) => setF({ ...f, categoria_id: Number(e.target.value), subcategoria_id: "" })}>
                  {cat.data.categorias.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
                <TextField select fullWidth size="small" label="Subcategoría" value={f.subcategoria_id} disabled={!categoria}
                  onChange={(e) => setF({ ...f, subcategoria_id: e.target.value ? Number(e.target.value) : "" })}>
                  <MenuItem value="">Todas</MenuItem>
                  {(categoria?.subcategorias ?? []).filter((s) => s.activo).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
                </TextField>
              </Stack>
              <Typography variant="body2" sx={{ fontWeight: 600, mt: 2.2, mb: 1 }}>Quién aprueba</Typography>
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <Stack spacing={1} sx={{ flex: 1 }}>
                  <TextField select fullWidth size="small" label="Nivel 1" value={f.nivel1_tipo} onChange={(e) => setF({ ...f, nivel1_tipo: e.target.value as TipoAprobador })}>
                    {TIPOS.map(([v, t]) => <MenuItem key={v} value={v}>{t}</MenuItem>)}
                  </TextField>
                  {f.nivel1_tipo === "PERSONA" && selectorPersona(f.nivel1_usuario_id, (v) => setF({ ...f, nivel1_usuario_id: v }))}
                </Stack>
                <ArrowIcon color="disabled" sx={{ mt: 1 }} />
                <Stack spacing={1} sx={{ flex: 1 }}>
                  <TextField select fullWidth size="small" label="Nivel 2 (opcional)" value={f.nivel2_tipo} onChange={(e) => setF({ ...f, nivel2_tipo: e.target.value as TipoAprobador | "" })}>
                    <MenuItem value="">Ninguno</MenuItem>
                    {TIPOS.map(([v, t]) => <MenuItem key={v} value={v}>{t}</MenuItem>)}
                  </TextField>
                  {f.nivel2_tipo === "PERSONA" && selectorPersona(f.nivel2_usuario_id, (v) => setF({ ...f, nivel2_usuario_id: v }))}
                </Stack>
              </Stack>
              <Typography variant="body2" sx={{ fontWeight: 600, mt: 2.2, mb: 1 }}>Si no responde</Typography>
              <Stack direction="row" spacing={1.5}>
                <TextField fullWidth size="small" type="number" label="Recordar a las (horas hábiles)" value={f.recordar_horas}
                  onChange={(e) => setF({ ...f, recordar_horas: Math.max(0, Number(e.target.value)) })} helperText="0 = sin recordatorio" />
                <TextField fullWidth size="small" type="number" label="Pasar a otra persona a las (h)" value={f.escalar_horas}
                  onChange={(e) => setF({ ...f, escalar_horas: e.target.value ? Math.max(1, Number(e.target.value)) : "" })} helperText="Vacío = no pasa" />
              </Stack>
              {!!f.escalar_horas && <Box sx={{ mt: 1.5 }}>{selectorPersona(f.escalar_a_id, (v) => setF({ ...f, escalar_a_id: v }), "Pasa a")}</Box>}
              <FormControlLabel sx={{ mt: 1.5 }} control={<Switch checked={f.usar_reemplazo} onChange={(e) => setF({ ...f, usar_reemplazo: e.target.checked })} />}
                label={<Typography variant="body2">Si el aprobador está ausente, pasa a su reemplazo (modo ausente)</Typography>} />
              <FormControlLabel control={<Switch checked={f.auto_si_aprobador} onChange={(e) => setF({ ...f, auto_si_aprobador: e.target.checked })} />}
                label={<Typography variant="body2">Si quien pide ya es el aprobador, se aprueba solo</Typography>} />
              <FormControlLabel control={<Switch checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} />}
                label={<Typography variant="body2">Regla activa</Typography>} />
              <Alert severity="warning" sx={{ mt: 1.5 }}>Si se rechaza, el ticket se cancela y el solicitante recibe el comentario del aprobador.</Alert>
              <Stack direction="row" justifyContent="flex-end" spacing={1} sx={{ mt: 2 }}>
                <Button color="inherit" onClick={() => setF(null)}>Cancelar</Button>
                <Button variant="contained" disabled={!f.categoria_id || guardar.isPending} onClick={() => guardar.mutate(f)}>Guardar</Button>
              </Stack>
            </Paper>
          </Grid>
        )}
      </Grid>
    </Box>
  );
}
