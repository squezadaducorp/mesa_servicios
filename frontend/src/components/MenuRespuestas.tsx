import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Box, Chip, Divider, InputAdornment, List, ListItemButton, ListItemIcon, ListItemText, Popover, Stack, TextField, Typography } from "@mui/material";
import BoltIcon from "@mui/icons-material/Bolt";
import SearchIcon from "@mui/icons-material/Search";
import { get } from "../api/client";
import type { RespuestaParaTicket } from "../api/types";

const CHIP = { fontFamily: "monospace", bgcolor: "#FFF3D6", color: "#8A5A00" } as const;
const ESTADO: Record<string, string> = { EN_PROCESO: "En Proceso", PENDIENTE_CLIENTE: "Pendiente Cliente", RESUELTO: "Resuelto" };

interface Props {
  ticketId: number;
  categoria: string;
  ancla: HTMLElement | null;
  filtroInicial: string;
  onElegir: (r: RespuestaParaTicket) => void;
  onCerrar: () => void;
}

export function useRespuestasTicket(ticketId: number, habilitado: boolean) {
  return useQuery({
    queryKey: ["respuestas", "ticket", ticketId],
    queryFn: () => get<RespuestaParaTicket[]>(`/respuestas/ticket/${ticketId}`),
    enabled: habilitado,
    staleTime: 60_000,
  });
}

/** Lista de respuestas rápidas: se abre con el botón ⚡ o al escribir «/» en la respuesta. */
export default function MenuRespuestas({ ticketId, categoria, ancla, filtroInicial, onElegir, onCerrar }: Props) {
  const lista = useRespuestasTicket(ticketId, !!ancla);
  const [filtro, setFiltro] = useState(filtroInicial);
  const [sel, setSel] = useState(0);
  const campo = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ancla) {
      setFiltro(filtroInicial);
      setSel(0);
    }
  }, [ancla, filtroInicial]);

  const filas = useMemo(() => {
    const q = filtro.trim().toLowerCase().replace(/^\//, "");
    return (lista.data ?? []).filter((r) => !q || r.atajo.slice(1).startsWith(q) || r.titulo.toLowerCase().includes(q));
  }, [lista.data, filtro]);
  const sugeridas = filas.filter((r) => r.sugerida);
  const otras = filas.filter((r) => !r.sugerida);
  const ordenadas = [...sugeridas, ...otras];

  const item = (r: RespuestaParaTicket) => {
    const i = ordenadas.indexOf(r);
    return (
      <ListItemButton key={r.id} selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => onElegir(r)} sx={{ mx: 1, borderRadius: 2 }}>
        <ListItemIcon sx={{ minWidth: 96 }}><Chip size="small" label={r.atajo} sx={CHIP} /></ListItemIcon>
        <ListItemText
          primary={r.titulo}
          secondary={`${r.alcance === "PERSONAL" ? "Mía" : "Del equipo"} · usada ${r.usos} ${r.usos === 1 ? "vez" : "veces"}${r.estado_destino ? ` · pasa a ${ESTADO[r.estado_destino] ?? r.estado_destino}` : ""}`}
          slotProps={{ primary: { sx: { fontWeight: 600, fontSize: 13.5 } } }}
        />
      </ListItemButton>
    );
  };

  return (
    <Popover
      open={!!ancla}
      anchorEl={ancla}
      onClose={onCerrar}
      anchorOrigin={{ vertical: "top", horizontal: "left" }}
      transformOrigin={{ vertical: "bottom", horizontal: "left" }}
      slotProps={{ paper: { sx: { width: 480, maxWidth: "calc(100vw - 32px)" } }, transition: { onEntered: () => campo.current?.focus() } }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", px: 1.5, pt: 1.2, pb: 0.5 }}>
        <BoltIcon sx={{ color: "#B57400" }} fontSize="small" />
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Respuestas rápidas</Typography>
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" color="text.secondary">↑↓ elegir · Enter insertar</Typography>
      </Stack>
      <Box sx={{ px: 1.5, pb: 1 }}>
        <TextField
          fullWidth
          size="small"
          inputRef={campo}
          value={filtro}
          placeholder="Buscar por atajo o título"
          onChange={(e) => { setFiltro(e.target.value); setSel(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, ordenadas.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter" && ordenadas[sel]) { e.preventDefault(); onElegir(ordenadas[sel]); }
          }}
          slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }}
        />
      </Box>
      <Box sx={{ maxHeight: 320, overflow: "auto" }}>
        {sugeridas.length > 0 && (
          <>
            <Typography variant="caption" sx={{ px: 2, color: "text.secondary", fontWeight: 700, letterSpacing: 0.5 }}>SUGERIDAS PARA «{categoria.toUpperCase()}»</Typography>
            <List dense sx={{ py: 0.5 }}>{sugeridas.map(item)}</List>
          </>
        )}
        {otras.length > 0 && (
          <>
            {sugeridas.length > 0 && <Typography variant="caption" sx={{ px: 2, color: "text.secondary", fontWeight: 700, letterSpacing: 0.5 }}>GENERALES</Typography>}
            <List dense sx={{ py: 0.5 }}>{otras.map(item)}</List>
          </>
        )}
        {!lista.isLoading && ordenadas.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 2 }}>
            {lista.data?.length ? "Ninguna coincide." : "Todavía no hay respuestas rápidas. Créelas en «Respuestas rápidas»."}
          </Typography>
        )}
      </Box>
      <Divider />
      <Box sx={{ px: 2, py: 1.2, bgcolor: "#F8FAFD" }}>
        <Typography variant="caption" color="text.secondary">
          El nombre del solicitante, el número de ticket y su firma ya vienen llenos. Puede editar el texto antes de enviar.
        </Typography>
      </Box>
    </Popover>
  );
}
