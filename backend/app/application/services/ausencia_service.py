"""Modo ausente / vacaciones: los tickets del analista pasan a su reemplazo y vuelven al terminar la ausencia.

- PROGRAMADA → ACTIVA (al llegar «desde»): se reasignan los tickets abiertos (si pasar_abiertos) y se avisa a los solicitantes.
- Mientras está ACTIVA, la asignación automática envía al reemplazo los tickets nuevos que le tocarían al ausente.
- ACTIVA → FINALIZADA (al llegar «hasta» o con «Volví antes»): se devuelven los tickets que sigan abiertos (si devolver).
El worker llama a procesar() en cada ciclo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService, fecha_local
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import ESTADOS_ABIERTOS, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import UsuarioRepository

MOTIVOS = {"VACACIONES": "vacaciones", "PERMISO": "permiso", "ENFERMEDAD": "enfermedad", "CAPACITACION": "capacitación", "OTRO": "ausencia"}
VIGENTES = ("PROGRAMADA", "ACTIVA")


def a_utc(local: datetime) -> datetime:
    """Las fechas llegan en hora de Ecuador (sin zona) y se guardan en UTC."""
    if local.tzinfo is None:
        local = local.replace(tzinfo=ZoneInfo(settings.ZONA_HORARIA))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def corto(d: datetime) -> str:
    return fecha_local(d)[:10] if d else ""


class AusenciaService:
    def __init__(self, session: Session):
        self.session = session
        self.notif = NotificacionService(session)
        self.usuarios = UsuarioRepository(session)

    # --------------------------------------------------------------- permisos
    @staticmethod
    def administra(u: m.Usuario) -> bool:
        return u.tiene(Permiso.USUARIO_ADMINISTRAR) or (u.tiene(Permiso.TICKET_ASIGNAR) and u.tiene(Permiso.TICKET_VER_TODOS))

    def _puede_gestionar(self, u: m.Usuario, usuario: m.Usuario) -> bool:
        return usuario.id == u.id or self.administra(u) or usuario.supervisor_id == u.id

    # ---------------------------------------------------------------- consulta
    def vigentes(self) -> list[m.UsuarioAusencia]:
        A = m.UsuarioAusencia
        return list(self.session.scalars(select(A).where(A.estado.in_(VIGENTES)).order_by(A.desde)).unique())

    def de_usuario(self, usuario_id: int) -> list[m.UsuarioAusencia]:
        A = m.UsuarioAusencia
        return list(self.session.scalars(
            select(A).where(or_(A.usuario_id == usuario_id, A.reemplazo_id == usuario_id), A.estado.in_(VIGENTES)).order_by(A.desde)
        ).unique())

    def tickets_abiertos(self, usuario_id: int) -> list[m.Ticket]:
        T = m.Ticket
        return list(self.session.scalars(
            select(T).where(T.responsable_id == usuario_id, T.eliminado == False, T.estado.in_([e.value for e in ESTADOS_ABIERTOS]))
            .order_by(T.fecha_creacion)
        ).unique())

    def tickets_pasados(self, ausencia_id: int) -> int:
        return len(self.session.scalars(select(m.AusenciaTicket.ticket_id).where(m.AusenciaTicket.ausencia_id == ausencia_id)).all())

    def _solapa(self, usuario_id: int, desde: datetime, hasta: datetime, excluir: int | None = None) -> m.UsuarioAusencia | None:
        A = m.UsuarioAusencia
        stmt = select(A).where(A.usuario_id == usuario_id, A.estado.in_(VIGENTES), A.desde < hasta, A.hasta > desde)
        if excluir:
            stmt = stmt.where(A.id != excluir)
        return self.session.scalars(stmt).first()

    def sugerir_reemplazos(self, usuario_id: int, desde: datetime | None, hasta: datetime | None) -> list[dict]:
        """Quien atiende las mismas categorías y tiene menos carga, sin ausencias en esas fechas."""
        from app.application.services.ticket_service import responsables_disponibles

        desde_u, hasta_u = (a_utc(desde), a_utc(hasta)) if desde and hasta else (utcnow(), utcnow())
        mias = {r.categoria_id for r in self.session.scalars(select(m.CategoriaResponsable).where(m.CategoriaResponsable.usuario_id == usuario_id))}
        nombres = dict(self.session.execute(select(m.Categoria.id, m.Categoria.nombre)).all())
        candidatos = [u for u in responsables_disponibles(self.session) if u.id != usuario_id and not self._solapa(u.id, desde_u, hasta_u)]
        carga = self.usuarios.carga_abierta([u.id for u in candidatos]) if candidatos else {}
        categorias: dict[int, set[int]] = {}
        for r in self.session.scalars(select(m.CategoriaResponsable)):
            categorias.setdefault(r.usuario_id, set()).add(r.categoria_id)
        filas = []
        for u in candidatos:
            comunes = sorted(nombres.get(c, "") for c in (categorias.get(u.id, set()) & mias))
            filas.append({"id": u.id, "nombre": u.nombre, "correo": u.correo, "tickets_abiertos": carga.get(u.id, 0),
                          "categorias_comunes": comunes})
        filas.sort(key=lambda f: (-len(f["categorias_comunes"]), f["tickets_abiertos"], f["nombre"]))
        if filas:
            filas[0]["sugerido"] = True
        return filas

    # ------------------------------------------------------------------ crear
    def crear(self, dto: s.AusenciaEntrada, ctx: Contexto) -> m.UsuarioAusencia:
        u = ctx.usuario
        from app.application.services.ticket_service import ROLES_ATIENDEN

        usuario = self.usuarios.get(dto.usuario_id or u.id)
        if usuario is None or not usuario.activo or usuario.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        if not self._puede_gestionar(u, usuario):
            raise Prohibido("Solo puede registrar sus propias ausencias")
        reemplazo = self.usuarios.get(dto.reemplazo_id)
        if reemplazo is None or not reemplazo.activo or reemplazo.eliminado or reemplazo.rol.codigo not in ROLES_ATIENDEN:
            raise ReglaNegocio("El reemplazo debe ser un usuario activo de la mesa de servicio")
        if reemplazo.id == usuario.id:
            raise ReglaNegocio("El reemplazo debe ser otra persona")
        desde, hasta = a_utc(dto.desde), a_utc(dto.hasta)
        ahora = utcnow()
        if hasta <= desde:
            raise ReglaNegocio("La fecha de regreso debe ser posterior a la de inicio")
        if hasta <= ahora:
            raise ReglaNegocio("La ausencia ya terminó")
        if self._solapa(usuario.id, desde, hasta):
            raise ReglaNegocio(f"{usuario.nombre} ya tiene una ausencia registrada en esas fechas")
        if self._solapa(reemplazo.id, desde, hasta):
            raise ReglaNegocio(f"{reemplazo.nombre} también estará ausente en esas fechas")
        a = m.UsuarioAusencia(usuario_id=usuario.id, reemplazo_id=reemplazo.id, motivo=dto.motivo, desde=desde, hasta=hasta,
                              pasar_abiertos=dto.pasar_abiertos, devolver=dto.devolver, avisar_solicitantes=dto.avisar_solicitantes,
                              estado="PROGRAMADA", creado_por=u.id, fecha_creacion=ahora)
        self.session.add(a)
        self.session.flush()
        self.session.refresh(a)
        AuditoriaService(self.session).registrar(ctx, "AUSENCIA", "usuario", usuario.id, {
            "ausencia": a.id, "motivo": a.motivo, "desde": fecha_local(desde), "hasta": fecha_local(hasta), "reemplazo": reemplazo.nombre})
        self.notif.notificar([reemplazo], "AUSENCIA_REEMPLAZO", f"Cubrirá a {usuario.nombre}",
                             f"Del {corto(desde)} al {corto(hasta)} ({MOTIVOS.get(a.motivo, 'ausencia')}).", None, "INFO")
        if usuario.id != u.id:
            self.notif.notificar([usuario], "AUSENCIA_REGISTRADA", "Se registró su ausencia",
                                 f"Del {corto(desde)} al {corto(hasta)}; le reemplaza {reemplazo.nombre}.", None, "INFO")
        if desde <= ahora:
            self.activar(a, ahora, ctx)
        return a

    def cancelar(self, ausencia_id: int, ctx: Contexto) -> m.UsuarioAusencia:
        """Programada: se anula. Activa: termina ahora («Volví antes») y se devuelven los tickets."""
        a = self.session.get(m.UsuarioAusencia, ausencia_id)
        if a is None or a.estado not in VIGENTES:
            raise NoEncontrado("Ausencia no encontrada o ya terminada")
        if not self._puede_gestionar(ctx.usuario, a.usuario):
            raise Prohibido("No puede modificar esta ausencia")
        ahora = utcnow()
        if a.estado == "PROGRAMADA":
            a.estado, a.fecha_fin_real = "CANCELADA", ahora
            self.notif.notificar([a.reemplazo], "AUSENCIA_CANCELADA", f"Ya no cubrirá a {a.usuario.nombre}",
                                 f"Se canceló la ausencia del {corto(a.desde)} al {corto(a.hasta)}.", None, "INFO")
        else:
            self.finalizar(a, ahora, ctx, anticipada=True)
        AuditoriaService(self.session).registrar(ctx, "AUSENCIA", "usuario", a.usuario_id, {"ausencia": a.id, "operacion": "cancelar"})
        return a

    # ------------------------------------------------------- inicio y regreso
    def activar(self, a: m.UsuarioAusencia, ahora: datetime, ctx: Contexto | None = None) -> int:
        from app.application.services.ticket_service import TicketService

        ctx = ctx or Contexto(ip="worker", equipo="ausencias")
        a.estado, a.fecha_inicio_real = "ACTIVA", ahora
        motivo_txt = MOTIVOS.get(a.motivo, "ausencia")
        movidos = 0
        if a.pasar_abiertos:
            svc = TicketService(self.session)
            for t in self.tickets_abiertos(a.usuario_id):
                svc._asignar(t, a.reemplazo, None, "AUSENCIA",
                             f"Reasignado de {a.usuario.nombre} a {a.reemplazo.nombre} por {motivo_txt} ({corto(a.desde)} – {corto(a.hasta)})",
                             ctx, ahora, teams=False)
                self.session.add(m.AusenciaTicket(ausencia_id=a.id, ticket_id=t.id))
                if a.avisar_solicitantes:
                    svc.correo_solicitante("AUSENCIA_REASIGNADO", t, ausente=a.usuario.nombre, reemplazo=a.reemplazo.nombre,
                                           regreso=corto(a.hasta), motivo=motivo_txt)
                movidos += 1
        self.notif.notificar([a.reemplazo], "AUSENCIA_REEMPLAZO", f"Usted cubre a {a.usuario.nombre} hasta el {corto(a.hasta)}",
                             f"Se le pasaron {movidos} ticket(s) y recibirá los nuevos que le tocarían a {a.usuario.nombre}.", None, "AVISO")
        self.session.flush()
        return movidos

    def finalizar(self, a: m.UsuarioAusencia, ahora: datetime, ctx: Contexto | None = None, anticipada: bool = False) -> int:
        from app.application.services.ticket_service import TicketService

        ctx = ctx or Contexto(ip="worker", equipo="ausencias")
        a.estado, a.fecha_fin_real = "FINALIZADA", ahora
        devueltos = 0
        if a.devolver and a.usuario.activo and not a.usuario.eliminado:
            svc = TicketService(self.session)
            abiertos = {e.value for e in ESTADOS_ABIERTOS}
            for at in self.session.scalars(select(m.AusenciaTicket).where(m.AusenciaTicket.ausencia_id == a.id,
                                                                         m.AusenciaTicket.devuelto == False)):
                t = self.session.get(m.Ticket, at.ticket_id)
                if t is None or t.eliminado or t.estado not in abiertos or t.responsable_id != a.reemplazo_id:
                    continue
                svc._asignar(t, a.usuario, None, "AUSENCIA",
                             f"Devuelto a {a.usuario.nombre} al terminar la ausencia" + (" (regresó antes)" if anticipada else ""),
                             ctx, ahora, teams=False)
                at.devuelto = True
                devueltos += 1
        self.notif.notificar([a.usuario], "AUSENCIA_FIN", "Bienvenido de vuelta",
                             f"Se le devolvieron {devueltos} ticket(s) que seguían abiertos." if a.devolver else "Su ausencia terminó.", None, "INFO")
        self.notif.notificar([a.reemplazo], "AUSENCIA_FIN", f"Terminó el reemplazo de {a.usuario.nombre}",
                             f"{devueltos} ticket(s) volvieron a {a.usuario.nombre}.", None, "INFO")
        self.session.flush()
        return devueltos

    def procesar(self, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        A = m.UsuarioAusencia
        iniciadas = terminadas = 0
        for a in self.session.scalars(select(A).where(A.estado == "PROGRAMADA", A.desde <= ahora)).unique().all():
            if a.hasta <= ahora:   # el worker estuvo detenido toda la ausencia
                a.estado, a.fecha_fin_real = "FINALIZADA", ahora
                continue
            self.activar(a, ahora)
            iniciadas += 1
        for a in self.session.scalars(select(A).where(A.estado == "ACTIVA", A.hasta <= ahora)).unique().all():
            self.finalizar(a, ahora)
            terminadas += 1
        return {"iniciadas": iniciadas, "terminadas": terminadas}


def a_salida(a: m.UsuarioAusencia, abiertos: int | None = None) -> dict:
    return {
        "id": a.id, "usuario": {"id": a.usuario.id, "nombre": a.usuario.nombre, "correo": a.usuario.correo},
        "reemplazo": {"id": a.reemplazo.id, "nombre": a.reemplazo.nombre, "correo": a.reemplazo.correo},
        "motivo": a.motivo, "desde": a.desde, "hasta": a.hasta, "estado": a.estado, "pasar_abiertos": a.pasar_abiertos,
        "devolver": a.devolver, "avisar_solicitantes": a.avisar_solicitantes, "tickets_abiertos": abiertos,
    }
