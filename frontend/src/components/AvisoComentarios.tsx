import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Alert, AlertTitle, Box, Button, IconButton, Stack, Tooltip } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ChatIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import VolumeOffIcon from "@mui/icons-material/VolumeOff";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import NotificationsOffIcon from "@mui/icons-material/NotificationsOff";
import { get, post } from "../api/client";
import type { Notificacion } from "../api/types";

/** Tipos de notificación que se avisan con ventana emergente y sonido: comentarios y respuestas en tickets. */
const TIPOS_AVISO = new Set(["COMENTARIO", "RESPUESTA"]);
const MAX_EN_PANTALLA = 3;
const DURACION_MS = 12_000;

// ------------------------------------------------------------ preferencias (por equipo y navegador)
const CLAVE_SONIDO = "mesa.aviso.sonido";
const CLAVE_EMERGENTE = "mesa.aviso.emergente";

function leer(clave: string, defecto: string): string {
  try {
    return localStorage.getItem(clave) ?? defecto;
  } catch {
    return defecto;
  }
}

function guardar(clave: string, valor: string) {
  try {
    localStorage.setItem(clave, valor);
  } catch {
    /* navegador sin almacenamiento: la preferencia dura solo esta sesión */
  }
  window.dispatchEvent(new Event("mesa-aviso-preferencias"));
}

export function usePreferenciasAviso() {
  const [sonido, setSonido] = useState(() => leer(CLAVE_SONIDO, "1") === "1");
  const [emergente, setEmergente] = useState(() => leer(CLAVE_EMERGENTE, "1") === "1");
  const [permiso, setPermiso] = useState<NotificationPermission | "no">(() =>
    typeof Notification === "undefined" ? "no" : Notification.permission,
  );
  useEffect(() => {
    const sync = () => {
      setSonido(leer(CLAVE_SONIDO, "1") === "1");
      setEmergente(leer(CLAVE_EMERGENTE, "1") === "1");
    };
    window.addEventListener("mesa-aviso-preferencias", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("mesa-aviso-preferencias", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return {
    sonido,
    emergente,
    permiso,
    cambiarSonido: () => guardar(CLAVE_SONIDO, sonido ? "0" : "1"),
    cambiarEmergente: () => guardar(CLAVE_EMERGENTE, emergente ? "0" : "1"),
    pedirPermiso: async () => {
      if (typeof Notification === "undefined") return;
      setPermiso(await Notification.requestPermission());
    },
  };
}

// ------------------------------------------------------------ sonido (generado, sin archivos)
let contextoAudio: AudioContext | null = null;

function tocarSonido() {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    contextoAudio ??= new Ctx();
    const ctx = contextoAudio;
    if (ctx.state === "suspended") void ctx.resume();
    const inicio = ctx.currentTime + 0.02;
    // Dos tonos suaves, ascendentes (≈0,4 s)
    [
      [880, 0],
      [1320, 0.16],
    ].forEach(([frecuencia, desfase]) => {
      const osc = ctx.createOscillator();
      const vol = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = frecuencia;
      const t0 = inicio + desfase;
      vol.gain.setValueAtTime(0.0001, t0);
      vol.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
      osc.connect(vol).connect(ctx.destination);
      osc.start(t0);
      osc.stop(t0 + 0.25);
    });
  } catch {
    /* el navegador bloqueó el audio: queda el aviso visual */
  }
}

// El navegador solo deja sonar audio después de que la persona interactuó con la página: se "despierta" con el primer clic
function prepararAudio() {
  const despertar = () => {
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx) {
        contextoAudio ??= new Ctx();
        if (contextoAudio.state === "suspended") void contextoAudio.resume();
      }
    } catch {
      /* sin audio */
    }
  };
  window.addEventListener("pointerdown", despertar, { once: true });
  window.addEventListener("keydown", despertar, { once: true });
}

// ------------------------------------------------------------ control del último aviso mostrado (compartido entre pestañas)
function claveUltimo(usuarioId: number) {
  return `mesa.aviso.ultimo.${usuarioId}`;
}

/** Reserva los avisos nuevos para esta pestaña: si otra pestaña ya los mostró, no se repiten ni suenan dos veces. */
function reservar(usuarioId: number, ids: number[]): number[] {
  const ultimo = Number(leer(claveUltimo(usuarioId), "0")) || 0;
  const nuevos = ids.filter((id) => id > ultimo);
  if (nuevos.length) {
    try {
      localStorage.setItem(claveUltimo(usuarioId), String(Math.max(...nuevos)));
    } catch {
      /* sin almacenamiento */
    }
  }
  return nuevos;
}

// ------------------------------------------------------------ componente
/**
 * Avisa con una ventana emergente y un sonido cada vez que llega un comentario a un ticket.
 * Se apoya en el contador de la campana (que se consulta cada 15 s): cuando sube, trae las no leídas
 * y muestra las de comentarios que aún no se avisaron. Si la pestaña no está a la vista y la persona
 * dio permiso, también sale la notificación del sistema operativo (Windows).
 */
export default function AvisoComentarios({ usuarioId, noLeidas }: { usuarioId: number; noLeidas: number | undefined }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const pref = usePreferenciasAviso();
  const prefRef = useRef(pref);
  prefRef.current = pref;
  const [avisos, setAvisos] = useState<Notificacion[]>([]);
  const iniciado = useRef(false);
  const anterior = useRef<number | undefined>(undefined);

  useEffect(prepararAudio, []);

  const abrir = useCallback(
    (n: Notificacion) => {
      void post(`/notificaciones/${n.id}/leida`).then(() => qc.invalidateQueries({ queryKey: ["notificaciones"] }));
      setAvisos((a) => a.filter((x) => x.id !== n.id));
      if (n.ticket_id) {
        void qc.invalidateQueries({ queryKey: ["ticket", String(n.ticket_id)] });
        navigate(`/tickets/${n.ticket_id}`);
      }
    },
    [navigate, qc],
  );

  useEffect(() => {
    if (noLeidas === undefined) return;
    const previo = anterior.current;
    anterior.current = noLeidas;
    // Primera carga: solo se marca hasta dónde ya se vio, para no avisar de comentarios antiguos
    const primera = !iniciado.current;
    if (!primera && (previo === undefined || noLeidas <= previo)) return;
    iniciado.current = true;
    let cancelado = false;
    get<Notificacion[]>("/notificaciones", { solo_no_leidas: true, limite: 20 })
      .then((lista) => {
        if (cancelado) return;
        const comentarios = lista.filter((n) => TIPOS_AVISO.has(n.tipo));
        if (primera && leer(claveUltimo(usuarioId), "") === "") {
          // Equipo nuevo: se toma como visto lo que ya había
          reservar(usuarioId, lista.map((n) => n.id));
          return;
        }
        const ids = new Set(reservar(usuarioId, comentarios.map((n) => n.id)));
        const nuevos = comentarios.filter((n) => ids.has(n.id)).sort((a, b) => a.id - b.id);
        if (!nuevos.length) return;
        const p = prefRef.current;
        if (p.sonido) tocarSonido();
        if (p.emergente) setAvisos((a) => [...a.filter((x) => !ids.has(x.id)), ...nuevos].slice(-MAX_EN_PANTALLA));
        if (p.permiso === "granted" && document.visibilityState !== "visible") {
          nuevos.slice(-MAX_EN_PANTALLA).forEach((n) => {
            try {
              const sistema = new Notification(n.titulo, { body: n.mensaje, tag: `mesa-${n.id}`, icon: "/isotipo.png" });
              sistema.onclick = () => {
                window.focus();
                abrir(n);
                sistema.close();
              };
            } catch {
              /* el sistema no permitió la notificación */
            }
          });
        }
        // Si la persona está mirando ese ticket, se refresca para que vea el comentario
        nuevos.forEach((n) => n.ticket_id && qc.invalidateQueries({ queryKey: ["ticket", String(n.ticket_id)] }));
      })
      .catch(() => {
        /* sin red: se intenta de nuevo en la próxima consulta */
      });
    return () => {
      cancelado = true;
    };
  }, [noLeidas, usuarioId, abrir, qc]);

  // Cada aviso se cierra solo después de unos segundos
  useEffect(() => {
    if (!avisos.length) return;
    const t = setTimeout(() => setAvisos((a) => a.slice(1)), DURACION_MS);
    return () => clearTimeout(t);
  }, [avisos]);

  if (!avisos.length) return null;
  return (
    <Stack
      spacing={1}
      sx={{ position: "fixed", right: 16, bottom: 16, zIndex: (t) => t.zIndex.snackbar, width: 380, maxWidth: "calc(100vw - 32px)" }}
      role="region"
      aria-live="polite"
      aria-label="Avisos de comentarios"
    >
      {avisos.map((n) => (
        <Alert
          key={n.id}
          severity="info"
          variant="filled"
          icon={<ChatIcon />}
          sx={{ bgcolor: "#0B255B", boxShadow: 6, alignItems: "flex-start" }}
          action={
            <IconButton size="small" color="inherit" aria-label="Cerrar aviso" onClick={() => setAvisos((a) => a.filter((x) => x.id !== n.id))}>
              <CloseIcon fontSize="small" />
            </IconButton>
          }
        >
          <AlertTitle sx={{ fontWeight: 600, mb: 0.25 }}>{n.titulo}</AlertTitle>
          <Box sx={{ fontSize: 13, opacity: 0.9, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
            {n.mensaje}
          </Box>
          {n.ticket_id && (
            <Button size="small" variant="outlined" color="inherit" sx={{ mt: 1 }} onClick={() => abrir(n)}>
              Ver ticket
            </Button>
          )}
        </Alert>
      ))}
    </Stack>
  );
}

/** Botones para silenciar el sonido o los avisos y activar las notificaciones de Windows (en la campana). */
export function ControlesAviso() {
  const p = usePreferenciasAviso();
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
      <Tooltip title={p.sonido ? "Silenciar el sonido de los comentarios" : "Activar el sonido de los comentarios"}>
        <IconButton size="small" onClick={p.cambiarSonido} aria-label={p.sonido ? "Silenciar sonido" : "Activar sonido"}>
          {p.sonido ? <VolumeUpIcon fontSize="small" /> : <VolumeOffIcon fontSize="small" color="disabled" />}
        </IconButton>
      </Tooltip>
      <Tooltip title={p.emergente ? "No mostrar avisos emergentes de comentarios" : "Mostrar avisos emergentes de comentarios"}>
        <IconButton size="small" onClick={p.cambiarEmergente} aria-label={p.emergente ? "Ocultar avisos" : "Mostrar avisos"}>
          {p.emergente ? <NotificationsActiveIcon fontSize="small" /> : <NotificationsOffIcon fontSize="small" color="disabled" />}
        </IconButton>
      </Tooltip>
      {p.permiso === "default" && (
        <Button size="small" onClick={() => void p.pedirPermiso()} sx={{ ml: 0.5 }}>
          Avisos de Windows
        </Button>
      )}
    </Box>
  );
}
