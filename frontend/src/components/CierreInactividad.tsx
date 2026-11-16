import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from "@mui/material";
import { actividad } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const EVENTOS = ["mousedown", "mousemove", "keydown", "wheel", "scroll", "touchstart"] as const;
const AVISO_MS = 60_000; // el aviso aparece un minuto antes del cierre
const ESCRITURA_MS = 5_000; // no escribir en el almacenamiento con cada movimiento del ratón
export const MENSAJE_INACTIVIDAD = "Su sesión se cerró por inactividad. Inicie sesión nuevamente.";

function formato(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")} minutos` : `${s} segundos`;
}

/**
 * Cierra la sesión cuando el usuario no interactúa con la Mesa durante el tiempo definido en
 * Administración › Configuración (seguridad.inactividad_min). Un minuto antes muestra un aviso.
 * La actividad se comparte entre pestañas: usar la Mesa en una mantiene abiertas las demás.
 */
export default function CierreInactividad() {
  const { usuario, inactividadMin, logout } = useAuth();
  const navigate = useNavigate();
  const [restante, setRestante] = useState<number | null>(null); // segundos; null = sin aviso
  const avisando = useRef(false);
  const ultimaEscritura = useRef(0);
  const cerrando = useRef(false);
  const limiteMs = inactividadMin * 60_000;

  const seguir = useCallback(() => {
    actividad.marcar();
    ultimaEscritura.current = Date.now();
    avisando.current = false;
    setRestante(null);
  }, []);

  const cerrar = useCallback(
    async (motivo?: string) => {
      if (cerrando.current) return;
      cerrando.current = true;
      avisando.current = false;
      setRestante(null);
      await logout(motivo);
      navigate("/login", { replace: true });
    },
    [logout, navigate],
  );

  useEffect(() => {
    if (!usuario || limiteMs <= 0) return;
    cerrando.current = false;
    if (actividad.ultima() === null) actividad.marcar();

    const alInteractuar = () => {
      if (avisando.current) return; // con el aviso abierto, solo cuenta el botón «Seguir conectado»
      const ahora = Date.now();
      if (ahora - ultimaEscritura.current < ESCRITURA_MS) return;
      ultimaEscritura.current = ahora;
      actividad.marcar(ahora);
    };
    const revisar = () => {
      const quedan = limiteMs - (Date.now() - (actividad.ultima() ?? Date.now()));
      if (quedan <= 0) {
        void cerrar(MENSAJE_INACTIVIDAD);
      } else if (quedan <= Math.min(AVISO_MS, limiteMs / 2)) {
        avisando.current = true;
        setRestante(Math.ceil(quedan / 1000));
      } else if (avisando.current) {
        // hubo actividad en otra pestaña
        avisando.current = false;
        setRestante(null);
      }
    };

    EVENTOS.forEach((e) => window.addEventListener(e, alInteractuar, { capture: true, passive: true }));
    document.addEventListener("visibilitychange", revisar); // al volver a la pestaña o despertar el equipo
    const intervalo = window.setInterval(revisar, 1_000);
    revisar();
    return () => {
      EVENTOS.forEach((e) => window.removeEventListener(e, alInteractuar, { capture: true }));
      document.removeEventListener("visibilitychange", revisar);
      window.clearInterval(intervalo);
    };
  }, [usuario, limiteMs, cerrar]);

  return (
    <Dialog open={restante !== null} onClose={seguir} aria-labelledby="titulo-inactividad">
      <DialogTitle id="titulo-inactividad">¿Sigue ahí?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Por seguridad, su sesión se cerrará por inactividad en <b>{formato(restante ?? 0)}</b>.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => void cerrar()}>Cerrar sesión</Button>
        <Button variant="contained" onClick={seguir} autoFocus>
          Seguir conectado
        </Button>
      </DialogActions>
    </Dialog>
  );
}
