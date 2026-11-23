"""Base de conocimiento: artículos con soluciones frecuentes que se sugieren antes de crear un ticket."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import mejoras2 as s
from app.application.services.auditoria_service import AuditoriaService
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Permiso, Rol
from app.infrastructure.ai.local import normalizar
from app.infrastructure.db import models as m

ROLES_MESA = {Rol.ANALISTA, Rol.SUPERVISOR, Rol.ADMIN_MESA, Rol.SUPER_ADMIN}
PALABRAS_VACIAS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y", "o", "que", "se", "no", "me", "mi", "mis",
    "por", "para", "con", "sin", "es", "esta", "este", "esto", "lo", "le", "su", "sus", "ya", "pero", "como", "cuando", "dice", "sale",
    "tengo", "puedo", "hay", "muy", "mas", "desde", "hoy", "favor", "ayuda", "buenos", "dias", "tardes", "hola", "gracias",
}


def es_mesa(u: m.Usuario) -> bool:
    return u.rol.codigo in ROLES_MESA


ROLES_PUBLICAN_EXTERNO = {Rol.SUPERVISOR, Rol.ADMIN_MESA, Rol.SUPER_ADMIN}
ENLACE_ARTICULO = re.compile(r"conocimiento\?articulo=(\d+)")


def es_personal(u: m.Usuario) -> bool:
    """Personal de Aducorp (35): todo rol salvo Cliente. Ve los artículos internos; la base de conocimiento es de toda la empresa."""
    return u.rol.codigo != Rol.CLIENTE


def exigir_sin_internos(session: Session, texto: str) -> None:
    """Una respuesta al solicitante nunca lleva el enlace de un artículo interno."""
    for aid in dict.fromkeys(int(x) for x in ENLACE_ARTICULO.findall(texto or "")):
        a = session.get(m.KbArticulo, aid)
        if a is not None and a.visibilidad == "INTERNO":
            raise ReglaNegocio(f"La respuesta enlaza el artículo interno «{a.titulo}». Envíe una versión externa o quite el enlace.")


def palabras(texto: str | None) -> set[str]:
    return {p for p in normalizar(texto or "").split() if len(p) > 2 and p not in PALABRAS_VACIAS}


def util_pct(a: m.KbArticulo) -> int | None:
    total = a.util_si + a.util_no
    return round(100 * a.util_si / total) if total else None


def extracto(texto: str, largo: int = 180) -> str:
    plano = re.sub(r"\s+", " ", texto or "").strip()
    return plano if len(plano) <= largo else plano[: largo - 1].rstrip() + "…"


def resumen(a: m.KbArticulo) -> dict:
    return {
        "id": a.id, "titulo": a.titulo, "categoria_id": a.categoria_id, "categoria": a.categoria.nombre if a.categoria else None,
        "subcategoria": a.subcategoria.nombre if a.subcategoria else None, "estado": a.estado, "visibilidad": a.visibilidad,
        "vistas": a.vistas, "util_pct": util_pct(a), "tickets_evitados": a.tickets_evitados,
        "extracto": extracto(a.sintoma or a.solucion),
    }


class ConocimientoService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ------------------------------------------------------------ visibilidad
    def _visibles(self, u: m.Usuario, incluir_borradores: bool):
        A = m.KbArticulo
        stmt = select(A).where(A.eliminado == False)
        if not es_personal(u):
            stmt = stmt.where(A.estado == "PUBLICADO", A.visibilidad == "EXTERNO")
        elif not incluir_borradores or not u.tiene(Permiso.KB_GESTIONAR):   # los borradores solo los ve quien escribe
            stmt = stmt.where(A.estado == "PUBLICADO")
        return stmt

    def obtener(self, articulo_id: int, u: m.Usuario) -> m.KbArticulo:
        a = self.session.scalar(self._visibles(u, True).where(m.KbArticulo.id == articulo_id))
        if a is None:
            raise NoEncontrado("Artículo no encontrado")
        return a

    def puede_editar(self, u: m.Usuario) -> bool:
        return u.tiene(Permiso.KB_GESTIONAR) and es_personal(u)

    @staticmethod
    def puede_publicar_externo(u: m.Usuario) -> bool:
        return u.rol.codigo in ROLES_PUBLICAN_EXTERNO

    def salida(self, a: m.KbArticulo, u: m.Usuario) -> dict:
        origen = self.session.get(m.Ticket, a.ticket_origen_id) if a.ticket_origen_id else None
        rel = self.session.get(m.KbArticulo, a.articulo_relacionado_id) if a.articulo_relacionado_id else None
        if rel is not None and (rel.eliminado or (rel.visibilidad == "INTERNO" and not es_personal(u))):
            rel = None
        return {
            "articulo_relacionado_id": rel.id if rel else None, "articulo_relacionado": rel.titulo if rel else None,
            "puede_publicar_externo": self.puede_publicar_externo(u),
            **resumen(a), "sintoma": a.sintoma, "solucion": a.solucion, "nota": a.nota, "palabras_clave": a.palabras_clave,
            "subcategoria_id": a.subcategoria_id, "ticket_origen_id": a.ticket_origen_id,
            "ticket_origen_numero": origen.numero if origen else None, "util_si": a.util_si, "util_no": a.util_no,
            "actualizado_por": a.autor.nombre if a.autor else None, "fecha_actualizacion": a.fecha_actualizacion,
            "fecha_creacion": a.fecha_creacion, "puede_editar": self.puede_editar(u),
        }

    # ----------------------------------------------------------------- listar
    def listar(self, u: m.Usuario, texto: str | None, categoria_id: int | None, estado: str | None) -> list[m.KbArticulo]:
        A = m.KbArticulo
        stmt = self._visibles(u, True)
        if categoria_id:
            stmt = stmt.where(A.categoria_id == categoria_id)
        if estado:
            stmt = stmt.where(A.estado == estado)
        elif not es_personal(u) or not u.tiene(Permiso.KB_GESTIONAR):
            stmt = stmt.where(A.estado == "PUBLICADO")
        else:
            stmt = stmt.where(A.estado != "ARCHIVADO")
        articulos = list(self.session.scalars(stmt.order_by(A.tickets_evitados.desc(), A.vistas.desc(), A.id.desc())).unique())
        if texto and texto.strip():
            buscadas = palabras(texto)
            if buscadas:
                puntuados = [(self._puntaje(a, buscadas), a) for a in articulos]
                return [a for p, a in sorted(puntuados, key=lambda x: -x[0]) if p > 0]
        return articulos

    @staticmethod
    def _puntaje(a: m.KbArticulo, buscadas: set[str]) -> float:
        titulo = palabras(a.titulo)
        claves = palabras((a.palabras_clave or "").replace(",", " "))
        cuerpo = palabras(f"{a.sintoma or ''} {a.solucion}")
        p = 0.0
        for w in buscadas:
            if w in titulo:
                p += 3
            if w in claves:
                p += 2.5
            if w in cuerpo:
                p += 1
        return p

    def sugerir(self, u: m.Usuario, dto: s.KbSugerirEntrada, limite: int = 3) -> list[dict]:
        """Artículos publicados que podrían resolver lo que la persona está escribiendo."""
        buscadas = palabras(dto.texto)
        if len(buscadas) < 2:
            return []
        candidatos = list(self.session.scalars(self._visibles(u, False)).unique())
        puntuados = []
        for a in candidatos:
            p = self._puntaje(a, buscadas)
            if dto.subcategoria_id and a.subcategoria_id == dto.subcategoria_id:
                p += 2
            elif dto.categoria_id and a.categoria_id == dto.categoria_id:
                p += 1
            pct = util_pct(a)
            if pct is not None:
                p *= 0.75 + pct / 400   # 0,75 a 1,0 según cuán útil resultó
            if p >= 4:
                puntuados.append((p, a))
        puntuados.sort(key=lambda x: -x[0])
        return [{**resumen(a), "extracto": extracto(a.solucion, 220)} for _, a in puntuados[:limite]]

    # -------------------------------------------------------------- acciones
    def ver(self, articulo_id: int, u: m.Usuario) -> m.KbArticulo:
        a = self.obtener(articulo_id, u)
        if a.estado == "PUBLICADO":
            a.vistas += 1
        return a

    def votar(self, articulo_id: int, util: bool, u: m.Usuario) -> m.KbArticulo:
        a = self.obtener(articulo_id, u)
        if util:
            a.util_si += 1
        else:
            a.util_no += 1
        return a

    def evitar_ticket(self, articulo_id: int, u: m.Usuario) -> m.KbArticulo:
        """La persona tocó «Se resolvió, no crear ticket»."""
        a = self.obtener(articulo_id, u)
        a.tickets_evitados += 1
        a.util_si += 1
        return a

    def registrar_vistos(self, ticket_id: int, articulo_ids: list[int]) -> None:
        for aid in dict.fromkeys(articulo_ids[:10]):
            a = self.session.get(m.KbArticulo, aid)
            if a is not None and not a.eliminado and self.session.get(m.KbTicketVisto, (ticket_id, aid)) is None:
                self.session.add(m.KbTicketVisto(ticket_id=ticket_id, articulo_id=aid))
                a.util_no += 1   # lo leyó y aun así necesitó crear el ticket

    def vistos(self, ticket_id: int) -> list[dict]:
        filas = self.session.scalars(
            select(m.KbArticulo).join(m.KbTicketVisto, m.KbTicketVisto.articulo_id == m.KbArticulo.id)
            .where(m.KbTicketVisto.ticket_id == ticket_id)
        ).unique()
        return [{"id": a.id, "nombre": a.titulo} for a in filas]

    # ------------------------------------------------------------ administrar
    def _validar(self, dto: s.KbEntrada) -> None:
        if dto.categoria_id and self.session.get(m.Categoria, dto.categoria_id) is None:
            raise ReglaNegocio("Categoría no válida")
        if dto.subcategoria_id:
            sub = self.session.get(m.Subcategoria, dto.subcategoria_id)
            if sub is None or (dto.categoria_id and sub.categoria_id != dto.categoria_id):
                raise ReglaNegocio("La subcategoría no pertenece a la categoría")
        if dto.ticket_origen_id and self.session.get(m.Ticket, dto.ticket_origen_id) is None:
            raise ReglaNegocio("Ticket de origen no válido")
        if dto.articulo_relacionado_id:
            rel = self.session.get(m.KbArticulo, dto.articulo_relacionado_id)
            if rel is None or rel.eliminado:
                raise ReglaNegocio("Artículo relacionado no válido")

    def guardar(self, dto: s.KbEntrada, ctx: Contexto, articulo_id: int | None = None) -> m.KbArticulo:
        u = ctx.usuario
        if not self.puede_editar(u):
            raise Prohibido("No tiene permiso para editar la base de conocimiento")
        self._validar(dto)
        if dto.estado == "PUBLICADO" and dto.visibilidad == "EXTERNO" and not self.puede_publicar_externo(u):
            raise Prohibido("Los artículos externos los publica un supervisor. Guárdelo como borrador para que lo revise.")
        ahora = utcnow()
        if articulo_id is None:
            a = m.KbArticulo(creado_por=u.id, fecha_creacion=ahora)
            self.session.add(a)
        else:
            a = self.obtener(articulo_id, u)
        datos = dto.model_dump()
        if datos["subcategoria_id"] and not datos["categoria_id"]:
            datos["categoria_id"] = self.session.get(m.Subcategoria, datos["subcategoria_id"]).categoria_id
        for k, v in datos.items():
            setattr(a, k, v.strip() if isinstance(v, str) else v)
        a.actualizado_por, a.fecha_actualizacion = u.id, ahora
        self.session.flush()
        if a.articulo_relacionado_id and a.articulo_relacionado_id != a.id:
            rel = self.session.get(m.KbArticulo, a.articulo_relacionado_id)
            if rel.articulo_relacionado_id is None:   # el vínculo queda en los dos sentidos
                rel.articulo_relacionado_id = a.id
        self.auditoria.registrar(ctx, AccionAuditoria.KB_MODIFICADO, "kb_articulo", a.id, {"titulo": a.titulo, "estado": a.estado})
        self.session.refresh(a)
        return a

    def eliminar(self, articulo_id: int, ctx: Contexto) -> None:
        if not self.puede_editar(ctx.usuario):
            raise Prohibido("No tiene permiso para editar la base de conocimiento")
        a = self.obtener(articulo_id, ctx.usuario)
        a.eliminado = True
        self.auditoria.registrar(ctx, AccionAuditoria.KB_MODIFICADO, "kb_articulo", a.id, {"titulo": a.titulo, "eliminado": True})

    def borrador_desde_ticket(self, ticket_id: int, ctx: Contexto) -> dict:
        """Propone un artículo a partir de un ticket resuelto (no se guarda hasta que lo confirmen)."""
        from app.application.services.ticket_service import TicketService

        if not self.puede_editar(ctx.usuario):
            raise Prohibido("No tiene permiso para editar la base de conocimiento")
        t = TicketService(self.session).obtener(ticket_id, ctx.usuario)
        if t.estado not in ("RESUELTO", "CERRADO"):
            raise ReglaNegocio("Solo se pueden usar tickets resueltos o cerrados")
        if t.clasificacion == "CONFIDENCIAL":   # (42) lo confidencial no alimenta la base de conocimiento
            raise ReglaNegocio("Un ticket confidencial no se puede usar para un artículo de la base de conocimiento")
        respuestas = [c for c in self.session.scalars(
            select(m.TicketComentario).where(m.TicketComentario.ticket_id == t.id, m.TicketComentario.es_interno == False,
                                             m.TicketComentario.usuario_id != t.solicitante_id)
            .order_by(m.TicketComentario.fecha.desc())).unique()]
        solucion = respuestas[0].texto if respuestas else ""
        return {"titulo": t.asunto, "sintoma": extracto(t.descripcion, 1000), "solucion": solucion,
                "categoria_id": t.categoria_id, "subcategoria_id": t.subcategoria_id, "ticket_origen_id": t.id,
                "ticket_origen_numero": t.numero, "palabras_clave": None}

    def categorias_con_conteo(self, u: m.Usuario) -> list[dict]:
        conteo: dict[int | None, int] = {}
        nombres: dict[int | None, str] = {}
        for a in self.listar(u, None, None, None):
            conteo[a.categoria_id] = conteo.get(a.categoria_id, 0) + 1
            nombres[a.categoria_id] = a.categoria.nombre if a.categoria else "Sin categoría"
        return [{"id": k, "nombre": nombres[k], "total": v} for k, v in sorted(conteo.items(), key=lambda x: -x[1])]
