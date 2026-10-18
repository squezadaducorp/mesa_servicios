import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Alert, Snackbar } from "@mui/material";

type Tipo = "success" | "error" | "info" | "warning";
const Ctx = createContext<(mensaje: string, tipo?: Tipo) => void>(() => {});

export function AvisoProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<{ mensaje: string; tipo: Tipo; clave: number } | null>(null);
  const avisar = useCallback((mensaje: string, tipo: Tipo = "success") => setEstado({ mensaje, tipo, clave: Date.now() }), []);
  return (
    <Ctx.Provider value={avisar}>
      {children}
      <Snackbar
        key={estado?.clave}
        open={!!estado}
        autoHideDuration={estado?.tipo === "error" ? 8000 : 4000}
        onClose={() => setEstado(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert severity={estado?.tipo ?? "info"} variant="filled" onClose={() => setEstado(null)} sx={{ maxWidth: 520 }}>
          {estado?.mensaje}
        </Alert>
      </Snackbar>
    </Ctx.Provider>
  );
}

export const useAviso = () => useContext(Ctx);

export function mensajeError(e: unknown): string {
  return e instanceof Error ? e.message : "Ocurrió un error inesperado";
}
