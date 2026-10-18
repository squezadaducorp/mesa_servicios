import { useState } from "react";
import {
  Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem, Stack, TextField,
} from "@mui/material";
import { useCatalogos } from "../api/hooks";
import type { TicketDetalle } from "../api/types";
import { NOMBRE_ESTADO } from "../components/Chips";

export type Dialogo = "estado" | "asignar" | "escalar" | "cerrar" | "reabrir" | "editar" | "excepcion" | "eliminar" | null;

export interface Ejecutar {
  (dialogo: Exclude<Dialogo, null>, datos: Record<string, unknown>): Promise<void>;
}

const TRANSICIONES: Record<string, string[]> = {
  NUEVO: ["ASIGNADO", "EN_PROCESO", "CANCELADO"],
  ASIGNADO: ["EN_PROCESO", "PENDIENTE_CLIENTE", "RESUELTO", "CANCELADO"],
  EN_PROCESO: ["PENDIENTE_CLIENTE", "RESUELTO", "CANCELADO"],
  PENDIENTE_CLIENTE: ["EN_PROCESO", "RESUELTO", "CANCELADO"],
  ESCALADO: ["ASIGNADO", "EN_PROCESO", "PENDIENTE_CLIENTE", "RESUELTO", "CANCELADO"],
};
export const estadosDestino = (estado: string) => TRANSICIONES[estado] ?? [];
const REQUIERE_COMENTARIO = ["PENDIENTE_CLIENTE", "CANCELADO"];

interface Props {
  ticket: TicketDetalle;
  abierto: Dialogo;
  estadoInicial?: string;
  onCerrar: () => void;
  ejecutar: Ejecutar;
}

export default function TicketDialogos({ ticket, abierto, estadoInicial, onCerrar, ejecutar }: Props) {
  const cat = useCatalogos();
  const [valores, setValores] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const v = (k: string, porDefecto = "") => valores[k] ?? porDefecto;
  const set = (k: string) => (e: { target: { value: string } }) => setValores((x) => ({ ...x, [k]: e.target.value }));
  const cerrar = () => {
    setValores({});
    onCerrar();
  };
  const enviar = async (dialogo: Exclude<Dialogo, null>, datos: Record<string, unknown>) => {
    setEnviando(true);
    try {
      await ejecutar(dialogo, datos);
      setValores({});
      onCerrar();
    } catch {
      /* el error se muestra con un aviso; el diálogo sigue abierto */
    } finally {
      setEnviando(false);
    }
  };

  const categoria = cat.data?.categorias.find((c) => c.id === ticket.categoria.id);
  const estado = v("estado", estadoInicial ?? estadosDestino(ticket.estado)[0] ?? "");
  const catEdit = cat.data?.categorias.find((c) => c.id === Number(v("categoria_id", String(ticket.categoria.id))));

  return (
    <>
      <Dialog open={abierto === "estado"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>Cambiar estado</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="Nuevo estado" value={estado} onChange={set("estado")}>
              {estadosDestino(ticket.estado).map((e) => (
                <MenuItem key={e} value={e}>
                  {NOMBRE_ESTADO[e]}
                </MenuItem>
              ))}
            </TextField>
            {estado === "PENDIENTE_CLIENTE" && (
              <DialogContentText variant="body2">El SLA se pausa hasta que el solicitante responda; se reanuda automáticamente con su comentario.</DialogContentText>
            )}
            <TextField
              label={REQUIERE_COMENTARIO.includes(estado) ? "Comentario para el solicitante (obligatorio)" : "Comentario (opcional)"}
              value={v("comentario")}
              onChange={set("comentario")}
              multiline
              minRows={3}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={enviando || !estado || (REQUIERE_COMENTARIO.includes(estado) && !v("comentario").trim())}
            onClick={() => enviar("estado", { estado, comentario: v("comentario") || null })}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "asignar"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>{ticket.responsable ? "Reasignar ticket" : "Asignar ticket"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="Responsable" value={v("responsable_id", String(ticket.responsable?.id ?? ""))} onChange={set("responsable_id")}>
              {(categoria?.responsables ?? []).map((r) => (
                <MenuItem key={r.usuario_id} value={String(r.usuario_id)}>
                  {r.nombre} {r.es_principal ? "(principal)" : ""}
                </MenuItem>
              ))}
              <MenuItem disabled>──────────</MenuItem>
              {(cat.data?.responsables ?? [])
                .filter((r) => !categoria?.responsables.some((x) => x.usuario_id === r.id))
                .map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>
                    {r.nombre}
                  </MenuItem>
                ))}
            </TextField>
            <TextField label="Motivo" value={v("motivo")} onChange={set("motivo")} multiline minRows={2} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={enviando || !v("responsable_id", String(ticket.responsable?.id ?? ""))}
            onClick={() => enviar("asignar", { responsable_id: Number(v("responsable_id", String(ticket.responsable?.id ?? ""))), motivo: v("motivo") || null })}
          >
            Asignar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "escalar"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>Escalar ticket</DialogTitle>
        <DialogContent>
          <DialogContentText variant="body2" sx={{ mb: 2 }}>
            Se notificará al supervisor de {ticket.categoria.nombre}
            {categoria?.supervisor ? ` (${categoria.supervisor.nombre})` : ""} y a la coordinación de la mesa.
          </DialogContentText>
          <TextField label="Motivo del escalamiento" value={v("motivo")} onChange={set("motivo")} multiline minRows={3} fullWidth required />
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button variant="contained" color="warning" disabled={enviando || v("motivo").trim().length < 5} onClick={() => enviar("escalar", { motivo: v("motivo") })}>
            Escalar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "cerrar"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>Cerrar ticket</DialogTitle>
        <DialogContent>
          <TextField label="Comentario de cierre (opcional)" value={v("comentario")} onChange={set("comentario")} multiline minRows={3} fullWidth sx={{ mt: 1 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button variant="contained" color="success" disabled={enviando} onClick={() => enviar("cerrar", { comentario: v("comentario") || null })}>
            Cerrar ticket
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "reabrir"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>Reabrir ticket</DialogTitle>
        <DialogContent>
          <DialogContentText variant="body2" sx={{ mb: 2 }}>
            El SLA continúa desde el tiempo ya consumido.
          </DialogContentText>
          <TextField label="Motivo de la reapertura" value={v("motivo")} onChange={set("motivo")} multiline minRows={3} fullWidth required />
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button variant="contained" disabled={enviando || v("motivo").trim().length < 5} onClick={() => enviar("reabrir", { motivo: v("motivo") })}>
            Reabrir
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "editar"} onClose={cerrar} fullWidth maxWidth="md">
        <DialogTitle>Editar ticket</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Asunto" value={v("asunto", ticket.asunto)} onChange={set("asunto")} />
            <TextField label="Descripción" value={v("descripcion", ticket.descripcion)} onChange={set("descripcion")} multiline minRows={4} />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                select
                fullWidth
                label="Categoría"
                value={v("categoria_id", String(ticket.categoria.id))}
                onChange={(e) => setValores((x) => ({ ...x, categoria_id: e.target.value, subcategoria_id: "" }))}
              >
                {(cat.data?.categorias ?? []).map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select fullWidth label="Subcategoría" value={v("subcategoria_id", String(ticket.subcategoria.id))} onChange={set("subcategoria_id")}>
                {(catEdit?.subcategorias ?? []).map((s) => (
                  <MenuItem key={s.id} value={String(s.id)}>
                    {s.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField select fullWidth label="Prioridad" value={v("prioridad_id", String(ticket.prioridad.id))} onChange={set("prioridad_id")} helperText="Cambiar la prioridad recalcula el SLA">
                {(cat.data?.prioridades ?? []).map((p) => (
                  <MenuItem key={p.id} value={String(p.id)}>
                    {p.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select fullWidth label="Cliente" value={v("cliente_id", String(ticket.cliente?.id ?? ""))} onChange={set("cliente_id")}>
                <MenuItem value="">Sin cliente</MenuItem>
                {(cat.data?.clientes ?? []).map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.razon_social}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField fullWidth label="Correo" value={v("correo", ticket.correo)} onChange={set("correo")} />
              <TextField fullWidth label="Teléfono" value={v("telefono", ticket.telefono ?? "")} onChange={set("telefono")} />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={enviando || !v("subcategoria_id", String(ticket.subcategoria.id))}
            onClick={() => {
              const datos: Record<string, unknown> = { version: ticket.version };
              for (const [k, val] of Object.entries(valores)) {
                datos[k] = k.endsWith("_id") ? (val ? Number(val) : null) : val || null;
              }
              enviar("editar", datos);
            }}
          >
            Guardar cambios
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "excepcion"} onClose={cerrar} fullWidth maxWidth="sm">
        <DialogTitle>Excepción de SLA</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="Tipo" value={v("tipo", "EXTENSION")} onChange={set("tipo")}>
              <MenuItem value="EXTENSION">Extensión de plazo (minutos laborables)</MenuItem>
              <MenuItem value="EXCLUSION">Excluir del indicador de cumplimiento</MenuItem>
            </TextField>
            {v("tipo", "EXTENSION") === "EXTENSION" && (
              <TextField type="number" label="Minutos adicionales" value={v("minutos", "60")} onChange={set("minutos")} slotProps={{ htmlInput: { min: 1 } }} />
            )}
            <TextField label="Motivo" value={v("motivo")} onChange={set("motivo")} multiline minRows={3} required />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={enviando || v("motivo").trim().length < 5}
            onClick={() =>
              enviar("excepcion", {
                tipo: v("tipo", "EXTENSION"),
                minutos: v("tipo", "EXTENSION") === "EXTENSION" ? Number(v("minutos", "60")) : null,
                motivo: v("motivo"),
              })
            }
          >
            Registrar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={abierto === "eliminar"} onClose={cerrar}>
        <DialogTitle>¿Eliminar el ticket {ticket.numero}?</DialogTitle>
        <DialogContent>
          <DialogContentText>El ticket dejará de mostrarse. La eliminación es lógica y queda registrada en la auditoría.</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={enviando} onClick={() => enviar("eliminar", {})}>
            Eliminar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
