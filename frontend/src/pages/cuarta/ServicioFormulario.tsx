import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Box, Breadcrumbs, Button, Checkbox, Chip, Divider, FormControlLabel, Link, MenuItem, Paper, TextField, Typography,
} from "@mui/material";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ChecklistIcon from "@mui/icons-material/Checklist";
import { Stack } from "../../components/Pila";
import { get, post } from "../../api/client";
import type { CampoServicio, OpcionesFormulario, Servicio } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";

type Valores = Record<string, string>;

function Campo({ c, valor, onCambio, op }: { c: CampoServicio; valor: string; onCambio: (v: string) => void; op?: OpcionesFormulario }) {
  const etiqueta = c.etiqueta + (c.requerido ? "" : "");
  const comunes = { label: etiqueta, required: c.requerido, fullWidth: true, helperText: c.ayuda ?? undefined, value: valor };
  if (c.tipo === "usuario") {
    const usuarios = op?.usuarios ?? [];
    const sel = usuarios.find((u) => String(u.id) === valor) ?? null;
    return (
      <Autocomplete
        options={usuarios}
        value={sel}
        onChange={(_, u) => onCambio(u ? String(u.id) : "")}
        getOptionLabel={(u) => u.nombre + (u.cargo ? ` · ${u.cargo}` : "")}
        renderInput={(p) => <TextField {...p} label={etiqueta} required={c.requerido} helperText={c.ayuda ?? undefined} />}
      />
    );
  }
  if (c.tipo === "area") {
    return (
      <TextField select {...comunes} onChange={(e) => onCambio(e.target.value)}>
        {(op?.areas ?? []).map((a) => <MenuItem key={a.id} value={String(a.id)}>{a.nombre}</MenuItem>)}
      </TextField>
    );
  }
  if (c.tipo === "lista") {
    return (
      <TextField select {...comunes} onChange={(e) => onCambio(e.target.value)}>
        {c.opciones.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
      </TextField>
    );
  }
  if (c.tipo === "fecha") {
    return <TextField type="date" {...comunes} onChange={(e) => onCambio(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />;
  }
  return (
    <TextField
      {...comunes}
      multiline={c.tipo === "parrafo"}
      minRows={c.tipo === "parrafo" ? 3 : undefined}
      type={c.tipo === "correo" ? "email" : c.tipo === "telefono" ? "tel" : "text"}
      onChange={(e) => onCambio(c.tipo === "cedula" ? e.target.value.replace(/\D/g, "").slice(0, 13) : e.target.value)}
      slotProps={{ htmlInput: c.tipo === "cedula" || c.tipo === "numero" ? { inputMode: "numeric" } : undefined }}
    />
  );
}

function Paso({ n, titulo, texto, activo, ultimo }: { n: number; titulo: string; texto: string; activo?: boolean; ultimo?: boolean }) {
  return (
    <Stack direction="row" sx={{ gap: 1.5 }}>
      <Stack alignItems="center">
        <Box sx={{ width: 26, height: 26, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 13, fontWeight: 700, color: "#fff",
          bgcolor: activo ? "primary.main" : "#9AA4B2", flexShrink: 0 }}>{n}</Box>
        {!ultimo && <Box sx={{ width: 2, flexGrow: 1, bgcolor: "divider", my: 0.5, minHeight: 24 }} />}
      </Stack>
      <Box sx={{ pb: ultimo ? 0 : 2 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, color: activo ? "text.primary" : "text.secondary" }}>{titulo}</Typography>
        <Typography variant="caption" color="text.secondary">{texto}</Typography>
      </Box>
    </Stack>
  );
}

export default function ServicioFormulario() {
  const { id } = useParams();
  const navigate = useNavigate();
  const avisar = useAviso();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["servicios", id], queryFn: () => get<Servicio>(`/servicios/${id}`) });
  const op = useQuery({ queryKey: ["servicios", "opciones"], queryFn: () => get<OpcionesFormulario>("/servicios/opciones"), staleTime: 300_000 });
  const [valores, setValores] = useState<Valores>({});
  const [marcadas, setMarcadas] = useState<string[]>([]);
  const [observaciones, setObservaciones] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (q.data) setMarcadas((q.data.opciones ?? []).filter((o) => o.marcado && !o.siempre).map((o) => o.clave));
  }, [q.data]);

  const s = q.data;
  const casillas = useMemo(() => (s?.opciones ?? []).filter((o) => !o.siempre), [s]);
  const tareas = useMemo(() => (s?.opciones ?? []).filter((o) => o.siempre || marcadas.includes(o.clave)), [s, marcadas]);
  const avisos = casillas.filter((o) => o.aviso && marcadas.includes(o.clave));

  const enviar = useMutation({
    mutationFn: () => post<{ id: number; numero: string; estado: string }>(`/servicios/${id}/solicitar`, {
      respuestas: valores, opciones: marcadas, observaciones: observaciones.trim() || null,
    }),
    onSuccess: (r) => {
      avisar(r.estado === "POR_APROBAR" ? `${r.numero} creado · esperando la aprobación del jefe` : `${r.numero} creado`);
      qc.invalidateQueries({ queryKey: ["servicios"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      navigate(`/tickets/${r.id}`);
    },
    onError: (e) => setError(mensajeError(e)),
  });

  if (q.isLoading) return <Cargando />;
  if (q.error || !s) return <ErrorCarga error={q.error} />;

  const campoJefe = (s.campos ?? []).find((c) => c.aprobador);
  const jefe = campoJefe ? op.data?.usuarios.find((u) => String(u.id) === valores[campoJefe.clave]) : undefined;
  const pideAprobacion = s.requiere_aprobacion;
  const fechaIngreso = (s.campos ?? []).find((c) => c.tipo === "fecha" && valores[c.clave]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (casillas.length && !(s.opciones ?? []).some((o) => o.siempre) && marcadas.length === 0) {
      setError("Marque al menos una opción");
      return;
    }
    enviar.mutate();
  };

  const pasos = [
    ...(pideAprobacion
      ? [{ t: "Aprueba el jefe directo", x: jefe ? `${jefe.nombre} recibe la solicitud en «Por aprobar» para aprobar o rechazar.` : "Su jefe directo recibe la solicitud para aprobar o rechazar." }]
      : []),
    { t: "Se crea el ticket con tareas", x: "Una tarea por cada acceso marcado, repartidas al responsable de cada una." },
    { t: "TI entrega", x: "Cada responsable marca su tarea como lista; usted ve el avance en «Mis solicitudes»." },
    { t: "Usted confirma", x: "Se cierra cuando todo funciona." },
  ];

  return (
    <Box component="form" onSubmit={submit}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/catalogo" underline="hover" color="inherit">Catálogo de servicios</Link>
        <Typography color="text.primary" variant="body2">{s.nombre}</Typography>
      </Breadcrumbs>
      <Stack direction="row" alignItems="center" sx={{ gap: 1.5, mb: 3 }}>
        <Typography variant="h5">{s.nombre}</Typography>
        <Chip size="small" label="FORMULARIO DEL SERVICIO" sx={{ bgcolor: "#FFF3D6", color: "#8A5A00", fontWeight: 700, fontSize: 11 }} />
        {!s.activo && <Chip size="small" label="Inactivo" />}
      </Stack>

      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", lg: "2.4fr 1fr" }, alignItems: "start" }}>
        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          {(s.campos ?? []).length > 0 && (
            <>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>1. {s.titulo_campos || "Datos de la solicitud"}</Typography>
              <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(4, 1fr)" } }}>
                {(s.campos ?? []).map((c) => (
                  <Box key={c.clave} sx={{ gridColumn: { sm: `span ${Math.min(4, Math.max(1, c.ancho))}` } }}>
                    <Campo c={c} valor={valores[c.clave] ?? ""} op={op.data} onCambio={(v) => setValores((x) => ({ ...x, [c.clave]: v }))} />
                  </Box>
                ))}
              </Box>
            </>
          )}
          {s.aviso && <Alert severity="info" sx={{ mt: 2 }}>{s.aviso}</Alert>}
          {casillas.length > 0 && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>2. {s.titulo_opciones || "¿Qué necesita?"}</Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "repeat(3, 1fr)" }, columnGap: 2 }}>
                {casillas.map((o) => (
                  <FormControlLabel key={o.clave} label={o.etiqueta}
                    control={<Checkbox checked={marcadas.includes(o.clave)}
                      onChange={(e) => setMarcadas((x) => (e.target.checked ? [...x, o.clave] : x.filter((k) => k !== o.clave)))} />} />
                ))}
              </Box>
            </>
          )}
          {avisos.map((o) => (
            <Alert key={o.clave} severity="warning" icon={<WarningAmberIcon />} sx={{ mt: 2 }}>{o.aviso}</Alert>
          ))}
          <TextField label="Observaciones (opcional)" fullWidth multiline minRows={2} sx={{ mt: 3 }} value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)} />
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          <Stack direction="row" justifyContent="flex-end" sx={{ gap: 1, mt: 3 }}>
            <Button component={RouterLink} to="/catalogo">Cancelar</Button>
            <Button type="submit" variant="contained" disabled={enviar.isPending || !s.activo}>
              {enviar.isPending ? "Enviando…" : "Enviar solicitud"}
            </Button>
          </Stack>
        </Paper>

        <Stack sx={{ gap: 2.5 }}>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>Qué pasará después</Typography>
            {pasos.map((p, i) => <Paso key={p.t} n={i + 1} titulo={p.t} texto={p.x} activo={i === 0} ultimo={i === pasos.length - 1} />)}
          </Paper>
          {tareas.length > 0 && (
            <Paper variant="outlined" sx={{ p: 2.5 }}>
              <Stack direction="row" alignItems="center" sx={{ gap: 1, mb: 1 }}>
                <ChecklistIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Tareas que se generarán ({tareas.length})</Typography>
              </Stack>
              {tareas.map((o) => (
                <Stack key={o.clave} direction="row" justifyContent="space-between" sx={{ gap: 2, py: 1, borderTop: "1px solid", borderColor: "divider" }}>
                  <Typography variant="body2">{o.tarea || o.etiqueta}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "right", flexShrink: 0 }}>
                    {o.responsable || s.responsable_categoria || "Responsable del ticket"}
                  </Typography>
                </Stack>
              ))}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                Plazo comprometido: {s.plazo}{pideAprobacion ? " después de aprobar" : ""}
                {fechaIngreso ? ` · fecha indicada: ${valores[fechaIngreso.clave].split("-").reverse().join("/")}` : ""}.
              </Typography>
            </Paper>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
