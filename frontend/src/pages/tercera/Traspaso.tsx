import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert, Avatar, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Grid, MenuItem, Radio,
  Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { Stack } from "../../components/Pila";
import ArrowIcon from "@mui/icons-material/ArrowForward";
import { post } from "../../api/client";
import { useCatalogos } from "../../api/hooks";
import type { UsuarioAdmin } from "../../api/types";
import type { PlanTraspaso } from "../../api/tercera";
import { mensajeError, useAviso } from "../../components/Aviso";
import { EstadoChip } from "../../components/Chips";
import { Cargando } from "../../components/Comunes";
import { fechaHora } from "../../utils/formato";
import { marca } from "../../theme";

type Modo = "UNO" | "EQUILIBRADO" | "COLA";
const MODOS: [Modo, string, string][] = [
  ["UNO", "Todo a una persona", "Todos los tickets abiertos pasan a un solo analista."],
  ["EQUILIBRADO", "Equilibrado entre varios", "Iguala la carga de los analistas elegidos y respeta la categoría de cada uno."],
  ["COLA", "Devolver a la cola", "Los toma la asignación automática (nunca vuelven a quien se va)."],
];

function iniciales(n: string) {
  return n.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

/** Traspasar la cartera de un analista que se va o cambia de área (mejora 23). */
export default function DialogoTraspaso({ usuario, todos, onCerrar }: { usuario: UsuarioAdmin; todos: UsuarioAdmin[]; onCerrar: (hecho?: boolean) => void }) {
  const avisar = useAviso();
  const cat = useCatalogos();
  const [modo, setModo] = useState<Modo>("EQUILIBRADO");
  const [destinos, setDestinos] = useState<number[]>([]);
  const [asignaciones, setAsignaciones] = useState<Record<number, number>>({});
  const [recurrentes, setRecurrentes] = useState(true);
  const [recurrentesA, setRecurrentesA] = useState<number | "">("");
  const [aprobaciones, setAprobaciones] = useState(true);
  const [aprobacionesA, setAprobacionesA] = useState<number | "">("");
  const [desactivar, setDesactivar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [avisarSol, setAvisarSol] = useState(true);
  const candidatos = (cat.data?.responsables ?? []).filter((r) => r.id !== usuario.id);
  const activos = todos.filter((u) => u.activo && u.id !== usuario.id);
  const cuerpo = {
    modo, destinos: modo === "COLA" ? [] : modo === "UNO" ? destinos.slice(0, 1) : destinos, asignaciones,
    recurrentes_a_id: recurrentesA || null, traspasar_recurrentes: recurrentes, aprobaciones_a_id: aprobacionesA || null,
    traspasar_aprobaciones: aprobaciones, desactivar, motivo: motivo.trim() || "Vista previa", avisar: avisarSol,
  };
  const plan = useQuery({
    queryKey: ["traspaso", usuario.id, modo, cuerpo.destinos, asignaciones],
    queryFn: () => post<PlanTraspaso>(`/admin/usuarios/${usuario.id}/traspaso/vista-previa`, cuerpo),
    enabled: modo === "COLA" || cuerpo.destinos.length > 0,
    retry: false,
  });
  const inicial = useQuery({
    queryKey: ["traspaso", usuario.id, "inicial"],
    queryFn: () => post<PlanTraspaso>(`/admin/usuarios/${usuario.id}/traspaso/vista-previa`, { ...cuerpo, modo: "COLA", destinos: [] }),
    retry: false,
  });
  useEffect(() => {
    if (modo === "UNO" && destinos.length > 1) setDestinos(destinos.slice(0, 1));
  }, [modo, destinos]);
  const traspasar = useMutation({
    mutationFn: () => post<{ tickets: number; en_cola: number; recurrentes: number; aprobaciones: number }>(`/admin/usuarios/${usuario.id}/traspaso`, cuerpo),
    onSuccess: (r) => {
      avisar(`Traspaso hecho: ${r.tickets} tickets reasignados${r.en_cola ? `, ${r.en_cola} a la cola` : ""}${r.recurrentes ? `, ${r.recurrentes} recurrentes` : ""}${r.aprobaciones ? `, ${r.aprobaciones} aprobaciones` : ""}`);
      onCerrar(true);
    },
  });
  const info = plan.data ?? inicial.data;
  const maxCarga = Math.max(1, ...(plan.data?.destinos ?? []).map((d) => d.tiene + d.recibe));
  const alternar = (id: number) => setDestinos((d) => (modo === "UNO" ? [id] : d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));

  return (
    <Dialog open onClose={() => onCerrar()} maxWidth="lg" fullWidth>
      <DialogTitle>Traspasar tickets de {usuario.nombre}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Para cuando alguien deja la empresa o cambia de área. (El modo ausente sigue siendo para vacaciones: solo desvía los tickets nuevos.)
        </Typography>
        {!info && inicial.isLoading ? <Cargando alto={160} /> : inicial.error ? <Alert severity="error">{mensajeError(inicial.error)}</Alert> : (
          <Grid container spacing={2.5}>
            <Grid size={{ xs: 12, md: 7.4 }}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flex: 1, p: 1.5, borderRadius: 2, bgcolor: "#FDF1F1", border: "1px solid #F3C9C9" }}>
                  <Avatar sx={{ bgcolor: "#C62828" }}>{iniciales(usuario.nombre)}</Avatar>
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{usuario.nombre}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {info?.origen.abiertos ?? 0} tickets abiertos · {info?.recurrentes ?? 0} recurrentes · {info?.aprobaciones ?? 0} aprobaciones
                    </Typography>
                  </Box>
                </Stack>
                <ArrowIcon sx={{ color: "text.secondary", display: { xs: "none", sm: "block" } }} />
                <Box sx={{ flex: 1 }}>
                  {MODOS.map(([k, t, d]) => (
                    <Stack key={k} direction="row" spacing={1} onClick={() => setModo(k)}
                      sx={{ mb: 0.8, p: 1, borderRadius: 2, cursor: "pointer", ...(modo === k ? { bgcolor: "#F2F7FC", border: `1px solid ${marca.celeste}` } : { border: "1px solid #EEF1F6" }) }}>
                      <Radio checked={modo === k} size="small" sx={{ p: 0.3 }} />
                      <Box><Typography variant="body2" sx={{ fontWeight: 600 }}>{t}</Typography><Typography variant="caption" color="text.secondary">{d}</Typography></Box>
                    </Stack>
                  ))}
                </Box>
              </Stack>

              {modo !== "COLA" && (
                <>
                  <Typography variant="subtitle2" sx={{ mt: 2.5, mb: 1 }}>{modo === "UNO" ? "¿A quién?" : "Entre quiénes repartir"}</Typography>
                  <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                    {candidatos.map((c) => (
                      <Chip key={c.id} label={c.nombre} onClick={() => alternar(c.id)} color={destinos.includes(c.id) ? "primary" : "default"}
                        variant={destinos.includes(c.id) ? "filled" : "outlined"} />
                    ))}
                  </Stack>
                </>
              )}

              {plan.error && <Alert severity="warning" sx={{ mt: 2 }}>{mensajeError(plan.error)}</Alert>}
              {plan.data && plan.data.destinos.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ mt: 2.5, mb: 1 }}>Vista previa del reparto</Typography>
                  <Table size="small">
                    <TableHead><TableRow><TableCell>Analista</TableCell><TableCell align="center">Tiene hoy</TableCell><TableCell align="center">Recibe</TableCell><TableCell>Carga después</TableCell></TableRow></TableHead>
                    <TableBody>
                      {plan.data.destinos.map((d) => (
                        <TableRow key={d.id}>
                          <TableCell>
                            <Stack direction="row" spacing={1} alignItems="center">
                              <Avatar sx={{ width: 26, height: 26, fontSize: 11, bgcolor: marca.azul }}>{iniciales(d.nombre)}</Avatar>
                              <Typography variant="body2">{d.nombre}</Typography>
                            </Stack>
                          </TableCell>
                          <TableCell align="center">{d.tiene}</TableCell>
                          <TableCell align="center"><Chip size="small" label={`+${d.recibe}`} color="primary" /></TableCell>
                          <TableCell>
                            <Box sx={{ width: 180, height: 10, borderRadius: 5, bgcolor: "#E3E8F0", display: "flex", overflow: "hidden" }}>
                              <Box sx={{ width: `${(d.tiene / maxCarga) * 100}%`, bgcolor: marca.celeste }} />
                              <Box sx={{ width: `${(d.recibe / maxCarga) * 100}%`, bgcolor: marca.azul }} />
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}
              {plan.data && plan.data.tickets.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ mt: 2.5, mb: 1 }}>Ticket por ticket (puede cambiar el destino de cualquiera)</Typography>
                  <Box sx={{ maxHeight: 260, overflow: "auto", border: "1px solid #EEF1F6", borderRadius: 2 }}>
                    <Table size="small" stickyHeader>
                      <TableHead><TableRow><TableCell>Ticket</TableCell><TableCell>Vence</TableCell><TableCell>Pasa a</TableCell></TableRow></TableHead>
                      <TableBody>
                        {plan.data.tickets.map((t) => (
                          <TableRow key={t.id}>
                            <TableCell>
                              <Typography variant="body2" sx={{ fontWeight: 700, color: marca.azul }}>{t.numero}</Typography>
                              <Typography variant="caption" color="text.secondary">{t.asunto} · {t.categoria}</Typography>
                            </TableCell>
                            <TableCell sx={{ whiteSpace: "nowrap" }}><EstadoChip estado={t.estado} /><Typography variant="caption" sx={{ display: "block" }}>{fechaHora(t.vence)}</Typography></TableCell>
                            <TableCell>
                              {modo === "COLA" || plan.data!.destinos.length < 2 ? t.destino : (
                                <TextField select size="small" value={t.destino_id ?? ""} onChange={(e) => setAsignaciones({ ...asignaciones, [t.id]: Number(e.target.value) })}>
                                  {plan.data!.destinos.map((d) => <MenuItem key={d.id} value={d.id}>{d.nombre}</MenuItem>)}
                                </TextField>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                </>
              )}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                El tiempo de SLA no se reinicia: cada ticket conserva su vencimiento. Cada cambio queda en el historial y en Auditoría con el motivo.
              </Typography>
            </Grid>
            <Grid size={{ xs: 12, md: 4.6 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>También traspasar</Typography>
              <FormControlLabel control={<Checkbox size="small" checked={recurrentes} onChange={(e) => setRecurrentes(e.target.checked)} />}
                label={<Typography variant="body2">Tickets recurrentes a su cargo ({info?.recurrentes ?? 0})</Typography>} />
              {recurrentes && (info?.recurrentes ?? 0) > 0 && (
                <TextField select fullWidth size="small" label="Pasan a" value={recurrentesA} onChange={(e) => setRecurrentesA(e.target.value ? Number(e.target.value) : "")} sx={{ mb: 1 }}>
                  <MenuItem value="">Asignación automática</MenuItem>
                  {candidatos.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
              )}
              <FormControlLabel control={<Checkbox size="small" checked={aprobaciones} onChange={(e) => setAprobaciones(e.target.checked)} />}
                label={<Typography variant="body2">Aprobaciones pendientes como jefe ({info?.aprobaciones ?? 0})</Typography>} />
              {aprobaciones && (info?.aprobaciones ?? 0) > 0 && (
                <TextField select fullWidth size="small" label="Pasan a" value={aprobacionesA} onChange={(e) => setAprobacionesA(e.target.value ? Number(e.target.value) : "")} sx={{ mb: 1 }}>
                  <MenuItem value="">{info?.jefe ? `Su jefe directo (${info.jefe.nombre})` : "Su jefe directo (no tiene: elija a alguien)"}</MenuItem>
                  {activos.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}</MenuItem>)}
                </TextField>
              )}
              <FormControlLabel control={<Checkbox size="small" checked={desactivar} onChange={(e) => setDesactivar(e.target.checked)} />}
                label={<Typography variant="body2">Desactivar el usuario al terminar</Typography>} />
              <Divider sx={{ my: 2 }} />
              <TextField fullWidth label="Motivo" placeholder="Renuncia, último día 20/11/2026" value={motivo} onChange={(e) => setMotivo(e.target.value)} sx={{ mb: 1.5 }} />
              <FormControlLabel control={<Switch checked={avisarSol} onChange={(e) => setAvisarSol(e.target.checked)} />}
                label={<Typography variant="body2">Avisar a cada solicitante quién lo atiende ahora</Typography>} />
              {traspasar.error && <Alert severity="error" sx={{ mt: 1.5 }}>{mensajeError(traspasar.error)}</Alert>}
            </Grid>
          </Grid>
        )}
      </DialogContent>
      <DialogActions>
        <Button color="inherit" onClick={() => onCerrar()}>Cancelar</Button>
        <Button variant="contained" disabled={traspasar.isPending || motivo.trim().length < 5 || (modo !== "COLA" && !destinos.length) || !!plan.error}
          onClick={() => traspasar.mutate()}>
          Traspasar {info?.origen.abiertos ?? 0} tickets
        </Button>
      </DialogActions>
    </Dialog>
  );
}
