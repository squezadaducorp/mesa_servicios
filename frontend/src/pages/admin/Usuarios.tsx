import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, InputAdornment, MenuItem, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import KeyIcon from "@mui/icons-material/Key";
import SearchIcon from "@mui/icons-material/Search";
import { get, patch, post } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { Pagina, Rol, UsuarioAdmin } from "../../api/types";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, Encabezado, ErrorCarga } from "../../components/Comunes";
import { fechaHora } from "../../utils/formato";

type Form = Partial<UsuarioAdmin> & { clave?: string };

export default function Usuarios() {
  const qc = useQueryClient();
  const avisar = useAviso();
  const cat = useCatalogos();
  const [texto, setTexto] = useState("");
  const [rolId, setRolId] = useState<number | "">("");
  const [pagina, setPagina] = useState(0);
  const [form, setForm] = useState<Form | null>(null);
  const [temporal, setTemporal] = useState<{ correo: string; clave: string } | null>(null);
  const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: () => get<Rol[]>("/admin/roles") });
  const q = useQuery({
    queryKey: ["admin", "usuarios", texto, rolId, pagina],
    queryFn: () => get<Pagina<UsuarioAdmin>>("/admin/usuarios", { texto, rol_id: rolId || undefined, pagina: pagina + 1, tamano: 25 }),
    placeholderData: keepPreviousData,
  });
  const supervisores = useQuery({
    queryKey: ["admin", "usuarios", "todos"],
    queryFn: () => get<Pagina<UsuarioAdmin>>("/admin/usuarios", { tamano: 500 }),
  });

  const guardar = useMutation({
    mutationFn: async (f: Form) => {
      const datos = {
        nombre: f.nombre,
        cargo: f.cargo || null,
        telefono: f.telefono || null,
        area_id: f.area_id || null,
        rol_id: f.rol_id,
        supervisor_id: f.supervisor_id || null,
        origen_autenticacion: f.origen_autenticacion ?? "LOCAL",
        usuario_ad: f.usuario_ad || null,
      };
      if (f.id) return { r: await patch<UsuarioAdmin>(`/admin/usuarios/${f.id}`, { ...datos, activo: f.activo }) };
      return { r: await post<{ usuario: UsuarioAdmin; clave_temporal: string | null }>("/admin/usuarios", { ...datos, correo: f.correo, clave: f.clave || null }) };
    },
    onSuccess: ({ r }) => {
      qc.invalidateQueries({ queryKey: ["admin", "usuarios"] });
      setForm(null);
      if ("clave_temporal" in r && r.clave_temporal) setTemporal({ correo: r.usuario.correo, clave: r.clave_temporal });
      else avisar("Usuario guardado");
    },
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const restablecer = useMutation({
    mutationFn: (u: UsuarioAdmin) => post<{ clave_temporal: string }>(`/admin/usuarios/${u.id}/restablecer-clave`).then((r) => ({ u, r })),
    onSuccess: ({ u, r }) => setTemporal({ correo: u.correo, clave: r.clave_temporal }),
    onError: (e) => avisar(mensajeError(e), "error"),
  });

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const areas = cat.data?.areas ?? [];

  return (
    <>
      <Encabezado
        titulo="Usuarios"
        subtitulo="Altas, roles, bloqueo y origen de autenticación (local o Active Directory)"
        acciones={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setForm({ origen_autenticacion: "LOCAL", activo: true })}>
            Nuevo usuario
          </Button>
        }
      />
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField
            placeholder="Buscar por nombre o correo"
            value={texto}
            onChange={(e) => {
              setTexto(e.target.value);
              setPagina(0);
            }}
            fullWidth
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
          />
          <TextField select label="Rol" value={rolId} onChange={(e) => setRolId(e.target.value ? Number(e.target.value) : "")} sx={{ minWidth: 220 }}>
            <MenuItem value="">Todos</MenuItem>
            {(roles.data ?? []).map((r) => (
              <MenuItem key={r.id} value={r.id}>
                {r.nombre}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </Paper>
      {q.isLoading ? (
        <Cargando />
      ) : q.error ? (
        <ErrorCarga error={q.error} />
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Nombre</TableCell>
                  <TableCell>Correo</TableCell>
                  <TableCell>Rol</TableCell>
                  <TableCell>Área / cargo</TableCell>
                  <TableCell>Origen</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Último ingreso</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {q.data?.items.map((u) => (
                  <TableRow key={u.id} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{u.nombre}</TableCell>
                    <TableCell>{u.correo}</TableCell>
                    <TableCell>{roles.data?.find((r) => r.id === u.rol_id)?.nombre ?? u.rol}</TableCell>
                    <TableCell>
                      <Typography variant="body2">{areas.find((a) => a.id === u.area_id)?.nombre ?? "—"}</Typography>
                      <Typography variant="caption" sx={{ color: "text.secondary" }}>
                        {u.cargo}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={u.origen_autenticacion === "AD" ? "Active Directory" : "Local"} />
                    </TableCell>
                    <TableCell>
                      {!u.activo ? <Chip size="small" label="Inactivo" /> : u.bloqueado ? <Chip size="small" color="error" label="Bloqueado" /> : <Chip size="small" color="success" label="Activo" />}
                    </TableCell>
                    <TableCell>{fechaHora(u.ultimo_login)}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      <Tooltip title="Editar">
                        <IconButton size="small" onClick={() => setForm(u)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {u.origen_autenticacion === "LOCAL" && (
                        <Tooltip title="Generar contraseña temporal">
                          <IconButton size="small" onClick={() => restablecer.mutate(u)}>
                            <KeyIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination component="div" count={q.data?.total ?? 0} page={pagina} onPageChange={(_, p) => setPagina(p)} rowsPerPage={25} rowsPerPageOptions={[25]} />
        </Paper>
      )}

      <Dialog open={!!form} onClose={() => setForm(null)} fullWidth maxWidth="sm">
        <DialogTitle>{form?.id ? "Editar usuario" : "Nuevo usuario"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Nombre completo" value={form?.nombre ?? ""} onChange={(e) => set("nombre", e.target.value)} required />
            <TextField label="Correo" type="email" value={form?.correo ?? ""} onChange={(e) => set("correo", e.target.value)} disabled={!!form?.id} required />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField select fullWidth label="Rol" value={form?.rol_id ?? ""} onChange={(e) => set("rol_id", Number(e.target.value))} required>
                {(roles.data ?? []).map((r) => (
                  <MenuItem key={r.id} value={r.id}>
                    {r.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select fullWidth label="Área" value={form?.area_id ?? ""} onChange={(e) => set("area_id", e.target.value ? Number(e.target.value) : null)}>
                <MenuItem value="">Sin área</MenuItem>
                {areas.map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    {a.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField fullWidth label="Cargo" value={form?.cargo ?? ""} onChange={(e) => set("cargo", e.target.value)} />
              <TextField fullWidth label="Teléfono" value={form?.telefono ?? ""} onChange={(e) => set("telefono", e.target.value)} />
            </Stack>
            <TextField select label="Supervisor directo" value={form?.supervisor_id ?? ""} onChange={(e) => set("supervisor_id", e.target.value ? Number(e.target.value) : null)}>
              <MenuItem value="">Ninguno</MenuItem>
              {supervisores.data?.items
                .filter((u) => ["SUPERVISOR", "ADMIN_MESA", "SUPER_ADMIN"].includes(u.rol) && u.id !== form?.id)
                .map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {u.nombre}
                  </MenuItem>
                ))}
            </TextField>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                select
                fullWidth
                label="Autenticación"
                value={form?.origen_autenticacion ?? "LOCAL"}
                onChange={(e) => set("origen_autenticacion", e.target.value as "LOCAL" | "AD")}
              >
                <MenuItem value="LOCAL">Local (contraseña de la mesa)</MenuItem>
                <MenuItem value="AD">Active Directory</MenuItem>
              </TextField>
              {form?.origen_autenticacion === "AD" && (
                <TextField fullWidth label="Usuario de dominio" placeholder="ADUCORP\\usuario" value={form?.usuario_ad ?? ""} onChange={(e) => set("usuario_ad", e.target.value)} />
              )}
            </Stack>
            {form?.id ? (
              <TextField select label="Estado" value={form.activo ? "1" : "0"} onChange={(e) => set("activo", e.target.value === "1")}>
                <MenuItem value="1">Activo</MenuItem>
                <MenuItem value="0">Inactivo</MenuItem>
              </TextField>
            ) : (
              form?.origen_autenticacion !== "AD" && (
                <TextField label="Contraseña inicial (opcional)" type="password" value={form?.clave ?? ""} onChange={(e) => set("clave", e.target.value)} helperText="Si la deja vacía se genera una temporal; el usuario deberá cambiarla al ingresar." />
              )
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setForm(null)}>Cancelar</Button>
          <Button variant="contained" disabled={!form?.nombre || !form?.correo || !form?.rol_id || guardar.isPending} onClick={() => form && guardar.mutate(form)}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!temporal} onClose={() => setTemporal(null)}>
        <DialogTitle>Contraseña temporal</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Comuníquela al usuario por un canal seguro. Solo se muestra esta vez y deberá cambiarla en su primer ingreso.
          </Alert>
          <Typography variant="body2">{temporal?.correo}</Typography>
          <Typography variant="h5" sx={{ fontFamily: "monospace", mt: 1, userSelect: "all" }}>
            {temporal?.clave}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => navigator.clipboard?.writeText(temporal?.clave ?? "")}>Copiar</Button>
          <Button variant="contained" onClick={() => setTemporal(null)}>
            Listo
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
