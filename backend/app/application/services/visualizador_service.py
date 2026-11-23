"""Visualizadores de un ticket (34): personas de Aducorp que lo siguen desde la Mesa sin atenderlo.

- Ven el ticket aunque su rol no se lo permita y comentan en público; no ven notas internas, no cambian estado,
  prioridad, responsable ni categoría, y no califican la encuesta.
- Los agrega el responsable, el solicitante, un supervisor o un administrador; cualquiera que ya vea el ticket
  puede «Seguir», y cada visualizador puede quitarse.
- Siempre reciben aviso en la campana; por correo según elijan: TODO (respuestas, estado y cierre), ESTADO (estado y
  cierre) o NINGUNO. Nunca se avisa a quien hizo el cambio.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Rol
from app.infrastructure.db import models as m

AVISOS = ("TODO", "ESTADO", "NINGUNO")
NOMBRE_AVISOS = {"TODO": "Todo", "ESTADO": "Estado y cierre", "NINGUNO": "Solo campana"}
MAX_VISUALIZADORES = 15
ROLES_GESTION = {Rol.SUPERVISOR, Rol.ADMIN_MESA, Rol.SUPER_ADMIN}


def ids(texto: str | None) -> list[int]:
    return [int(x) for x in (texto or "").replace(";", ",").split(",") if x.strip().isdigit()]


class VisualizadorService:
    def __init__(self, session: Session):
        self.session = session
        self.notif = NotificacionService(session)
        self.auditoria = AuditoriaService(session)

    def filas(self, ticket_id: int) -> list[m.TicketVisualizador]:
        V = m.TicketVisualizador
        return list(self.session.scalars(select(V).where(V.ticket_id == ticket_id).order_by(V.fecha, V.id)).unique())

    def fila(self, ticket_id: int, usuario_id: int) -> m.TicketVisualizador | None:
        V = m.TicketVisualizador
        return self.session.scalar(select(V).where(V.ticket_id == ticket_id, V.usuario_id == usuario_id))

    def es_visualizador(self, u: m.Usuario, t: m.Ticket) -> bool:
        return self.fila(t.id, u.id) is not None

    @staticmethod
    def puede_gestionar(svc, u: m.Usuario, t: m.Ticket) -> bool:
        return svc.es_gestor(u, t) or t.solicitante_id == u.id or u.rol.codigo in ROLES_GESTION

    def _ticket(self, ticket_id: int, u: m.Usuario):
        from app.application.services.ticket_service import TicketService

        svc = TicketService(self.session)
        return svc, svc.obtener(ticket_id, u)

    def salida(self, t: m.Ticket, u: m.Usuario, gestiona: bool) -> list[dict]:
        return [{
            "usuario_id": v.usuario_id, "nombre": v.usuario.nombre, "cargo": v.usuario.cargo,
            "area": v.usuario.area.nombre if v.usuario.area else None, "avisos_correo": v.avisos_correo, "origen": v.origen,
            "agregado_por": v.agregador.nombre if v.agregador else None, "fecha": v.fecha.isoformat() + "Z",
            "propio": v.usuario_id == u.id, "editable": gestiona or v.usuario_id == u.id,
        } for v in self.filas(t.id)]

    # ------------------------------------------------------------- cambios
    def _agregar(self, svc, t: m.Ticket, usuario: m.Usuario, avisos: str, origen: str, por: m.Usuario | None,
                 ctx: Contexto | None, ahora: datetime) -> m.TicketVisualizador:
        if avisos not in AVISOS:
            raise ReglaNegocio("Aviso no válido")
        if usuario.id == t.solicitante_id:
            raise ReglaNegocio("El solicitante ya recibe todos los avisos del ticket")
        if self.fila(t.id, usuario.id):
            raise ReglaNegocio(f"{usuario.nombre} ya sigue este ticket")
        if len(self.filas(t.id)) >= MAX_VISUALIZADORES:
            raise ReglaNegocio(f"Un ticket admite hasta {MAX_VISUALIZADORES} visualizadores")
        v = m.TicketVisualizador(ticket_id=t.id, usuario_id=usuario.id, avisos_correo=avisos, origen=origen,
                                 agregado_por=por.id if por else None, fecha=ahora)
        self.session.add(v)
        self.session.flush()
        cargo = f" ({usuario.cargo})" if usuario.cargo else ""
        if origen == "SEGUIR":
            detalle = f"{usuario.nombre}{cargo} empezó a seguir el ticket"
        elif origen == "CATEGORIA":
            detalle = f"{usuario.nombre}{cargo} sigue el ticket por la categoría"
        else:
            detalle = f"{por.nombre if por else 'El sistema'} agregó a {usuario.nombre}{cargo} como visualizador"
        svc._hist(t, por, "VISUALIZADOR", "visualizadores", None, usuario.nombre, detalle, ahora)
        if ctx is not None:
            self.auditoria.registrar(ctx, AccionAuditoria.VISUALIZADOR_AGREGADO, "ticket", t.id,
                                     {"numero": t.numero, "usuario": usuario.nombre, "origen": origen})
        if por is not None and por.id != usuario.id:
            self.notif.notificar([usuario], "VISUALIZADOR", f"Sigue {t.numero}",
                                 f"{por.nombre} lo agregó como visualizador de «{t.asunto}».", t)
        return v

    def agregar(self, ticket_id: int, usuario_id: int, avisos: str, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        svc, t = self._ticket(ticket_id, u)
        if not self.puede_gestionar(svc, u, t):
            raise Prohibido("Solo el responsable, el solicitante o un supervisor agregan visualizadores")
        usuario = self.session.get(m.Usuario, usuario_id)
        if usuario is None or usuario.eliminado or not usuario.activo:
            raise NoEncontrado("Usuario no encontrado")
        self._agregar(svc, t, usuario, avisos, "MANUAL", u, ctx, utcnow())
        return t

    def seguir(self, ticket_id: int, avisos: str, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        svc, t = self._ticket(ticket_id, u)
        if t.responsable_id == u.id:
            raise ReglaNegocio("Usted es el responsable: ya recibe los avisos del ticket")
        self._agregar(svc, t, u, avisos, "SEGUIR", u, ctx, utcnow())
        return t

    def cambiar_avisos(self, ticket_id: int, usuario_id: int, avisos: str, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        svc, t = self._ticket(ticket_id, u)
        v = self.fila(t.id, usuario_id)
        if v is None:
            raise NoEncontrado("No es visualizador del ticket")
        if usuario_id != u.id and not self.puede_gestionar(svc, u, t):
            raise Prohibido("Solo puede cambiar sus propios avisos")
        if avisos not in AVISOS:
            raise ReglaNegocio("Aviso no válido")
        v.avisos_correo = avisos
        return t

    def quitar(self, ticket_id: int, usuario_id: int, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        svc, t = self._ticket(ticket_id, u)
        v = self.fila(t.id, usuario_id)
        if v is None:
            raise NoEncontrado("No es visualizador del ticket")
        if usuario_id != u.id and not self.puede_gestionar(svc, u, t):
            raise Prohibido("Solo puede dejar de seguir usted mismo")
        nombre = v.usuario.nombre
        self.session.delete(v)
        ahora = utcnow()
        detalle = f"{nombre} dejó de seguir el ticket" if usuario_id == u.id else f"{u.nombre} quitó a {nombre} de los visualizadores"
        svc._hist(t, u, "VISUALIZADOR", "visualizadores", nombre, None, detalle, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.VISUALIZADOR_QUITADO, "ticket", t.id, {"numero": t.numero, "usuario": nombre})
        self.session.flush()
        return t

    def candidatos(self, ticket_id: int, q: str | None, u: m.Usuario) -> list[dict]:
        svc, t = self._ticket(ticket_id, u)
        if not self.puede_gestionar(svc, u, t):
            raise Prohibido("Solo el responsable, el solicitante o un supervisor agregan visualizadores")
        U = m.Usuario
        fuera = {t.solicitante_id, *(v.usuario_id for v in self.filas(t.id))}
        stmt = select(U).where(U.eliminado == False, U.activo == True)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            stmt = stmt.where(or_(U.nombre.ilike(patron), U.correo.ilike(patron), U.cargo.ilike(patron)))
        filas = [x for x in self.session.scalars(stmt.order_by(U.nombre).limit(60)).unique() if x.id not in fuera]
        return [{"id": x.id, "nombre": x.nombre, "cargo": x.cargo, "area": x.area.nombre if x.area else None} for x in filas[:20]]

    def precargar(self, svc, t: m.Ticket, categoria: m.Categoria, ahora: datetime) -> None:
        """Visualizadores automáticos configurados en la categoría."""
        for uid in ids(categoria.visualizadores):
            usuario = self.session.get(m.Usuario, uid)
            if usuario and usuario.activo and not usuario.eliminado and uid not in (t.solicitante_id, t.responsable_id) \
                    and self.fila(t.id, uid) is None:
                self._agregar(svc, t, usuario, "ESTADO", "CATEGORIA", None, None, ahora)

    # --------------------------------------------------------------- avisos
    def avisar(self, t: m.Ticket, autor_id: int | None, tipo: str, titulo: str, mensaje: str) -> int:
        """tipo: RESPUESTA (respuesta pública), ESTADO (cambio de estado) o CIERRE."""
        filas = [v for v in self.filas(t.id) if v.usuario_id != autor_id and v.usuario.activo and not v.usuario.eliminado]
        if not filas:
            return 0
        self.notif.notificar([v.usuario for v in filas], "VISUALIZADOR", titulo, mensaje, t)
        por_correo = [v.usuario for v in filas
                      if v.avisos_correo == "TODO" or (v.avisos_correo == "ESTADO" and tipo in ("ESTADO", "CIERRE"))]
        if por_correo:
            self.notif.correo("TICKET_VISUALIZADOR", por_correo, t, novedad=mensaje)
        return len(filas)
