import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { actividad, post, renovar, sesion } from "../api/client";
import type { TokenSalida, UsuarioSesion } from "../api/types";

interface Auth {
  usuario: UsuarioSesion | null;
  cargando: boolean;
  login: (correo: string, clave: string) => Promise<UsuarioSesion>;
  logout: (motivo?: string) => Promise<void>;
  /** Minutos sin actividad antes de cerrar la sesión (0 = sin límite). */
  inactividadMin: number;
  /** Por qué se cerró la última sesión (se muestra en la pantalla de inicio). */
  motivoCierre: string | null;
  aplicarToken: (t: TokenSalida) => void;
  puede: (...permisos: string[]) => boolean;
}

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioSesion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [inactividadMin, setInactividadMin] = useState(0);
  const [motivoCierre, setMotivoCierre] = useState<string | null>(null);
  const qc = useQueryClient();

  const aplicarToken = useCallback((t: TokenSalida) => {
    sesion.guardar(t);
    actividad.marcar(); // iniciar sesión cuenta como actividad
    setInactividadMin(t.inactividad_min ?? 0);
    setMotivoCierre(null);
    setUsuario(t.usuario);
  }, []);

  useEffect(() => {
    const motivoVisible = (m?: string) => (m && /inactividad/i.test(m) ? m : null);
    sesion.alRenovar((t) => {
      setInactividadMin(t.inactividad_min ?? 0);
      setUsuario(t.usuario);
    });
    sesion.alExpirar((motivo) => {
      setMotivoCierre(motivoVisible(motivo));
      setUsuario(null);
      qc.clear();
    });
    // Si se cierra la sesión en otra pestaña, esta también se cierra
    const alCambiarAlmacenamiento = (e: StorageEvent) => {
      if (e.key === "aducorp.refresh" && e.newValue === null) {
        sesion.limpiar();
        setUsuario(null);
        qc.clear();
      }
    };
    window.addEventListener("storage", alCambiarAlmacenamiento);
    // Restaurar la sesión con el refresh token guardado
    renovar()
      .then((t) => {
        setUsuario(t?.usuario ?? null);
        if (!t) setMotivoCierre(motivoVisible(sesion.motivoRechazo()));
      })
      .finally(() => setCargando(false));
    return () => window.removeEventListener("storage", alCambiarAlmacenamiento);
  }, [qc]);

  const login = useCallback(
    async (correo: string, clave: string) => {
      const t = await post<TokenSalida>("/auth/login", { correo, clave });
      aplicarToken(t);
      return t.usuario;
    },
    [aplicarToken],
  );

  const logout = useCallback(async (motivo?: string) => {
    const rt = sesion.refreshToken();
    try {
      if (rt) await post("/auth/logout", { refresh_token: rt });
    } catch {
      /* la sesión se cierra localmente aunque falle la red */
    }
    sesion.limpiar();
    setMotivoCierre(motivo ?? null);
    setUsuario(null);
    qc.clear();
  }, [qc]);

  const puede = useCallback((...permisos: string[]) => !!usuario && permisos.some((p) => usuario.permisos.includes(p)), [usuario]);

  const valor = useMemo(
    () => ({ usuario, cargando, login, logout, aplicarToken, puede, inactividadMin, motivoCierre }),
    [usuario, cargando, login, logout, aplicarToken, puede, inactividadMin, motivoCierre],
  );
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth fuera de AuthProvider");
  return c;
}
