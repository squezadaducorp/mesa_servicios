"""Respuestas rápidas: textos guardados que el equipo inserta en la respuesta de un ticket."""
from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import mejoras2 as s
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.conocimiento_service import es_mesa
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Permiso
from app.infrastructure.db import models as m


def fecha_local(d) -> str:
    if d is None:
        return ""
    return d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")


def rellenar(texto: str, t: m.Ticket, u: m.Usuario) -> str:
    """Reemplaza {solicitante}, {ticket}, {asunto}, {mi_nombre}, {mi_area}, {vence}… con los datos del ticket."""
    datos = {
        "solicitante": (t.solicitante_nombre or "").split(" ")[0] if t.solicitante_nombre else "",
        "solicitante_completo": t.solicitante_nombre or "",
        "ticket": t.numero, "numero": t.numero, "asunto": t.asunto,
        "mi_nombre": u.nombre, "mi_area": u.area.nombre if u.area else "Mesa de Servicios",
        "responsable": t.responsable.nombre if t.responsable else u.nombre,
        "vence": fecha_local(t.sla_resolucion_vence), "categoria": t.categoria.nombre if t.categoria else "",
    }
    for k, v in datos.items():
        texto = texto.replace("{" + k + "}", v)
    return texto


class RespuestasService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    def _disponibles(self, u: m.Usuario):
        R = m.RespuestaRapida
        return select(R).where(R.activo == True, or_(
            R.alcance == "TODOS",
            and_(R.alcance == "AREA", R.area_id == u.area_id),
            and_(R.alcance == "PERSONAL", R.propietario_id == u.id),
        ))

    def puede_editar(self, u: m.Usuario, r: m.RespuestaRapida) -> bool:
        if r.alcance == "PERSONAL":
            return r.propietario_id == u.id
        return u.tiene(Permiso.RESPUESTAS_GESTIONAR)

    def salida(self, r: m.RespuestaRapida, u: m.Usuario) -> dict:
        return {
            "id": r.id, "atajo": r.atajo, "titulo": r.titulo, "texto": r.texto, "categoria_id": r.categoria_id,
            "subcategoria_id": r.subcategoria_id, "categoria": r.categoria.nombre if r.categoria else None,
            "subcategoria": r.subcategoria.nombre if r.subcategoria else None, "estado_destino": r.estado_destino,
            "alcance": r.alcance, "area_id": r.area_id, "area": r.area.nombre if r.area else None,
            "propietario_id": r.propietario_id, "propietario": r.propietario.nombre if r.propietario else None,
            "usos": r.usos, "activo": r.activo, "puede_editar": self.puede_editar(u, r),
        }

    def listar(self, u: m.Usuario, todas: bool = False) -> list[m.RespuestaRapida]:
        R = m.RespuestaRapida
        if todas and u.tiene(Permiso.RESPUESTAS_GESTIONAR):
            stmt = select(R).where(or_(R.alcance != "PERSONAL", R.propietario_id == u.id))
        else:
            stmt = self._disponibles(u)
        return list(self.session.scalars(stmt.order_by(R.usos.desc(), R.atajo)).unique())

    def para_ticket(self, t: m.Ticket, u: m.Usuario) -> list[dict]:
        """Respuestas disponibles para este ticket, primero las de su subcategoría y categoría."""
        if not es_mesa(u):
            return []
        filas = []
        for r in self.listar(u):
            if r.subcategoria_id and r.subcategoria_id != t.subcategoria_id:
                continue   # pertenece a otra subcategoría: no aplica a este ticket
            if r.categoria_id and r.categoria_id != t.categoria_id:
                continue
            sugerida = bool(r.subcategoria_id or r.categoria_id)
            orden = 0 if r.subcategoria_id else 1 if r.categoria_id else 2
            filas.append((orden, -r.usos, {
                "id": r.id, "atajo": r.atajo, "titulo": r.titulo, "texto": rellenar(r.texto, t, u),
                "estado_destino": r.estado_destino, "sugerida": sugerida, "alcance": r.alcance, "usos": r.usos,
            }))
        return [f[2] for f in sorted(filas, key=lambda f: (f[0], f[1]))]

    def registrar_uso(self, respuesta_id: int, u: m.Usuario) -> m.RespuestaRapida | None:
        r = self.session.scalar(self._disponibles(u).where(m.RespuestaRapida.id == respuesta_id))
        if r is not None:
            r.usos += 1
            r.ultimo_uso = utcnow()
        return r

    def guardar(self, dto: s.RespuestaEntrada, ctx: Contexto, respuesta_id: int | None = None) -> m.RespuestaRapida:
        u = ctx.usuario
        if not es_mesa(u):
            raise Prohibido("Solo el equipo de la mesa usa respuestas rápidas")
        if dto.alcance != "PERSONAL" and not u.tiene(Permiso.RESPUESTAS_GESTIONAR):
            raise Prohibido("Solo puede guardar respuestas personales («Solo yo»)")
        if dto.alcance == "AREA" and not dto.area_id:
            raise ReglaNegocio("Indique el área que puede usar la respuesta")
        if dto.subcategoria_id:
            sub = self.session.get(m.Subcategoria, dto.subcategoria_id)
            if sub is None or (dto.categoria_id and sub.categoria_id != dto.categoria_id):
                raise ReglaNegocio("La subcategoría no pertenece a la categoría")
            dto.categoria_id = sub.categoria_id
        if respuesta_id is None:
            r = m.RespuestaRapida(fecha_creacion=utcnow())
        else:
            r = self.session.get(m.RespuestaRapida, respuesta_id)
            if r is None:
                raise NoEncontrado("Respuesta no encontrada")
            if not self.puede_editar(u, r):
                raise Prohibido("No puede editar esta respuesta")
        R = m.RespuestaRapida
        repetida = self.session.scalar(self._disponibles(u).where(R.atajo == dto.atajo, R.id != (respuesta_id or 0)))
        if repetida is not None:
            raise Conflicto(f"El atajo {dto.atajo} ya existe («{repetida.titulo}»)")
        for k, v in dto.model_dump().items():
            setattr(r, k, v.strip() if isinstance(v, str) else v)
        r.propietario_id = u.id if dto.alcance == "PERSONAL" else None
        r.area_id = dto.area_id if dto.alcance == "AREA" else None
        if respuesta_id is None:
            self.session.add(r)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.RESPUESTA_RAPIDA_MODIFICADA, "respuesta_rapida", r.id,
                                 {"atajo": r.atajo, "alcance": r.alcance, "activo": r.activo})
        self.session.refresh(r)
        return r
