"""Proveedor LLM opcional (Claude, vía SDK oficial de Anthropic).

Se activa con AI_PROVIDER=llm y ANTHROPIC_API_KEY. Atención: el texto del ticket
sale de la red de ADUCORP hacia la API de Anthropic. Ante cualquier error o
rechazo, el servicio de IA vuelve al motor local.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.config import settings
from app.infrastructure.ai.local import CategoriaIA

log = logging.getLogger(__name__)

SISTEMA = (
    "Eres el asistente de la Mesa de Servicios de ADUCORP, agencia de aduanas de Ecuador "
    "(SENAE, Ecuapass, COPCI). Respondes siempre en español, con tono profesional y conciso."
)


class _Clasificacion(BaseModel):
    subcategoria_id: int = Field(description="Id de la subcategoría elegida del catálogo")
    confianza: float = Field(description="Confianza entre 0 y 1")
    motivo: str


class _Texto(BaseModel):
    texto: str


class ProveedorClaude:
    proveedor = "LLM"

    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None, timeout=30, max_retries=1)
        self.modelo = settings.AI_MODEL

    def _parse(self, prompt: str, formato: type[BaseModel], max_tokens: int = 2000):
        r = self.client.messages.parse(
            model=self.modelo,
            max_tokens=max_tokens,
            system=SISTEMA,
            messages=[{"role": "user", "content": prompt}],
            output_format=formato,
        )
        if r.stop_reason == "refusal" or r.parsed_output is None:
            raise RuntimeError(f"Respuesta no utilizable del modelo (stop_reason={r.stop_reason})")
        return r.parsed_output

    def clasificar(self, texto: str, catalogo: list[CategoriaIA]) -> tuple[int, float, str]:
        lineas = [f"- [{s.id}] {c.nombre} / {s.nombre}" for c in catalogo for s in c.subcategorias]
        prompt = (
            "Clasifica la solicitud en UNA subcategoría del catálogo.\n\nCatálogo (id entre corchetes):\n"
            + "\n".join(lineas)
            + f"\n\nSolicitud:\n<solicitud>\n{texto}\n</solicitud>"
        )
        out = self._parse(prompt, _Clasificacion, 1000)
        return out.subcategoria_id, max(0.0, min(out.confianza, 1.0)), out.motivo

    def respuesta(self, contexto: str) -> str:
        prompt = (
            "Redacta una respuesta inicial breve (máximo 120 palabras) para el solicitante del ticket. "
            "No inventes plazos ni resultados; pide la documentación que falte si aplica.\n\n" + contexto
        )
        return self._parse(prompt, _Texto).texto

    def resumen(self, contexto: str) -> str:
        prompt = "Resume el ticket en un máximo de 3 oraciones: qué se pide, qué se hizo y qué falta.\n\n" + contexto
        return self._parse(prompt, _Texto).texto[:1000]
