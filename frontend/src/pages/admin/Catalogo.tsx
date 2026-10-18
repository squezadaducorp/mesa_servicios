import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, IconButton, MenuItem, Paper, Radio, Stack, Switch, Tab, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Tabs, TextField, Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import { get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { Categoria, Cliente, Pagina, Subcategoria, UsuarioAdmin } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";
import { P } from "../../utils/permisos";

const MODOS = { PRINCIPAL: "Responsable principal", BALANCEO: "Balanceo por carga", MANUAL: "Manual (la mesa asigna)" };

type FormCat = {
  id?: number;
  codigo: string;
  nombre: string;
  descripcion: string;
  palabras_clave: string;
  color: string;
  orden: number;
  modo_asignacion: keyof typeof MODOS;
  supervisor_id: number | "";
  activo: boolean;
  responsables: { usuario_id: number; es_principal: boolean }[];
};

export default function Catalogo() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const avisar = useAviso();
  const cat = useCatalogos();
  const [tab, setTab] = useState(0);
  const categorias = useQuery({ queryKey: ["admin", "categorias"], queryFn: () => get<Categoria[]>("/admin/categorias") });
  const usuarios = useQuery({
    queryKey: ["admin", "usuarios", "todos"],
    queryFn: () => get<Pagina<UsuarioAdmin>>("/admin/usuarios", { tamano: 500 }),
    enabled: puede(P.USUARIOS),
  });
  const [fc, setFc] = useState<FormCat | null>(null);
  const [fs, setFs] = useState<(Partial<Subcategoria> & { categoria_id: number }) | null>(null);
  const [fcl, setFcl] = useState<Partial<Cliente> | null>(null);

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ["admin", "categorias"] });
    qc.invalidateQueries({ queryKey: ["catalogos"] });
  };
  const ok = (m: string) => () => {
    refrescar();
    avisar(m);
  };
  const err = (e: unknown) => avisar(mensajeError(e), "error");

  const guardarCat = useMutation({
    mutationFn: (f: FormCat) => {
      const { id, ...datos } = f;
      const body = { ...datos, supervisor_id: datos.supervisor_id || null, color: datos.color || null };
      return id ? put(`/admin/categorias/${id}`, body) : post("/admin/categorias", body);
    },
    onSuccess: () => {
      setFc(null);
      ok("Categoría guardada")();
    },
    onError: err,
  });
  const guardarSub = useMutation({
    mutationFn: (f: Partial<Subcategoria> & { categoria_id: number }) => {
      const body = { nombre: f.nombre, palabras_clave: f.palabras_clave || null, respuesta_plantilla: f.respuesta_plantilla || null, activo: f.activo ?? true };
      return f.id ? put(`/admin/categorias/${f.categoria_id}/subcategorias/${f.id}`, body) : post(`/admin/categorias/${f.categoria_id}/subcategorias`, body);
    },
    onSuccess: () => {
      setFs(null);
      ok("Subcategoría guardada")();
    },
    onError: err,
  });
  const guardarCliente = useMutation({
    mutationFn: (f: Partial<Cliente>) => {
      const body = { ruc: f.ruc || null, razon_social: f.razon_social, correo: f.correo || null, telefono: f.telefono || null, es_vip: !!f.es_vip, activo: f.activo ?? true };
      return f.id ? put(`/admin/clientes/${f.id}`, body) : post("/admin/clientes", body);
    },
    onSuccess: () => {
      setFcl(null);
      ok("Cliente guardado")();
    },
    onError: err,
  });

  if (categorias.isLoading || cat.isLoading) return <Cargando />;
  if (categorias.error) return <ErrorCarga error={categorias.error} />;

  const candidatos = usuarios.data?.items.filter((u) => u.activo) ?? cat.data?.responsables.map((r) => ({ ...r, rol: "ANALISTA" })) ?? [];
  const analistas = candidatos.filter((u) => ["ANALISTA", "SUPERVISOR", "ADMIN_MESA"].includes(u.rol));
  const supervisores = candidatos.filter((u) => ["SUPERVISOR", "ADMIN_MESA", "SUPER_ADMIN"].includes(u.rol));

  const editarCat = (c?: Categoria) =>
    setFc(
      c
        ? {
            id: c.id,
            codigo: c.codigo,
            nombre: c.nombre,
            descripcion: c.descripcion ?? "",
            palabras_clave: c.palabras_clave ?? "",
            color: c.color ?? "",
            orden: c.orden,
            modo_asignacion: c.modo_asignacion,
            supervisor_id: c.supervisor?.id ?? "",
            activo: c.activo,
            responsables: c.responsables.map((r) => ({ usuario_id: r.usuario_id, es_principal: r.es_principal })),
          }
        : { codigo: "", nombre: "", descripcion: "", palabras_clave: "", color: "#1367AC", orden: (categorias.data?.length ?? 0) + 1, modo_asignacion: "PRINCIPAL", supervisor_id: "", activo: true, responsables: [] },
    );

  const alternarResp = (id: number) =>
    setFc((f) => {
      if (!f) return f;
      const existe = f.responsables.some((r) => r.usuario_id === id);
      const resp = existe ? f.responsables.filter((r) => r.usuario_id !== id) : [...f.responsables, { usuario_id: id, es_principal: f.responsables.length === 0 }];
      if (resp.length && !resp.some((r) => r.es_principal)) resp[0].es_principal = true;
      return { ...f, responsables: resp };
    });

  return (
    <>
      <Encabezado
        titulo="Categorías y clientes"
        subtitulo="Catálogo de servicios, responsables por categoría, reglas de asignación y clientes"
        acciones={
          tab === 0 ? (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => editarCat()}>
              Nueva categoría
            </Button>
          ) : (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setFcl({ activo: true })}>
              Nuevo cliente
            </Button>
          )
        }
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Categorías" />
        <Tab label="Clientes" />
      </Tabs>

      {tab === 0 &&
        categorias.data?.map((c) => (
          <Accordion key={c.id} disableGutters sx={{ mb: 1, "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" }, flex: 1, minWidth: 0 }}>
                <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: c.color ?? "primary.main", flexShrink: 0, display: { xs: "none", sm: "block" } }} />
                <Typography sx={{ fontWeight: 600 }}>{c.nombre}</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {c.responsables.map((r) => r.nombre).join(", ") || "Sin responsables"} · {c.subcategorias.length} subcategorías
                </Typography>
                {!c.activo && <Chip size="small" label="Inactiva" />}
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}>
                <Chip size="small" label={MODOS[c.modo_asignacion]} />
                <Chip size="small" variant="outlined" label={`Supervisor: ${c.supervisor?.nombre ?? "—"}`} />
                <Box sx={{ flex: 1 }} />
                <Button size="small" startIcon={<EditIcon />} onClick={() => editarCat(c)}>
                  Editar categoría
                </Button>
                <Button size="small" startIcon={<AddIcon />} onClick={() => setFs({ categoria_id: c.id, activo: true })}>
                  Subcategoría
                </Button>
              </Stack>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Subcategoría</TableCell>
                      <TableCell>Palabras clave (IA)</TableCell>
                      <TableCell>Estado</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {c.subcategorias.map((s) => (
                      <TableRow key={s.id} hover>
                        <TableCell>{s.nombre}</TableCell>
                        <TableCell sx={{ maxWidth: 360 }}>
                          <Typography variant="caption" noWrap component="div">
                            {s.palabras_clave}
                          </Typography>
                        </TableCell>
                        <TableCell>{s.activo ? <Chip size="small" color="success" label="Activa" /> : <Chip size="small" label="Inactiva" />}</TableCell>
                        <TableCell align="right">
                          <IconButton size="small" onClick={() => setFs({ ...s, categoria_id: c.id })} aria-label="Editar">
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </AccordionDetails>
          </Accordion>
        ))}

      {tab === 1 && (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Razón social</TableCell>
                  <TableCell>RUC</TableCell>
                  <TableCell>Correo</TableCell>
                  <TableCell>Teléfono</TableCell>
                  <TableCell>VIP</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {(cat.data?.clientes ?? []).map((c) => (
                  <TableRow key={c.id} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{c.razon_social}</TableCell>
                    <TableCell>{c.ruc}</TableCell>
                    <TableCell>{c.correo}</TableCell>
                    <TableCell>{c.telefono}</TableCell>
                    <TableCell>{c.es_vip && <Chip size="small" color="secondary" label="VIP" />}</TableCell>
                    <TableCell align="right">
                      <IconButton size="small" onClick={() => setFcl(c)} aria-label="Editar">
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      <Dialog open={!!fc} onClose={() => setFc(null)} fullWidth maxWidth="md">
        <DialogTitle>{fc?.id ? "Editar categoría" : "Nueva categoría"}</DialogTitle>
        {fc && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField label="Código" value={fc.codigo} onChange={(e) => setFc({ ...fc, codigo: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") })} disabled={!!fc.id} required />
                <TextField label="Nombre" value={fc.nombre} onChange={(e) => setFc({ ...fc, nombre: e.target.value })} fullWidth required />
                <TextField label="Color" type="color" value={fc.color || "#1367AC"} onChange={(e) => setFc({ ...fc, color: e.target.value })} sx={{ width: 110 }} />
                <TextField label="Orden" type="number" value={fc.orden} onChange={(e) => setFc({ ...fc, orden: Number(e.target.value) })} sx={{ width: 100 }} />
              </Stack>
              <TextField label="Descripción" value={fc.descripcion} onChange={(e) => setFc({ ...fc, descripcion: e.target.value })} multiline minRows={2} />
              <TextField
                label="Palabras clave para clasificación automática"
                helperText="Separadas por coma"
                value={fc.palabras_clave}
                onChange={(e) => setFc({ ...fc, palabras_clave: e.target.value })}
              />
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select fullWidth label="Modo de asignación" value={fc.modo_asignacion} onChange={(e) => setFc({ ...fc, modo_asignacion: e.target.value as FormCat["modo_asignacion"] })}>
                  {Object.entries(MODOS).map(([k, v]) => (
                    <MenuItem key={k} value={k}>
                      {v}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField select fullWidth label="Supervisor" value={fc.supervisor_id} onChange={(e) => setFc({ ...fc, supervisor_id: e.target.value ? Number(e.target.value) : "" })}>
                  <MenuItem value="">Sin supervisor</MenuItem>
                  {supervisores.map((u) => (
                    <MenuItem key={u.id} value={u.id}>
                      {u.nombre}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Responsables (marque el principal)
                </Typography>
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 0.5 }}>
                  {analistas.map((u) => {
                    const r = fc.responsables.find((x) => x.usuario_id === u.id);
                    return (
                      <Stack key={u.id} direction="row" sx={{ alignItems: "center" }}>
                        <Checkbox size="small" checked={!!r} onChange={() => alternarResp(u.id)} />
                        <Typography variant="body2" sx={{ flex: 1 }}>
                          {u.nombre}
                        </Typography>
                        <Radio
                          size="small"
                          checked={!!r?.es_principal}
                          disabled={!r}
                          onChange={() => setFc({ ...fc, responsables: fc.responsables.map((x) => ({ ...x, es_principal: x.usuario_id === u.id })) })}
                          slotProps={{ input: { "aria-label": `Principal: ${u.nombre}` } }}
                        />
                      </Stack>
                    );
                  })}
                </Box>
              </Box>
              <FormControlLabel control={<Switch checked={fc.activo} onChange={(e) => setFc({ ...fc, activo: e.target.checked })} />} label="Activa" />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setFc(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!fc?.codigo || !fc?.nombre || guardarCat.isPending} onClick={() => fc && guardarCat.mutate(fc)}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!fs} onClose={() => setFs(null)} fullWidth maxWidth="sm">
        <DialogTitle>{fs?.id ? "Editar subcategoría" : "Nueva subcategoría"}</DialogTitle>
        {fs && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField label="Nombre" value={fs.nombre ?? ""} onChange={(e) => setFs({ ...fs, nombre: e.target.value })} required />
              <TextField label="Palabras clave (IA)" value={fs.palabras_clave ?? ""} onChange={(e) => setFs({ ...fs, palabras_clave: e.target.value })} helperText="Separadas por coma" />
              <TextField
                label="Plantilla de respuesta sugerida"
                value={fs.respuesta_plantilla ?? ""}
                onChange={(e) => setFs({ ...fs, respuesta_plantilla: e.target.value })}
                multiline
                minRows={3}
                helperText="Variables: {solicitante}, {numero}, {responsable}"
              />
              <FormControlLabel control={<Switch checked={fs.activo ?? true} onChange={(e) => setFs({ ...fs, activo: e.target.checked })} />} label="Activa" />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setFs(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!fs?.nombre || guardarSub.isPending} onClick={() => fs && guardarSub.mutate(fs)}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!fcl} onClose={() => setFcl(null)} fullWidth maxWidth="sm">
        <DialogTitle>{fcl?.id ? "Editar cliente" : "Nuevo cliente"}</DialogTitle>
        {fcl && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField label="Razón social" value={fcl.razon_social ?? ""} onChange={(e) => setFcl({ ...fcl, razon_social: e.target.value })} required />
              <TextField
                label="RUC"
                value={fcl.ruc ?? ""}
                onChange={(e) => setFcl({ ...fcl, ruc: e.target.value.replace(/\D/g, "").slice(0, 13) })}
                helperText="13 dígitos"
                error={!!fcl.ruc && fcl.ruc.length !== 13}
              />
              <TextField label="Correo" type="email" value={fcl.correo ?? ""} onChange={(e) => setFcl({ ...fcl, correo: e.target.value })} />
              <TextField label="Teléfono" value={fcl.telefono ?? ""} onChange={(e) => setFcl({ ...fcl, telefono: e.target.value })} />
              <FormControlLabel control={<Switch checked={!!fcl.es_vip} onChange={(e) => setFcl({ ...fcl, es_vip: e.target.checked })} />} label="Cliente VIP (eleva la prioridad sugerida)" />
              <FormControlLabel control={<Switch checked={fcl.activo ?? true} onChange={(e) => setFcl({ ...fcl, activo: e.target.checked })} />} label="Activo" />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setFcl(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!fcl?.razon_social || (!!fcl?.ruc && fcl.ruc.length !== 13) || guardarCliente.isPending} onClick={() => fcl && guardarCliente.mutate(fcl)}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
