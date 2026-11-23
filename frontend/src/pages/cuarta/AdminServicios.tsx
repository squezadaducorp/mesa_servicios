import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, IconButton, Link,
  MenuItem, Paper, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import EditIcon from "@mui/icons-material/Edit";
import { Stack } from "../../components/Pila";
import { get, post, put } from "../../api/client";
import type { CampoServicio, OpcionServicio, Servicio, TipoCampo } from "../../api/cuarta";
import { useCatalogos } from "../../api/hooks";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";
import { ICONOS, IconoServicio } from "./Catalogo";

const TIPOS: { v: TipoCampo; t: string }[] = [
  { v: "texto", t: "Texto" }, { v: "parrafo", t: "Párrafo" }, { v: "fecha", t: "Fecha" }, { v: "numero", t: "Número" },
  { v: "cedula", t: "Cédula / RUC" }, { v: "correo", t: "Correo" }, { v: "telefono", t: "Teléfono" }, { v: "area", t: "Área" },
  { v: "usuario", t: "Persona" }, { v: "lista", t: "Lista de opciones" },
];

type Borrador = Omit<Servicio, "id" | "plazo" | "categoria" | "subcategoria" | "responsable_categoria"> & { id?: number };

const NUEVO: Borrador = {
  nombre: "", descripcion: "", icono: "servicio", grupo: "Accesos", categoria_id: 0, subcategoria_id: 0, plazo_horas: 8, plazo_texto: null,
  requiere_aprobacion: false, lo_pide: null as unknown as string, orden: 0, activo: true, titulo_campos: "", titulo_opciones: "", aviso: "",
  campos: [], opciones: [],
};

function Editor({ inicial, onCerrar }: { inicial: Borrador; onCerrar: () => void }) {
  const avisar = useAviso();
  const qc = useQueryClient();
  const cat = useCatalogos();
  const [b, setB] = useState<Borrador>(inicial);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Borrador>(k: K, v: Borrador[K]) => setB((x) => ({ ...x, [k]: v }));
  const campos = b.campos ?? [];
  const opciones = b.opciones ?? [];
  const setCampo = (i: number, c: Partial<CampoServicio>) => set("campos", campos.map((x, j) => (j === i ? { ...x, ...c } : x)));
  const setOpcion = (i: number, o: Partial<OpcionServicio>) => set("opciones", opciones.map((x, j) => (j === i ? { ...x, ...o } : x)));
  const categoria = cat.data?.categorias.find((c) => c.id === b.categoria_id);
  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = { ...b, lo_pide: b.lo_pide || null, plazo_texto: b.plazo_texto || null,
        opciones: opciones.map(({ responsable: _r, ...o }) => o) };
      return b.id ? put(`/servicios/admin/${b.id}`, cuerpo) : post("/servicios/admin", cuerpo);
    },
    onSuccess: () => {
      avisar("Servicio guardado");
      qc.invalidateQueries({ queryKey: ["servicios"] });
      onCerrar();
    },
    onError: (e) => setError(mensajeError(e)),
  });

  return (
    <Dialog open onClose={onCerrar} maxWidth="lg" fullWidth>
      <DialogTitle>{b.id ? `Editar «${inicial.nombre}»` : "Nuevo servicio"}</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" } }}>
          <TextField label="Nombre" value={b.nombre} onChange={(e) => set("nombre", e.target.value)} sx={{ gridColumn: { md: "span 2" } }} required />
          <TextField label="Grupo (filtro del catálogo)" value={b.grupo} onChange={(e) => set("grupo", e.target.value)} />
          <TextField select label="Ícono" value={b.icono} onChange={(e) => set("icono", e.target.value)}>
            {Object.keys(ICONOS).map((k) => (
              <MenuItem key={k} value={k}><Stack direction="row" alignItems="center" sx={{ gap: 1 }}><IconoServicio icono={k} tam={24} />{k}</Stack></MenuItem>
            ))}
          </TextField>
          <TextField label="Descripción (se ve en la tarjeta)" value={b.descripcion} onChange={(e) => set("descripcion", e.target.value)}
            sx={{ gridColumn: { md: "span 4" } }} required />
          <TextField select label="Categoría del ticket" value={b.categoria_id || ""} required
            onChange={(e) => setB((x) => ({ ...x, categoria_id: Number(e.target.value), subcategoria_id: 0 }))} sx={{ gridColumn: { md: "span 2" } }}>
            {(cat.data?.categorias ?? []).filter((c) => c.activo).map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
          </TextField>
          <TextField select label="Subcategoría" value={b.subcategoria_id || ""} required onChange={(e) => set("subcategoria_id", Number(e.target.value))}
            sx={{ gridColumn: { md: "span 2" } }}>
            {(categoria?.subcategorias ?? []).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
          </TextField>
          <TextField type="number" label="Plazo (horas laborables)" value={b.plazo_horas} helperText="8 h = 1 día hábil"
            onChange={(e) => set("plazo_horas", Number(e.target.value))} />
          <TextField label="Texto del plazo (opcional)" placeholder="El mismo día" value={b.plazo_texto ?? ""} onChange={(e) => set("plazo_texto", e.target.value)} />
          <TextField label="Lo pide" placeholder="Todos" value={b.lo_pide ?? ""} onChange={(e) => set("lo_pide", e.target.value)} />
          <TextField type="number" label="Orden" value={b.orden} onChange={(e) => set("orden", Number(e.target.value))} />
          <FormControlLabel control={<Switch checked={b.requiere_aprobacion} onChange={(e) => set("requiere_aprobacion", e.target.checked)} />}
            label="Aprueba el jefe directo" sx={{ gridColumn: { md: "span 2" } }} />
          <FormControlLabel control={<Switch checked={b.activo} onChange={(e) => set("activo", e.target.checked)} />} label="Activo en el catálogo"
            sx={{ gridColumn: { md: "span 2" } }} />
          <TextField label="Aviso al inicio del formulario (opcional)" value={b.aviso ?? ""} onChange={(e) => set("aviso", e.target.value)}
            sx={{ gridColumn: { md: "span 4" } }} />
        </Box>

        <Divider sx={{ my: 3 }} />
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Campos del formulario</Typography>
          <Button size="small" startIcon={<AddIcon />}
            onClick={() => set("campos", [...campos, { clave: "", etiqueta: "", tipo: "texto", requerido: true, opciones: [], ancho: 2, aprobador: false }])}>
            Agregar campo
          </Button>
        </Stack>
        <TextField size="small" label="Título de la sección" value={b.titulo_campos ?? ""} onChange={(e) => set("titulo_campos", e.target.value)}
          placeholder="Datos de la solicitud" sx={{ mb: 1.5, width: { xs: "100%", md: 420 } }} />
        {campos.map((c, i) => (
          <Stack key={i} direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 1, py: 1, borderTop: "1px solid", borderColor: "divider" }}>
            <TextField size="small" label="Etiqueta" value={c.etiqueta} onChange={(e) => setCampo(i, { etiqueta: e.target.value })} sx={{ flex: 2 }} />
            <TextField size="small" select label="Tipo" value={c.tipo} onChange={(e) => setCampo(i, { tipo: e.target.value as TipoCampo })} sx={{ flex: 1, minWidth: 140 }}>
              {TIPOS.map((t) => <MenuItem key={t.v} value={t.v}>{t.t}</MenuItem>)}
            </TextField>
            {c.tipo === "lista" && (
              <TextField size="small" label="Opciones (separadas por coma)" value={c.opciones.join(", ")} sx={{ flex: 2 }}
                onChange={(e) => setCampo(i, { opciones: e.target.value.split(",").map((x) => x.trimStart()) })}
                onBlur={() => setCampo(i, { opciones: c.opciones.map((x) => x.trim()).filter(Boolean) })} />
            )}
            <TextField size="small" select label="Ancho" value={c.ancho} onChange={(e) => setCampo(i, { ancho: Number(e.target.value) })} sx={{ width: 100 }}>
              {[1, 2, 3, 4].map((n) => <MenuItem key={n} value={n}>{n}/4</MenuItem>)}
            </TextField>
            <FormControlLabel control={<Checkbox size="small" checked={c.requerido} onChange={(e) => setCampo(i, { requerido: e.target.checked })} />} label="Obligatorio" />
            {c.tipo === "usuario" && (
              <Tooltip title="La persona elegida en este campo aprueba la solicitud (p. ej., el jefe de quien ingresa)">
                <FormControlLabel control={<Checkbox size="small" checked={c.aprobador} onChange={(e) => setCampo(i, { aprobador: e.target.checked })} />} label="Aprueba" />
              </Tooltip>
            )}
            <IconButton aria-label="Quitar campo" onClick={() => set("campos", campos.filter((_, j) => j !== i))}><DeleteIcon /></IconButton>
          </Stack>
        ))}

        <Divider sx={{ my: 3 }} />
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Opciones y tareas que se generan</Typography>
          <Button size="small" startIcon={<AddIcon />}
            onClick={() => set("opciones", [...opciones, { clave: "", etiqueta: "", tarea: "", marcado: false, siempre: false }])}>
            Agregar opción
          </Button>
        </Stack>
        <TextField size="small" label="Título de la sección" value={b.titulo_opciones ?? ""} onChange={(e) => set("titulo_opciones", e.target.value)}
          placeholder="¿Qué necesita?" sx={{ mb: 1.5, width: { xs: "100%", md: 420 } }} />
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          Cada opción marcada crea una tarea. «Siempre» = tarea fija sin casilla. Sin responsable, la tarea queda con el responsable del ticket
          {categoria ? ` (categoría ${categoria.nombre})` : ""}.
        </Typography>
        {opciones.map((o, i) => (
          <Stack key={i} direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} sx={{ gap: 1, py: 1, borderTop: "1px solid", borderColor: "divider" }}>
            <TextField size="small" label="Casilla" value={o.etiqueta} onChange={(e) => setOpcion(i, { etiqueta: e.target.value })} sx={{ flex: 2 }} />
            <TextField size="small" label="Tarea que genera" value={o.tarea ?? ""} onChange={(e) => setOpcion(i, { tarea: e.target.value })} sx={{ flex: 2 }} />
            <TextField size="small" select label="Responsable" value={o.responsable_id ?? ""} sx={{ flex: 1.3, minWidth: 160 }}
              onChange={(e) => setOpcion(i, { responsable_id: e.target.value === "" ? null : Number(e.target.value) })}>
              <MenuItem value="">Responsable del ticket</MenuItem>
              {(cat.data?.responsables ?? []).map((u) => <MenuItem key={u.id} value={u.id}>{u.nombre}</MenuItem>)}
            </TextField>
            <FormControlLabel control={<Checkbox size="small" checked={o.marcado} onChange={(e) => setOpcion(i, { marcado: e.target.checked })} />} label="Marcada" />
            <FormControlLabel control={<Checkbox size="small" checked={o.siempre} onChange={(e) => setOpcion(i, { siempre: e.target.checked })} />} label="Siempre" />
            <IconButton aria-label="Quitar opción" onClick={() => set("opciones", opciones.filter((_, j) => j !== i))}><DeleteIcon /></IconButton>
          </Stack>
        ))}
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" onClick={() => { setError(null); guardar.mutate(); }} disabled={guardar.isPending}>Guardar</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function AdminServicios() {
  const q = useQuery({ queryKey: ["servicios", "admin"], queryFn: () => get<Servicio[]>("/servicios/admin") });
  const [editar, setEditar] = useState<Borrador | null>(null);
  if (q.isLoading) return <Cargando />;
  if (q.error) return <ErrorCarga error={q.error} />;
  return (
    <Box>
      <Encabezado titulo="Catálogo de servicios"
        subtitulo="Formularios que ven los usuarios en el catálogo: campos, quién aprueba, tareas que se generan y tiempo comprometido."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditar({ ...NUEVO })}>Nuevo servicio</Button>} />
      <Paper variant="outlined" sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Servicio</TableCell><TableCell>Grupo</TableCell><TableCell>Categoría</TableCell><TableCell>Plazo</TableCell>
              <TableCell>Aprobación</TableCell><TableCell>Tareas</TableCell><TableCell>Estado</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {(q.data ?? []).map((s) => (
              <TableRow key={s.id} hover>
                <TableCell>
                  <Stack direction="row" alignItems="center" sx={{ gap: 1.5 }}>
                    <IconoServicio icono={s.icono} tam={32} />
                    <Link component={RouterLink} to={`/catalogo/${s.id}`} sx={{ fontWeight: 600 }}>{s.nombre}</Link>
                  </Stack>
                </TableCell>
                <TableCell>{s.grupo}</TableCell>
                <TableCell>{s.categoria} › {s.subcategoria}</TableCell>
                <TableCell>{s.plazo}</TableCell>
                <TableCell>{s.requiere_aprobacion ? "Jefe directo" : "—"}</TableCell>
                <TableCell>{(s.opciones ?? []).length}</TableCell>
                <TableCell>{s.activo ? <Chip size="small" color="success" label="Activo" /> : <Chip size="small" label="Inactivo" />}</TableCell>
                <TableCell align="right">
                  <IconButton aria-label={`Editar ${s.nombre}`} onClick={() => setEditar({ ...s, campos: s.campos ?? [], opciones: s.opciones ?? [] })}><EditIcon /></IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editar && <Editor inicial={editar} onCerrar={() => setEditar(null)} />}
    </Box>
  );
}
