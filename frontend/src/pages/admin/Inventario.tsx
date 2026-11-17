import { useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, InputAdornment, Link,
  MenuItem, Paper, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import ComputerIcon from "@mui/icons-material/Computer";
import LaptopIcon from "@mui/icons-material/LaptopMac";
import PrintIcon from "@mui/icons-material/Print";
import RouterIcon from "@mui/icons-material/Router";
import UsbIcon from "@mui/icons-material/Usb";
import PhoneIcon from "@mui/icons-material/PhoneAndroid";
import MonitorIcon from "@mui/icons-material/Monitor";
import StorageIcon from "@mui/icons-material/Storage";
import DevicesOtherIcon from "@mui/icons-material/DevicesOther";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import UploadIcon from "@mui/icons-material/UploadFile";
import LinkIcon from "@mui/icons-material/Link";
import EditIcon from "@mui/icons-material/Edit";
import { api, del, descargar, get, post, put } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { Equipo, EquipoDetalle, PersonaEnNombre } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { mensajeError, useAviso } from "../../components/Aviso";
import { EstadoChip } from "../../components/Chips";
import { Cargando, Encabezado, Vacio } from "../../components/Comunes";
import { duracion, fecha } from "../../utils/formato";
import { P } from "../../utils/permisos";

export const TIPOS: Record<string, [string, ReactNode]> = {
  ESCRITORIO: ["Escritorio", <ComputerIcon fontSize="small" />], PORTATIL: ["Portátil", <LaptopIcon fontSize="small" />],
  IMPRESORA: ["Impresora", <PrintIcon fontSize="small" />], RED: ["Red", <RouterIcon fontSize="small" />], TOKEN: ["Token", <UsbIcon fontSize="small" />],
  TELEFONO: ["Teléfono", <PhoneIcon fontSize="small" />], MONITOR: ["Monitor", <MonitorIcon fontSize="small" />],
  SERVIDOR: ["Servidor", <StorageIcon fontSize="small" />], OTRO: ["Otro", <DevicesOtherIcon fontSize="small" />],
};
const ESTADOS: Record<string, string> = { EN_USO: "En uso", BODEGA: "En bodega", REPARACION: "En reparación", BAJA: "De baja" };

export function IconoEquipo({ tipo, grande }: { tipo: string; grande?: boolean }) {
  const t = grande ? 44 : 32;
  return <Box sx={{ width: t, height: t, borderRadius: 2, bgcolor: "#EEF5FC", color: "primary.main", display: "grid", placeItems: "center", flexShrink: 0 }}>{TIPOS[tipo]?.[1] ?? TIPOS.OTRO[1]}</Box>;
}

const colorFallas = (f: number) => (f >= 5 ? { bgcolor: "#FDECEA", color: "#C62828", fontWeight: 700 } : f >= 3 ? { bgcolor: "#FFF3E0", color: "#E65100" } : {});

type Form = Omit<Equipo, "id" | "usuario" | "area" | "fallas_12m"> & { id?: number };
const NUEVO: Form = { codigo: "", tipo: "ESCRITORIO", marca_modelo: "", serie: null, usuario_id: null, area_id: null, compartido: false, ubicacion: null, estado: "EN_USO", fecha_compra: null, garantia_hasta: null, sistema: null, notas: null };

function Editor({ inicial, onCerrar }: { inicial: Form; onCerrar: (id?: number) => void }) {
  const cat = useCatalogos();
  const avisar = useAviso();
  const [f, setF] = useState<Form>(inicial);
  const [error, setError] = useState<string | null>(null);
  const personas = useQuery({ queryKey: ["personas-en-nombre"], queryFn: () => get<PersonaEnNombre[]>("/tickets/en-nombre/personas") });
  const guardar = useMutation({
    mutationFn: () => {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
      return f.id ? put<Equipo>(`/inventario/${f.id}`, body) : post<Equipo>("/inventario", body);
    },
    onSuccess: (e) => {
      avisar("Equipo guardado");
      onCerrar(e.id);
    },
    onError: (e) => setError(mensajeError(e)),
  });
  const txt = (k: keyof Form, label: string, extra = {}) => (
    <TextField label={label} value={(f[k] as string | null) ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} {...extra} />
  );
  const persona = personas.data?.find((p) => p.id === f.usuario_id) ?? null;
  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="md" fullWidth>
      <DialogTitle>{f.id ? `Editar ${f.codigo}` : "Nuevo equipo"}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, mt: 1 }}>
          {error && <Alert severity="error" sx={{ gridColumn: "1 / -1" }}>{error}</Alert>}
          {txt("codigo", "Código", { required: true, helperText: "El de la etiqueta, por ejemplo ADU-PC-014" })}
          <TextField select label="Tipo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
            {Object.entries(TIPOS).map(([k, [n]]) => <MenuItem key={k} value={k}>{n}</MenuItem>)}
          </TextField>
          {txt("marca_modelo", "Marca y modelo", { required: true })}
          {txt("serie", "Serie")}
          <Autocomplete options={personas.data ?? []} value={persona} getOptionLabel={(p) => `${p.nombre}${p.area ? ` · ${p.area}` : ""}`}
            onChange={(_, p) => setF({ ...f, usuario_id: p?.id ?? null, area_id: f.area_id ?? (p ? cat.data?.areas.find((a) => a.nombre === p.area)?.id ?? null : null) })}
            renderInput={(p) => <TextField {...p} label="Asignado a" />} />
          <TextField select label="Área" value={f.area_id ?? ""} onChange={(e) => setF({ ...f, area_id: e.target.value ? Number(e.target.value) : null })}>
            <MenuItem value="">(Ninguna)</MenuItem>
            {(cat.data?.areas ?? []).map((a) => <MenuItem key={a.id} value={a.id}>{a.nombre}</MenuItem>)}
          </TextField>
          {txt("ubicacion", "Ubicación")}
          <TextField select label="Estado" value={f.estado} onChange={(e) => setF({ ...f, estado: e.target.value as Form["estado"] })}>
            {Object.entries(ESTADOS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
          {txt("fecha_compra", "Fecha de compra", { type: "date", slotProps: { inputLabel: { shrink: true } } })}
          {txt("garantia_hasta", "Garantía hasta", { type: "date", slotProps: { inputLabel: { shrink: true } } })}
          {txt("sistema", "Sistema y características", { placeholder: "Windows 11 Pro · 16 GB RAM" })}
          <FormControlLabel control={<Switch checked={f.compartido} onChange={(e) => setF({ ...f, compartido: e.target.checked })} />} label="Compartido (lo pueden elegir todos)" />
          {txt("notas", "Notas", { multiline: true, minRows: 2, sx: { gridColumn: "1 / -1" } })}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" disabled={guardar.isPending || f.codigo.length < 2 || f.marca_modelo.length < 2} onClick={() => guardar.mutate()}>Guardar</Button>
      </DialogActions>
    </Dialog>
  );
}

function Importar({ onCerrar }: { onCerrar: (cambio?: boolean) => void }) {
  const [res, setRes] = useState<{ creados: number; actualizados: number; errores: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const subir = async (archivo: File) => {
    setSubiendo(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      setRes(await api("POST", "/inventario/importar", { form }));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setSubiendo(false);
    }
  };
  return (
    <Dialog open onClose={() => onCerrar(!!res)} maxWidth="sm" fullWidth>
      <DialogTitle>Importar equipos desde Excel</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2">
            Una fila por equipo. Si el código ya existe, se actualiza. La persona se busca por su correo.
          </Typography>
          <Button variant="text" sx={{ alignSelf: "flex-start" }} onClick={() => descargar("/inventario/plantilla", undefined, "plantilla-equipos.xlsx")}>Descargar plantilla</Button>
          <Button component="label" variant="outlined" startIcon={<UploadIcon />} disabled={subiendo} sx={{ alignSelf: "flex-start" }}>
            {subiendo ? "Importando…" : "Elegir archivo .xlsx"}
            <input hidden type="file" accept=".xlsx" onChange={(e) => { const a = e.target.files?.[0]; if (a) subir(a); e.target.value = ""; }} />
          </Button>
          {error && <Alert severity="error">{error}</Alert>}
          {res && (
            <Alert severity={res.errores.length ? "warning" : "success"}>
              {res.creados} creados · {res.actualizados} actualizados{res.errores.length ? ` · ${res.errores.length} filas con error:` : ""}
              {res.errores.map((x) => <Typography key={x} variant="caption" sx={{ display: "block" }}>{x}</Typography>)}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={() => onCerrar(!!res)}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}

export default function Inventario() {
  const { puede } = useAuth();
  const gestiona = puede(P.INVENTARIO);
  const qc = useQueryClient();
  const avisar = useAviso();
  const [texto, setTexto] = useState("");
  const [buscado, setBuscado] = useState("");
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("EN_USO");
  const [elegido, setElegido] = useState<number | null>(null);
  const [editando, setEditando] = useState<Form | null>(null);
  const [importando, setImportando] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setBuscado(texto), 300);
    return () => clearTimeout(t);
  }, [texto]);
  const lista = useQuery({ queryKey: ["inventario", buscado, tipo, estado], queryFn: () => get<Equipo[]>("/inventario", { texto: buscado, tipo, estado }) });
  const id = elegido ?? lista.data?.[0]?.id ?? null;
  const ficha = useQuery({ queryKey: ["inventario", "ficha", id], queryFn: () => get<EquipoDetalle>(`/inventario/${id}`), enabled: !!id });
  const eliminar = useMutation({
    mutationFn: (x: number) => del(`/inventario/${x}`),
    onSuccess: () => { setElegido(null); qc.invalidateQueries({ queryKey: ["inventario"] }); avisar("Equipo eliminado"); },
  });
  const e = ficha.data;
  const enlace = (x: number) => `${window.location.origin}/tickets/nuevo?equipo=${x}`;

  return (
    <>
      <Encabezado titulo="Inventario de equipos" subtitulo="Cada ticket queda en el historial del equipo, y el inventario cuenta sus fallas."
        acciones={gestiona && (
          <>
            <Button variant="outlined" startIcon={<UploadIcon />} onClick={() => setImportando(true)}>Importar desde Excel</Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditando({ ...NUEVO })}>Nuevo equipo</Button>
          </>
        )} />
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "7.3fr 4.7fr" }, alignItems: "start" }}>
        <Paper>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ p: 2 }}>
            <TextField placeholder="Código, serie, persona…" sx={{ flex: 1 }} value={texto} onChange={(ev) => setTexto(ev.target.value)}
              slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }} />
            <TextField select value={tipo} onChange={(ev) => setTipo(ev.target.value)} sx={{ width: { sm: 160 } }} slotProps={{ select: { displayEmpty: true } }}>
              <MenuItem value="">Todos los tipos</MenuItem>
              {Object.entries(TIPOS).map(([k, [n]]) => <MenuItem key={k} value={k}>{n}</MenuItem>)}
            </TextField>
            <TextField select value={estado} onChange={(ev) => setEstado(ev.target.value)} sx={{ width: { sm: 150 } }} slotProps={{ select: { displayEmpty: true } }}>
              <MenuItem value="">Todos</MenuItem>
              {Object.entries(ESTADOS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </TextField>
          </Stack>
          {lista.isLoading ? <Cargando /> : (
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Equipo</TableCell><TableCell>Asignado a</TableCell><TableCell>Estado</TableCell><TableCell align="right">Fallas 12 m</TableCell></TableRow></TableHead>
                <TableBody>
                  {(lista.data ?? []).map((x) => (
                    <TableRow key={x.id} hover selected={x.id === id} sx={{ cursor: "pointer" }} onClick={() => setElegido(x.id)}>
                      <TableCell>
                        <Stack direction="row" spacing={1.2} sx={{ alignItems: "center" }}>
                          <IconoEquipo tipo={x.tipo} />
                          <Box>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main" }}>{x.codigo}</Typography>
                            <Typography variant="caption" color="text.secondary">{TIPOS[x.tipo]?.[0]} · {x.marca_modelo}</Typography>
                          </Box>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{x.usuario ?? (x.compartido ? "Compartido" : "—")}</Typography>
                        <Typography variant="caption" color="text.secondary">{x.area ?? ""}</Typography>
                      </TableCell>
                      <TableCell><Chip size="small" label={ESTADOS[x.estado]} variant="outlined" color={x.estado === "EN_USO" ? "success" : "default"} /></TableCell>
                      <TableCell align="right"><Chip size="small" label={x.fallas_12m} sx={colorFallas(x.fallas_12m)} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {lista.data?.length === 0 && <Vacio texto={gestiona ? "No hay equipos. Regístrelos uno a uno o impórtelos desde Excel." : "No hay equipos"} />}
            </Box>
          )}
        </Paper>
        <Paper sx={{ p: 2.5 }}>
          {!id ? <Vacio texto="Elija un equipo" /> : !e ? <Cargando alto={200} /> : (
            <>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                <IconoEquipo tipo={e.tipo} grande />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="h6" sx={{ lineHeight: 1.2 }}>{e.codigo}</Typography>
                  <Typography variant="body2" color="text.secondary">{e.marca_modelo}{e.serie ? ` · serie ${e.serie}` : ""}</Typography>
                </Box>
                {gestiona && <Button size="small" startIcon={<EditIcon />} onClick={() => setEditando({ ...e })}>Editar</Button>}
              </Stack>
              {e.aviso && <Alert severity="warning" icon={<WarningAmberIcon />} sx={{ my: 1.5 }}>{e.aviso}</Alert>}
              <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>Historial de fallas</Typography>
              {e.historial.map((h) => (
                <Stack key={h.ticket_id} direction="row" spacing={1.2} sx={{ py: 1, borderBottom: "1px solid #EEF1F6", alignItems: "center" }}>
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography variant="body2"><Link component={RouterLink} to={`/tickets/${h.ticket_id}`} sx={{ fontWeight: 700 }}>{h.numero}</Link> · {h.asunto}</Typography>
                    <Typography variant="caption" color="text.secondary">{fecha(h.fecha_creacion)}{h.minutos_resolucion ? ` · resuelto en ${duracion(h.minutos_resolucion)}` : ""}</Typography>
                  </Box>
                  <EstadoChip estado={h.estado} />
                </Stack>
              ))}
              {e.historial.length === 0 && <Typography variant="body2" color="text.secondary">Sin tickets registrados.</Typography>}
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
                {[["Asignado a", e.usuario ?? (e.compartido ? "Compartido" : "—")], ["Ubicación", e.ubicacion ?? "—"],
                  ["Compra", e.fecha_compra ? `${fecha(e.fecha_compra)}${e.garantia_hasta ? ` · garantía hasta ${fecha(e.garantia_hasta)}` : ""}` : "—"], ["Sistema", e.sistema ?? "—"]].map(([k, v]) => (
                  <Box key={k}><Typography variant="caption" color="text.secondary">{k}</Typography><Typography variant="body2">{v}</Typography></Box>
                ))}
              </Box>
              {e.notas && <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap" }}>{e.notas}</Typography>}
              <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                <Button size="small" startIcon={<LinkIcon />} onClick={() => { navigator.clipboard?.writeText(enlace(e.id)); avisar("Enlace copiado: al abrirlo se crea un ticket con este equipo ya elegido"); }}>
                  Copiar enlace para la etiqueta
                </Button>
                {gestiona && <Button size="small" color="error" onClick={() => window.confirm(`¿Eliminar ${e.codigo}? Su historial de tickets se conserva.`) && eliminar.mutate(e.id)}>Eliminar</Button>}
              </Stack>
            </>
          )}
        </Paper>
      </Box>
      {editando && <Editor inicial={editando} onCerrar={(x) => { setEditando(null); if (x) { qc.invalidateQueries({ queryKey: ["inventario"] }); setElegido(x); } }} />}
      {importando && <Importar onCerrar={(c) => { setImportando(false); if (c) qc.invalidateQueries({ queryKey: ["inventario"] }); }} />}
    </>
  );
}
