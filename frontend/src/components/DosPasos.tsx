import { useRef, type ClipboardEvent, type KeyboardEvent } from "react";
import { Box, Button, Typography } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { Stack } from "./Pila";
import type { Activacion } from "../api/cuarta";

/** Seis cajas para el código de 6 dígitos (pegar, borrar y flechas funcionan como se espera). */
export function CodigoCajas({ valor, onCambio, autoFocus, deshabilitado }: { valor: string; onCambio: (v: string) => void; autoFocus?: boolean; deshabilitado?: boolean }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digitos = Array.from({ length: 6 }, (_, i) => valor[i] ?? "");
  const poner = (i: number, d: string) => {
    const arr = [...digitos];
    arr[i] = d;
    onCambio(arr.join("").slice(0, 6));
  };
  const tecla = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digitos[i] && i > 0) {
      poner(i - 1, "");
      refs.current[i - 1]?.focus();
    } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
    else if (e.key === "ArrowRight" && i < 5) refs.current[i + 1]?.focus();
  };
  const pegar = (e: ClipboardEvent<HTMLInputElement>) => {
    const t = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (t) {
      e.preventDefault();
      onCambio(t);
      refs.current[Math.min(t.length, 5)]?.focus();
    }
  };
  return (
    <Stack direction="row" justifyContent="center" sx={{ gap: { xs: 0.75, sm: 1.25 } }}>
      {digitos.map((d, i) => (
        <Box
          key={i}
          component="input"
          ref={(el: HTMLInputElement | null) => { refs.current[i] = el; }}
          value={d}
          disabled={deshabilitado}
          autoFocus={autoFocus && i === 0}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          aria-label={`Dígito ${i + 1} de 6`}
          maxLength={1}
          onPaste={pegar}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => tecla(i, e)}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
            const v = e.target.value.replace(/\D/g, "").slice(-1);
            poner(i, v);
            if (v && i < 5) refs.current[i + 1]?.focus();
          }}
          sx={{
            width: { xs: 42, sm: 50 }, height: { xs: 52, sm: 58 }, textAlign: "center", fontSize: 26, fontWeight: 700, color: "#10203C",
            border: "2px solid #D5DCE6", borderRadius: 2.5, outline: "none", bgcolor: "#fff", fontFamily: "inherit",
            "&:focus": { borderColor: "primary.main", boxShadow: "0 0 0 3px rgba(19,103,172,.15)" },
          }}
        />
      ))}
    </Stack>
  );
}

/** QR + pasos para Microsoft / Google Authenticator. */
export function PasosAuthenticator({ a }: { a: Activacion }) {
  const pasos = ["Instale Microsoft Authenticator o Google Authenticator en su celular.", "Toque «Agregar cuenta» y escanee este código.",
    "Escriba el código de 6 dígitos que aparece en la app."];
  return (
    <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ xs: "center", sm: "flex-start" }} sx={{ gap: 3 }}>
      <Box sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 3, bgcolor: "#fff", flexShrink: 0 }}>
        <Box component="img" src={a.qr} alt="Código QR para el Authenticator" sx={{ width: 180, height: 180, display: "block" }} />
      </Box>
      <Box>
        {pasos.map((p, i) => (
          <Stack key={i} direction="row" sx={{ gap: 1.25, mb: 1.5 }}>
            <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: "primary.main", color: "#fff", display: "grid", placeItems: "center",
              fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{i + 1}</Box>
            <Typography variant="body2">{p}</Typography>
          </Stack>
        ))}
        <Typography variant="caption" color="text.secondary">
          ¿No puede escanear? Clave: <Box component="b" sx={{ color: "text.primary", fontFamily: "monospace", fontSize: 13 }}>{a.clave}</Box>
        </Typography>
      </Box>
    </Stack>
  );
}

export function descargarCodigos(codigos: string[], cuenta?: string) {
  const texto = [
    "Mesa de Servicios ADUCORP · Códigos de respaldo",
    cuenta ? `Cuenta: ${cuenta}` : "",
    `Generados: ${new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil" })}`,
    "",
    "Úselos si no tiene el celular. Cada código sirve una sola vez.",
    "",
    ...codigos,
    "",
  ].filter((l, i) => l !== "" || i > 2).join("\r\n");
  const url = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "codigos-respaldo-mesa-aducorp.txt";
  a.click();
  URL.revokeObjectURL(url);
}

export function CodigosRespaldo({ codigos, cuenta }: { codigos: string[]; cuenta?: string }) {
  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>Códigos de respaldo (úselos una sola vez)</Typography>
        <Button size="small" startIcon={<DownloadIcon />} onClick={() => descargarCodigos(codigos, cuenta)}>Descargar</Button>
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, 1fr)" }, gap: 1.5, p: 2, bgcolor: "#F4F6FA", borderRadius: 2,
        fontFamily: "monospace", fontWeight: 700, fontSize: 15 }}>
        {codigos.map((c) => <span key={c}>{c}</span>)}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        Guárdelos en un lugar seguro: no se vuelven a mostrar.
      </Typography>
    </Box>
  );
}
