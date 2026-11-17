import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider, List, ListItem, ListItemIcon,
  ListItemText, MenuItem, Paper, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography,
} from "@mui/material";
import LightbulbIcon from "@mui/icons-material/TipsAndUpdates";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import PersonIcon from "@mui/icons-material/Person";
import GroupIcon from "@mui/icons-material/SupervisorAccount";
import ShieldIcon from "@mui/icons-material/Shield";
import MailOutlineIcon from "@mui/icons-material/EmailOutlined";
import LockIcon from "@mui/icons-material/Lock";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import CloseIcon from "@mui/icons-material/Close";
import { api, get, post } from "../api/client";
import { useCatalogos } from "../api/hooks";
import type { EquipoOpcion, KbArticulo, KbResumen, PersonaEnNombre, SugerenciaTicket, TicketDetalle } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { mensajeError, useAviso } from "../components/Aviso";
import { Cargando, Encabezado } from "../components/Comunes";
import { duracion, tamanoArchivo } from "../utils/formato";
import { P } from "../utils/permisos";
import { Pasos } from "./Conocimiento";
import { IconoEquipo, TIPOS } from "./admin/Inventario";

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
  const [params] = useSearchParams();
  const [paraOtro, setParaOtro] = useState(false);
  const [persona, setPersona] = useState<PersonaEnNombre | null>(null);
  const [motivo, setMotivo] = useState("");
  const [equipoId, setEquipoId] = useState<number | null>(Number(params.get("equipo")) || null);
  const [kbSug, setKbSug] = useState<KbResumen[]>([]);
  const [kbVistos, setKbVistos] = useState<number[]>([]);
  const [kbAbierto, setKbAbierto] = useState<KbArticulo | null>(null);
  const personas = useQuery({ queryKey: ["personas-en-nombre"], queryFn: () => get<PersonaEnNombre[]>("/tickets/en-nombre/personas"), staleTime: 60_000 });
  const solicitanteId = paraOtro && persona ? persona.id : usuario?.id;
  const equipos = useQuery({
    queryKey: ["equipos-opciones", solicitanteId],
    queryFn: () => get<EquipoOpcion[]>("/inventario/opciones", { solicitante_id: solicitanteId }),
    enabled: !!solicitanteId,
  });

  // Artículos de la base de conocimiento que podrían resolverlo sin crear el ticket
  useEffect(() => {
    const texto = `${asunto} ${descripcion}`.trim();
    if (texto.length < 12) {
      setKbSug([]);
      return;
    }
    const t = setTimeout(() => {
      post<KbResumen[]>("/conocimiento/sugerir", { texto, categoria_id: categoriaId || null, subcategoria_id: subId || null })
        .then(setKbSug)
        .catch(() => setKbSug([]));
    }, 600);
    return () => clearTimeout(t);
  }, [asunto, descripcion, categoriaId, subId]);

  const abrirArticulo = async (id: number) => {
    try {
      setKbAbierto(await get<KbArticulo>(`/conocimiento/${id}`));
      setKbVistos((v) => (v.includes(id) ? v : [...v, id]));
    } catch (e) {
      avisar(mensajeError(e), "error");
    }
  };
  const resuelto = async (id: number) => {
    try {
      await post(`/conocimiento/${id}/evitar-ticket`);
      avisar("¡Qué bien que se resolvió! No se creó ningún ticket.");
      navigate("/tickets", { replace: true });
    } catch (e) {
      avisar(mensajeError(e), "error");
    }
  };

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
  const puedeEnNombre = (personas.data?.length ?? 0) > 0;
  const restringida = paraOtro && !gestorMesa && !!categoria?.restringida_en_nombre;
  const mostrarEquipo = !!categoria?.pide_equipo || !!equipoId;
  const equipo = equipos.data?.find((x) => x.id === equipoId) ?? null;

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
        solicitante_id: paraOtro && persona ? persona.id : null,
        en_nombre_motivo: paraOtro && persona ? motivo.trim() || null : null,
        equipo_id: mostrarEquipo ? equipoId : null,
        kb_vistos: kbVistos,
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
            {puedeEnNombre && (
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>¿Para quién es este ticket?</Typography>
                <ToggleButtonGroup value={paraOtro ? "otro" : "yo"} exclusive color="primary" size="small" sx={{ mb: paraOtro ? 2 : 0, flexWrap: "wrap" }}
                  onChange={(_, v) => {
                    if (!v) return;
                    setParaOtro(v === "otro");
                    setEquipoId(null);
                    if (v === "yo") {
                      setPersona(null);
                      setCorreo(usuario?.correo ?? "");
                      setTelefono(usuario?.telefono ?? "");
                    }
                  }}>
                  <ToggleButton value="yo"><PersonIcon fontSize="small" sx={{ mr: 0.8 }} />Para mí</ToggleButton>
                  <ToggleButton value="otro"><GroupIcon fontSize="small" sx={{ mr: 0.8 }} />En nombre de otra persona</ToggleButton>
                </ToggleButtonGroup>
                {paraOtro && (
                  <Stack spacing={2}>
                    <Autocomplete
                      options={personas.data ?? []}
                      value={persona}
                      onChange={(_, p) => {
                        setPersona(p);
                        setEquipoId(null);
                        if (p) {
                          setCorreo(p.correo);
                          setTelefono("");
                        }
                      }}
                      getOptionLabel={(p) => `${p.nombre}${p.area ? ` · ${p.area}` : ""}`}
                      renderInput={(p) => <TextField {...p} required label="Persona que necesita la atención"
                        helperText={gestorMesa ? "Registro de la mesa (llamada, visita o correo)." : "Solo aparecen las personas que usted tiene autorizadas."} />}
                    />
                    <TextField label={gestorMesa ? "Motivo (opcional)" : "Motivo (obligatorio)"} required={!gestorMesa} multiline value={motivo}
                      onChange={(e) => setMotivo(e.target.value)} slotProps={{ htmlInput: { maxLength: 300 } }}
                      placeholder="Ej.: está de viaje sin acceso a la Mesa; me pidió por teléfono reportarlo." />
                  </Stack>
                )}
                <Divider sx={{ mt: 2 }} />
              </Box>
            )}
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
              {restringida && (
                <Alert severity="warning" icon={<LockIcon />} sx={{ gridColumn: "1 / -1" }}>
                  «{categoria?.nombre}» no se puede pedir en nombre de otra persona: debe solicitarlo {persona?.nombre ?? "la persona"} o la Mesa de Servicios.
                </Alert>
              )}
              {mostrarEquipo && (
                <Autocomplete
                  sx={{ gridColumn: "1 / -1" }}
                  options={equipos.data ?? []}
                  value={equipo}
                  onChange={(_, o) => setEquipoId(o?.id ?? null)}
                  getOptionLabel={(o) => `${o.codigo} · ${o.marca_modelo}`}
                  renderInput={(p) => <TextField {...p} label="Equipo afectado (opcional)" helperText="Primero aparecen los equipos asignados a la persona, luego los compartidos." />}
                  renderOption={(props, o) => {
                    const { key, ...rest } = props as typeof props & { key: string };
                    return (
                      <li key={key} {...rest}>
                        <Stack direction="row" spacing={1.2} sx={{ alignItems: "center", width: "100%" }}>
                          <IconoEquipo tipo={o.tipo} />
                          <Box sx={{ flex: 1 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{o.codigo}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {TIPOS[o.tipo]?.[0]} · {o.marca_modelo}{o.propio ? (paraOtro ? " · de la persona" : " · suyo") : o.compartido ? " · compartido" : ""}
                            </Typography>
                          </Box>
                          {o.fallas_12m > 0 && <Typography variant="caption" color="text.secondary">{o.fallas_12m} falla{o.fallas_12m === 1 ? "" : "s"}</Typography>}
                        </Stack>
                      </li>
                    );
                  }}
                />
              )}
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
              <Button type="submit" variant="contained"
                disabled={enviando || !categoriaId || !subId || restringida || (paraOtro && (!persona || (!gestorMesa && motivo.trim().length < 5)))}>
                {enviando ? "Creando…" : paraOtro && persona ? `Crear en nombre de ${persona.nombre.split(" ")[0]}` : "Crear ticket"}
              </Button>
            </Stack>
          </Stack>
        </Paper>

        <Stack spacing={2} sx={{ position: { lg: "sticky" }, top: { lg: 88 } }}>
        {kbSug.length > 0 && (
          <Paper sx={{ p: 2.5, border: "1.5px solid", borderColor: "primary.light", background: "linear-gradient(180deg,#EEF5FC 0%,#fff 60%)" }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
              <LightbulbIcon sx={{ color: "#B57400" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Antes de enviar: quizá esto lo resuelve</Typography>
            </Stack>
            <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>Artículos de la base de conocimiento parecidos a lo que escribe.</Typography>
            <Stack spacing={1.2}>
              {kbSug.map((k, i) => (
                <Paper key={k.id} variant="outlined" sx={{ p: 1.6, ...(i === 0 ? { borderColor: "primary.main", borderWidth: 1.5 } : {}) }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
                    <MenuBookIcon color="primary" fontSize="small" sx={{ mt: 0.2 }} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700, color: "primary.main", cursor: "pointer" }} onClick={() => abrirArticulo(k.id)}>{k.titulo}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {k.categoria ?? "General"}{k.util_pct !== null ? ` · a ${k.util_pct} % le sirvió` : ""} · {k.vistas} vistas
                      </Typography>
                      {i === 0 && k.extracto && <Typography variant="body2" sx={{ mt: 0.8 }}>{k.extracto}</Typography>}
                    </Box>
                    {k.util_pct !== null && k.util_pct >= 50 && <Chip size="small" label={`${k.util_pct} %`} sx={{ bgcolor: "#E8F5E9", color: "#2E7D32" }} />}
                  </Stack>
                  {i === 0 && (
                    <Stack direction="row" sx={{ mt: 1.2, flexWrap: "wrap", gap: 1 }}>
                      <Button size="small" variant="contained" color="success" startIcon={<CheckCircleIcon />} onClick={() => resuelto(k.id)}>Se resolvió, no crear ticket</Button>
                      <Button size="small" variant="outlined" onClick={() => abrirArticulo(k.id)}>Ver artículo completo</Button>
                    </Stack>
                  )}
                </Paper>
              ))}
            </Stack>
            <Typography variant="caption" sx={{ display: "block", mt: 1.5, color: "text.secondary" }}>
              Si ninguno sirve, cree el ticket normal: el responsable verá qué artículos ya revisó.
            </Typography>
          </Paper>
        )}
        {paraOtro && !gestorMesa && (
          <Paper sx={{ p: 2.5 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
              <ShieldIcon color="primary" />
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Controles de seguridad</Typography>
            </Stack>
            <Alert severity="info" icon={<MailOutlineIcon />} sx={{ mb: 1.5 }}>
              {persona ? persona.nombre.split(" ")[0] : "La persona"} recibirá un correo avisando que usted creó el ticket en su nombre, con el motivo.
            </Alert>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.8 }}>Qué podrá ver usted</Typography>
            {["Este ticket, en solo lectura, desde «Tickets en los que participé».", "No verá otros tickets de esa persona.", "Las respuestas del analista le llegan a la persona, no a usted."].map((x, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ mb: 0.6 }}>
                <Typography variant="body2" sx={{ color: "primary.main", fontWeight: 700 }}>{i + 1}.</Typography>
                <Typography variant="body2">{x}</Typography>
              </Stack>
            ))}
          </Paper>
        )}
        <Paper sx={{ p: 3 }}>
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
        </Stack>
      </Box>
      <Dialog open={!!kbAbierto} onClose={() => setKbAbierto(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{kbAbierto?.titulo}</DialogTitle>
        <DialogContent>
          {kbAbierto?.sintoma && <Typography variant="body2" sx={{ mb: 2, color: "text.secondary" }}>{kbAbierto.sintoma}</Typography>}
          {kbAbierto && <Pasos texto={kbAbierto.solucion} />}
          {kbAbierto?.nota && <Alert severity="warning" sx={{ mt: 1.5 }}>{kbAbierto.nota}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKbAbierto(null)}>No me sirvió, seguir con el ticket</Button>
          <Button variant="contained" color="success" startIcon={<CheckCircleIcon />} onClick={() => kbAbierto && resuelto(kbAbierto.id)}>Se resolvió, no crear ticket</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
