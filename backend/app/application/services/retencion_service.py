"""Clasificación de la información y retención (ISO 27001, mejora 42; controles A.5.12, A.5.13, A.8.10 y A.5.33).

- Cada ticket es Pública, Interna (por defecto) o Confidencial. La categoría puede fijar con cuál nace.
  Confidencial: solo lo ven el solicitante, el responsable, el supervisor del área y TI; los correos llevan solo
  el número y el enlace; no alimenta la base de conocimiento ni se envía a la IA externa.
- Bajar la clasificación pide motivo; todo cambio queda en el historial del ticket y en Auditoría.
- Retención: los tickets se conservan ``retencion.tickets_anios`` años (5) desde su cierre. Pasado ese plazo
  TI ve la lista y aprueba la depuración: se borran los adjuntos y el texto, y quedan el número, las fechas y las
  métricas. Un ticket con «retención legal» (reclamo o auditoría de SENAE) nunca se depura.
- La anonimización de ex-empleados queda pendiente de la opinión de Legal (no se construye aquí).
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Estado, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

NIVELES = ("PUBLICA", "INTERNA", "CONFIDENCIAL")
NOMBRES = {"PUBLICA": "Pública", "INTERNA": "Interna", "CONFIDENCIAL": "Confidencial"}
TEXTO_DEPURADO = "[Contenido depurado por la política de retención de la Mesa de Servicios]"
CONFIG = {
    "retencion.tickets_anios": ("5", "Años que se conservan los tickets desde su cierre antes de poder depurarlos"),
    "retencion.aviso_mensual": ("si", "Avisar el primer día de cada mes si hay tickets listos para depurar (si/no)"),
}
LOTE = 200


class RetencionService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ------------------------------------------------------------ clasificación
    def clasificar(self, ticket_id: int, nivel: str, motivo: str | None, ctx: Contexto) -> m.Ticket:
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        svc = TicketService(self.session)
        t = svc.obtener(ticket_id, u)
        if "clasificar" not in svc.acciones(u, t):
            raise Prohibido("No puede cambiar la clasificación de este ticket")
        if nivel not in NIVELES:
            raise ReglaNegocio("Clasificación no válida")
        if nivel == t.clasificacion:
            return t
        baja = NIVELES.index(nivel) < NIVELES.index(t.clasificacion)
        motivo = (motivo or "").strip()
        if baja and not svc.es_gestor(u, t):
            raise Prohibido("Solo quien atiende el ticket puede bajar su clasificación")
        if baja and len(motivo) < 5:
            raise ReglaNegocio("Indique el motivo para bajar la clasificación")
        anterior = t.clasificacion
        t.clasificacion, t.fecha_actualizacion = nivel, utcnow()
        svc._hist(t, u, "CLASIFICACION", "clasificacion", NOMBRES[anterior], NOMBRES[nivel], motivo or None)
        self.auditoria.registrar(ctx, AccionAuditoria.CLASIFICACION_CAMBIADA, "ticket", t.id,
                                 {"numero": t.numero, "de": anterior, "a": nivel, "motivo": motivo or None})
        return t

    def retencion_legal(self, ticket_id: int, activa: bool, motivo: str | None, ctx: Contexto) -> m.Ticket:
        from app.application.services.ticket_service import TicketService

        if not ctx.usuario.tiene(Permiso.SISTEMA_ADMINISTRAR):
            raise Prohibido("Solo TI puede poner o quitar la retención legal")
        svc = TicketService(self.session)
        t = svc.obtener(ticket_id, ctx.usuario)
        motivo = (motivo or "").strip()
        if len(motivo) < 5:
            raise ReglaNegocio("Indique el motivo (reclamo, auditoría de SENAE, proceso legal…)")
        if t.retencion_legal == activa:
            return t
        t.retencion_legal = activa
        svc._hist(t, ctx.usuario, "RETENCION_LEGAL", "retencion_legal", "No" if activa else "Sí", "Sí" if activa else "No", motivo)
        self.auditoria.registrar(ctx, AccionAuditoria.RETENCION_LEGAL, "ticket", t.id, {"numero": t.numero, "activa": activa, "motivo": motivo})
        return t

    # ------------------------------------------------------------ retención
    def config(self) -> dict[str, str]:
        guardada = CatalogoRepository(self.session).configuracion()
        return {k: guardada.get(k, defecto) for k, (defecto, _) in CONFIG.items()}

    def anios(self) -> int:
        try:
            return max(1, int(self.config()["retencion.tickets_anios"]))
        except ValueError:
            return 5

    def _vencidos(self, ahora: datetime):
        limite = ahora - timedelta(days=365 * self.anios() + self.anios() // 4)
        fin = func.coalesce(m.Ticket.fecha_cierre, m.Ticket.fecha_resolucion, m.Ticket.fecha_actualizacion, m.Ticket.fecha_creacion)
        return select(m.Ticket).where(
            m.Ticket.estado.in_((Estado.CERRADO, Estado.CANCELADO)), m.Ticket.retencion_legal == False,
            m.Ticket.fecha_depuracion.is_(None), fin < limite).order_by(fin)

    def resumen(self, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        stmt = self._vencidos(ahora)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        muestra = list(self.session.scalars(stmt.limit(50)).unique())
        por_nivel = dict(self.session.execute(select(m.Ticket.clasificacion, func.count()).where(m.Ticket.eliminado == False)
                                              .group_by(m.Ticket.clasificacion)).all())
        return {
            "anios": self.anios(),
            "clasificacion": {n: por_nivel.get(n, 0) for n in NIVELES},
            "retencion_legal": self.session.scalar(select(func.count()).where(m.Ticket.retencion_legal == True)) or 0,
            "depurados": self.session.scalar(select(func.count()).where(m.Ticket.fecha_depuracion.is_not(None))) or 0,
            "por_depurar": total,
            "muestra": [{"id": t.id, "numero": t.numero, "asunto": t.asunto, "categoria": t.categoria.nombre if t.categoria else None,
                         "estado": t.estado, "fecha_cierre": (t.fecha_cierre or t.fecha_resolucion).isoformat() + "Z"
                         if (t.fecha_cierre or t.fecha_resolucion) else None, "clasificacion": t.clasificacion} for t in muestra],
        }

    def depurar(self, confirmacion: str, ctx: Contexto) -> dict:
        """Borra el contenido de los tickets vencidos (un lote por llamada). Requiere escribir DEPURAR."""
        from app.infrastructure.storage.local import AlmacenamientoLocal

        if not ctx.usuario.tiene(Permiso.SISTEMA_ADMINISTRAR):
            raise Prohibido("Solo TI puede aprobar la depuración")
        if (confirmacion or "").strip().upper() != "DEPURAR":
            raise ReglaNegocio("Escriba DEPURAR para confirmar")
        ahora = utcnow()
        tickets = list(self.session.scalars(self._vencidos(ahora).limit(LOTE)).unique())
        almacen = AlmacenamientoLocal()
        archivos = 0
        for t in tickets:
            for a in self.session.scalars(select(m.TicketAdjunto).where(m.TicketAdjunto.ticket_id == t.id)):
                if a.ruta_almacenamiento:
                    try:
                        almacen.ruta(a.ruta_almacenamiento).unlink(missing_ok=True)
                        archivos += 1
                    except (OSError, ValueError):
                        pass
                a.eliminado, a.nombre_original, a.ruta_almacenamiento = True, "depurado", ""
            for c in self.session.scalars(select(m.TicketComentario).where(m.TicketComentario.ticket_id == t.id)):
                c.texto, c.copia_a = TEXTO_DEPURADO, None
            for cp in self.session.scalars(select(m.TicketCopia).where(m.TicketCopia.ticket_id == t.id)):
                self.session.delete(cp)
            t.asunto, t.descripcion = "[Depurado]", TEXTO_DEPURADO
            t.telefono, t.resumen_ia, t.en_nombre_motivo = None, None, None
            t.fecha_depuracion = ahora
        self.session.flush()
        restantes = self.session.scalar(select(func.count()).select_from(self._vencidos(ahora).subquery())) or 0
        self.auditoria.registrar(ctx, AccionAuditoria.DEPURACION_RETENCION, "ticket", None,
                                 {"tickets": [t.numero for t in tickets], "adjuntos_borrados": archivos, "anios": self.anios()})
        return {"depurados": len(tickets), "adjuntos": archivos, "restantes": restantes}

    def procesar(self, ahora: datetime | None = None) -> dict:
        """Primer día del mes: si hay tickets que cumplieron el plazo, avisa a TI para que apruebe la depuración."""
        from app.application.services.revision_acceso_service import _lista, _local

        ahora = ahora or utcnow()
        if _local(ahora, "%d") != "01" or (self.config()["retencion.aviso_mensual"] or "").strip().lower() not in ("si", "sí", "true", "1"):
            return {"omitido": "no corresponde"}
        mes = _local(ahora, "%Y-%m")
        marca = self.session.get(m.Configuracion, "retencion.ultimo_aviso")
        if marca is not None and marca.valor == mes:
            return {"omitido": "ya se avisó este mes"}
        total = self.session.scalar(select(func.count()).select_from(self._vencidos(ahora).subquery())) or 0
        if marca is None:
            marca = m.Configuracion(clave="retencion.ultimo_aviso", valor=mes, descripcion="Último mes en que se avisó de la depuración (no editar)")
            self.session.add(marca)
        marca.valor, marca.fecha_actualizacion = mes, ahora
        if not total:
            return {"por_depurar": 0}
        from app.application.services.revision_acceso_service import RevisionAccesoService

        svc = RevisionAccesoService(self.session)
        cuerpo = (f"<p>Hay <b>{total}</b> tickets que cumplieron {self.anios()} años desde su cierre y pueden depurarse "
                  "según la política de retención.</p><p>Revise la lista y apruebe la depuración en "
                  f"<a href=\"{settings.APP_URL}/cumplimiento\">Seguridad y cumplimiento › Retención</a>. "
                  "Nada se borra hasta que usted lo apruebe.</p>")
        svc._correo(_lista(svc.config()["accesos.informe_correo"]), f"{total} tickets listos para depurar ({html.escape(mes)})",
                    cuerpo, "AVISO_RETENCION")
        return {"por_depurar": total}

    def ticket(self, ticket_id: int) -> m.Ticket:
        t = self.session.get(m.Ticket, ticket_id)
        if t is None:
            raise NoEncontrado("Ticket no encontrado")
        return t
