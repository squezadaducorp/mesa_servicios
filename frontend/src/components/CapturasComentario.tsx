import { useEffect, useState } from "react";
import { Box, Chip, Dialog, DialogContent, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import { descargar, obtenerBlob } from "../api/client";
import type { Adjunto } from "../api/types";
import { tamanoArchivo } from "../utils/formato";

export const esImagen = (mime: string, nombre = "") => /^image\/(png|jpe?g|gif)$/.test(mime) || /\.(png|jpe?g|gif)$/i.test(nombre);

/** Nombre legible para una imagen pegada con Ctrl+V (el portapapeles la entrega como «image.png»). */
export function nombrarCaptura(f: File, n: number): File {
  const ext = (f.type.split("/")[1] || "png").replace("jpeg", "jpg");
  const d = new Date();
  const p = (x: number) => String(x).padStart(2, "0");
  const nombre = `captura-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}${n ? `-${n + 1}` : ""}.${ext}`;
  return new File([f], nombre, { type: f.type || "image/png" });
}

/** Imágenes que vienen en un evento de pegado o arrastre. */
export function imagenesDe(dt: DataTransfer | null): File[] {
  return Array.from(dt?.files ?? []).filter((f) => f.type.startsWith("image/"));
}

function useUrlObjeto(fuente: Blob | (() => Promise<Blob>) | null) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    let vivo = true;
    let creada: string | undefined;
    if (!fuente) return;
    Promise.resolve(typeof fuente === "function" ? fuente() : fuente)
      .then((b) => {
        if (!vivo) return;
        creada = URL.createObjectURL(b);
        setUrl(creada);
      })
      .catch(() => undefined);
    return () => {
      vivo = false;
      if (creada) URL.revokeObjectURL(creada);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fuente]);
  return url;
}

function Miniatura({ url, nombre, onAbrir, alto = 120 }: { url?: string; nombre: string; onAbrir?: () => void; alto?: number }) {
  return (
    <Tooltip title={nombre}>
      <Box
        component="button"
        type="button"
        onClick={onAbrir}
        aria-label={`Ver ${nombre}`}
        sx={{
          p: 0, border: "1px solid #D5DCE6", borderRadius: 1.5, overflow: "hidden", cursor: "zoom-in", bgcolor: "#fff",
          width: alto * 1.5, height: alto, display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        {url ? <img src={url} alt={nombre} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} /> : <Typography variant="caption">Cargando…</Typography>}
      </Box>
    </Tooltip>
  );
}

function Visor({ url, nombre, onCerrar, onDescargar }: { url?: string; nombre: string; onCerrar: () => void; onDescargar?: () => void }) {
  return (
    <Dialog open onClose={onCerrar} maxWidth="xl">
      <Stack direction="row" sx={{ alignItems: "center", px: 2, py: 1, gap: 1 }}>
        <Typography variant="subtitle2" sx={{ flex: 1, wordBreak: "break-all" }}>{nombre}</Typography>
        {onDescargar && <IconButton onClick={onDescargar} aria-label="Descargar"><DownloadIcon /></IconButton>}
        <IconButton onClick={onCerrar} aria-label="Cerrar"><CloseIcon /></IconButton>
      </Stack>
      <DialogContent sx={{ pt: 0 }}>
        {url && <img src={url} alt={nombre} style={{ maxWidth: "100%", maxHeight: "80vh", display: "block", margin: "0 auto" }} />}
      </DialogContent>
    </Dialog>
  );
}

function CapturaGuardada({ ticketId, a }: { ticketId: number; a: Adjunto }) {
  const [fuente] = useState(() => () => obtenerBlob(`/tickets/${ticketId}/adjuntos/${a.id}`, { vista: true }));
  const url = useUrlObjeto(fuente);
  const [abierta, setAbierta] = useState(false);
  const bajar = () => descargar(`/tickets/${ticketId}/adjuntos/${a.id}`, undefined, a.nombre_original).catch(() => undefined);
  return (
    <>
      <Miniatura url={url} nombre={a.nombre_original} onAbrir={() => setAbierta(true)} />
      {abierta && <Visor url={url} nombre={a.nombre_original} onCerrar={() => setAbierta(false)} onDescargar={bajar} />}
    </>
  );
}

/** Capturas y archivos que vienen dentro de un comentario ya enviado. */
export function AdjuntosDeComentario({ ticketId, adjuntos }: { ticketId: number; adjuntos?: Adjunto[] }) {
  if (!adjuntos?.length) return null;
  const imagenes = adjuntos.filter((a) => esImagen(a.tipo_mime, a.nombre_original));
  const otros = adjuntos.filter((a) => !esImagen(a.tipo_mime, a.nombre_original));
  return (
    <Box sx={{ mt: 1 }}>
      {imagenes.length > 0 && (
        <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
          {imagenes.map((a) => <CapturaGuardada key={a.id} ticketId={ticketId} a={a} />)}
        </Stack>
      )}
      {otros.length > 0 && (
        <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1, mt: imagenes.length ? 1 : 0 }}>
          {otros.map((a) => (
            <Chip key={a.id} size="small" icon={<InsertDriveFileIcon />} variant="outlined" clickable
              label={`${a.nombre_original} · ${tamanoArchivo(a.tamano_bytes)}`}
              onClick={() => descargar(`/tickets/${ticketId}/adjuntos/${a.id}`, undefined, a.nombre_original).catch(() => undefined)} />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function PorEnviar({ f, onQuitar }: { f: File; onQuitar: () => void }) {
  const url = useUrlObjeto(esImagen(f.type, f.name) ? f : null);
  const [abierta, setAbierta] = useState(false);
  if (!esImagen(f.type, f.name)) {
    return <Chip icon={<InsertDriveFileIcon />} label={`${f.name} · ${tamanoArchivo(f.size)}`} onDelete={onQuitar} variant="outlined" />;
  }
  return (
    <Box sx={{ position: "relative" }}>
      <Miniatura url={url} nombre={f.name} alto={80} onAbrir={() => setAbierta(true)} />
      <IconButton size="small" onClick={onQuitar} aria-label={`Quitar ${f.name}`}
        sx={{ position: "absolute", top: -10, right: -10, bgcolor: "#fff", border: "1px solid #D5DCE6", "&:hover": { bgcolor: "#F5F8FC" } }}>
        <CloseIcon fontSize="small" />
      </IconButton>
      {abierta && <Visor url={url} nombre={f.name} onCerrar={() => setAbierta(false)} />}
    </Box>
  );
}

/** Capturas y archivos elegidos para el comentario que se está escribiendo. */
export function ArchivosPorEnviar({ archivos, onQuitar }: { archivos: File[]; onQuitar: (i: number) => void }) {
  if (!archivos.length) return null;
  return (
    <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1.5, mt: 1.5, alignItems: "center" }}>
      {archivos.map((f, i) => <PorEnviar key={`${f.name}-${i}-${f.size}`} f={f} onQuitar={() => onQuitar(i)} />)}
    </Stack>
  );
}
