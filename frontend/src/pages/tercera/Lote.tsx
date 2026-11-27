import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, TextField, Typography } from "@mui/material";
import { Stack } from "../../components/Pila";
import CloseIcon from "@mui/icons-material/Close";
import PersonAddIcon from "@mui/icons-material/PersonAddAlt";
import FlagIcon from "@mui/icons-material/Flag";
import SwapIcon from "@mui/icons-material/SwapHoriz";
import NoteIcon from "@mui/icons-material/NoteAddOutlined";
import MergeIcon from "@mui/icons-material/MergeType";
import LowPriorityIcon from "@mui/icons-material/LowPriority";
import { post } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { TicketListado } from "../../api/types";
import type { LoteResultado } from "../../api/tercera";
import { mensajeError } from "../../components/Aviso";
import { NOMBRE_ESTADO } from "../../components/Chips";
import { marca } from "../../theme";
import { UnirDialogo } from "./TicketTercera";

type Accion = "REASIGNAR" | "PRIORIDAD" | "ESTADO" | "CATEGORIA" | "NOTA";
const TITULO: Record<Accion, string> = { REASIGNAR: "Reasignar", PRIORIDAD: "Cambiar prioridad", ESTADO: "Cambiar estado", CATEGORIA: "Cambiar categoría", NOTA: "Agregar nota interna" };
const ESTADOS = ["EN_PROCESO", "PENDIENTE_CLIENTE", "RESUELTO", "CERRADO", "CANCELADO"];

function DialogoLote({ accion, tickets, onCerrar }: { accion: Accion; tickets: TicketListado[]; onCerrar: (hecho?: boolean) => void }) {
  const cat = useCatalogos();
  const [f, setF] = useState({ responsable_id: "" as number | "", prioridad_id: "" as number | "", estado: "", categoria_id: "" as number | "", subcategoria_id: "" as number | "", texto: "", motivo: "" });
  const [resultado, setResultado] = useState<LoteResultado | null>(null);
  const aplicar = useMutation({
    mutationFn: () => post<LoteResultado>("/tickets/lote", {
      ids: tickets.map((t) => t.id), accion, responsable_id: f.responsable_id || null, prioridad_id: f.prioridad_id || null, estado: f.estado || null,
      categoria_id: f.categoria_id || null, subcategoria_id: f.subcategoria_id || null, texto: f.texto.trim() || null, motivo: f.motivo.trim() || null,
    }),
    onSuccess: setResultado,
  });
  const categoria = cat.data?.categorias.find((c) => c.id === f.categoria_id);
  const listo =
    (accion === "REASIGNAR" && f.responsable_id) || (accion === "PRIORIDAD" && f.prioridad_id) ||
    (accion === "ESTADO" && f.estado && f.texto.trim().length >= 5) ||
    (accion === "CATEGORIA" && f.subcategoria_id) || (accion === "NOTA" && f.texto.trim().length >= 2);
  return (
    <Dialog open onClose={() => onCerrar(!!resultado)} maxWidth="sm" fullWidth>
      <DialogTitle>{TITULO[accion]} · {tickets.length} tickets</DialogTitle>
      <DialogContent>
        {resultado ? (
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {resultado.ok.length > 0 && <Alert severity="success">Listo en {resultado.ok.length}: {resultado.ok.join(", ")}</Alert>}
            {resultado.sin_cambio.length > 0 && <Alert severity="info">Ya estaban así ({resultado.sin_cambio.length}): {resultado.sin_cambio.join(", ")}</Alert>}
            {resultado.errores.length > 0 && (
              <Alert severity="warning">
                No se pudieron cambiar {resultado.errores.length}:
                {resultado.errores.map((e) => <Box key={e.numero}><b>{e.numero}</b>: {e.error}</Box>)}
              </Alert>
            )}
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {aplicar.error && <Alert severity="error">{mensajeError(aplicar.error)}</Alert>}
            {accion === "REASIGNAR" && (
              <>
                <TextField select label="Nuevo responsable" value={f.responsable_id} onChange={(e) => setF({ ...f, responsable_id: Number(e.target.value) })}>
                  {(cat.data?.responsables ?? []).map((r) => <MenuItem key={r.id} value={r.id}>{r.nombre}</MenuItem>)}
                </TextField>
                <TextField label="Motivo (opcional)" value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} />
              </>
            )}
            {accion === "PRIORIDAD" && (
              <TextField select label="Prioridad" value={f.prioridad_id} onChange={(e) => setF({ ...f, prioridad_id: Number(e.target.value) })}
                helperText="El vencimiento del SLA se recalcula con la nueva prioridad, sin reiniciar lo ya transcurrido.">
                {(cat.data?.prioridades ?? []).map((p) => <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>)}
              </TextField>
            )}
            {accion === "ESTADO" && (
              <>
                <TextField select label="Nuevo estado" value={f.estado} onChange={(e) => setF({ ...f, estado: e.target.value })}>
                  {ESTADOS.map((e) => <MenuItem key={e} value={e}>{NOMBRE_ESTADO[e]}</MenuItem>)}
                </TextField>
                <TextField label="Motivo del cambio (obligatorio)" multiline minRows={2} required value={f.texto} onChange={(e) => setF({ ...f, texto: e.target.value })}
                  helperText="En Pendiente cliente, Resuelto, Cerrado y Cancelado lo ve el solicitante; en En proceso queda como nota interna." />
              </>
            )}
            {accion === "CATEGORIA" && (
              <Stack direction="row" spacing={1.5}>
                <TextField select fullWidth label="Categoría" value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: Number(e.target.value), subcategoria_id: "" })}>
                  {(cat.data?.categorias ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
                <TextField select fullWidth label="Subcategoría" value={f.subcategoria_id} disabled={!categoria} onChange={(e) => setF({ ...f, subcategoria_id: Number(e.target.value) })}>
                  {(categoria?.subcategorias ?? []).filter((s) => s.activo).map((s) => <MenuItem key={s.id} value={s.id}>{s.nombre}</MenuItem>)}
                </TextField>
              </Stack>
            )}
            {accion === "NOTA" && (
              <TextField label="Nota interna (solo la ve el equipo)" multiline minRows={3} value={f.texto} onChange={(e) => setF({ ...f, texto: e.target.value })} />
            )}
            <Typography variant="caption" color="text.secondary">
              Cada ticket pasa por las mismas reglas y permisos que si lo cambiara uno por uno. Los que no se puedan cambiar se informan sin detener el resto.
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {resultado ? <Button variant="contained" onClick={() => onCerrar(true)}>Cerrar</Button> : (
          <>
            <Button color="inherit" onClick={() => onCerrar()}>Cancelar</Button>
            <Button variant="contained" disabled={!listo || aplicar.isPending} onClick={() => aplicar.mutate()}>Aplicar a {tickets.length}</Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}

/** Barra que aparece al seleccionar tickets en la lista. */
export function BarraLote({ seleccion, onLimpiar, onListo }: { seleccion: TicketListado[]; onLimpiar: () => void; onListo: (principalId?: number) => void }) {
  const [accion, setAccion] = useState<Accion | "UNIR" | null>(null);
  if (!seleccion.length) return null;
  const botones: [Accion | "UNIR", string, React.ReactNode][] = [
    ["REASIGNAR", "Reasignar", <PersonAddIcon key="r" />],
    ["PRIORIDAD", "Prioridad", <FlagIcon key="p" />],
    ["ESTADO", "Estado", <SwapIcon key="e" />],
    ["CATEGORIA", "Categoría", <LowPriorityIcon key="c" />],
    ["NOTA", "Nota interna", <NoteIcon key="n" />],
    ["UNIR", "Unir", <MergeIcon key="u" />],
  ];
  return (
    <>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap
        sx={{ bgcolor: marca.navy, color: "#fff", borderRadius: 2, px: 2, py: 1.1, mb: 2, flexWrap: "wrap", position: "sticky", top: 72, zIndex: 3 }}>
        <IconButton size="small" sx={{ color: "#fff" }} onClick={onLimpiar} aria-label="Quitar selección"><CloseIcon fontSize="small" /></IconButton>
        <Typography sx={{ fontWeight: 700, mr: 1 }}>{seleccion.length} seleccionado{seleccion.length === 1 ? "" : "s"}</Typography>
        <Box sx={{ flex: 1 }} />
        {botones.map(([k, t, i]) => (
          <Button key={k} startIcon={i} sx={{ color: "#fff" }} disabled={k === "UNIR" && seleccion.length < 2} onClick={() => setAccion(k)}>{t}</Button>
        ))}
      </Stack>
      {accion && accion !== "UNIR" && (
        <DialogoLote accion={accion} tickets={seleccion} onCerrar={(hecho) => { setAccion(null); if (hecho) onListo(); }} />
      )}
      {accion === "UNIR" && (
        <UnirDialogo
          tickets={seleccion.map((t) => ({ id: t.id, numero: t.numero, asunto: t.asunto, estado: t.estado, estado_nombre: t.estado_nombre, solicitante: t.solicitante_nombre, fecha_creacion: t.fecha_creacion }))}
          principalInicial={[...seleccion].sort((a, b) => a.fecha_creacion.localeCompare(b.fecha_creacion))[0].id}
          onCerrar={(pid) => { setAccion(null); if (pid) onListo(pid); }}
        />
      )}
    </>
  );
}
