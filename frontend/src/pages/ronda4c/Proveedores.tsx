/** Proveedores y contratos (33): cumplimiento del plazo pactado, contratos por vencer y multas reclamables. */
import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Autocomplete, Avatar, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Link, Paper,
  Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/EditOutlined";
import PhoneIcon from "@mui/icons-material/PhoneOutlined";
import MailIcon from "@mui/icons-material/EmailOutlined";
import DescriptionIcon from "@mui/icons-material/DescriptionOutlined";
import { Stack } from "../../components/Pila";
import { del, get, post, put } from "../../api/client";
import type { Cumplimiento, ProveedorDetalle, ProveedoresLista } from "../../api/ronda4c";
import { mensajeError, useAviso } from "../../components/Aviso";
import CampoCorreos from "../../components/CampoCorreos";
import { Cargando, Encabezado, ErrorCarga, Vacio } from "../../components/Comunes";
import { fecha, fechaHora } from "../../utils/formato";
import { duracionCorta } from "../ronda4b/comun";

const CUMPLE: Record<Cumplimiento, { texto: string; color: string; fondo: string }> = {
  CUMPLE: { texto: "Cumple", color: "#2E7D32", fondo: "#E8F5E9" },
  AL_LIMITE: { texto: "Al límite", color: "#E65100", fondo: "#FFF3E0" },
  INCUMPLE: { texto: "Incumple", color: "#C62828", fondo: "#FFEBEE" },
};
const usd = (n: number) => `USD ${n.toLocaleString("es-EC", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function ChipCumplimiento({ v }: { v: Cumplimiento }) {
  const c = CUMPLE[v];
  return <Chip size="small" label={c.texto} sx={{ color: c.color, bgcolor: c.fondo, border: `1px solid ${c.color}55`, fontWeight: 600 }} />;
}

interface Form {
  nombre: string; servicio: string; telefono: string; correo: string; correos_copia: string[]; portal: string; contacto: string;
  contrato_numero: string; contrato_vence: string; contrato_detalle: string; atencion_24x7: boolean; plazo_horas: string;
  valor_mensual: string; multa_pct_hora: string; subcategorias: number[]; notas: string; activo: boolean;
}
const VACIO: Form = {
  nombre: "", servicio: "", telefono: "", correo: "", correos_copia: [], portal: "", contacto: "", contrato_numero: "", contrato_vence: "",
  contrato_detalle: "", atencion_24x7: false, plazo_horas: "8", valor_mensual: "", multa_pct_hora: "", subcategorias: [], notas: "", activo: true,
};

function DialogoProveedor({ abierto, p, onCerrar, onListo }: { abierto: boolean; p: ProveedorDetalle | null; onCerrar: () => void; onListo: (id: number) => void }) {
  const avisar = useAviso();
  const [f, setF] = useState<Form>(VACIO);
  const opciones = useQuery({ queryKey: ["proveedores", "opciones"], queryFn: () => get<{ subcategorias: { id: number; nombre: string }[] }>("/proveedores/opciones"), enabled: abierto });
  useEffect(() => {
    if (!abierto) return;
    setF(p ? {
      nombre: p.nombre, servicio: p.servicio, telefono: p.telefono ?? "", correo: p.correo ?? "", correos_copia: p.correos_copia, portal: p.portal ?? "",
      contacto: p.contacto ?? "", contrato_numero: p.contrato_numero ?? "", contrato_vence: p.contrato_vence ?? "", contrato_detalle: p.contrato_detalle ?? "",
      atencion_24x7: p.atencion_24x7, plazo_horas: String(p.plazo_horas), valor_mensual: p.valor_mensual?.toString() ?? "",
      multa_pct_hora: p.multa_pct_hora?.toString() ?? "", subcategorias: p.subcategorias, notas: p.notas ?? "", activo: p.activo,
    } : VACIO);
  }, [abierto, p]);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const guardar = useMutation({
    mutationFn: () => {
      const n = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));
      const t = (s: string) => s.trim() || null;
      const datos = {
        nombre: f.nombre.trim(), servicio: f.servicio.trim(), telefono: t(f.telefono), correo: t(f.correo), correos_copia: f.correos_copia,
        portal: t(f.portal), contacto: t(f.contacto), contrato_numero: t(f.contrato_numero), contrato_vence: f.contrato_vence || null,
        contrato_detalle: t(f.contrato_detalle), atencion_24x7: f.atencion_24x7, plazo_horas: Number(f.plazo_horas) || 8,
        valor_mensual: n(f.valor_mensual), multa_pct_hora: n(f.multa_pct_hora), subcategorias: f.subcategorias, notas: t(f.notas), activo: f.activo,
      };
      return p ? put<ProveedorDetalle>(`/proveedores/${p.id}`, datos) : post<ProveedorDetalle>("/proveedores", datos);
    },
    onSuccess: (r) => { avisar(p ? "Proveedor actualizado" : "Proveedor registrado"); onListo(r.id); onCerrar(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  const subs = opciones.data?.subcategorias ?? [];
  return (
    <Dialog open={abierto} onClose={onCerrar} fullWidth maxWidth="md">
      <DialogTitle>{p ? `Editar ${p.nombre}` : "Nuevo proveedor"}</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
          <TextField label="Proveedor" required value={f.nombre} onChange={(e) => set("nombre", e.target.value)} />
          <TextField label="Servicio" required placeholder="Internet corporativo GYE" value={f.servicio} onChange={(e) => set("servicio", e.target.value)} />
          <TextField label="Teléfono de soporte" value={f.telefono} onChange={(e) => set("telefono", e.target.value)} />
          <TextField label="Contacto / ejecutivo" value={f.contacto} onChange={(e) => set("contacto", e.target.value)} />
          <TextField label="Correo de soporte" type="email" value={f.correo} onChange={(e) => set("correo", e.target.value)} />
          <TextField label="Portal de soporte" value={f.portal} onChange={(e) => set("portal", e.target.value)} />
          <Box sx={{ gridColumn: "1 / -1" }}>
            <CampoCorreos etiqueta="Copia de los correos al proveedor" valor={f.correos_copia} onCambio={(v) => set("correos_copia", v)} ayuda="Por ejemplo, su ejecutivo de cuenta." />
          </Box>
          <Divider sx={{ gridColumn: "1 / -1" }}>Contrato</Divider>
          <TextField label="N.º de contrato" value={f.contrato_numero} onChange={(e) => set("contrato_numero", e.target.value)} />
          <TextField label="Vence" type="date" value={f.contrato_vence} onChange={(e) => set("contrato_vence", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Plazo de solución (horas)" type="number" value={f.plazo_horas} onChange={(e) => set("plazo_horas", e.target.value)}
            helperText={f.atencion_24x7 ? "Horas de reloj (24/7)" : "Horas laborables según el calendario de la Mesa"} slotProps={{ htmlInput: { min: 1 } }} />
          <FormControlLabel control={<Switch checked={f.atencion_24x7} onChange={(e) => set("atencion_24x7", e.target.checked)} />} label="Atención 24/7" />
          <TextField label="Valor mensual (USD)" value={f.valor_mensual} onChange={(e) => set("valor_mensual", e.target.value)} inputMode="decimal" />
          <TextField label="Multa (% de la mensualidad por hora extra)" value={f.multa_pct_hora} onChange={(e) => set("multa_pct_hora", e.target.value)} inputMode="decimal" />
          <TextField label="Detalle del contrato" sx={{ gridColumn: "1 / -1" }} placeholder="20 Mbps simétrico, archivo CT-2025-031.pdf" value={f.contrato_detalle}
            onChange={(e) => set("contrato_detalle", e.target.value)} />
          <Autocomplete
            multiple
            sx={{ gridColumn: "1 / -1" }}
            options={subs.map((s) => s.id)}
            getOptionLabel={(id) => subs.find((s) => s.id === id)?.nombre ?? String(id)}
            value={f.subcategorias}
            onChange={(_, v) => set("subcategorias", v)}
            renderInput={(pr) => <TextField {...pr} label="Categorías que se escalan a este proveedor" helperText="Aparece primero como sugerido en esos tickets." />}
          />
          <TextField label="Notas" multiline minRows={2} sx={{ gridColumn: "1 / -1" }} value={f.notas} onChange={(e) => set("notas", e.target.value)} />
          {p && <FormControlLabel control={<Switch checked={f.activo} onChange={(e) => set("activo", e.target.checked)} />} label="Activo" />}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cancelar</Button>
        <Button variant="contained" disabled={f.nombre.trim().length < 2 || f.servicio.trim().length < 2 || guardar.isPending} onClick={() => guardar.mutate()}>Guardar</Button>
      </DialogActions>
    </Dialog>
  );
}

function Ficha({ id, onEditar, onEliminado }: { id: number; onEditar: (p: ProveedorDetalle) => void; onEliminado: () => void }) {
  const avisar = useAviso();
  const q = useQuery({ queryKey: ["proveedores", id], queryFn: () => get<ProveedorDetalle>(`/proveedores/${id}`) });
  const eliminar = useMutation({
    mutationFn: () => del(`/proveedores/${id}`),
    onSuccess: () => { avisar("Proveedor eliminado"); onEliminado(); },
    onError: (e) => avisar(mensajeError(e), "error"),
  });
  if (q.isLoading) return <Cargando />;
  if (q.error || !q.data) return <ErrorCarga error={q.error} />;
  const p = q.data;
  const max = Math.max(1, ...p.meses.map((m) => m.casos));
  return (
    <>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" }, alignItems: "start" }}>
        <Paper sx={{ p: 3 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="h6">Ficha · {p.nombre}</Typography>
            <Button size="small" startIcon={<EditIcon />} onClick={() => onEditar(p)}>Editar</Button>
          </Stack>
          <Stack spacing={1}>
            <Stack direction="row" spacing={1.2}><PhoneIcon fontSize="small" color="action" />
              <Typography variant="body2">Soporte {p.telefono ?? "—"} ({p.atencion_24x7 ? "24/7" : "horario laboral"}){p.contacto ? ` · Ejecutivo: ${p.contacto}` : ""}</Typography>
            </Stack>
            <Stack direction="row" spacing={1.2}><MailIcon fontSize="small" color="action" />
              <Typography variant="body2">{p.correo ?? "Sin correo"}{p.correos_copia.length ? ` · copia a ${p.correos_copia.join(", ")}` : ""}</Typography>
            </Stack>
            <Stack direction="row" spacing={1.2}><DescriptionIcon fontSize="small" color="action" />
              <Typography variant="body2">
                {[p.contrato_numero, p.valor_mensual != null ? `${usd(p.valor_mensual)} mensuales` : null, p.contrato_detalle].filter(Boolean).join(" · ") || "Sin datos del contrato"}
              </Typography>
            </Stack>
            <Typography variant="body2">Plazo pactado: <b>{p.plazo}</b>{p.multa_texto ? ` · multa ${p.multa_texto}` : ""}</Typography>
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" color="text.secondary">Categorías que se escalan a este proveedor</Typography>
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75, mt: 0.75 }}>
            {p.subcategorias_nombres.length === 0 && <Typography variant="body2" color="text.secondary">Ninguna: se puede elegir en cualquier ticket.</Typography>}
            {p.subcategorias_nombres.map((s) => <Chip key={s} size="small" label={s} />)}
          </Stack>
          {p.notas && <Typography variant="body2" sx={{ mt: 1.5, whiteSpace: "pre-wrap" }}>{p.notas}</Typography>}
          <Button size="small" color="error" sx={{ mt: 2 }} onClick={() => window.confirm(`¿Eliminar a ${p.nombre}? Sus casos quedan en el historial.`) && eliminar.mutate()} disabled={eliminar.isPending}>Eliminar proveedor</Button>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Casos de {p.nombre} en {p.anio}</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 0.75, alignItems: "end", height: 130 }}>
            {p.meses.map((m) => (
              <Tooltip key={m.mes} title={`${m.casos} caso(s), ${m.fuera} fuera de plazo`}>
                <Box sx={{ height: `${Math.max(3, (m.casos / max) * 100)}%`, bgcolor: m.fuera > 1 ? "#C62828" : m.fuera === 1 ? "#E65100" : "#6FA8D6", borderRadius: "3px 3px 0 0", opacity: m.casos ? 1 : 0.35 }} />
              </Tooltip>
            ))}
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 0.75, mt: 0.5 }}>
            {p.meses.map((m) => <Typography key={m.mes} variant="caption" color="text.secondary" align="center">{m.letra}</Typography>)}
          </Box>
          <Typography variant="body2" sx={{ mt: 2 }}>
            {p.caidas_anio} caída{p.caidas_anio === 1 ? "" : "s"} en el año · {p.fuera_plazo_anio} fuera de plazo · multas reclamables: <b>{usd(p.multas_anio)}</b>
          </Typography>
        </Paper>
      </Box>
      <Paper sx={{ mt: 2 }}>
        <Typography variant="h6" sx={{ p: 2.5, pb: 1 }}>Casos</Typography>
        {p.casos.length === 0 ? <Vacio texto="Todavía no se le ha escalado ningún ticket" /> : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Ticket</TableCell><TableCell>Caso</TableCell><TableCell>Reportado</TableCell><TableCell>Vence</TableCell>
                  <TableCell>Solución</TableCell><TableCell>Estado</TableCell><TableCell align="right">Multa</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {p.casos.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell><Link component={RouterLink} to={`/tickets/${c.ticket_id}`}>{c.ticket_numero}</Link>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{c.ticket_asunto}</Typography></TableCell>
                    <TableCell>{c.numero_caso ?? "—"}</TableCell>
                    <TableCell>{fechaHora(c.fecha_reporte)}</TableCell>
                    <TableCell>{fechaHora(c.vence)}</TableCell>
                    <TableCell>{c.minutos_solucion != null ? duracionCorta(c.minutos_solucion) : "—"}</TableCell>
                    <TableCell>
                      {c.estado === "ABIERTO"
                        ? <Chip size="small" color={c.vencido ? "error" : "warning"} label={c.vencido ? "Abierto, vencido" : "Abierto"} />
                        : <Chip size="small" color={c.cumplido ? "success" : "error"} variant="outlined" label={c.cumplido ? "En plazo" : "Fuera de plazo"} />}
                    </TableCell>
                    <TableCell align="right">{c.multa ? usd(c.multa) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </>
  );
}

export default function Proveedores() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["proveedores"], queryFn: () => get<ProveedoresLista>("/proveedores") });
  const [sel, setSel] = useState<number | null>(null);
  const [dialogo, setDialogo] = useState<{ p: ProveedorDetalle | null } | null>(null);
  const lista = q.data?.proveedores;
  useEffect(() => {
    if (lista?.length && (sel === null || !lista.some((p) => p.id === sel))) setSel(lista[0].id);
  }, [lista, sel]);
  if (q.isLoading) return <Cargando />;
  if (q.error || !q.data) return <ErrorCarga error={q.error} />;
  const r = q.data;
  const refrescar = (id?: number) => {
    qc.invalidateQueries({ queryKey: ["proveedores"] });
    if (id) setSel(id);
  };
  return (
    <>
      <Encabezado
        titulo="Proveedores y contratos"
        subtitulo="Plazo pactado de cada proveedor, casos escalados y multas reclamables."
        acciones={<Button variant="contained" startIcon={<AddIcon />} onClick={() => setDialogo({ p: null })}>Nuevo proveedor</Button>}
      />
      {r.alertas.map((a) => (
        <Alert key={a.id} severity="warning" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => setSel(a.id)}>Ver contrato</Button>}>
          <b>El contrato con {a.nombre} {a.dias < 0 ? `venció el ${fecha(a.contrato_vence)}` : `vence en ${a.dias} día${a.dias === 1 ? "" : "s"} (${fecha(a.contrato_vence)})`}</b>
          {a.fuera_mes > 0 ? ` y lleva ${a.fuera_mes} caída${a.fuera_mes === 1 ? "" : "s"} fuera de plazo este mes` : ""}.
          {a.avisado && r.aviso_correo.length ? ` Aviso enviado a ${r.aviso_correo.join(", ")} 30 días antes.` : ""}
        </Alert>
      ))}
      <Paper sx={{ mb: 2 }}>
        {r.proveedores.length === 0 ? <Vacio texto="Aún no hay proveedores. Registre el primero con «Nuevo proveedor»." /> : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Proveedor</TableCell><TableCell>Servicio</TableCell><TableCell>Contrato vence</TableCell><TableCell>Plazo pactado</TableCell>
                  <TableCell align="center">Casos abiertos</TableCell><TableCell>Solución promedio</TableCell><TableCell>Cumplimiento</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {r.proveedores.map((p) => (
                  <TableRow key={p.id} hover selected={p.id === sel} onClick={() => setSel(p.id)} sx={{ cursor: "pointer", opacity: p.activo ? 1 : 0.55 }}>
                    <TableCell>
                      <Stack direction="row" spacing={1.2} alignItems="center">
                        <Avatar sx={{ width: 32, height: 32, fontSize: 14, bgcolor: "primary.main" }}>{p.nombre[0]}</Avatar>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>{p.nombre}</Typography>
                        {!p.activo && <Chip size="small" label="Inactivo" />}
                      </Stack>
                    </TableCell>
                    <TableCell>{p.servicio}</TableCell>
                    <TableCell>
                      {p.contrato_vence ? fecha(p.contrato_vence) : "—"}
                      {p.dias_para_vencer != null && (
                        <Typography variant="caption" sx={{ display: "block", color: p.dias_para_vencer <= 45 ? "error.main" : "text.secondary", fontWeight: p.dias_para_vencer <= 45 ? 700 : 400 }}>
                          {p.dias_para_vencer < 0 ? "vencido" : `en ${p.dias_para_vencer} días`}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{p.plazo}</TableCell>
                    <TableCell align="center"><Chip size="small" label={p.casos_abiertos} /></TableCell>
                    <TableCell>{p.solucion_promedio_min != null ? duracionCorta(p.solucion_promedio_min) : "—"}</TableCell>
                    <TableCell><ChipCumplimiento v={p.cumplimiento} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
      {sel !== null && <Ficha key={sel} id={sel} onEditar={(p) => setDialogo({ p })} onEliminado={() => { setSel(null); refrescar(); }} />}
      <DialogoProveedor abierto={!!dialogo} p={dialogo?.p ?? null} onCerrar={() => setDialogo(null)} onListo={(id) => refrescar(id)} />
    </>
  );
}
