import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, CircularProgress, Divider, List, ListItem, ListItemIcon, ListItemText, MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import CloseIcon from "@mui/icons-material/Close";
import { api, post } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { SugerenciaTicket, TicketDetalle } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";
import { Cargando, Encabezado } from "../components/Comunes";
import { duracion, tamanoArchivo } from "../utils/formato";
import { P } from "../utils/permisos";

export default function TicketNuevo() {
  const { usuario, puede } = useAuth();
  const cat = useCatalogos();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const avisar = useAviso();
  const [asunto, setAsunto] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [categoriaId, setCategoriaId] = useState<number | "">("");
  const [subId, setSubId] = useState<number | "">("");
  const [prioridadId, setPrioridadId] = useState<number | "">("");
  const [clienteId, setClienteId] = useState<number | "">("");
  const [responsableId, setResponsableId] = useState<number | "">("");
  const [canal, setCanal] = useState("PORTAL");
  const [telefono, setTelefono] = useState(usuario?.telefono ?? "");
  const [correo, setCorreo] = useState(usuario?.correo ?? "");
  const [archivos, setArchivos] = useState<File[]>([]);
  const [sug, setSug] = useState<SugerenciaTicket | null>(null);
  const [analizando, setAnalizando] = useState(false);
  const [tocado, setTocado] = useState({ categoria: false, prioridad: false });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  // Sugerencias de IA mientras el usuario escribe
  useEffect(() => {
    if (asunto.trim().length + descripcion.trim().length < 15) return;
    const t = setTimeout(async () => {
      setAnalizando(true);
      try {
        const s = await post<SugerenciaTicket>("/ia/sugerir", { asunto, descripcion, cliente_id: clienteId || null });
        setSug(s);
        const top = s.clasificaciones[0];
        if (top && !tocado.categoria && top.confianza >= 0.3) {
          setCategoriaId(top.categoria_id);
          setSubId(top.subcategoria_id);
        }
        if (s.prioridad_id && !tocado.prioridad) setPrioridadId(s.prioridad_id);
      } catch {
        /* la IA es opcional */
      } finally {
        setAnalizando(false);
      }
    }, 700);
    return () => clearTimeout(t);
  }, [asunto, descripcion, clienteId, tocado.categoria, tocado.prioridad]);

  if (cat.isLoading || !cat.data) return <Cargando />;
  const categoria = cat.data.categorias.find((c) => c.id === categoriaId);
  const prioridad = cat.data.prioridades.find((p) => p.id === prioridadId);
  const gestorMesa = puede(P.VER_TODOS);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const t = await post<TicketDetalle>("/tickets", {
        asunto,
        descripcion,
        categoria_id: categoriaId,
        subcategoria_id: subId,
        prioridad_id: prioridadId || null,
        cliente_id: clienteId || null,
        telefono: telefono || null,
        correo: correo || null,
        canal,
        responsable_id: responsableId || null,
      });
      for (const f of archivos) {
        const form = new FormData();
        form.append("archivo", f);
        try {
          await api("POST", `/tickets/${t.id}/adjuntos`, { form });
        } catch (err) {
          avisar(`No se pudo adjuntar ${f.name}: ${mensajeError(err)}`, "warning");
        }
      }
      qc.invalidateQueries({ queryKey: ["tickets"] });
      avisar(`Ticket ${t.numero} creado`);
      navigate(`/tickets/${t.id}`, { replace: true });
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      <Encabezado titulo="Nuevo ticket" subtitulo="Describa su requerimiento; la IA sugiere la categoría y la prioridad mientras escribe." />
      <Box component="form" onSubmit={enviar} sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" }, alignItems: "start" }}>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField label="Asunto" value={asunto} onChange={(e) => setAsunto(e.target.value)} required slotProps={{ htmlInput: { maxLength: 200, minLength: 5 } }} />
            <TextField
              label="Descripción"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              required
              multiline
              minRows={6}
              helperText="Incluya número de DAI, guía, partida o trámite cuando aplique."
              slotProps={{ htmlInput: { minLength: 10 } }}
            />
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
              <TextField
                select
                label="Categoría"
                value={categoriaId}
                required
                onChange={(e) => {
                  setTocado((t) => ({ ...t, categoria: true }));
                  setCategoriaId(Number(e.target.value));
                  setSubId("");
                }}
              >
                {cat.data.categorias.map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Subcategoría"
                value={subId}
                required
                disabled={!categoria}
                onChange={(e) => {
                  setTocado((t) => ({ ...t, categoria: true }));
                  setSubId(Number(e.target.value));
                }}
              >
                {(categoria?.subcategorias ?? []).filter((s) => s.activo).map((s) => (
                  <MenuItem key={s.id} value={s.id}>
                    {s.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Prioridad"
                value={prioridadId}
                onChange={(e) => {
                  setTocado((t) => ({ ...t, prioridad: true }));
                  setPrioridadId(Number(e.target.value));
                }}
                helperText={prioridad ? `Respuesta ${duracion(prioridad.sla_respuesta_min)} · resolución ${duracion(prioridad.sla_resolucion_min)} laborables` : "Si no elige, se usa la sugerida"}
              >
                {cat.data.prioridades.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Cliente" value={clienteId} onChange={(e) => setClienteId(e.target.value ? Number(e.target.value) : "")}>
                <MenuItem value="">Sin cliente</MenuItem>
                {cat.data.clientes.filter((c) => c.activo).map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.razon_social}
                    {c.es_vip ? " ★" : ""}
                  </MenuItem>
                ))}
              </TextField>
              <TextField label="Correo de contacto" type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} />
              <TextField label="Teléfono" value={telefono} onChange={(e) => setTelefono(e.target.value)} />
              {gestorMesa && (
                <TextField select label="Canal" value={canal} onChange={(e) => setCanal(e.target.value)}>
                  {["PORTAL", "CORREO", "TELEFONO", "PRESENCIAL"].map((c) => (
                    <MenuItem key={c} value={c}>
                      {c.charAt(0) + c.slice(1).toLowerCase()}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              {puede(P.ASIGNAR) && (
                <TextField select label="Asignar a" value={responsableId} onChange={(e) => setResponsableId(e.target.value ? Number(e.target.value) : "")} helperText="Vacío = asignación automática">
                  <MenuItem value="">Automático</MenuItem>
                  {(categoria?.responsables ?? []).map((r) => (
                    <MenuItem key={r.usuario_id} value={r.usuario_id}>
                      {r.nombre}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            </Box>
            <Box>
              <Button component="label" startIcon={<AttachFileIcon />} variant="outlined">
                Adjuntar archivos
                <input
                  hidden
                  type="file"
                  multiple
                  onChange={(e) => {
                    setArchivos((a) => [...a, ...Array.from(e.target.files ?? [])]);
                    e.target.value = "";
                  }}
                />
              </Button>
              {archivos.length > 0 && (
                <List dense>
                  {archivos.map((f, i) => (
                    <ListItem
                      key={`${f.name}-${i}`}
                      secondaryAction={
                        <Button size="small" onClick={() => setArchivos((a) => a.filter((_, j) => j !== i))} aria-label="Quitar">
                          <CloseIcon fontSize="small" />
                        </Button>
                      }
                    >
                      <ListItemIcon sx={{ minWidth: 32 }}>
                        <InsertDriveFileIcon fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={f.name} secondary={tamanoArchivo(f.size)} />
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>
            <Divider />
            <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
              <Button onClick={() => navigate(-1)}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={enviando || !categoriaId || !subId}>
                {enviando ? "Creando…" : "Crear ticket"}
              </Button>
            </Stack>
          </Stack>
        </Paper>

        <Paper sx={{ p: 3, position: { lg: "sticky" }, top: { lg: 88 } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
            <AutoAwesomeIcon color="primary" />
            <Typography variant="h6">Asistente IA</Typography>
            {analizando && <CircularProgress size={18} />}
          </Stack>
          {!sug ? (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Escriba el asunto y la descripción para recibir sugerencias de clasificación, prioridad y responsable.
            </Typography>
          ) : (
            <Stack spacing={2}>
              <Box>
                <Typography variant="overline" sx={{ color: "text.secondary" }}>
                  Clasificación sugerida
                </Typography>
                <Stack spacing={1} sx={{ mt: 0.5 }}>
                  {sug.clasificaciones.length === 0 && <Typography variant="body2">Sin coincidencias claras.</Typography>}
                  {sug.clasificaciones.map((c) => (
                    <Box
                      key={c.subcategoria_id}
                      onClick={() => {
                        setTocado((t) => ({ ...t, categoria: true }));
                        setCategoriaId(c.categoria_id);
                        setSubId(c.subcategoria_id);
                      }}
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        cursor: "pointer",
                        border: "1px solid",
                        borderColor: subId === c.subcategoria_id ? "primary.main" : "divider",
                        bgcolor: subId === c.subcategoria_id ? "#EEF5FC" : undefined,
                      }}
                    >
                      <Stack direction="row" sx={{ justifyContent: "space-between" }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {c.subcategoria}
                        </Typography>
                        <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 600 }}>
                          {Math.round(c.confianza * 100)} %
                        </Typography>
                      </Stack>
                      <Typography variant="caption" sx={{ color: "text.secondary" }}>
                        {c.categoria}
                        {c.motivos.length ? ` · ${c.motivos.slice(0, 4).join(", ")}` : ""}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
              <Box>
                <Typography variant="overline" sx={{ color: "text.secondary" }}>
                  Prioridad sugerida
                </Typography>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap", gap: 0.5 }}>
                  <Chip label={sug.prioridad} color="primary" size="small" />
                  {sug.prioridad_motivos.map((m) => (
                    <Chip key={m} label={m} size="small" variant="outlined" />
                  ))}
                </Stack>
              </Box>
              {sug.responsable && (
                <Box>
                  <Typography variant="overline" sx={{ color: "text.secondary" }}>
                    Responsable sugerido
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {sug.responsable.nombre}
                  </Typography>
                </Box>
              )}
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Motor: {sug.proveedor === "LOCAL" ? "IA local (reglas y palabras clave)" : sug.proveedor}
              </Typography>
            </Stack>
          )}
        </Paper>
      </Box>
    </>
  );
}
