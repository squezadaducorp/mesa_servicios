"""Protecciones para el texto que se envía a un modelo de IA externo (matriz TI-REG-IA-001).

- R11 seudonimización: nombres, RUC/cédula, correos y teléfonos se cambian por marcadores
  antes de salir de la red de ADUCORP, y los marcadores se devuelven a su valor al recibir
  la respuesta (el proveedor nunca ve el dato real).
- R13 inyección de instrucciones: el texto del usuario no puede cerrar las etiquetas que lo
  delimitan, y la salida del modelo se revisa en busca de señales de manipulación.
- Límite de tamaño para no enviar textos enormes (costo, R14).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_CARACTERES = 8000   # por campo enviado al modelo

_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# RUC (13 dígitos) y cédula (10 dígitos) de Ecuador; también con guion antes del verificador.
_IDENTIFICACION = re.compile(r"(?<!\d)(?:\d{13}|\d{10}|\d{9}-\d)(?!\d)")
# Teléfonos: +593…, 09xxxxxxxx, (02) 2xx xxxx, etc.
_TELEFONO = re.compile(r"(?<![\w])(?:\+?593[\s-]?|\(?0\d\)?[\s-]?)\d{1,3}[\s-]?\d{3}[\s-]?\d{3,4}(?![\w])")

# Señales de que el texto de un ticket intentó manipular al modelo o de que la salida no es
# una respuesta normal de soporte. Se registran y la sugerencia se descarta.
_SENALES = [
    re.compile(p, re.I)
    for p in (
        r"(?:ignor|olvid|disregard|forget)\w*\s+(?:\w+\s+){0,3}(?:instrucciones|instructions|reglas|rules)",
        r"system\s*prompt|instrucciones\s+del\s+sistema",
        r"</?(?:solicitud|asunto|descripcion|comentario|system|instrucciones)\b",
    )
]
# En la salida además: enlaces (una respuesta de soporte sugerida no debe inventar enlaces).
_SENALES_SALIDA = _SENALES + [re.compile(r"https?://|www\.", re.I)]


def neutralizar(texto: str | None, limite: int = MAX_CARACTERES) -> str:
    """Impide que el texto cierre o abra etiquetas del contexto y lo recorta."""
    t = (texto or "")[:limite]
    return t.replace("<", "‹").replace(">", "›")


@dataclass
class Seudonimizador:
    """Cambia datos personales por marcadores y permite revertirlos en la respuesta."""

    nombres: dict[str, str] = field(default_factory=dict)   # valor real -> marcador
    _mapa: dict[str, str] = field(default_factory=dict)      # marcador -> valor real
    _n: dict[str, int] = field(default_factory=dict)

    def nombre(self, valor: str | None, marcador: str | None = None) -> str:
        """Registra un nombre conocido (solicitante, cliente, autor) y devuelve su marcador."""
        v = (valor or "").strip()
        if not v:
            return marcador and f"[{marcador}]" or ""
        if v in self.nombres:
            return self.nombres[v]
        etiqueta = f"[{marcador}]" if marcador else self._nuevo("PERSONA")
        self.nombres[v] = etiqueta
        self._mapa[etiqueta] = v
        return etiqueta

    def _nuevo(self, tipo: str) -> str:
        self._n[tipo] = self._n.get(tipo, 0) + 1
        return f"[{tipo}_{self._n[tipo]}]"

    def _patron(self, texto: str, regex: re.Pattern, tipo: str) -> str:
        def cambiar(mt: re.Match) -> str:
            v = mt.group(0)
            if v not in self.nombres:
                etq = self._nuevo(tipo)
                self.nombres[v] = etq
                self._mapa[etq] = v
            return self.nombres[v]

        return regex.sub(cambiar, texto)

    def aplicar(self, texto: str | None) -> str:
        t = texto or ""
        t = self._patron(t, _CORREO, "CORREO")
        t = self._patron(t, _IDENTIFICACION, "ID")
        t = self._patron(t, _TELEFONO, "TELEFONO")
        # Nombres conocidos (más largos primero para no partir nombres compuestos).
        for real in sorted((k for k in self.nombres if not k.startswith("[")), key=len, reverse=True):
            if len(real) >= 3 and not real.isdigit() and "@" not in real:
                t = re.sub(re.escape(real), self.nombres[real], t, flags=re.I)
        return t

    def revertir(self, texto: str) -> str:
        for etq, real in self._mapa.items():
            texto = texto.replace(etq, real)
        return texto


def entrada_sospechosa(texto: str) -> bool:
    """True si el texto del ticket parece intentar dar instrucciones al modelo (R13)."""
    return any(p.search(texto or "") for p in _SENALES)


def salida_anomala(texto: str) -> bool:
    """True si la salida del modelo muestra señales de manipulación (R13); se descarta."""
    return any(p.search(texto or "") for p in _SENALES_SALIDA)
