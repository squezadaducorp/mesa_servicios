import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { post, renovar, sesion } from "../api/client";
import type { TokenSalida, UsuarioSesion } from "../api/types";

interface Auth {
  usuario: UsuarioSesion | null;
  cargando: boolean;
  login: (correo: string, clave: string) => Promise<UsuarioSesion>;
  logout: () => Promise<void>;
  aplicarToken: (t: TokenSalida) => void;
  puede: (...permisos: string[]) => boolean;
}

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioSesion | null>(null);
  const [cargando, setCargando] = useState(true);
  const qc = useQueryClient();

  const aplicarToken = useCallback((t: TokenSalida) => {
    sesion.guardar(t);
    setUsuario(t.usuario);
  }, []);

  useEffect(() => {
    sesion.alRenovar((t) => setUsuario(t.usuario));
    sesion.alExpirar(() => {
      setUsuario(null);
      qc.clear();
    });
    // Restaurar la sesión con el refresh token guardado
    renovar()
      .then((t) => setUsuario(t?.usuario ?? null))
      .finally(() => setCargando(false));
  }, [qc]);

  const login = useCallback(
    async (correo: string, clave: string) => {
      const t = await post<TokenSalida>("/auth/login", { correo, clave });
      aplicarToken(t);
      return t.usuario;
    },
    [aplicarToken],
  );

  const logout = useCallback(async () => {
    const rt = sesion.refreshToken();
    try {
      if (rt) await post("/auth/logout", { refresh_token: rt });
    } catch {
      /* la sesión se cierra localmente aunque falle la red */
    }
    sesion.limpiar();
    setUsuario(null);
    qc.clear();
  }, [qc]);

  const puede = useCallback((...permisos: string[]) => !!usuario && permisos.some((p) => usuario.permisos.includes(p)), [usuario]);

  const valor = useMemo(() => ({ usuario, cargando, login, logout, aplicarToken, puede }), [usuario, cargando, login, logout, aplicarToken, puede]);
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth fuera de AuthProvider");
  return c;
}
