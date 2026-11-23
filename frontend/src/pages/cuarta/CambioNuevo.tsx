import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Box, Breadcrumbs, Button, Chip, FormControlLabel, Link, MenuItem, Paper, Radio, RadioGroup, TextField, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import { get, post, put } from "../../api/client";
import type { Cambio, OpcionesCambio } from "../../api/cuarta";
import { mensajeError, useAviso } from "../../components/Aviso";
import { Cargando, ErrorCarga } from "../../components/Comunes";

interface Form {
  formato: "MESA" | "GENERAL";
  titulo: string;
  telefono: string;
  tipo_solicitud: string;
  aplicacion: string;
  partes: string[];
  pantalla: string;
  desde_donde: string;
  ticket_relacionado: string;
  situacion_actual: string;
  situacion_deseada: string;
  justificacion: string;
  beneficiados: string;
  prioridad_sugerida: string;
}

const VACIO: Form = {
  formato: "MESA", titulo: "", telefono: "", tipo_solicitud: "MEJORA", aplicacion: "Mesa de Servicios", partes: [], pantalla: "", desde_donde: "",
  ticket_relacionado: "", situacion_actual: "", situacion_deseada: "", justificacion: "", beneficiados: "", prioridad_sugerida: "MEDIA",
};

const PARTES_MESA = ["Tickets", "Catálogo de servicios", "Aprobaciones", "Reportes e indicadores", "Correos y avisos", "Usuarios y permisos",
  "Inventario", "Base de conocimiento", "Categorías y SLA"];

function Seccion({ n, titulo, children }: { n: number; titulo: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 }, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>{n}. {titulo}</Typography>
      {children}
    </Paper>
  );
}

export default function CambioNuevo() {
  const { id } = useParams();
  const editando = !!id;
  const navigate = useNavigate();
  const avisar = useAviso();
  const qc = useQueryClient();
  const op = useQuery({ queryKey: ["cambios", "opciones"], queryFn: () => get<OpcionesCambio>("/cambios/opciones") });
  const actual = useQuery({ queryKey: ["cambios", id], queryFn: () => get<Cambio>(`/cambios/${id}`), enabled: editando });
  const [f, setF] = useState<Form>(VACIO);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    const c = actual.data;
    if (c) {
      setF({
        formato: c.formato, titulo: c.titulo, telefono: c.telefono ?? "", tipo_solicitud: c.tipo_solicitud, aplicacion: c.aplicacion ?? "",
        partes: c.partes ?? [], pantalla: c.pantalla ?? "", desde_donde: c.desde_donde ?? "", ticket_relacionado: c.ticket_relacionado ?? "",
        situacion_actual: c.situacion_actual, situacion_deseada: c.situacion_deseada, justificacion: c.justificacion ?? "",
        beneficiados: c.beneficiados ?? "", prioridad_sugerida: c.prioridad_sugerida ?? "MEDIA",
      });
    }
  }, [actual.data]);

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        ...f, telefono: f.telefono || null, aplicacion: f.formato === "MESA" ? "Mesa de Servicios" : f.aplicacion || null, pantalla: f.pantalla || null,
        desde_donde: f.desde_donde || null, ticket_relacionado: f.ticket_relacionado || null, justificacion: f.justificacion || null,
        beneficiados: f.beneficiados || null,
      };
      return editando ? put<Cambio>(`/cambios/${id}`, cuerpo) : post<Cambio>("/cambios", cuerpo);
    },
    onSuccess: (c) => {
      avisar(editando ? "Solicitud actualizada" : `${c.numero} registrado · TI lo evaluará`);
      qc.invalidateQueries({ queryKey: ["cambios"] });
      navigate(`/cambios/${c.id}`);
    },
    onError: (e) => setError(mensajeError(e)),
  });

  if (op.isLoading || actual.isLoading) return <Cargando />;
  if (op.error) return <ErrorCarga error={op.error} />;
  const t = op.data!.textos;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    guardar.mutate();
  };

  return (
    <Box component="form" onSubmit={submit} sx={{ maxWidth: 980 }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/cambios" underline="hover" color="inherit">Cambios</Link>
        <Typography color="text.primary" variant="body2">{editando ? actual.data?.numero : "Solicitar cambio"}</Typography>
      </Breadcrumbs>
      <Typography variant="h5" sx={{ mb: 0.5 }}>{editando ? `Corregir ${actual.data?.numero}` : "Solicitar un cambio"}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Llene las secciones 1 a 6. TI completa la sección 7 (evaluación) y, según el riesgo, lo aprueban el Jefe de TI y Gerencia.
      </Typography>

      <ToggleButtonGroup exclusive color="primary" value={f.formato} onChange={(_, v) => v && set("formato", v)} sx={{ mb: 2, flexWrap: "wrap" }}>
        <ToggleButton value="MESA">TI-FOR-001 · Cambio en la Mesa de Servicios</ToggleButton>
        <ToggleButton value="GENERAL">TI-FOR-002 · Cambio en otro sistema o servicio</ToggleButton>
      </ToggleButtonGroup>

      <Seccion n={1} titulo="Datos de la solicitud">
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "3fr 1fr" } }}>
          <TextField label="¿Qué cambio necesita? (título corto)" required value={f.titulo} onChange={(e) => set("titulo", e.target.value)}
            placeholder="Ej.: Actualizar el sistema contable a la versión 2027" />
          <TextField label="Teléfono o extensión" value={f.telefono} onChange={(e) => set("telefono", e.target.value)} />
        </Box>
      </Seccion>

      <Seccion n={2} titulo="Tipo de solicitud">
        <RadioGroup row value={f.tipo_solicitud} onChange={(e) => set("tipo_solicitud", e.target.value)}>
          {Object.entries(t.tipo_solicitud).map(([k, v]) => <FormControlLabel key={k} value={k} control={<Radio />} label={v} />)}
        </RadioGroup>
      </Seccion>

      <Seccion n={3} titulo="¿Dónde está el cambio?">
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          {f.formato === "GENERAL" && (
            <TextField select label="Aplicación o servicio" value={f.aplicacion} onChange={(e) => set("aplicacion", e.target.value)} required>
              {op.data!.aplicaciones.filter((a) => a !== "Mesa de Servicios").map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
            </TextField>
          )}
          <Autocomplete multiple freeSolo options={f.formato === "MESA" ? PARTES_MESA : []} value={f.partes}
            onChange={(_, v) => set("partes", v.map((x) => x.trim()).filter(Boolean).slice(0, 15))}
            renderValue={(v, getTagProps) => v.map((x, i) => <Chip size="small" label={x} {...getTagProps({ index: i })} key={x} />)}
            renderInput={(p) => <TextField {...p} label="Parte afectada" helperText="Elija o escriba y presione Enter" />} />
          <TextField label="Pantalla, menú o proceso" value={f.pantalla} onChange={(e) => set("pantalla", e.target.value)} />
          <TextField select label="¿Desde dónde lo usa?" value={f.desde_donde} onChange={(e) => set("desde_donde", e.target.value)}>
            <MenuItem value="">—</MenuItem>
            {Object.entries(t.desde_donde).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
          <TextField label="Tickets relacionados (opcional)" placeholder="ADU-2026-000799" value={f.ticket_relacionado}
            onChange={(e) => set("ticket_relacionado", e.target.value)} />
        </Box>
      </Seccion>

      <Seccion n={4} titulo="¿Cómo funciona hoy?">
        <TextField fullWidth multiline minRows={3} required value={f.situacion_actual} onChange={(e) => set("situacion_actual", e.target.value)}
          placeholder="Describa el problema o la forma actual de trabajar" />
      </Seccion>

      <Seccion n={5} titulo="¿Cómo debería funcionar?">
        <TextField fullWidth multiline minRows={3} required value={f.situacion_deseada} onChange={(e) => set("situacion_deseada", e.target.value)}
          placeholder="Lo que espera ver cuando el cambio esté listo" />
      </Seccion>

      <Seccion n={6} titulo="Justificación y prioridad">
        <TextField fullWidth multiline minRows={2} label="¿Por qué es necesario? (beneficio, plazo legal, riesgo)" value={f.justificacion}
          onChange={(e) => set("justificacion", e.target.value)} sx={{ mb: 2 }} />
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          <TextField select label="¿A quiénes beneficia?" value={f.beneficiados} onChange={(e) => set("beneficiados", e.target.value)}>
            <MenuItem value="">—</MenuItem>
            {Object.entries(t.beneficiados).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
          </TextField>
          <TextField select label="Prioridad sugerida" value={f.prioridad_sugerida} onChange={(e) => set("prioridad_sugerida", e.target.value)}>
            <MenuItem value="ALTA">Alta</MenuItem><MenuItem value="MEDIA">Media</MenuItem><MenuItem value="BAJA">Baja</MenuItem>
          </TextField>
        </Box>
      </Seccion>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Stack direction="row" justifyContent="flex-end" sx={{ gap: 1, mb: 4 }}>
        <Button component={RouterLink} to={editando ? `/cambios/${id}` : "/cambios"}>Cancelar</Button>
        <Button type="submit" variant="contained" disabled={guardar.isPending}>{editando ? "Guardar" : "Enviar a TI"}</Button>
      </Stack>
    </Box>
  );
}
