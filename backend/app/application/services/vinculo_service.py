"""Tickets vinculados y unión de duplicados (mejora 22).

Tipos de vínculo (se guardan en un sentido, ticket_id «tipo» relacionado_id):
- RELACIONADO: solo referencia.
- DUPLICADO: ticket_id se unió como duplicado de relacionado_id (lo crea «Unir»).
- BLOQUEADO_POR: ticket_id no se puede resolver hasta que relacionado_id esté resuelto, cerrado o cancelado.
- NO_DUPLICADO: el analista descartó la sugerencia de duplicado (no se muestra).
La detección de posibles duplicados solo sugiere: nunca une tickets por su cuenta.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.security import utcnow
from app.domain.correos import MAX_COPIAS
from app.domain.enums import ESTADOS_ABIERTOS, AccionAuditoria, Estado
from app.infrastructure.ai.local import normalizar
from app.infrastructure.db import models as m

ETIQUETAS = {
    # (tipo, desde este ticket) → texto
    ("RELACIONADO", True): "Relacionado con", ("RELACIONADO", False): "Relacionado con",
    ("DUPLICADO", True): "Duplicado de", ("DUPLICADO", False): "Tiene como duplicado",
    ("BLOQUEADO_POR", True): "Bloqueado por", ("BLOQUEADO_POR", False): "Bloquea a",
}
TERMINADOS = {Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO}
VACIAS = {"de", "la", "el", "en", "y", "a", "los", "las", "del", "por", "para", "con", "no", "se", "que", "un", "una", "mi", "me",
          "al", "lo", "es", "su", "sus", "le", "hay", "favor", "buenos", "dias", "tardes", "hola", "gracias", "ayuda"}


def _palabras(texto: str) -> set[str]:
    return {p for p in normalizar(texto).split() if len(p) > 2 and p not in VACIAS}


def parecido(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


class VinculoService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ============================================================ consultas
    def _filas(self, ticket_id: int) -> list[m.TicketVinculo]:
        V = m.TicketVinculo
        return list(self.session.scalars(select(V).where(or_(V.ticket_id == ticket_id, V.relacionado_id == ticket_id)).order_by(V.id)).unique())

    def de_ticket(self, t: m.Ticket, u: m.Usuario | None = None) -> list[dict]:
        salida = []
        for v in self._filas(t.id):
            if v.tipo == "NO_DUPLICADO":
                continue
            propio = v.ticket_id == t.id
            otro = v.relacionado if propio else v.ticket
            if otro.eliminado:
                continue
            salida.append({"id": v.id, "tipo": v.tipo, "etiqueta": ETIQUETAS[(v.tipo, propio)], "desde_este": propio,
                           "ticket": {"id": otro.id, "numero": otro.numero, "asunto": otro.asunto, "estado": otro.estado,
                                      "estado_nombre": otro.estado_rel.nombre if otro.estado_rel else otro.estado},
                           "fecha": v.fecha})
        return salida

    def duplicado_de(self, t: m.Ticket) -> dict | None:
        V = m.TicketVinculo
        v = self.session.scalars(select(V).where(V.ticket_id == t.id, V.tipo == "DUPLICADO")).first()
        return {"id": v.relacionado.id, "numero": v.relacionado.numero} if v else None

    def bloqueos_abiertos(self, t: m.Ticket) -> list[m.Ticket]:
        V = m.TicketVinculo
        filas = self.session.scalars(select(V).where(V.ticket_id == t.id, V.tipo == "BLOQUEADO_POR")).unique()
        return [v.relacionado for v in filas if v.relacionado.estado not in TERMINADOS and not v.relacionado.eliminado]

    # ============================================================ vincular
    def _svc(self):
        from app.application.services.ticket_service import TicketService

        return TicketService(self.session)

    def _otro(self, svc, u: m.Usuario, relacionado: str | int) -> m.Ticket:
        texto = str(relacionado).strip().upper()
        t = svc.repo.por_numero(texto) if not texto.isdigit() else svc.repo.get(int(texto))
        if t is None or t.eliminado or not svc.repo.puede_ver(u, t.id):
            raise NoEncontrado(f"No encontramos el ticket {relacionado}")
        return t

    def vincular(self, ticket_id: int, relacionado: str | int, tipo: str, ctx: Contexto) -> list[dict]:
        u = ctx.usuario
        svc = self._svc()
        t = svc.obtener(ticket_id, u)
        svc._exigir(u, t, "vincular")
        if tipo not in ("RELACIONADO", "BLOQUEADO_POR"):
            raise ReglaNegocio("Para marcar un duplicado use «Unir»")
        otro = self._otro(svc, u, relacionado)
        if otro.id == t.id:
            raise ReglaNegocio("Elija otro ticket")
        for v in self._filas(t.id):
            if {v.ticket_id, v.relacionado_id} == {t.id, otro.id} and v.tipo != "NO_DUPLICADO":
                raise ReglaNegocio(f"{otro.numero} ya está vinculado a este ticket")
        ahora = utcnow()
        self.session.add(m.TicketVinculo(ticket_id=t.id, relacionado_id=otro.id, tipo=tipo, creado_por=u.id, fecha=ahora))
        self.session.flush()
        svc._hist(t, u, "VINCULO", "vinculo", None, f"{ETIQUETAS[(tipo, True)]} {otro.numero}", ahora=ahora)
        svc._hist(otro, u, "VINCULO", "vinculo", None, f"{ETIQUETAS[(tipo, False)]} {t.numero}", ahora=ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_VINCULADO, "ticket", t.id, {"numero": t.numero, "tipo": tipo, "con": otro.numero})
        return self.de_ticket(t, u)

    def desvincular(self, ticket_id: int, vinculo_id: int, ctx: Contexto) -> list[dict]:
        u = ctx.usuario
        svc = self._svc()
        t = svc.obtener(ticket_id, u)
        svc._exigir(u, t, "vincular")
        v = self.session.get(m.TicketVinculo, vinculo_id)
        if v is None or t.id not in (v.ticket_id, v.relacionado_id):
            raise NoEncontrado("Vínculo no encontrado")
        if v.tipo == "DUPLICADO":
            raise ReglaNegocio("Un ticket unido como duplicado no se puede desvincular")
        otro = v.relacionado if v.ticket_id == t.id else v.ticket
        svc._hist(t, u, "VINCULO", "vinculo", f"{v.tipo} {otro.numero}", None, "Vínculo quitado")
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_VINCULADO, "ticket", t.id, {"numero": t.numero, "quitado": v.tipo, "con": otro.numero})
        self.session.delete(v)
        self.session.flush()
        return self.de_ticket(t, u)

    # ==================================================== posibles duplicados
    def posibles_duplicados(self, ticket_id: int, u: m.Usuario, limite: int = 3) -> list[dict]:
        svc = self._svc()
        t = svc.obtener(ticket_id, u)
        if "vincular" not in svc.acciones(u, t) or Estado(t.estado) in TERMINADOS:
            return []
        ya = {v.ticket_id if v.relacionado_id == t.id else v.relacionado_id for v in self._filas(t.id)}
        T = m.Ticket
        candidatos = svc.session.scalars(
            svc.repo.consulta_visible(u, incluir_participados=True).where(
                T.id != t.id, T.categoria_id == t.categoria_id, T.estado.in_([e.value for e in ESTADOS_ABIERTOS]),
                T.fecha_creacion >= t.fecha_creacion - timedelta(hours=24), T.fecha_creacion <= t.fecha_creacion + timedelta(hours=24))
        ).unique()
        texto = f"{t.asunto} {t.descripcion}"
        salida = []
        for c in candidatos:
            if c.id in ya:
                continue
            p = parecido(texto, f"{c.asunto} {c.descripcion}")
            misma_sub = c.subcategoria_id == t.subcategoria_id
            misma_area = bool(c.area_id and c.area_id == t.area_id)
            puntaje = p + (0.15 if misma_sub else 0) + (0.1 if misma_area else 0) + (0.1 if c.equipo_id and c.equipo_id == t.equipo_id else 0)
            if puntaje < 0.35 or p < 0.12:
                continue
            razones = ["asunto parecido"] + (["misma subcategoría"] if misma_sub else []) + (["misma área"] if misma_area else [])
            salida.append({"id": c.id, "numero": c.numero, "asunto": c.asunto, "solicitante": c.solicitante_nombre,
                           "estado": c.estado, "fecha_creacion": c.fecha_creacion, "puntaje": round(puntaje, 2), "razones": razones})
        return sorted(salida, key=lambda x: -x["puntaje"])[:limite]

    def descartar(self, ticket_id: int, otro_id: int, ctx: Contexto) -> None:
        u = ctx.usuario
        svc = self._svc()
        t = svc.obtener(ticket_id, u)
        svc._exigir(u, t, "vincular")
        self.session.add(m.TicketVinculo(ticket_id=t.id, relacionado_id=otro_id, tipo="NO_DUPLICADO", creado_por=u.id))
        self.session.flush()

    # =============================================================== unir
    def unir(self, principal_id: int, duplicados: list[int], mensaje: str | None, avisar: bool, mantener_prioridad: bool,
             ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        svc = self._svc()
        principal = svc.obtener(principal_id, u)
        svc._exigir(u, principal, "vincular")
        if Estado(principal.estado) in TERMINADOS:
            raise ReglaNegocio("El ticket principal ya está terminado: elija uno abierto")
        ids = [i for i in dict.fromkeys(duplicados) if i != principal.id]
        if not ids:
            raise ReglaNegocio("Elija al menos un ticket para unir al principal")
        if len(ids) > 20:
            raise ReglaNegocio("Máximo 20 tickets por unión")
        dups = []
        for i in ids:
            d = svc.obtener(i, u)
            if "vincular" not in svc.acciones(u, d):
                raise Prohibido(f"No puede gestionar {d.numero}")
            if Estado(d.estado) in TERMINADOS:
                raise ReglaNegocio(f"{d.numero} ya está terminado")
            dups.append(d)
        ahora = utcnow()
        mensaje = (mensaje or "").strip() or f"Varias personas reportaron lo mismo. Lo atendemos en {principal.numero} y le avisaremos al resolverlo."
        from app.application.services.aprobacion_service import AprobacionService

        for d in dups:
            for c in svc.repo.comentarios(d.id, incluir_internos=True):
                self.session.add(m.TicketComentario(ticket_id=principal.id, usuario_id=c.usuario_id, texto=f"[Desde {d.numero}] {c.texto}",
                                                    es_interno=c.es_interno, tipo=c.tipo, minutos_invertidos=c.minutos_invertidos, fecha=c.fecha))
            if d.descripcion:
                self.session.add(m.TicketComentario(ticket_id=principal.id, usuario_id=d.solicitante_id, es_interno=False, tipo="COMENTARIO",
                                                    texto=f"[Desde {d.numero} · {d.solicitante_nombre}] {d.asunto}: {d.descripcion}"[:4000],
                                                    fecha=d.fecha_creacion))
            for a in svc.repo.adjuntos(d.id):
                self.session.add(m.TicketAdjunto(ticket_id=principal.id, nombre_original=a.nombre_original, ruta_almacenamiento=a.ruta_almacenamiento,
                                                 tipo_mime=a.tipo_mime, tamano_bytes=a.tamano_bytes, hash_sha256=a.hash_sha256,
                                                 subido_por=a.subido_por, fecha=a.fecha))
            svc.agregar_copias(principal, list(dict.fromkeys((c or "").strip().lower() for c in [d.correo, d.solicitante.correo, *svc.copias(d)] if c))[: MAX_COPIAS],
                              "MANUAL", ahora)
            self.session.add(m.TicketVinculo(ticket_id=d.id, relacionado_id=principal.id, tipo="DUPLICADO", creado_por=u.id, fecha=ahora))
            if d.estado == Estado.POR_APROBAR:
                AprobacionService(self.session).anular(d, f"Unido a {principal.numero}")
            d.sla_excluido = True
            svc._agregar_comentario(d, u, f"Se unió como duplicado de {principal.numero}. {mensaje}", False, "COMENTARIO", None, ahora)
            svc._aplicar_estado(d, Estado(d.estado), Estado.CANCELADO, u, ctx, ahora)
            svc._hist(d, u, "UNION", "duplicado_de", None, principal.numero, "Cerrado como duplicado; no cuenta en el SLA", ahora)
            if avisar:
                svc.notif.correo_directo("TICKETS_UNIDOS", d.correo, d.solicitante_nombre, principal, duplicado=d.numero, comentario=mensaje)
                svc.notif.notificar([d.solicitante], "TICKETS_UNIDOS", f"{d.numero} se atiende en {principal.numero}", mensaje, principal)
        if mantener_prioridad:
            mejor = min([principal, *dups], key=lambda x: x.prioridad.orden)
            if mejor.prioridad_id != principal.prioridad_id:
                anterior = principal.prioridad.nombre
                principal.prioridad_id, principal.prioridad = mejor.prioridad_id, mejor.prioridad
                principal.sla_respuesta_min, principal.sla_resolucion_min = svc.sla.minutos_sla(principal.categoria_id, mejor.prioridad)
                principal.sla_nivel_alerta = 0
                svc.sla.recalcular(principal, ahora)
                svc._hist(principal, u, "EDICION", "prioridad_id", anterior, mejor.prioridad.nombre, "Prioridad más alta de los tickets unidos", ahora)
        numeros = [d.numero for d in dups]
        svc._hist(principal, u, "UNION", "duplicados", None, ", ".join(numeros), f"Se unieron {len(dups)} ticket(s) duplicados", ahora)
        principal.fecha_actualizacion = ahora
        self.auditoria.registrar(ctx, AccionAuditoria.TICKETS_UNIDOS, "ticket", principal.id,
                                 {"principal": principal.numero, "duplicados": numeros, "avisar": avisar})
        self.session.flush()
        return principal
