"""Motor de IA local: funciona sin conexión a internet (on-premise).

Clasificación por palabras clave del catálogo, prioridad por reglas, riesgo de
incumplimiento por proyección y resumen extractivo. Las palabras clave se editan
desde Administración → Categorías, sin tocar código.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sin_tildes.lower())).strip()


@dataclass
class SubcatIA:
    id: int
    nombre: str
    palabras: list[str]


@dataclass
class CategoriaIA:
    id: int
    nombre: str
    palabras: list[str]
    subcategorias: list[SubcatIA] = field(default_factory=list)


@dataclass
class Clasificacion:
    categoria_id: int
    categoria: str
    subcategoria_id: int
    subcategoria: str
    confianza: float
    motivos: list[str]


TERMINOS_URGENTES = {
    "urgente": 3, "inmediato": 3, "hoy mismo": 3, "retenido": 2, "retenida": 2, "retencion": 2, "canal rojo": 2,
    "aforo fisico": 2, "multa": 2, "sancion": 2, "plazo vence": 3, "vence hoy": 3, "manana vence": 2, "demanda": 2,
    "bodegaje": 1, "demoraje": 2, "contenedor en puerto": 2, "embargo": 3, "clausura": 3,
}
TERMINOS_BAJA = {"consulta general": 2, "informacion": 1, "cotizacion": 1, "cuando pueda": 2, "sin prisa": 2, "capacitacion": 1}


def _contiene(texto: str, frase: str) -> bool:
    return re.search(rf"\b{re.escape(frase)}\b", texto) is not None


class MotorIALocal:
    proveedor = "LOCAL"

    # ------------------------------------------------------------ clasificar
    def clasificar(self, texto: str, catalogo: list[CategoriaIA], top: int = 3) -> list[Clasificacion]:
        t = normalizar(texto)
        puntajes: list[tuple[float, CategoriaIA, SubcatIA, list[str]]] = []
        for cat in catalogo:
            hits_cat = [p for p in cat.palabras if p and _contiene(t, normalizar(p))]
            base_cat = sum(2 if " " in p else 1 for p in hits_cat)
            for sub in cat.subcategorias:
                frases = {normalizar(p) for p in sub.palabras if p} | {normalizar(sub.nombre)}
                hits_sub = [f for f in frases if f and _contiene(t, f)]
                puntaje = base_cat + sum(4 if " " in f else 3 for f in hits_sub)
                if puntaje:
                    puntajes.append((puntaje, cat, sub, hits_sub + hits_cat))
        if not puntajes:
            return []
        puntajes.sort(key=lambda x: x[0], reverse=True)
        total = sum(p[0] for p in puntajes[:5]) + 2
        return [
            Clasificacion(c.id, c.nombre, s.id, s.nombre, round(min(0.97, p / total + 0.15), 2), sorted(set(m))[:6])
            for p, c, s, m in puntajes[:top]
        ]

    # ------------------------------------------------------------- prioridad
    def sugerir_prioridad(self, texto: str, cliente_vip: bool = False) -> tuple[str, float, list[str]]:
        t = normalizar(texto)
        urg = [(k, v) for k, v in TERMINOS_URGENTES.items() if _contiene(t, k)]
        baja = [(k, v) for k, v in TERMINOS_BAJA.items() if _contiene(t, k)]
        puntaje = sum(v for _, v in urg) - sum(v for _, v in baja)
        motivos = [f"menciona «{k}»" for k, _ in urg + baja]
        niveles = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
        idx = 0 if puntaje <= -2 else 1 if puntaje <= 1 else 2 if puntaje <= 4 else 3
        if cliente_vip and idx < 3:
            idx += 1
            motivos.append("cliente VIP")
        confianza = 0.55 if not motivos else min(0.92, 0.6 + 0.08 * len(motivos))
        return niveles[idx], round(confianza, 2), motivos or ["sin señales de urgencia: prioridad estándar"]

    # ------------------------------------------------------------- respuesta
    def respuesta_sugerida(self, plantilla: str | None, contexto: dict[str, str]) -> str:
        texto = plantilla or (
            "Estimado/a {solicitante}: hemos recibido su solicitud {numero}. {responsable} la está revisando "
            "y le informaremos los próximos pasos a la brevedad."
        )
        for k, v in contexto.items():
            texto = texto.replace("{" + k + "}", v or "")
        return texto

    # ---------------------------------------------------------------- riesgo
    def riesgo_incumplimiento(
        self, porcentaje: float, carga_responsable: int, sin_primera_respuesta: bool, escalado: bool, sin_responsable: bool
    ) -> tuple[float, str, list[str]]:
        """Probabilidad heurística (0-100) de incumplir el SLA de resolución."""
        motivos = []
        r = 0.65 * min(porcentaje, 100)
        if porcentaje >= 75:
            motivos.append(f"SLA consumido al {porcentaje:.0f} %")
        if carga_responsable > 6:
            r += min(15, (carga_responsable - 6) * 2.5)
            motivos.append(f"responsable con {carga_responsable} tickets abiertos")
        if sin_primera_respuesta and porcentaje > 15:
            r += 10
            motivos.append("sin primera respuesta")
        if escalado:
            r += 5
            motivos.append("ticket escalado")
        if sin_responsable:
            r += 10
            motivos.append("sin responsable asignado")
        r = round(min(r, 100), 1)
        nivel = "ALTO" if r >= 70 else "MEDIO" if r >= 40 else "BAJO"
        return r, nivel, motivos or ["avance dentro de lo esperado"]

    # --------------------------------------------------------------- resumen
    def resumir(self, asunto: str, descripcion: str, comentarios: list[tuple[str, str]], estado: str, porcentaje: float) -> str:
        oraciones = re.split(r"(?<=[.!?])\s+", (descripcion or "").strip())
        partes = [f"{asunto}.", " ".join(oraciones[:2])]
        if comentarios:
            autor, texto = comentarios[-1]
            partes.append(f"Último comentario de {autor}: «{texto[:180]}{'…' if len(texto) > 180 else ''}».")
        partes.append(f"Estado: {estado}; SLA consumido {porcentaje:.0f} %; {len(comentarios)} comentario(s).")
        return " ".join(p for p in partes if p).strip()[:1000]
