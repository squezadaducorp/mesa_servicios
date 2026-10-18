"""Inteligencia artificial: clasificación, prioridad, responsable, respuesta, riesgo y resumen."""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado
from app.infrastructure.ai.local import CategoriaIA, Clasificacion, MotorIALocal, SubcatIA
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, TicketRepository, UsuarioRepository

log = logging.getLogger(__name__)


def _palabras(texto: str | None) -> list[str]:
    return [p.strip() for p in (texto or "").split(",") if p.strip()]


class IaService:
    def __init__(self, session: Session):
        self.session = session
        self.local = MotorIALocal()
        self.catalogo = CatalogoRepository(session)
        self._llm = None
        if settings.AI_PROVIDER == "llm" and settings.ANTHROPIC_API_KEY:
            try:
                from app.infrastructure.ai.claude import ProveedorClaude

                self._llm = ProveedorClaude()
            except Exception:   # SDK no instalado o mal configurado: se queda en modo local
                log.exception("No se pudo iniciar el proveedor LLM; se usa el motor local")

    def _catalogo_ia(self) -> list[CategoriaIA]:
        return [
            CategoriaIA(c.id, c.nombre, _palabras(c.palabras_clave),
                        [SubcatIA(s.id, s.nombre, _palabras(s.palabras_clave)) for s in c.subcategorias if s.activo and not s.eliminado])
            for c in self.catalogo.categorias()
        ]

    def _guardar(self, tipo: str, valor, confianza: float | None, proveedor: str, ticket_id: int | None = None, usuario_id: int | None = None):
        self.session.add(
            m.IaSugerencia(ticket_id=ticket_id, tipo=tipo, valor=json.dumps(valor, ensure_ascii=False, default=str),
                           confianza=Decimal(str(round(confianza, 2))) if confianza is not None else None,
                           proveedor=proveedor, usuario_id=usuario_id, fecha=utcnow())
        )

    # ------------------------------------------------------- clasificación
    def clasificar(self, texto: str) -> tuple[list[Clasificacion], str]:
        catalogo = self._catalogo_ia()
        if self._llm:
            try:
                sub_id, conf, motivo = self._llm.clasificar(texto, catalogo)
                for c in catalogo:
                    for s in c.subcategorias:
                        if s.id == sub_id:
                            locales = [x for x in self.local.clasificar(texto, catalogo) if x.subcategoria_id != sub_id][:2]
                            return [Clasificacion(c.id, c.nombre, s.id, s.nombre, round(conf, 2), [motivo]), *locales], "LLM"
            except Exception:
                log.exception("Fallo de clasificación LLM; se usa el motor local")
        return self.local.clasificar(texto, catalogo), "LOCAL"

    def sugerir_responsable(self, categoria: m.Categoria) -> m.Usuario | None:
        candidatos = [r for r in categoria.responsables if r.usuario.activo and not r.usuario.eliminado]
        if not candidatos or categoria.modo_asignacion == "MANUAL":
            return None
        if categoria.modo_asignacion == "PRINCIPAL" or len(candidatos) == 1:
            principal = next((r for r in candidatos if r.es_principal), candidatos[0])
            return principal.usuario
        carga = UsuarioRepository(self.session).carga_abierta([r.usuario_id for r in candidatos])
        return min(candidatos, key=lambda r: (carga[r.usuario_id], not r.es_principal, r.usuario_id)).usuario

    def sugerir_ticket(self, asunto: str, descripcion: str, cliente_id: int | None, usuario_id: int | None) -> dict:
        texto = f"{asunto}. {descripcion}"
        clasificaciones, proveedor = self.clasificar(texto)
        cliente = self.session.get(m.Cliente, cliente_id) if cliente_id else None
        prio, conf_p, motivos_p = self.local.sugerir_prioridad(texto, bool(cliente and cliente.es_vip))
        prioridad = self.catalogo.prioridad_por_codigo(prio)
        responsable = None
        if clasificaciones:
            cat = self.catalogo.categoria(clasificaciones[0].categoria_id)
            responsable = self.sugerir_responsable(cat) if cat else None
            self._guardar("CLASIFICACION", clasificaciones[0].__dict__, clasificaciones[0].confianza, proveedor, usuario_id=usuario_id)
        self._guardar("PRIORIDAD", {"prioridad": prio, "motivos": motivos_p}, conf_p, "LOCAL", usuario_id=usuario_id)
        return {
            "proveedor": proveedor,
            "clasificaciones": [c.__dict__ for c in clasificaciones],
            "prioridad": prio,
            "prioridad_id": prioridad.id if prioridad else None,
            "prioridad_confianza": conf_p,
            "prioridad_motivos": motivos_p,
            "responsable": responsable,
        }

    # ------------------------------------------------------------ respuesta
    def respuesta_sugerida(self, t: m.Ticket, usuario_id: int | None) -> tuple[str, str]:
        if self._llm:
            try:
                texto = self._llm.respuesta(self._contexto(t))
                self._guardar("RESPUESTA", {"texto": texto}, None, "LLM", t.id, usuario_id)
                return texto, "LLM"
            except Exception:
                log.exception("Fallo de respuesta LLM; se usa plantilla")
        texto = self.local.respuesta_sugerida(
            t.subcategoria.respuesta_plantilla,
            {"solicitante": t.solicitante_nombre, "numero": t.numero, "responsable": t.responsable.nombre if t.responsable else "Nuestro equipo"},
        )
        self._guardar("RESPUESTA", {"texto": texto}, None, "LOCAL", t.id, usuario_id)
        return texto, "LOCAL"

    # -------------------------------------------------------------- resumen
    def resumen(self, t: m.Ticket, usuario_id: int | None = None) -> tuple[str, str]:
        comentarios = TicketRepository(self.session).comentarios(t.id, incluir_internos=True)
        texto, proveedor = None, "LOCAL"
        if self._llm:
            try:
                texto, proveedor = self._llm.resumen(self._contexto(t, comentarios)), "LLM"
            except Exception:
                log.exception("Fallo de resumen LLM; se usa resumen extractivo")
        if texto is None:
            texto = self.local.resumir(t.asunto, t.descripcion, [(c.usuario.nombre, c.texto) for c in comentarios],
                                       t.estado_rel.nombre, float(t.sla_consumido_pct or 0))
        t.resumen_ia = texto[:1000]
        self._guardar("RESUMEN", {"texto": texto}, None, proveedor, t.id, usuario_id)
        return texto, proveedor

    # --------------------------------------------------------------- riesgo
    def riesgo(self, t: m.Ticket, carga: int | None = None) -> tuple[float, str, list[str]]:
        if carga is None and t.responsable_id:
            carga = UsuarioRepository(self.session).carga_abierta([t.responsable_id])[t.responsable_id]
        r, nivel, motivos = self.local.riesgo_incumplimiento(
            float(t.sla_consumido_pct or 0), carga or 0, t.fecha_primera_respuesta is None,
            t.estado == Estado.ESCALADO, t.responsable_id is None,
        )
        t.riesgo_ia = Decimal(str(r))
        return r, nivel, motivos

    def _contexto(self, t: m.Ticket, comentarios: list[m.TicketComentario] | None = None) -> str:
        partes = [
            f"Ticket {t.numero} · {t.categoria.nombre} / {t.subcategoria.nombre} · prioridad {t.prioridad.nombre} · estado {t.estado_rel.nombre}",
            f"Solicitante: {t.solicitante_nombre}" + (f" · Cliente: {t.cliente.razon_social}" if t.cliente else ""),
            f"<asunto>{t.asunto}</asunto>",
            f"<descripcion>{t.descripcion}</descripcion>",
        ]
        for c in (comentarios or [])[-10:]:
            partes.append(f"<comentario autor=\"{c.usuario.nombre}\">{c.texto}</comentario>")
        return "\n".join(partes)
