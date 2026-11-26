import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Box, Button, CircularProgress, IconButton, Menu, MenuItem, Paper, Stack, Tooltip, Typography,
} from "@mui/material";
import FormatBoldIcon from "@mui/icons-material/FormatBold";
import FormatItalicIcon from "@mui/icons-material/FormatItalic";
import FormatUnderlinedIcon from "@mui/icons-material/FormatUnderlined";
import FormatColorTextIcon from "@mui/icons-material/FormatColorText";
import FormatClearIcon from "@mui/icons-material/FormatClear";
import AddPhotoAlternateIcon from "@mui/icons-material/AddPhotoAlternateOutlined";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import CloseIcon from "@mui/icons-material/Close";
import AddIcon from "@mui/icons-material/Add";
import { api, obtenerBlob } from "../api/client";
import { imagenesDe, nombrarCaptura, useUrlObjeto, Visor } from "./CapturasComentario";
import { mensajeError, useAviso } from "./Aviso";
import { marca } from "../theme";

/*
 * Solución de un artículo como paso a paso. Se guarda como texto:
 *   - una línea por paso;
 *   - formato con [b]negrita[/b], [i]cursiva[/i], [u]subrayado[/u] y [color=#C62828]color[/color];
 *   - imágenes con [imagen:ID] en una línea propia, debajo del paso al que pertenecen.
 * Así los artículos anteriores (texto simple, un paso por línea) se siguen viendo igual.
 */

export interface Paso {
  texto: string;
  imagenes: number[];
}

const MARCA_IMAGEN = /\[imagen:(\d+)\]/g;
const ETIQUETA = /\[(\/?)(b|i|u|color)(?:=(#[0-9a-fA-F]{6}))?\]/g;

export const COLORES = [
  { nombre: "Rojo", valor: "#C62828" },
  { nombre: "Naranja", valor: "#E65100" },
  { nombre: "Verde", valor: "#2E7D32" },
  { nombre: "Azul", valor: "#1367AC" },
  { nombre: "Morado", valor: "#5E35B1" },
  { nombre: "Gris", valor: "#5A6577" },
];

export function parsearPasos(texto: string): Paso[] {
  const pasos: Paso[] = [];
  for (const linea of (texto || "").split("\n")) {
    const imagenes = [...linea.matchAll(MARCA_IMAGEN)].map((m) => Number(m[1]));
    const resto = linea.replace(MARCA_IMAGEN, " ").replace(/^\s*\d+[.)-]\s*/, "").replace(/\s+/g, " ").trim();
    if (!resto && !imagenes.length) continue;
    if (!resto && pasos.length) pasos[pasos.length - 1].imagenes.push(...imagenes);   // imagen debajo del paso anterior
    else pasos.push({ texto: resto, imagenes });
  }
  return pasos;
}

export function serializarPasos(pasos: Paso[]): string {
  return pasos
    .map((p) => [p.texto.replace(/\s*\n\s*/g, " ").trim(), ...p.imagenes.map((id) => `[imagen:${id}]`)].filter(Boolean).join("\n"))
    .filter(Boolean)
    .join("\n");
}

/** Texto con [b] [i] [u] [color=#…]: se arma con elementos de React (nunca HTML), así no hay riesgo de inyección. */
export function TextoConFormato({ texto }: { texto: string }) {
  const partes: ReactNode[] = [];
  const estado = { b: 0, i: 0, u: 0, colores: [] as string[] };
  let ultimo = 0;
  const empujar = (t: string) => {
    if (!t) return;
    const color = estado.colores[estado.colores.length - 1];
    if (!estado.b && !estado.i && !estado.u && !color) {
      partes.push(t);
      return;
    }
    partes.push(
      <span key={partes.length} style={{
        fontWeight: estado.b ? 700 : undefined, fontStyle: estado.i ? "italic" : undefined,
        textDecoration: estado.u ? "underline" : undefined, color,
      }}>{t}</span>,
    );
  };
  for (const m of texto.matchAll(ETIQUETA)) {
    empujar(texto.slice(ultimo, m.index));
    ultimo = (m.index ?? 0) + m[0].length;
    const cierra = m[1] === "/";
    const tag = m[2] as "b" | "i" | "u" | "color";
    if (tag === "color") {
      if (cierra) estado.colores.pop();
      else if (m[3]) estado.colores.push(m[3]);
    } else {
      estado[tag] = Math.max(0, estado[tag] + (cierra ? -1 : 1));
    }
  }
  empujar(texto.slice(ultimo));
  return <>{partes.map((p, i) => <Fragment key={i}>{p}</Fragment>)}</>;
}

const tieneFormato = (t: string) => new RegExp(ETIQUETA.source).test(t);

/** Imagen de un artículo, traída con la sesión (respeta si el artículo es interno o externo). */
export type FuenteImagen = (id: number) => Promise<Blob>;
const fuenteConSesion: FuenteImagen = (id) => obtenerBlob(`/conocimiento/imagenes/${id}`);

export function ImagenArticulo({ id, alto = 360, onQuitar, fuenteImagen = fuenteConSesion }: { id: number; alto?: number; onQuitar?: () => void; fuenteImagen?: FuenteImagen }) {
  const [fuente] = useState(() => () => fuenteImagen(id));
  const url = useUrlObjeto(fuente);
  const [abierta, setAbierta] = useState(false);
  const nombre = `Imagen del paso`;
  return (
    <Box sx={{ position: "relative", display: "inline-block", maxWidth: "100%" }}>
      <Box component="button" type="button" onClick={() => setAbierta(true)} aria-label="Ampliar imagen"
        sx={{ p: 0, border: "1px solid #D5DCE6", borderRadius: 1.5, overflow: "hidden", cursor: "zoom-in", bgcolor: "#fff", display: "block", maxWidth: "100%" }}>
        {url
          ? <img src={url} alt={nombre} style={{ display: "block", maxWidth: "100%", maxHeight: alto, objectFit: "contain" }} />
          : <Box sx={{ width: alto * 1.2, maxWidth: "100%", height: Math.min(alto, 120), display: "flex", alignItems: "center", justifyContent: "center" }}><CircularProgress size={20} /></Box>}
      </Box>
      {onQuitar && (
        <IconButton size="small" onClick={onQuitar} aria-label="Quitar imagen"
          sx={{ position: "absolute", top: -10, right: -10, bgcolor: "#fff", border: "1px solid #D5DCE6", "&:hover": { bgcolor: "#F5F8FC" } }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      )}
      {abierta && <Visor url={url} nombre={nombre} onCerrar={() => setAbierta(false)} />}
    </Box>
  );
}

/** Solución al leer el artículo: pasos numerados con su formato y sus imágenes. */
export function Pasos({ texto, fuenteImagen }: { texto: string; fuenteImagen?: FuenteImagen }) {
  const pasos = parsearPasos(texto);
  if (pasos.length <= 1 && !pasos[0]?.imagenes.length) {
    return <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}><TextoConFormato texto={pasos[0]?.texto ?? texto} /></Typography>;
  }
  return (
    <>
      {pasos.map((p, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ mb: 1.2 }}>
          <Typography variant="body2" sx={{ color: marca.azul, fontWeight: 700, minWidth: 18 }}>{i + 1}.</Typography>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {p.texto && <Typography variant="body2"><TextoConFormato texto={p.texto} /></Typography>}
            {p.imagenes.length > 0 && (
              <Stack sx={{ mt: 1, gap: 1 }}>
                {p.imagenes.map((id) => <Box key={id}><ImagenArticulo id={id} fuenteImagen={fuenteImagen} /></Box>)}
              </Stack>
            )}
          </Box>
        </Stack>
      ))}
    </>
  );
}

let siguienteClave = 1;
type PasoEditable = Paso & { clave: number; subiendo: number };
const editable = (p: Paso): PasoEditable => ({ ...p, clave: siguienteClave++, subiendo: 0 });

/** Editor de la solución: un recuadro por paso, con formato e imágenes (botón, Ctrl+V o arrastrar). */
export function EditorPasos({ valor, onCambio }: { valor: string; onCambio: (texto: string) => void }) {
  const avisar = useAviso();
  const [pasos, setPasos] = useState<PasoEditable[]>(() => {
    const p = parsearPasos(valor);
    return (p.length ? p : [{ texto: "", imagenes: [] }]).map(editable);
  });
  const campos = useRef<Record<number, HTMLTextAreaElement | HTMLInputElement | null>>({});
  const [menuColor, setMenuColor] = useState<{ ancla: HTMLElement; clave: number } | null>(null);
  const [enfocar, setEnfocar] = useState<number | null>(null);

  const primera = useRef(true);
  const avisarCambio = useRef(onCambio);
  avisarCambio.current = onCambio;
  useEffect(() => {
    if (primera.current) {
      primera.current = false;
      return;
    }
    avisarCambio.current(serializarPasos(pasos));
  }, [pasos]);

  const aplicar = (fn: (ps: PasoEditable[]) => PasoEditable[]) => setPasos(fn);
  const cambiar = (clave: number, cambio: Partial<PasoEditable> | ((p: PasoEditable) => Partial<PasoEditable>)) =>
    aplicar((ps) => ps.map((p) => (p.clave === clave ? { ...p, ...(typeof cambio === "function" ? cambio(p) : cambio) } : p)));

  const agregarDespues = (clave: number | null) => {
    const nuevo = editable({ texto: "", imagenes: [] });
    aplicar((ps) => {
      const i = clave === null ? ps.length - 1 : ps.findIndex((p) => p.clave === clave);
      return [...ps.slice(0, i + 1), nuevo, ...ps.slice(i + 1)];
    });
    setEnfocar(nuevo.clave);
  };
  const mover = (clave: number, d: -1 | 1) => aplicar((ps) => {
    const i = ps.findIndex((p) => p.clave === clave);
    const j = i + d;
    if (j < 0 || j >= ps.length) return ps;
    const copia = [...ps];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    return copia;
  });
  const quitar = (clave: number) => aplicar((ps) => (ps.length > 1 ? ps.filter((p) => p.clave !== clave) : [editable({ texto: "", imagenes: [] })]));

  const subir = async (clave: number, archivos: File[]) => {
    const imagenes = archivos.filter((f) => f.type.startsWith("image/"));
    if (!imagenes.length) {
      if (archivos.length) avisar("Solo se pueden agregar imágenes (PNG, JPG o GIF)", "error");
      return;
    }
    cambiar(clave, (p) => ({ subiendo: p.subiendo + imagenes.length }));
    for (const [n, f] of imagenes.entries()) {
      try {
        const nombrado = /^image\.(png|jpe?g|gif)$/i.test(f.name) || !f.name ? nombrarCaptura(f, n) : f;
        const form = new FormData();
        form.append("archivo", nombrado, nombrado.name);
        const r = await api<{ id: number }>("POST", "/conocimiento/imagenes", { form });
        cambiar(clave, (p) => ({ imagenes: [...p.imagenes, r.id], subiendo: p.subiendo - 1 }));
      } catch (e) {
        cambiar(clave, (p) => ({ subiendo: p.subiendo - 1 }));
        avisar(mensajeError(e), "error");
      }
    }
  };

  /** Envuelve lo seleccionado con la etiqueta; sin selección, deja el cursor entre las dos marcas. */
  const envolver = (clave: number, abre: string, cierra: string) => {
    const el = campos.current[clave];
    const paso = pasos.find((p) => p.clave === clave);
    if (!el || !paso) return;
    const ini = el.selectionStart ?? paso.texto.length;
    const fin = el.selectionEnd ?? ini;
    const t = paso.texto;
    cambiar(clave, { texto: t.slice(0, ini) + abre + t.slice(ini, fin) + cierra + t.slice(fin) });
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(ini + abre.length, fin + abre.length);
    });
  };
  const limpiarFormato = (clave: number) => cambiar(clave, (p) => ({ texto: p.texto.replace(ETIQUETA, "") }));

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Solución · paso a paso *</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.2 }}>
        Escriba un paso en cada recuadro (Enter crea el siguiente). Seleccione texto y use los botones para negrita, cursiva, subrayado o color.
        Para agregar una imagen use «Imagen», pegue una captura con Ctrl+V o arrástrela al paso.
      </Typography>
      <Stack spacing={1.2}>
        {pasos.map((p, i) => (
          <Paper key={p.clave} variant="outlined" sx={{ p: 1.2, pl: 1.5 }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              const imgs = imagenesDe(e.dataTransfer);
              if (imgs.length) {
                e.preventDefault();
                subir(p.clave, imgs);
              }
            }}>
            <Stack direction="row" sx={{ alignItems: "center", gap: 0.3, flexWrap: "wrap" }}>
              <Typography sx={{ color: marca.azul, fontWeight: 700, mr: 1 }}>Paso {i + 1}</Typography>
              <Tooltip title="Negrita"><IconButton size="small" onClick={() => envolver(p.clave, "[b]", "[/b]")} aria-label="Negrita"><FormatBoldIcon fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="Cursiva"><IconButton size="small" onClick={() => envolver(p.clave, "[i]", "[/i]")} aria-label="Cursiva"><FormatItalicIcon fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="Subrayado"><IconButton size="small" onClick={() => envolver(p.clave, "[u]", "[/u]")} aria-label="Subrayado"><FormatUnderlinedIcon fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="Color del texto"><IconButton size="small" onClick={(e) => setMenuColor({ ancla: e.currentTarget, clave: p.clave })} aria-label="Color del texto"><FormatColorTextIcon fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="Quitar formato"><IconButton size="small" onClick={() => limpiarFormato(p.clave)} aria-label="Quitar formato"><FormatClearIcon fontSize="small" /></IconButton></Tooltip>
              <Button size="small" component="label" startIcon={<AddPhotoAlternateIcon />} sx={{ ml: 0.5 }}>
                Imagen
                <input type="file" accept="image/png,image/jpeg,image/gif" multiple hidden
                  onChange={(e) => {
                    const fs = Array.from(e.target.files ?? []);
                    e.target.value = "";
                    subir(p.clave, fs);
                  }} />
              </Button>
              <Box sx={{ flex: 1 }} />
              <Tooltip title="Subir paso"><span><IconButton size="small" disabled={i === 0} onClick={() => mover(p.clave, -1)} aria-label="Subir paso"><ArrowUpwardIcon fontSize="small" /></IconButton></span></Tooltip>
              <Tooltip title="Bajar paso"><span><IconButton size="small" disabled={i === pasos.length - 1} onClick={() => mover(p.clave, 1)} aria-label="Bajar paso"><ArrowDownwardIcon fontSize="small" /></IconButton></span></Tooltip>
              <Tooltip title="Eliminar paso"><IconButton size="small" onClick={() => quitar(p.clave)} aria-label="Eliminar paso"><DeleteIcon fontSize="small" /></IconButton></Tooltip>
            </Stack>
            <Box
              component="textarea"
              ref={(el: HTMLTextAreaElement | null) => {
                campos.current[p.clave] = el;
                if (el && enfocar === p.clave) {
                  el.focus();
                  setEnfocar(null);
                }
              }}
              rows={2}
              value={p.texto}
              placeholder={i === 0 ? "Ej.: Abra Teams y entre a Configuración" : "Siguiente paso…"}
              aria-label={`Paso ${i + 1}`}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => cambiar(p.clave, { texto: e.target.value.replace(/\n/g, " ") })}
              onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  agregarDespues(p.clave);
                }
              }}
              onPaste={(e: React.ClipboardEvent<HTMLTextAreaElement>) => {
                const imgs = imagenesDe(e.clipboardData);
                if (imgs.length) {
                  e.preventDefault();
                  subir(p.clave, imgs);
                }
              }}
              sx={{
                mt: 0.5, width: "100%", boxSizing: "border-box", resize: "vertical", font: "inherit", fontSize: 14, p: 1,
                border: "1px solid #C9D2DE", borderRadius: 1, outline: "none", "&:focus": { borderColor: marca.azul, boxShadow: `0 0 0 1px ${marca.azul}` },
              }}
            />
            {tieneFormato(p.texto) && (
              <Box sx={{ mt: 0.5, px: 1, py: 0.6, bgcolor: "#F5F8FC", borderRadius: 1 }}>
                <Typography variant="caption" color="text.secondary">Así se verá: </Typography>
                <Typography variant="body2" component="span"><TextoConFormato texto={p.texto} /></Typography>
              </Box>
            )}
            {(p.imagenes.length > 0 || p.subiendo > 0) && (
              <Stack direction="row" sx={{ mt: 1.5, gap: 2, flexWrap: "wrap", alignItems: "center" }}>
                {p.imagenes.map((id) => (
                  <ImagenArticulo key={id} id={id} alto={110} onQuitar={() => cambiar(p.clave, (x) => ({ imagenes: x.imagenes.filter((y) => y !== id) }))} />
                ))}
                {p.subiendo > 0 && <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><CircularProgress size={18} /><Typography variant="caption">Subiendo imagen…</Typography></Stack>}
              </Stack>
            )}
          </Paper>
        ))}
      </Stack>
      <Button size="small" startIcon={<AddIcon />} sx={{ mt: 1 }} onClick={() => agregarDespues(null)}>Agregar paso</Button>
      <Menu anchorEl={menuColor?.ancla} open={!!menuColor} onClose={() => setMenuColor(null)}>
        {COLORES.map((c) => (
          <MenuItem key={c.valor} onClick={() => { if (menuColor) envolver(menuColor.clave, `[color=${c.valor}]`, "[/color]"); setMenuColor(null); }}>
            <Box sx={{ width: 14, height: 14, borderRadius: "50%", bgcolor: c.valor, mr: 1.2 }} />
            <Typography sx={{ color: c.valor, fontWeight: 600 }}>{c.nombre}</Typography>
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
}
