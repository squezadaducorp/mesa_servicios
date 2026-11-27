"""Gestión de problemas (mejora 30).

Un *incidente* es algo que hoy le impide trabajar a alguien y se resuelve rápido (un ticket). Un *problema* es la causa de
fondo que hace que se repita: se analiza una vez (5 porqués), se documenta como **error conocido** con una solución temporal
que los analistas aplican en minutos, y se corrige con un **cambio** (mejora 27).

Flujo: Detectado → En análisis → Error conocido → Solución en cambio → Cerrado. Al cerrar se avisa a los solicitantes de los
incidentes agrupados.

- Patrón detectado: N tickets parecidos (misma subcategoría y asunto parecido) en los últimos D días que no están en ningún
  problema (problemas.patron_minimo y problemas.patron_dias en Configuración). Solo sugiere: nunca crea problemas solo.
- En cada ticket nuevo el analista ve si coincide con un error conocido y puede «Vincular y responder con la solución».
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.conocimiento_service import es_mesa
from app.application.services.notificacion_service import NotificacionService
from app.application.services.vinculo_service import _palabras, parecido
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Estado, Permiso
from app.infrastructure.ai.local import normalizar
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

TZ = ZoneInfo(settings.ZONA_HORARIA)
ESTADOS = ("DETECTADO", "EN_ANALISIS", "ERROR_CONOCIDO", "SOLUCION_EN_CAMBIO", "CERRADO")
NOMBRE_ESTADO = {"DETECTADO": "Detectado", "EN_ANALISIS": "En análisis", "ERROR_CONOCIDO": "Error conocido",
                 "SOLUCION_EN_CAMBIO": "Solución en cambio", "CERRADO": "Cerrado"}
ABIERTOS = ESTADOS[:-1]
CON_SOLUCION = ("ERROR_CONOCIDO", "SOLUCION_EN_CAMBIO")     # se ofrecen en los tickets nuevos parecidos
TERMINADOS = {Estado.RESUELTO.value, Estado.CERRADO.value, Estado.CANCELADO.value}
VIGENCIA_IGNORADO_DIAS = 14


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def _firma(sub_id: int | None, ids: list[int]) -> str:
    return hashlib.sha256(f"{sub_id}:{min(ids)}".encode()).hexdigest()


class ProblemaService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)
        self.notif = NotificacionService(session)

    # ============================================================ permisos
    @staticmethod
    def gestor(u: m.Usuario) -> bool:
        return u.tiene(Permiso.PROBLEMAS_GESTIONAR)

    def puede_ver(self, u: m.Usuario) -> bool:
        return self.gestor(u) or es_mesa(u) or u.tiene(Permiso.PANEL_VER)

    def _exigir_ver(self, u: m.Usuario) -> None:
        if not self.puede_ver(u):
            raise Prohibido("La gestión de problemas es solo para el equipo de TI")

    def _exigir_gestor(self, u: m.Usuario) -> None:
        if not self.gestor(u):
            raise Prohibido("No tiene permiso para gestionar problemas")

    def _config(self) -> dict:
        return CatalogoRepository(self.session).configuracion()

    def _entero(self, clave: str, defecto: int) -> int:
        try:
            return max(2, int(self._config().get(clave) or defecto))
        except ValueError:
            return defecto

    def obtener(self, problema_id: int, u: m.Usuario) -> m.Problema:
        self._exigir_ver(u)
        p = self.session.get(m.Problema, problema_id)
        if p is None:
            raise NoEncontrado("Problema no encontrado")
        return p

    # ============================================================ crear / editar
    def _siguiente_numero(self, anio: int) -> tuple[int, str]:
        ultimo = self.session.scalar(select(func.max(m.Problema.secuencia)).where(m.Problema.anio == anio)) or 0
        return ultimo + 1, f"PRB-{anio}-{ultimo + 1:03d}"

    def _validar_responsable(self, uid: int | None) -> None:
        if uid is None:
            return
        r = self.session.get(m.Usuario, uid)
        if r is None or not r.activo or r.eliminado or not es_mesa(r):
            raise ReglaNegocio("El responsable debe ser alguien del equipo de TI")

    def _validar_clasificacion(self, categoria_id: int | None, subcategoria_id: int | None) -> int | None:
        if subcategoria_id:
            sub = self.session.get(m.Subcategoria, subcategoria_id)
            if sub is None or (categoria_id and sub.categoria_id != categoria_id):
                raise ReglaNegocio("La subcategoría no pertenece a la categoría")
            return sub.categoria_id
        if categoria_id and self.session.get(m.Categoria, categoria_id) is None:
            raise ReglaNegocio("Categoría no válida")
        return categoria_id

    def crear(self, dto, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        self._validar_responsable(dto.responsable_id)
        categoria_id = self._validar_clasificacion(dto.categoria_id, dto.subcategoria_id)
        ahora = utcnow()
        anio = ahora.replace(tzinfo=timezone.utc).astimezone(TZ).year
        seq, numero = self._siguiente_numero(anio)
        p = m.Problema(numero=numero, anio=anio, secuencia=seq, titulo=dto.titulo.strip(), descripcion=(dto.descripcion or "").strip() or None,
                       categoria_id=categoria_id, subcategoria_id=dto.subcategoria_id, responsable_id=dto.responsable_id or u.id,
                       palabras_clave=(dto.palabras_clave or "").strip() or None, estado="DETECTADO",
                       origen="PATRON" if dto.tickets and dto.desde_patron else "MANUAL", creado_por=u.id, fecha_creacion=ahora,
                       fecha_actualizacion=ahora)
        self.session.add(p)
        self.session.flush()
        for tid in dict.fromkeys(dto.tickets or []):
            self._vincular(p, self._ticket(tid), u, False, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_REGISTRADO, "problema", p.id,
                                 {"numero": p.numero, "titulo": p.titulo, "tickets": len(dto.tickets or [])})
        if p.responsable_id and p.responsable_id != u.id:
            self.notif.notificar([p.responsable], "PROBLEMA", f"{p.numero} a su cargo", f"«{p.titulo}»: analice la causa de fondo.")
        self.session.flush()
        return p

    def editar(self, problema_id: int, dto, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        p = self.obtener(problema_id, u)
        if p.estado == "CERRADO":
            raise ReglaNegocio("El problema está cerrado; reábralo para editarlo")
        self._validar_responsable(dto.responsable_id)
        p.categoria_id = self._validar_clasificacion(dto.categoria_id, dto.subcategoria_id)
        p.subcategoria_id = dto.subcategoria_id
        if dto.cambio_id and self.session.get(m.Cambio, dto.cambio_id) is None:
            raise ReglaNegocio("Cambio no encontrado")
        anterior_resp = p.responsable_id
        p.titulo = dto.titulo.strip()
        for campo in ("descripcion", "causa_raiz", "solucion_definitiva", "solucion_temporal", "palabras_clave"):
            v = getattr(dto, campo)
            setattr(p, campo, (v or "").strip() or None)
        porques = [{"pregunta": x.pregunta.strip(), "respuesta": x.respuesta.strip()} for x in dto.porques if x.pregunta.strip() or x.respuesta.strip()]
        p.porques = json.dumps(porques, ensure_ascii=False) if porques else None
        p.responsable_id = dto.responsable_id or p.responsable_id
        p.cambio_id = dto.cambio_id
        if p.estado == "DETECTADO" and (porques or p.causa_raiz):
            p.estado = "EN_ANALISIS"
        p.fecha_actualizacion = utcnow()
        self.session.flush()
        if p.articulo_id and p.solucion_temporal:
            self._sincronizar_articulo(p, u)
        if p.responsable_id != anterior_resp and p.responsable_id != u.id:
            self.notif.notificar([self.session.get(m.Usuario, p.responsable_id)], "PROBLEMA", f"{p.numero} a su cargo",
                                 f"«{p.titulo}»: analice la causa de fondo.")
        self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_MODIFICADO, "problema", p.id, {"numero": p.numero, "estado": p.estado})
        self.session.refresh(p)
        return p

    def cambiar_estado(self, problema_id: int, estado: str, nota: str | None, avisar: bool, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        p = self.obtener(problema_id, u)
        if estado not in ESTADOS:
            raise ReglaNegocio("Estado no válido")
        if estado == p.estado:
            return p
        if len((nota or "").strip()) < 5:
            raise ReglaNegocio("Indique el motivo del cambio de estado")
        ahora = utcnow()
        if estado in ("ERROR_CONOCIDO", "SOLUCION_EN_CAMBIO", "CERRADO") and not p.causa_raiz:
            raise ReglaNegocio("Registre la causa raíz antes de avanzar")
        if estado == "ERROR_CONOCIDO" and not p.solucion_temporal:
            raise ReglaNegocio("Un error conocido necesita la solución temporal que aplicarán los analistas")
        if estado == "SOLUCION_EN_CAMBIO" and not p.cambio_id:
            raise ReglaNegocio("Indique el cambio (CAM) que aplica la solución definitiva")
        if estado == "CERRADO" and not (p.solucion_definitiva or (nota or "").strip()):
            raise ReglaNegocio("Indique la solución definitiva o una nota de cierre")
        anterior = p.estado
        p.estado = estado
        if estado in CON_SOLUCION and p.fecha_causa is None:
            p.fecha_causa = ahora
        if estado == "CERRADO":
            p.fecha_cierre, p.nota_cierre = ahora, (nota or "").strip() or None
            if avisar:
                self._avisar_cierre(p)
        elif anterior == "CERRADO":
            p.fecha_cierre = None
        p.fecha_actualizacion = ahora
        self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_MODIFICADO, "problema", p.id,
                                 {"numero": p.numero, "de": anterior, "a": estado, "nota": nota})
        self.session.flush()
        return p

    def _avisar_cierre(self, p: m.Problema) -> int:
        """Un correo por solicitante (sobre su ticket más reciente) diciendo que la causa ya se corrigió."""
        por_persona: dict[int, m.Ticket] = {}
        for pt in self._vinculos(p.id):
            t = pt.ticket
            if t.eliminado or t.estado == Estado.CANCELADO:
                continue
            if t.solicitante_id not in por_persona or t.fecha_creacion > por_persona[t.solicitante_id].fecha_creacion:
                por_persona[t.solicitante_id] = t
        solucion = p.solucion_definitiva or p.nota_cierre or ""
        for t in por_persona.values():
            self.notif.notificar([t.solicitante], "PROBLEMA_RESUELTO", f"{t.numero}: causa corregida", f"{p.titulo}. {solucion}"[:900], t)
            self.notif.correo("PROBLEMA_RESUELTO", [t.solicitante], t, problema=p.numero, titulo_problema=p.titulo, solucion=solucion)
        return len(por_persona)

    # ============================================================ base de conocimiento
    def _sincronizar_articulo(self, p: m.Problema, u: m.Usuario) -> m.KbArticulo:
        a = self.session.get(m.KbArticulo, p.articulo_id) if p.articulo_id else None
        ahora = utcnow()
        if a is None or a.eliminado:
            a = m.KbArticulo(creado_por=u.id, fecha_creacion=ahora)
            self.session.add(a)
        a.titulo = f"{p.titulo} (error conocido {p.numero})"[:200]
        a.sintoma = (p.descripcion or p.titulo)[:1000]
        a.solucion = p.solucion_temporal or ""
        a.visibilidad = "EXTERNO"   # la solución temporal es para los solicitantes; el análisis técnico queda en el problema
        a.nota = "Solución temporal mientras TI corrige la causa de fondo." + (f" Corrección prevista con {p.cambio.numero}." if p.cambio else "")
        a.palabras_clave = p.palabras_clave
        a.categoria_id, a.subcategoria_id = p.categoria_id, p.subcategoria_id
        a.estado = "PUBLICADO"
        a.actualizado_por, a.fecha_actualizacion = u.id, ahora
        self.session.flush()
        p.articulo_id = a.id
        return a

    def publicar(self, problema_id: int, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        p = self.obtener(problema_id, u)
        if not p.solucion_temporal:
            raise ReglaNegocio("Escriba la solución temporal antes de publicarla")
        a = self._sincronizar_articulo(p, u)
        self.auditoria.registrar(ctx, AccionAuditoria.KB_MODIFICADO, "kb_articulo", a.id, {"titulo": a.titulo, "problema": p.numero})
        return p

    # ============================================================ incidentes
    def _ticket(self, ref: int | str) -> m.Ticket:
        T = m.Ticket
        t = self.session.get(T, int(ref)) if str(ref).isdigit() else self.session.scalar(select(T).where(T.numero == str(ref).strip().upper()))
        if t is None or t.eliminado:
            raise NoEncontrado(f"Ticket {ref} no encontrado")
        return t

    def _vinculos(self, problema_id: int) -> list[m.ProblemaTicket]:
        PT = m.ProblemaTicket
        return list(self.session.scalars(select(PT).where(PT.problema_id == problema_id).order_by(PT.id.desc())).unique())

    def _vincular(self, p: m.Problema, t: m.Ticket, u: m.Usuario, con_solucion: bool, ahora: datetime) -> m.ProblemaTicket:
        PT = m.ProblemaTicket
        v = self.session.scalar(select(PT).where(PT.problema_id == p.id, PT.ticket_id == t.id))
        if v is None:
            v = PT(problema_id=p.id, ticket_id=t.id, con_solucion=con_solucion, vinculado_por=u.id, fecha=ahora)
            self.session.add(v)
        elif con_solucion:
            v.con_solucion = True
        self.session.flush()
        return v

    def vincular(self, problema_id: int, ticket: str, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        p = self.obtener(problema_id, u)
        t = self._ticket(ticket)
        self._vincular(p, t, u, False, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_VINCULADO, "problema", p.id, {"numero": p.numero, "ticket": t.numero})
        return p

    def desvincular(self, problema_id: int, ticket_id: int, ctx: Contexto) -> m.Problema:
        u = ctx.usuario
        self._exigir_gestor(u)
        p = self.obtener(problema_id, u)
        PT = m.ProblemaTicket
        v = self.session.scalar(select(PT).where(PT.problema_id == p.id, PT.ticket_id == ticket_id))
        if v:
            self.session.delete(v)
            self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_VINCULADO, "problema", p.id,
                                     {"numero": p.numero, "ticket": v.ticket.numero, "quitado": True})
            self.session.flush()
        return p

    # ============================================================ desde el ticket
    def _svc_ticket(self):
        from app.application.services.ticket_service import TicketService

        return TicketService(self.session)

    def del_ticket(self, ticket_id: int, u: m.Usuario) -> dict:
        """Problemas del ticket y errores conocidos que se le parecen (solo para el equipo de TI)."""
        svc = self._svc_ticket()
        t = svc.obtener(ticket_id, u)
        if not es_mesa(u):
            return {"problemas": [], "coincidencias": []}
        PT, P = m.ProblemaTicket, m.Problema
        propios = list(self.session.scalars(select(P).join(PT, PT.problema_id == P.id).where(PT.ticket_id == t.id)).unique())
        salida = {"problemas": [self._corto(p) for p in propios], "coincidencias": []}
        acciones = svc.acciones(u, t)
        if "comentar" not in acciones or t.estado in TERMINADOS:
            return salida
        descartados = set(self.session.scalars(select(m.ProblemaDescarte.problema_id).where(m.ProblemaDescarte.ticket_id == t.id)))
        ya = {p.id for p in propios} | descartados
        salida["coincidencias"] = [
            {**self._corto(p), "solucion_temporal": p.solucion_temporal, "puntaje": round(puntaje, 2)}
            for p, puntaje in self.coincidencias(t) if p.id not in ya][:2]
        return salida

    def coincidencias(self, t: m.Ticket) -> list[tuple[m.Problema, float]]:
        P = m.Problema
        texto = f"{t.asunto} {t.descripcion}"
        norm = normalizar(texto)
        salida = []
        for p in self.session.scalars(select(P).where(P.estado.in_(CON_SOLUCION), P.solucion_temporal.is_not(None))).unique():
            base = parecido(texto, f"{p.titulo} {p.descripcion or ''} {p.palabras_clave or ''}")
            asuntos = [pt.ticket.asunto for pt in self._vinculos(p.id)[:20]]
            similar = max([base] + [parecido(t.asunto, a) for a in asuntos])
            claves = [c.strip() for c in (p.palabras_clave or "").split(",") if c.strip()]
            frase = any(normalizar(c) and normalizar(c) in norm for c in claves)
            puntaje = similar + (0.15 if p.subcategoria_id and p.subcategoria_id == t.subcategoria_id else 0) + (0.3 if frase else 0)
            if puntaje >= 0.35 and (similar >= 0.15 or frase):
                salida.append((p, puntaje))
        return sorted(salida, key=lambda x: -x[1])

    def aplicar(self, problema_id: int, ticket_id: int, responder: bool, ctx: Contexto) -> dict:
        """«Vincular y responder con la solución»: agrupa el ticket y envía la solución temporal al solicitante."""
        u = ctx.usuario
        if not es_mesa(u):
            raise Prohibido("Solo el equipo de TI puede vincular tickets a problemas")
        p = self.session.get(m.Problema, problema_id)
        if p is None:
            raise NoEncontrado("Problema no encontrado")
        svc = self._svc_ticket()
        t = svc.obtener(ticket_id, u)
        svc._exigir(u, t, "comentar")
        self._vincular(p, t, u, responder and bool(p.solucion_temporal), utcnow())
        if responder and p.solucion_temporal:
            from app.application.schemas.esquemas import ComentarioEntrada

            svc.comentar(t.id, ComentarioEntrada(texto=f"Es un error conocido ({p.numero}). Mientras TI corrige la causa de fondo, "
                                                       f"puede hacer lo siguiente:\n\n{p.solucion_temporal}"), ctx)
        self.auditoria.registrar(ctx, AccionAuditoria.PROBLEMA_VINCULADO, "problema", p.id,
                                 {"numero": p.numero, "ticket": t.numero, "respuesta": responder})
        return self.del_ticket(t.id, u)

    def descartar(self, problema_id: int, ticket_id: int, ctx: Contexto) -> dict:
        u = ctx.usuario
        svc = self._svc_ticket()
        t = svc.obtener(ticket_id, u)
        if not es_mesa(u):
            raise Prohibido("Solo el equipo de TI")
        self.session.add(m.ProblemaDescarte(problema_id=problema_id, ticket_id=t.id, usuario_id=u.id, fecha=utcnow()))
        self.session.flush()
        return self.del_ticket(t.id, u)

    # ============================================================ patrón detectado
    def patrones(self, ahora: datetime | None = None) -> list[dict]:
        ahora = ahora or utcnow()
        dias, minimo = self._entero("problemas.patron_dias", 7), self._entero("problemas.patron_minimo", 5)
        T, PT = m.Ticket, m.ProblemaTicket
        en_problema = select(PT.ticket_id)
        tickets = list(self.session.scalars(
            select(T).where(T.eliminado == False, T.fecha_creacion >= ahora - timedelta(days=dias), T.canal != "CATALOGO",
                            T.estado != Estado.CANCELADO, T.id.not_in(en_problema)).order_by(T.fecha_creacion)).unique())
        D = m.ProblemaDescarte
        ignorados = set(self.session.scalars(select(D.firma).where(D.firma.is_not(None), D.fecha >= ahora - timedelta(days=VIGENCIA_IGNORADO_DIAS))))
        por_sub: dict[int, list[m.Ticket]] = {}
        for t in tickets:
            por_sub.setdefault(t.subcategoria_id, []).append(t)
        salida = []
        for sub_id, grupo in por_sub.items():
            if len(grupo) < minimo:
                continue
            libres = list(grupo)
            while len(libres) >= minimo:
                semilla = libres[0]
                cluster = [t for t in libres if t is semilla or parecido(semilla.asunto, t.asunto) >= 0.25
                           or parecido(f"{semilla.asunto} {semilla.descripcion}", f"{t.asunto} {t.descripcion}") >= 0.3]
                libres = [t for t in libres if t not in cluster]
                if len(cluster) < minimo:
                    continue
                ids = [t.id for t in cluster]
                firma = _firma(sub_id, ids)
                if firma in ignorados:
                    continue
                comunes = Counter(p for t in cluster for p in _palabras(t.asunto)).most_common(4)
                asunto = Counter(t.asunto.strip() for t in cluster).most_common(1)[0][0]
                areas = sorted({t.area.nombre for t in cluster if t.area})
                salida.append({"firma": firma, "cantidad": len(cluster), "dias": dias, "titulo": asunto,
                               "palabras": ", ".join(p for p, _ in comunes), "areas": areas,
                               "categoria_id": cluster[0].categoria_id, "subcategoria_id": sub_id,
                               "subcategoria": cluster[0].subcategoria.nombre,
                               "tickets": [{"id": t.id, "numero": t.numero, "asunto": t.asunto} for t in cluster]})
        return sorted(salida, key=lambda x: -x["cantidad"])

    def ignorar_patron(self, firma: str, ctx: Contexto) -> None:
        self._exigir_gestor(ctx.usuario)
        self.session.add(m.ProblemaDescarte(firma=firma[:64], usuario_id=ctx.usuario.id, fecha=utcnow()))
        self.session.flush()

    # ============================================================ consultas
    def listar(self, u: m.Usuario, estado: str | None = None, texto: str | None = None) -> list[m.Problema]:
        self._exigir_ver(u)
        P = m.Problema
        stmt = select(P)
        if estado == "ABIERTOS":
            stmt = stmt.where(P.estado.in_(ABIERTOS))
        elif estado:
            stmt = stmt.where(P.estado == estado)
        if texto:
            q = f"%{texto.strip()}%"
            stmt = stmt.where((P.titulo.ilike(q)) | (P.numero.ilike(q)))
        return list(self.session.scalars(stmt.order_by(P.anio.desc(), P.secuencia.desc())).unique())

    def _conteo(self, problema_id: int) -> int:
        return self.session.scalar(select(func.count(m.ProblemaTicket.id)).where(m.ProblemaTicket.problema_id == problema_id)) or 0

    def resumen(self, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        P, PT = m.Problema, m.ProblemaTicket
        local = ahora.replace(tzinfo=timezone.utc).astimezone(TZ)
        inicio_mes = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
        abiertos = self.session.scalar(select(func.count(P.id)).where(P.estado.in_(ABIERTOS))) or 0
        conocidos = self.session.scalar(select(func.count(P.id)).where(P.estado == "ERROR_CONOCIDO")) or 0
        evitados = self.session.scalar(select(func.count(PT.id)).where(PT.con_solucion == True, PT.fecha >= inicio_mes)) or 0
        con_causa = list(self.session.execute(select(P.fecha_creacion, P.fecha_causa).where(P.fecha_causa.is_not(None),
                                                                                          P.fecha_causa >= ahora - timedelta(days=365))))
        dias = round(sum((b - a).total_seconds() for a, b in con_causa) / 86400 / len(con_causa), 1) if con_causa else None
        return {"abiertos": abiertos, "errores_conocidos": conocidos, "evitados_mes": evitados, "dias_hasta_causa": dias}

    def _corto(self, p: m.Problema) -> dict:
        return {"id": p.id, "numero": p.numero, "titulo": p.titulo, "estado": p.estado, "estado_nombre": NOMBRE_ESTADO[p.estado]}

    def salida_lista(self, p: m.Problema, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        return {**self._corto(p), "incidentes": self._conteo(p.id), "responsable": p.responsable.nombre if p.responsable else None,
                "dias_abierto": None if p.estado == "CERRADO" else (ahora - p.fecha_creacion).days,
                "fecha_creacion": iso(p.fecha_creacion), "categoria": p.categoria.nombre if p.categoria else None}

    def impacto(self, vinculos: list[m.ProblemaTicket]) -> dict:
        tickets = [v.ticket for v in vinculos if not v.ticket.eliminado]
        minutos = sum((t.minutos_resolucion if t.minutos_resolucion is not None else t.sla_minutos_consumidos or 0) for t in tickets)
        return {"incidentes": len(tickets), "personas": len({t.solicitante_id for t in tickets}), "horas": round(minutos / 60, 1),
                "evitados": sum(1 for v in vinculos if v.con_solucion)}

    def salida(self, p: m.Problema, u: m.Usuario) -> dict:
        vinculos = self._vinculos(p.id)
        art = self.session.get(m.KbArticulo, p.articulo_id) if p.articulo_id else None
        return {
            **self.salida_lista(p),
            "descripcion": p.descripcion, "origen": p.origen, "categoria_id": p.categoria_id, "subcategoria_id": p.subcategoria_id,
            "subcategoria": p.subcategoria.nombre if p.subcategoria else None, "responsable_id": p.responsable_id,
            "porques": json.loads(p.porques) if p.porques else [], "causa_raiz": p.causa_raiz, "solucion_definitiva": p.solucion_definitiva,
            "solucion_temporal": p.solucion_temporal, "palabras_clave": p.palabras_clave, "nota_cierre": p.nota_cierre,
            "articulo": {"id": art.id, "titulo": art.titulo, "estado": art.estado} if art and not art.eliminado else None,
            "cambio": {"id": p.cambio.id, "numero": p.cambio.numero, "titulo": p.cambio.titulo, "estado": p.cambio.estado,
                       "ventana_inicio": iso(p.cambio.ventana_inicio)} if p.cambio else None,
            "cambio_id": p.cambio_id, "fecha_causa": iso(p.fecha_causa), "fecha_cierre": iso(p.fecha_cierre),
            "incidentes_lista": [{"id": v.ticket.id, "numero": v.ticket.numero, "asunto": v.ticket.asunto, "estado": v.ticket.estado,
                                  "estado_nombre": v.ticket.estado_rel.nombre if v.ticket.estado_rel else v.ticket.estado,
                                  "solicitante": v.ticket.solicitante_nombre, "fecha": iso(v.ticket.fecha_creacion), "con_solucion": v.con_solucion}
                                 for v in vinculos if not v.ticket.eliminado],
            "impacto": self.impacto(vinculos), "gestor": self.gestor(u),
        }

    def opciones(self) -> dict:
        from app.application.services.cambio_service import ABIERTOS as CAMBIOS_ABIERTOS

        U, C = m.Usuario, m.Cambio
        responsables = [{"id": x.id, "nombre": x.nombre} for x in self.session.scalars(
            select(U).where(U.activo == True, U.eliminado == False).order_by(U.nombre)).unique() if es_mesa(x)]
        cambios = [{"id": c.id, "numero": c.numero, "titulo": c.titulo, "estado": c.estado} for c in self.session.scalars(
            select(C).where(C.estado.in_(CAMBIOS_ABIERTOS + ("IMPLEMENTADO",))).order_by(C.anio.desc(), C.secuencia.desc()).limit(100)).unique()]
        return {"responsables": responsables, "cambios": cambios, "estados": NOMBRE_ESTADO}
