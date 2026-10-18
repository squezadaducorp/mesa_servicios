"""Repositorios específicos del dominio."""
from datetime import datetime

from sqlalchemy import false, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.domain.enums import ESTADOS_ABIERTOS, Permiso, Rol as RolEnum
from app.infrastructure.db import models as m
from app.infrastructure.repositories.base import Repository


class UsuarioRepository(Repository[m.Usuario]):
    model = m.Usuario

    def por_correo(self, correo: str) -> m.Usuario | None:
        return self.session.scalar(
            select(m.Usuario).where(func.lower(m.Usuario.correo) == correo.lower().strip(), m.Usuario.eliminado == False)
        )

    def por_usuario_ad(self, usuario_ad: str) -> m.Usuario | None:
        return self.session.scalar(
            select(m.Usuario).where(func.lower(m.Usuario.usuario_ad) == usuario_ad.lower(), m.Usuario.eliminado == False)
        )

    def por_rol(self, *codigos: str) -> list[m.Usuario]:
        return list(
            self.session.scalars(
                select(m.Usuario).join(m.Rol).where(m.Rol.codigo.in_(codigos), m.Usuario.activo == True, m.Usuario.eliminado == False)
            ).unique()
        )

    def rol_por_codigo(self, codigo: str) -> m.Rol | None:
        return self.session.scalar(select(m.Rol).where(m.Rol.codigo == codigo))

    def carga_abierta(self, usuario_ids: list[int]) -> dict[int, int]:
        filas = self.session.execute(
            select(m.Ticket.responsable_id, func.count())
            .where(m.Ticket.responsable_id.in_(usuario_ids), m.Ticket.estado.in_([e.value for e in ESTADOS_ABIERTOS]), m.Ticket.eliminado == False)
            .group_by(m.Ticket.responsable_id)
        ).all()
        carga = {uid: 0 for uid in usuario_ids}
        carga.update({uid: n for uid, n in filas})
        return carga


class RefreshTokenRepository(Repository[m.RefreshToken]):
    model = m.RefreshToken

    def por_hash(self, token_hash: str) -> m.RefreshToken | None:
        return self.session.scalar(select(m.RefreshToken).where(m.RefreshToken.token_hash == token_hash))

    def revocar_familia(self, familia: str, ahora: datetime) -> None:
        self.session.execute(
            update(m.RefreshToken)
            .where(m.RefreshToken.familia == familia, m.RefreshToken.revocado == False)
            .values(revocado=True, fecha_revocacion=ahora)
        )

    def revocar_usuario(self, usuario_id: int, ahora: datetime) -> None:
        self.session.execute(
            update(m.RefreshToken)
            .where(m.RefreshToken.usuario_id == usuario_id, m.RefreshToken.revocado == False)
            .values(revocado=True, fecha_revocacion=ahora)
        )


class CatalogoRepository:
    def __init__(self, session: Session):
        self.session = session

    def categorias(self, solo_activas: bool = True) -> list[m.Categoria]:
        stmt = select(m.Categoria).where(m.Categoria.eliminado == False).order_by(m.Categoria.orden, m.Categoria.nombre)
        if solo_activas:
            stmt = stmt.where(m.Categoria.activo == True)
        return list(self.session.scalars(stmt).unique())

    def categoria(self, id_: int) -> m.Categoria | None:
        return self.session.get(m.Categoria, id_)

    def subcategoria(self, id_: int) -> m.Subcategoria | None:
        return self.session.get(m.Subcategoria, id_)

    def prioridades(self) -> list[m.Prioridad]:
        return list(self.session.scalars(select(m.Prioridad).order_by(m.Prioridad.orden)))

    def prioridad(self, id_: int) -> m.Prioridad | None:
        return self.session.get(m.Prioridad, id_)

    def prioridad_por_codigo(self, codigo: str) -> m.Prioridad | None:
        return self.session.scalar(select(m.Prioridad).where(m.Prioridad.codigo == codigo))

    def politica(self, categoria_id: int, prioridad_id: int) -> m.SlaPolitica | None:
        return self.session.scalar(
            select(m.SlaPolitica).where(
                m.SlaPolitica.categoria_id == categoria_id, m.SlaPolitica.prioridad_id == prioridad_id, m.SlaPolitica.activo == True
            )
        )

    def estados(self) -> list[m.EstadoTicket]:
        return list(self.session.scalars(select(m.EstadoTicket).order_by(m.EstadoTicket.orden)))

    def areas(self) -> list[m.Area]:
        return list(self.session.scalars(select(m.Area).where(m.Area.activo == True).order_by(m.Area.nombre)))

    def clientes(self) -> list[m.Cliente]:
        return list(
            self.session.scalars(select(m.Cliente).where(m.Cliente.eliminado == False, m.Cliente.activo == True).order_by(m.Cliente.razon_social))
        )

    def horario_predeterminado(self) -> m.HorarioLaboral | None:
        return self.session.scalar(select(m.HorarioLaboral).where(m.HorarioLaboral.es_predeterminado == True, m.HorarioLaboral.activo == True))

    def excepciones_calendario(self) -> list[m.CalendarioExcepcion]:
        return list(self.session.scalars(select(m.CalendarioExcepcion).order_by(m.CalendarioExcepcion.fecha)))

    def plantilla(self, codigo: str) -> m.PlantillaCorreo | None:
        return self.session.scalar(select(m.PlantillaCorreo).where(m.PlantillaCorreo.codigo == codigo, m.PlantillaCorreo.activo == True))

    def configuracion(self) -> dict[str, str]:
        return {c.clave: c.valor for c in self.session.scalars(select(m.Configuracion))}


class TicketRepository(Repository[m.Ticket]):
    model = m.Ticket

    def por_numero(self, numero: str) -> m.Ticket | None:
        return self.session.scalar(select(m.Ticket).where(m.Ticket.numero == numero, m.Ticket.eliminado == False))

    def filtro_visibilidad(self, usuario: m.Usuario):
        """Alcance de datos según permisos: todos, área (categorías supervisadas), asignados o propios."""
        permisos = usuario.permisos
        if Permiso.TICKET_VER_TODOS in permisos:
            return None
        condiciones = []
        if Permiso.TICKET_VER_AREA in permisos:
            condiciones.append(m.Ticket.categoria_id.in_(select(m.Categoria.id).where(m.Categoria.supervisor_id == usuario.id)))
        if Permiso.TICKET_VER_ASIGNADOS in permisos:
            condiciones.append(m.Ticket.responsable_id == usuario.id)
        if Permiso.TICKET_VER_PROPIOS in permisos:
            condiciones.append(m.Ticket.solicitante_id == usuario.id)
        return or_(*condiciones) if condiciones else false()

    def consulta_visible(self, usuario: m.Usuario):
        stmt = select(m.Ticket).where(m.Ticket.eliminado == False)
        filtro = self.filtro_visibilidad(usuario)
        return stmt if filtro is None else stmt.where(filtro)

    def puede_ver(self, usuario: m.Usuario, ticket_id: int) -> bool:
        stmt = self.consulta_visible(usuario).where(m.Ticket.id == ticket_id).with_only_columns(m.Ticket.id)
        return self.session.scalar(stmt) is not None

    def siguiente_numero(self, anio: int) -> str:
        if self.session.bind.dialect.name == "mssql":
            numero = self.session.execute(
                text("DECLARE @n VARCHAR(20); EXEC dbo.sp_GenerarNumeroTicket @anio = :anio, @numero = @n OUTPUT; SELECT @n;"), {"anio": anio}
            ).scalar_one()
            return numero
        sec = self.session.get(m.TicketSecuencia, anio, with_for_update=True)
        if sec is None:
            sec = m.TicketSecuencia(anio=anio, ultimo=0)
            self.session.add(sec)
        sec.ultimo += 1
        self.session.flush()
        return f"ADU-{anio}-{sec.ultimo:06d}"

    def abiertos_para_sla(self) -> list[m.Ticket]:
        return list(
            self.session.scalars(
                select(m.Ticket).where(
                    m.Ticket.eliminado == False,
                    m.Ticket.sla_excluido == False,
                    m.Ticket.estado.in_(["NUEVO", "ASIGNADO", "EN_PROCESO", "ESCALADO", "PENDIENTE_CLIENTE"]),
                )
            ).unique()
        )

    def comentarios(self, ticket_id: int, incluir_internos: bool) -> list[m.TicketComentario]:
        stmt = select(m.TicketComentario).where(m.TicketComentario.ticket_id == ticket_id).order_by(m.TicketComentario.fecha, m.TicketComentario.id)
        if not incluir_internos:
            stmt = stmt.where(m.TicketComentario.es_interno == False)
        return list(self.session.scalars(stmt).unique())

    def adjuntos(self, ticket_id: int) -> list[m.TicketAdjunto]:
        return list(
            self.session.scalars(
                select(m.TicketAdjunto).where(m.TicketAdjunto.ticket_id == ticket_id, m.TicketAdjunto.eliminado == False).order_by(m.TicketAdjunto.fecha)
            ).unique()
        )

    def historial(self, ticket_id: int) -> list[m.TicketHistorial]:
        return list(
            self.session.scalars(
                select(m.TicketHistorial).where(m.TicketHistorial.ticket_id == ticket_id).order_by(m.TicketHistorial.fecha, m.TicketHistorial.id)
            ).unique()
        )

    def escalamientos(self, ticket_id: int) -> list[m.TicketEscalamiento]:
        return list(self.session.scalars(select(m.TicketEscalamiento).where(m.TicketEscalamiento.ticket_id == ticket_id).order_by(m.TicketEscalamiento.fecha)))

    def pausa_abierta(self, ticket_id: int) -> m.SlaPausa | None:
        return self.session.scalar(
            select(m.SlaPausa).where(m.SlaPausa.ticket_id == ticket_id, m.SlaPausa.fin.is_(None)).order_by(m.SlaPausa.inicio.desc())
        )

    def existe_incumplimiento(self, ticket_id: int, tipo: str) -> bool:
        return self.session.scalar(
            select(m.SlaIncumplimiento.id).where(m.SlaIncumplimiento.ticket_id == ticket_id, m.SlaIncumplimiento.tipo == tipo)
        ) is not None


class NotificacionRepository(Repository[m.Notificacion]):
    model = m.Notificacion

    def del_usuario(self, usuario_id: int, solo_no_leidas: bool, limite: int) -> list[m.Notificacion]:
        stmt = select(m.Notificacion).where(m.Notificacion.usuario_id == usuario_id)
        if solo_no_leidas:
            stmt = stmt.where(m.Notificacion.leida == False)
        return list(self.session.scalars(stmt.order_by(m.Notificacion.fecha.desc(), m.Notificacion.id.desc()).limit(limite)))

    def no_leidas(self, usuario_id: int) -> int:
        return self.session.scalar(
            select(func.count()).select_from(m.Notificacion).where(m.Notificacion.usuario_id == usuario_id, m.Notificacion.leida == False)
        ) or 0

    def marcar_todas(self, usuario_id: int, ahora: datetime) -> None:
        self.session.execute(
            update(m.Notificacion)
            .where(m.Notificacion.usuario_id == usuario_id, m.Notificacion.leida == False)
            .values(leida=True, fecha_lectura=ahora)
        )


class AuditoriaRepository(Repository[m.Auditoria]):
    model = m.Auditoria


def coordinadores(session: Session) -> list[m.Usuario]:
    return UsuarioRepository(session).por_rol(RolEnum.ADMIN_MESA)
