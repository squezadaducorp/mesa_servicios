import { useState } from "react";
import { Autocomplete, Chip, TextField } from "@mui/material";

// Misma regla que el backend (app/domain/correos.py)
const PATRON = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$/;
export const MAX_COPIAS = 10;
export const correoValido = (c: string) => c.length <= 150 && PATRON.test(c);

interface Props {
  valor: string[];
  onCambio: (correos: string[]) => void;
  etiqueta?: string;
  ayuda?: string;
  placeholder?: string;
  sugerencias?: string[];
  disabled?: boolean;
  size?: "small" | "medium";
}

/** Campo de varios correos: se separan con Enter, coma, punto y coma o espacio, y se muestran como etiquetas que se pueden quitar. */
export default function CampoCorreos({ valor, onCambio, etiqueta = "Correos", ayuda, placeholder, sugerencias = [], disabled, size = "small" }: Props) {
  const [texto, setTexto] = useState("");
  const [error, setError] = useState<string | null>(null);

  const agregar = (partes: string[], resto = "") => {
    const nuevos = [...valor];
    const invalidos: string[] = [];
    for (const p of partes.map((x) => x.trim().toLowerCase()).filter(Boolean)) {
      if (!correoValido(p)) invalidos.push(p);
      else if (!nuevos.includes(p)) nuevos.push(p);
    }
    if (nuevos.length > MAX_COPIAS) {
      setError(`Máximo ${MAX_COPIAS} correos`);
      return;
    }
    setError(invalidos.length ? `Correo no válido: ${invalidos.join(", ")}` : null);
    setTexto(invalidos.length ? invalidos.join(", ") : resto);
    if (nuevos.length !== valor.length) onCambio(nuevos);
  };

  return (
    <Autocomplete<string, true, false, true>
      multiple
      freeSolo
      size={size}
      disabled={disabled}
      options={sugerencias.filter((s) => !valor.includes(s))}
      value={valor}
      inputValue={texto}
      onInputChange={(_, v, motivo) => {
        if (motivo === "reset") return;
        if (/[,;\s]/.test(v)) {
          const partes = v.split(/[,;\s]+/);
          const resto = partes.pop() ?? "";
          agregar(partes, resto);
        } else {
          setTexto(v);
          if (error) setError(null);
        }
      }}
      onChange={(_, v, motivo) => {
        if (motivo === "createOption" || motivo === "selectOption") agregar([v[v.length - 1] as string]);
        else {
          onCambio(v as string[]);
          setError(null);
        }
      }}
      onBlur={() => texto.trim() && agregar([texto])}
      renderValue={(seleccion, getItemProps) =>
        seleccion.map((c, index) => {
          const { key, ...props } = getItemProps({ index });
          return <Chip key={key} size="small" label={c} {...props} />;
        })
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={etiqueta}
          placeholder={valor.length ? undefined : placeholder ?? "nombre@empresa.com"}
          error={!!error}
          helperText={error ?? ayuda}
        />
      )}
    />
  );
}
