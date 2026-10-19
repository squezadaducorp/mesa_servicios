"""Casos de uso del módulo de tickets."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.ia_service import IaService
from app.application.services.notificacion_service import NotificacionService
from app.application.services.sla_service import SlaService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.archivos import contenido_valido
from app.domain.enums import ESTADOS_PAUSA_SLA, AccionAuditoria, Estado, Permiso, Rol
from app.domain.reglas import TransicionInvalida, cuenta_como_primera_respuesta, es_reapertura, validar_transicion
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, TicketRepository, UsuarioRepository, coordinadores
from app.infrastructure.storage.local import AlmacenamientoLocal

ROLES_ATIENDEN = {Rol.ANALISTA, Rol.SUPERVISOR, Rol.ADMIN_MESA, Rol.SUPER_ADMIN}


def limites_dia_utc(desde, hasta) -> tuple[datetime | None, datetime | None]:
    """Convierte fechas locales (Ecuador) a límites UTC [desde 00:00, hasta+1 00:00)."""
    tz = ZoneInfo(settings.ZONA_HORARIA)
    f = lambda d: datetime.combine(d, time.min, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731
    return (f(desde) if desde else None, f(hasta + timedelta(days=1)) if hasta else None)


class TicketService:
    def __init__(self, session: Session, almacenamiento: AlmacenamientoLocal | None = None):
        self.session = session
        self.repo = TicketRepository(session)
        self.catalogo = CatalogoRepository(session)
        self.usuarios = UsuarioRepository(session)
        self.sla = SlaService(session)
        self.notif = NotificacionService(session)
        self.auditoria = AuditoriaService(session)
        self.ia = IaService(session)
        self._almacenamiento = almacenamiento

    @property
    def almacenamiento(self) -> AlmacenamientoLocal:
        if self._almacenamiento is None:
            self._almacenamiento = AlmacenamientoLocal()
        return self._almacenamiento

    # ================================================================ permisos
    @staticmethod
    def es_gestor(u: m.Usuario, t: m.Ticket) -> bool:
        """Quien puede operar el ticket: mesa de servicio, supervisor de la categoría o responsable."""
        if u.rol.codigo in (Rol.SUPER_ADMIN, Rol.ADMIN_MESA):
            return True
        if t.categoria.supervisor_id == u.id and u.tiene(Permiso.TICKET_VER_AREA):
            return True
        return t.responsable_id == u.id

    def acciones(self, u: m.Usuario, t: m.Ticket) -> list[str]:
        gestor = self.es_gestor(u, t)
        propio = t.solicitante_id == u.id
        estado = Estado(t.estado)
        a = []
        if estado == Estado.CANCELADO:
            return a
        abierto = estado not in (Estado.RESUELTO, Estado.CERRADO)
        if gestor and u.tiene(Permiso.TICKET_EDITAR) and abierto:
            a.append("editar")
        if u.tiene(Permiso.TICKET_ASIGNAR) and abierto and (u.tiene(Permiso.TICKET_VER_TODOS) or t.categoria.supervisor_id == u.id):
            a.append("asignar")
        if gestor and u.tiene(Permiso.TICKET_CAMBIAR_ESTADO) and abierto:
            a.append("cambiar_estado")
        if gestor and u.tiene(Permiso.TICKET_ESCALAR) and abierto and estado != Estado.ESCALADO:
            a.append("escalar")
        if (gestor and u.tiene(Permiso.TICKET_CERRAR) and estado != Estado.CERRADO) or (propio and estado == Estado.RESUELTO):
            a.append("cerrar")
        if u.tiene(Permiso.TICKET_REABRIR) and estado in (Estado.RESUELTO, Estado.CERRADO) and (gestor or propio):
            a.append("reabrir")
        if u.tiene(Permiso.TICKET_COMENTAR) and (gestor or propio):
            a.append("comentar")
            if gestor:
                a.append("nota_interna")
        if u.tiene(Permiso.TICKET_ADJUNTAR) and (gestor or propio):
            a.append("adjuntar")
        if u.tiene(Permiso.SLA_MODIFICAR) and abierto:
            a.append("excepcion_sla")
        if u.tiene(Permiso.REGISTRO_ELIMINAR):
            a.append("eliminar")
        if u.tiene(Permiso.IA_USAR) and gestor:
            a.append("ia")
        return a

    def _exigir(self, u: m.Usuario, t: m.Ticket, accion: str) -> None:
        if accion not in self.acciones(u, t):
            raise Prohibido("No tiene permiso para realizar esta acción sobre el ticket")

    def obtener(self, ticket_id: int, u: m.Usuario) -> m.Ticket:
        t = self.repo.get(ticket_id)
        if t is None or t.eliminado or not self.repo.puede_ver(u, ticket_id):
            raise NoEncontrado("Ticket no encontrado")
        return t

    def _hist(self, t: m.Ticket, u: m.Usuario | None, accion: str, campo=None, anterior=None, nuevo=None, detalle=None, ahora=None):
        self.session.add(
            m.TicketHistorial(ticket_id=t.id, usuario_id=u.id if u else None, accion=accion, campo=campo,
                              valor_anterior=None if anterior is None else str(anterior)[:500],
                              valor_nuevo=None if nuevo is None else str(nuevo)[:500], detalle=detalle, fecha=ahora or utcnow())
        )

    def _supervisor(self, t: m.Ticket) -> m.Usuario | None:
        if t.categoria.supervisor:
            return t.categoria.supervisor
        if t.responsable and t.responsable.supervisor_id:
            return self.usuarios.get(t.responsable.supervisor_id)
        return None

    # ================================================================== crear
    def crear(self, dto: s.TicketCrear, ctx: Contexto) -> m.Ticket:
        u: m.Usuario = ctx.usuario
        if not u.tiene(Permiso.TICKET_CREAR):
            raise Prohibido("No tiene permiso para crear tickets")
        categoria = self.catalogo.categoria(dto.categoria_id)
        sub = self.catalogo.subcategoria(dto.subcategoria_id)
        if not categoria or not categoria.activo or categoria.eliminado:
            raise ReglaNegocio("Categoría no válida")
        if not sub or sub.categoria_id != categoria.id or not sub.activo or sub.eliminado:
            raise ReglaNegocio("La subcategoría no pertenece a la categoría seleccionada")

        solicitante = u
        if dto.solicitante_id and dto.solicitante_id != u.id:
            if not u.tiene(Permiso.TICKET_VER_TODOS) or not u.tiene(Permiso.TICKET_ASIGNAR):
                raise Prohibido("Solo la mesa de servicio puede registrar tickets a nombre de otro usuario")
            solicitante = self.usuarios.get(dto.solicitante_id)
            if solicitante is None or not solicitante.activo:
                raise ReglaNegocio("Solicitante no válido")

        if dto.prioridad_id:
            prioridad = self.catalogo.prioridad(dto.prioridad_id)
            if prioridad is None:
                raise ReglaNegocio("Prioridad no válida")
        else:
            cliente = self.session.get(m.Cliente, dto.cliente_id) if dto.cliente_id else None
            codigo, _, _ = self.ia.local.sugerir_prioridad(f"{dto.asunto}. {dto.descripcion}", bool(cliente and cliente.es_vip))
            prioridad = self.catalogo.prioridad_por_codigo(codigo)

        responsable = None
        if dto.responsable_id:
            if not u.tiene(Permiso.TICKET_ASIGNAR):
                raise Prohibido("No tiene permiso para asignar responsables")
            responsable = self._validar_responsable(dto.responsable_id)
        else:
            responsable = self.ia.sugerir_responsable(categoria)

        ahora = utcnow()
        resp_min, res_min = self.sla.minutos_sla(categoria.id, prioridad)
        t = m.Ticket(
            numero=self.repo.siguiente_numero(datetime.now(ZoneInfo(settings.ZONA_HORARIA)).year),
            asunto=dto.asunto.strip(), descripcion=dto.descripcion.strip(),
            solicitante_id=solicitante.id, solicitante_nombre=solicitante.nombre, solicitante_cargo=solicitante.cargo,
            area_id=solicitante.area_id, cliente_id=dto.cliente_id, correo=str(dto.correo or solicitante.correo),
            telefono=dto.telefono or solicitante.telefono, categoria_id=categoria.id, subcategoria_id=sub.id,
            prioridad_id=prioridad.id, estado=Estado.NUEVO, canal=dto.canal, fecha_creacion=ahora, fecha_actualizacion=ahora,
            sla_respuesta_min=resp_min, sla_resolucion_min=res_min,
        )
        self.sla.inicializar(t)
        self.repo.add(t)
        self.session.refresh(t)
        self._hist(t, u, "CREACION", None, None, t.numero, ahora=ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_CREADO, "ticket", t.id, {"numero": t.numero, "categoria": categoria.nombre})

        self.notif.notificar([solicitante], "TICKET_CREADO", f"{t.numero} registrado", f"Su solicitud «{t.asunto}» fue registrada.", t)
        if t.canal != "CORREO":   # los tickets que llegan por correo reciben el acuse del buzón
            self.notif.correo("TICKET_CREADO", [solicitante], t)
        if responsable:
            self._asignar(t, responsable, u if dto.responsable_id else None, "MANUAL" if dto.responsable_id else "AUTOMATICA",
                          "Asignación directa al registrar" if dto.responsable_id else f"Asignación automática ({categoria.modo_asignacion.lower()})", ctx, ahora,
                          teams=False)
        else:
            self.notif.notificar([self._supervisor(t), *coordinadores(self.session)], "TICKET_SIN_ASIGNAR",
                                 f"{t.numero} pendiente de asignación", f"«{t.asunto}» ({categoria.nombre}) no tiene responsable.", t, "AVISO")
        self.notif.teams("TICKET_CREADO", t)
        self.session.flush()
        return t

    def _validar_responsable(self, usuario_id: int) -> m.Usuario:
        r = self.usuarios.get(usuario_id)
        if r is None or not r.activo or r.eliminado or r.rol.codigo not in ROLES_ATIENDEN:
            raise ReglaNegocio("El responsable debe ser un usuario activo de la mesa de servicio (analista o supervisor)")
        return r

    def _asignar(self, t: m.Ticket, nuevo: m.Usuario, por: m.Usuario | None, tipo: str, motivo: str | None, ctx: Contexto, ahora: datetime,
                 teams: bool = True):
        anterior = t.responsable
        t.responsable_id = nuevo.id
        t.responsable = nuevo
        t.fecha_asignacion = ahora
        if t.estado == Estado.NUEVO:
            t.estado = Estado.ASIGNADO
            self._hist(t, por, "CAMBIO_ESTADO", "estado", Estado.NUEVO, Estado.ASIGNADO, ahora=ahora)
        self.session.add(m.TicketAsignacion(ticket_id=t.id, responsable_anterior_id=anterior.id if anterior else None,
                                            responsable_nuevo_id=nuevo.id, asignado_por=por.id if por else None, tipo=tipo, motivo=motivo, fecha=ahora))
        self._hist(t, por, "ASIGNACION", "responsable", anterior.nombre if anterior else None, nuevo.nombre, motivo, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.ASIGNACION, "ticket", t.id,
                                 {"numero": t.numero, "de": anterior.nombre if anterior else None, "a": nuevo.nombre, "tipo": tipo})
        self.notif.notificar([nuevo], "TICKET_ASIGNADO", f"{t.numero} asignado a usted", f"«{t.asunto}» · prioridad {t.prioridad.nombre}.", t)
        self.notif.correo("TICKET_ASIGNADO", [nuevo], t)
        if teams:
            self.notif.teams("TICKET_ASIGNADO", t)
        t.fecha_actualizacion = ahora

    # ================================================================= editar
    def editar(self, ticket_id: int, dto: s.TicketEditar, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "editar")
        if dto.version is not None and dto.version != t.version:
            raise Conflicto("El ticket fue modificado por otro usuario. Recargue antes de guardar.")
        ahora = utcnow()
        cambios = {}
        datos = dto.model_dump(exclude_unset=True, exclude={"version"})
        if "categoria_id" in datos or "subcategoria_id" in datos:
            cat_id = datos.get("categoria_id", t.categoria_id)
            sub = self.catalogo.subcategoria(datos.get("subcategoria_id", t.subcategoria_id))
            if not sub or sub.categoria_id != cat_id:
                raise ReglaNegocio("La subcategoría no pertenece a la categoría seleccionada")
        if "prioridad_id" in datos and self.catalogo.prioridad(datos["prioridad_id"]) is None:
            raise ReglaNegocio("Prioridad no válida")
        for campo, valor in datos.items():
            actual = getattr(t, campo)
            if valor is not None and valor != actual:
                cambios[campo] = (actual, valor)
                setattr(t, campo, str(valor) if campo == "correo" else valor)
        if not cambios:
            return t
        self.session.flush()
        self.session.refresh(t)
        if {"categoria_id", "prioridad_id"} & cambios.keys():
            resp_min, res_min = self.sla.minutos_sla(t.categoria_id, t.prioridad)
            if (resp_min, res_min) != (t.sla_respuesta_min, t.sla_resolucion_min):
                cambios["sla"] = (f"{t.sla_respuesta_min}/{t.sla_resolucion_min} min", f"{resp_min}/{res_min} min")
                t.sla_respuesta_min, t.sla_resolucion_min = resp_min, res_min
                # Un nuevo SLA puede quitar o poner el ticket en alerta: se recalculan los niveles.
                t.sla_nivel_alerta = 0
                self.sla.recalcular(t, ahora)
        for campo, (antes, despues) in cambios.items():
            self._hist(t, u, "EDICION", campo, antes, despues, ahora=ahora)
        t.fecha_actualizacion = ahora
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_MODIFICADO, "ticket", t.id,
                                 {"numero": t.numero, "campos": {k: [str(a), str(b)] for k, (a, b) in cambios.items()}})
        return t

    # ================================================================ asignar
    def asignar(self, ticket_id: int, dto: s.AsignarEntrada, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "asignar")
        nuevo = self._validar_responsable(dto.responsable_id)
        if t.responsable_id == nuevo.id:
            raise ReglaNegocio("El ticket ya está asignado a ese responsable")
        tipo = "REASIGNACION" if t.responsable_id else "MANUAL"
        self._asignar(t, nuevo, u, tipo, dto.motivo, ctx, utcnow())
        return t

    def aceptar(self, ticket_id: int, ctx: Contexto) -> m.Ticket:
        """Tomar el ticket e iniciar la atención (botón «Aceptar» de Teams)."""
        u = ctx.usuario
        t = self.repo.get(ticket_id)
        if t is None or t.eliminado:
            raise NoEncontrado("Ticket no encontrado")
        if Estado(t.estado) not in (Estado.NUEVO, Estado.ASIGNADO, Estado.ESCALADO):
            raise ReglaNegocio(f"El ticket está {t.estado_rel.nombre.lower() if t.estado_rel else t.estado} y no puede aceptarse")
        if t.responsable_id != u.id:
            atiende_categoria = any(r.usuario_id == u.id for r in t.categoria.responsables)
            puede_asignar = self.repo.puede_ver(u, t.id) and "asignar" in self.acciones(u, t)
            if not (puede_asignar or (atiende_categoria and t.responsable_id is None)):
                raise Prohibido("Solo puede aceptar tickets sin responsable de sus categorías o los que ya tiene asignados")
            self._validar_responsable(u.id)
            self._asignar(t, u, u, "REASIGNACION" if t.responsable_id else "MANUAL", "Aceptado desde Microsoft Teams", ctx, utcnow(), teams=False)
        if Estado(t.estado) != Estado.EN_PROCESO:
            self._aplicar_estado(t, Estado(t.estado), Estado.EN_PROCESO, u, ctx, utcnow())
        return t

    # ========================================================== cambiar estado
    def cambiar_estado(self, ticket_id: int, nuevo: str, comentario: str | None, ctx: Contexto, *, accion: str = "cambiar_estado") -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, accion)
        actual, destino = Estado(t.estado), Estado(nuevo)
        try:
            validar_transicion(actual, destino)
        except TransicionInvalida as e:
            raise ReglaNegocio(str(e)) from e
        if destino == Estado.CERRADO and "cerrar" not in self.acciones(u, t):
            raise Prohibido("No tiene permiso para cerrar el ticket")
        if es_reapertura(actual, destino) and "reabrir" not in self.acciones(u, t):
            raise Prohibido("No tiene permiso para reabrir el ticket")
        if destino in (Estado.ASIGNADO, Estado.EN_PROCESO) and t.responsable_id is None:
            raise ReglaNegocio("Asigne un responsable antes de iniciar la atención")
        if destino in (Estado.PENDIENTE_CLIENTE, Estado.CANCELADO) and not (comentario or "").strip():
            raise ReglaNegocio("Indique un comentario para el solicitante")
        ahora = utcnow()
        self._aplicar_estado(t, actual, destino, u, ctx, ahora)
        if comentario and comentario.strip():
            self._agregar_comentario(t, u, comentario.strip(), False, "COMENTARIO", None, ahora)
            if self.es_gestor(u, t):
                self.responder_por_correo(t, u, comentario.strip())
        return t

    def correo_solicitante(self, codigo: str, t: m.Ticket, **extra) -> None:
        """Al usuario solicitante o, si el ticket vino de un remitente externo, a la dirección del correo original."""
        if settings.BUZON_ENABLED and t.solicitante.correo.lower() == settings.BUZON_CORREO.lower():
            self.notif.correo_directo(codigo, t.correo, t.correo, t, **extra)
        else:
            self.notif.correo(codigo, [t.solicitante], t, **extra)

    def responder_por_correo(self, t: m.Ticket, autor: m.Usuario, texto: str) -> None:
        """Los tickets que llegaron por correo reciben las respuestas del equipo en el mismo hilo de correo."""
        if settings.BUZON_ENABLED and t.canal == "CORREO":
            self.correo_solicitante("RESPUESTA_TICKET", t, comentario=texto[:4000], autor=autor.nombre)

    def _aplicar_estado(self, t: m.Ticket, actual: Estado, destino: Estado, u: m.Usuario | None, ctx: Contexto, ahora: datetime) -> None:
        reapertura = es_reapertura(actual, destino)
        # 1) Reloj SLA
        if reapertura:
            self.sla.reabrir(t, ahora)
            t.reaperturas += 1
        elif actual in ESTADOS_PAUSA_SLA and destino not in ESTADOS_PAUSA_SLA:
            self.sla.reanudar(t, ahora)
        if cuenta_como_primera_respuesta(destino) and not reapertura:
            self.sla.registrar_primera_respuesta(t, ahora)
        if destino == Estado.RESUELTO:
            self.sla.registrar_resolucion(t, ahora)
        if destino == Estado.CERRADO:
            if t.fecha_resolucion is None:
                self.sla.registrar_resolucion(t, ahora)
            t.fecha_cierre = ahora
        if destino in ESTADOS_PAUSA_SLA:
            self.sla.pausar(t, destino, u.id if u else None, ahora)
        elif t.sla_pausa_desde is None:
            self.sla.recalcular(t, ahora)
        # 2) Estado e historial
        t.estado = destino
        t.fecha_actualizacion = ahora
        self._hist(t, u, "REAPERTURA" if reapertura else "CIERRE" if destino == Estado.CERRADO else "CAMBIO_ESTADO",
                   "estado", actual, destino, ahora=ahora)
        accion = (AccionAuditoria.REAPERTURA if reapertura else AccionAuditoria.CIERRE if destino == Estado.CERRADO
                  else AccionAuditoria.CAMBIO_ESTADO)
        self.auditoria.registrar(ctx, accion, "ticket", t.id, {"numero": t.numero, "de": actual, "a": destino})
        # 3) Avisos
        solicitante = t.solicitante
        if destino == Estado.CERRADO:
            self.notif.notificar([solicitante], "TICKET_CERRADO", f"{t.numero} cerrado", f"Su solicitud «{t.asunto}» fue cerrada.", t)
            self.correo_solicitante("TICKET_CERRADO", t)
            self.notif.teams("TICKET_CERRADO", t)
        elif destino == Estado.RESUELTO:
            self.notif.notificar([solicitante], "TICKET_RESUELTO", f"{t.numero} resuelto",
                                 f"«{t.asunto}» fue resuelto. Puede confirmarlo o reabrirlo si persiste.", t)
        elif destino == Estado.PENDIENTE_CLIENTE:
            self.notif.notificar([solicitante], "PENDIENTE_CLIENTE", f"{t.numero} requiere su respuesta",
                                 f"El equipo necesita información para continuar con «{t.asunto}».", t, "AVISO")
        elif reapertura:
            self.notif.notificar([t.responsable, self._supervisor(t)], "TICKET_REABIERTO", f"{t.numero} reabierto",
                                 f"«{t.asunto}» fue reabierto ({t.reaperturas} reapertura(s)).", t, "AVISO")

    # ================================================================= escalar
    def escalar(self, ticket_id: int, dto: s.EscalarEntrada, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "escalar")
        destino = self.usuarios.get(dto.escalar_a_id) if dto.escalar_a_id else self._supervisor(t)
        if dto.escalar_a_id and (destino is None or destino.rol.codigo not in ROLES_ATIENDEN):
            raise ReglaNegocio("Destino de escalamiento no válido")
        ahora = utcnow()
        actual = Estado(t.estado)
        if actual in ESTADOS_PAUSA_SLA:
            self.sla.reanudar(t, ahora)
        self.sla.recalcular(t, ahora)
        t.estado = Estado.ESCALADO
        t.fecha_actualizacion = ahora
        self.session.add(m.TicketEscalamiento(ticket_id=t.id, nivel=0, tipo="MANUAL", escalado_por=u.id,
                                              escalado_a=destino.id if destino else None, motivo=dto.motivo,
                                              sla_consumido_pct=t.sla_consumido_pct, fecha=ahora))
        self._hist(t, u, "ESCALAMIENTO", "estado", actual, Estado.ESCALADO, dto.motivo, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.ESCALAMIENTO, "ticket", t.id,
                                 {"numero": t.numero, "a": destino.nombre if destino else None, "motivo": dto.motivo})
        destinatarios = [destino, *coordinadores(self.session)]
        self.notif.notificar(destinatarios, "TICKET_ESCALADO", f"{t.numero} escalado", f"«{t.asunto}»: {dto.motivo}", t, "AVISO")
        self.notif.correo("TICKET_ESCALADO", destinatarios, t, motivo=dto.motivo)
        self.notif.teams("TICKET_ESCALADO", t, dto.motivo)
        return t

    # ========================================================== cerrar/reabrir
    def cerrar(self, ticket_id: int, comentario: str | None, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "cerrar")
        ahora = utcnow()
        if comentario and comentario.strip():
            self._agregar_comentario(t, u, comentario.strip(), False, "COMENTARIO", None, ahora)
        if t.estado not in (Estado.RESUELTO, Estado.CERRADO):
            if t.responsable_id is None:
                raise ReglaNegocio("Asigne un responsable antes de cerrar el ticket")
            self._aplicar_estado(t, Estado(t.estado), Estado.RESUELTO, u, ctx, ahora)
        if t.estado == Estado.CERRADO:
            raise ReglaNegocio("El ticket ya está cerrado")
        self._aplicar_estado(t, Estado.RESUELTO, Estado.CERRADO, u, ctx, ahora)
        return t

    def reabrir(self, ticket_id: int, motivo: str, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "reabrir")
        ahora = utcnow()
        self._aplicar_estado(t, Estado(t.estado), Estado.EN_PROCESO, u, ctx, ahora)
        self._agregar_comentario(t, u, f"Reapertura: {motivo}", False, "COMENTARIO", None, ahora)
        return t

    # ============================================================ comentarios
    def comentar(self, ticket_id: int, dto: s.ComentarioEntrada, ctx: Contexto) -> m.TicketComentario:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "comentar")
        if dto.es_interno and "nota_interna" not in self.acciones(u, t):
            raise Prohibido("Solo el equipo de la mesa puede registrar notas internas")
        ahora = utcnow()
        c = self._agregar_comentario(t, u, dto.texto.strip(), dto.es_interno, dto.tipo, dto.minutos_invertidos, ahora)
        es_solicitante = t.solicitante_id == u.id and not self.es_gestor(u, t)
        if es_solicitante:
            # Respuesta del cliente: el SLA se reanuda automáticamente
            if t.estado == Estado.PENDIENTE_CLIENTE:
                self._aplicar_estado(t, Estado.PENDIENTE_CLIENTE, Estado.EN_PROCESO, None, ctx, ahora)
                self._hist(t, u, "REANUDACION", None, None, None, "El solicitante respondió; SLA reanudado", ahora)
            self.notif.notificar([t.responsable], "COMENTARIO", f"{t.numero}: nuevo comentario", f"{u.nombre}: {dto.texto[:200]}", t)
        else:
            if not dto.es_interno:
                self.sla.registrar_primera_respuesta(t, ahora)
                self.notif.notificar([t.solicitante], "COMENTARIO", f"{t.numero}: respuesta del equipo", f"{u.nombre}: {dto.texto[:200]}", t)
                self.responder_por_correo(t, u, dto.texto.strip())
        t.fecha_actualizacion = ahora
        return c

    def _agregar_comentario(self, t, u, texto, interno, tipo, minutos, ahora) -> m.TicketComentario:
        c = m.TicketComentario(ticket_id=t.id, usuario_id=u.id, texto=texto, es_interno=interno, tipo=tipo,
                               minutos_invertidos=minutos, fecha=ahora)
        self.session.add(c)
        self.session.flush()
        self.session.refresh(c)
        return c

    # ============================================================== adjuntos
    def adjuntar(self, ticket_id: int, nombre: str, tipo_mime: str, contenido: bytes, ctx: Contexto) -> m.TicketAdjunto:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "adjuntar")
        return self.guardar_adjunto(t, u, nombre, tipo_mime, contenido, ctx)

    def guardar_adjunto(self, t: m.Ticket, u: m.Usuario, nombre: str, tipo_mime: str, contenido: bytes, ctx: Contexto) -> m.TicketAdjunto:
        """Valida (extensión, tamaño, contenido) y guarda el archivo. También lo usa el buzón de correo."""
        config = self.catalogo.configuracion()
        max_mb = int(config.get("adjuntos.max_mb", settings.ADJUNTOS_MAX_MB))
        permitidas = {e.strip().lower() for e in config.get("adjuntos.extensiones", settings.ADJUNTOS_EXTENSIONES).split(",")}
        extension = Path(nombre).suffix.lower().lstrip(".")
        if extension not in permitidas:
            raise ReglaNegocio(f"Tipo de archivo no permitido (.{extension}). Permitidos: {', '.join(sorted(permitidas))}")
        if len(contenido) == 0:
            raise ReglaNegocio("El archivo está vacío")
        if len(contenido) > max_mb * 1024 * 1024:
            raise ReglaNegocio(f"El archivo supera el máximo de {max_mb} MB")
        if not contenido_valido(extension, contenido):
            self.auditoria.registrar(ctx, AccionAuditoria.ADJUNTO_SUBIDO, "ticket", t.id, {"archivo": Path(nombre).name[:255], "rechazado": "contenido"},
                                     resultado="ERROR")
            raise ReglaNegocio("El contenido del archivo no corresponde a su extensión o no está permitido")
        ruta, sha = self.almacenamiento.guardar(contenido, extension)
        a = m.TicketAdjunto(ticket_id=t.id, nombre_original=Path(nombre).name[:255], ruta_almacenamiento=ruta,
                            tipo_mime=(tipo_mime or "application/octet-stream")[:100], tamano_bytes=len(contenido),
                            hash_sha256=sha, subido_por=u.id, fecha=utcnow())
        self.session.add(a)
        self.session.flush()
        self.session.refresh(a)
        self._hist(t, u, "ADJUNTO", None, None, a.nombre_original)
        self.auditoria.registrar(ctx, AccionAuditoria.ADJUNTO_SUBIDO, "ticket", t.id, {"archivo": a.nombre_original, "sha256": sha})
        return a

    def adjunto(self, ticket_id: int, adjunto_id: int, ctx: Contexto) -> tuple[m.TicketAdjunto, Path]:
        t = self.obtener(ticket_id, ctx.usuario)
        a = self.session.get(m.TicketAdjunto, adjunto_id)
        if a is None or a.ticket_id != t.id or a.eliminado:
            raise NoEncontrado("Adjunto no encontrado")
        self.auditoria.registrar(ctx, AccionAuditoria.ADJUNTO_DESCARGADO, "ticket", t.id, {"archivo": a.nombre_original})
        return a, self.almacenamiento.ruta(a.ruta_almacenamiento)

    # ======================================================= SLA y eliminación
    def excepcion_sla(self, ticket_id: int, dto: s.ExcepcionSlaEntrada, ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "excepcion_sla")
        if dto.tipo == "EXTENSION" and not dto.minutos:
            raise ReglaNegocio("Indique los minutos laborables de la extensión")
        ahora = utcnow()
        self.session.add(m.SlaExcepcion(ticket_id=t.id, tipo=dto.tipo, minutos=dto.minutos, motivo=dto.motivo, aprobado_por=u.id, fecha=ahora))
        if dto.tipo == "EXTENSION":
            t.sla_minutos_extension = (t.sla_minutos_extension or 0) + dto.minutos
            t.sla_nivel_alerta = 0
            if t.sla_incumplido:
                t.sla_incumplido = False
        else:
            t.sla_excluido = True
        self.sla.recalcular(t, ahora)
        self._hist(t, u, "EXCEPCION_SLA", "sla", None, f"{dto.tipo} {dto.minutos or ''}".strip(), dto.motivo, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "ticket", t.id, {"numero": t.numero, **dto.model_dump()})
        return t

    def eliminar(self, ticket_id: int, ctx: Contexto) -> None:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "eliminar")
        t.eliminado, t.eliminado_por, t.fecha_eliminacion = True, u.id, utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.REGISTRO_ELIMINADO, "ticket", t.id, {"numero": t.numero})

    # =============================================================== consulta
    def consulta(self, u: m.Usuario, f: s.FiltroTickets):
        stmt = self.repo.consulta_visible(u)
        T = m.Ticket
        if f.texto:
            patron = f"%{f.texto.strip()}%"
            stmt = stmt.where(or_(T.numero.ilike(patron), T.asunto.ilike(patron), T.solicitante_nombre.ilike(patron)))
        if f.estado:
            stmt = stmt.where(T.estado.in_(f.estado))
        for campo in ("categoria_id", "subcategoria_id", "prioridad_id", "responsable_id", "cliente_id"):
            valor = getattr(f, campo)
            if valor:
                stmt = stmt.where(getattr(T, campo) == valor)
        if f.sla == "CUMPLIDO":
            stmt = stmt.where(T.sla_resolucion_cumplido == True, T.sla_incumplido == False)
        elif f.sla == "INCUMPLIDO":
            stmt = stmt.where(T.sla_incumplido == True)
        elif f.sla == "EN_CURSO":
            stmt = stmt.where(T.sla_resolucion_cumplido.is_(None), T.sla_incumplido == False)
        elif f.sla == "EN_RIESGO":
            stmt = stmt.where(T.sla_consumido_pct >= 75, T.estado.in_(["NUEVO", "ASIGNADO", "EN_PROCESO", "ESCALADO"]))
        desde, hasta = limites_dia_utc(f.desde, f.hasta)
        if desde:
            stmt = stmt.where(T.fecha_creacion >= desde)
        if hasta:
            stmt = stmt.where(T.fecha_creacion < hasta)
        if f.solo_mios:
            stmt = stmt.where(or_(T.responsable_id == u.id, T.solicitante_id == u.id))
        orden = {
            "fecha_desc": (T.fecha_creacion.desc(), T.id.desc()),
            "fecha_asc": (T.fecha_creacion.asc(), T.id.asc()),
            "sla_desc": (T.sla_consumido_pct.desc(), T.id.desc()),
            "prioridad": (T.prioridad_id.asc(), T.fecha_creacion.asc()),
        }[f.orden]
        return stmt.order_by(*orden)

    def listar(self, u: m.Usuario, f: s.FiltroTickets, pagina: int, tamano: int):
        return self.repo.paginar(self.consulta(u, f), pagina, tamano)


# ================================================================ mapeos
def a_listado(t: m.Ticket) -> dict:
    return {
        "id": t.id, "numero": t.numero, "asunto": t.asunto, "fecha_creacion": t.fecha_creacion,
        "solicitante_nombre": t.solicitante_nombre, "cliente": t.cliente.razon_social if t.cliente else None,
        "categoria": t.categoria.nombre, "subcategoria": t.subcategoria.nombre, "prioridad": t.prioridad.nombre,
        "prioridad_codigo": t.prioridad.codigo, "responsable": t.responsable.nombre if t.responsable else None,
        "estado": t.estado, "estado_nombre": t.estado_rel.nombre, "sla_consumido_pct": float(t.sla_consumido_pct or 0),
        "sla_resolucion_vence": t.sla_resolucion_vence, "sla_incumplido": t.sla_incumplido, "cumplimiento_sla": t.cumplimiento_sla,
    }


def a_detalle(svc: TicketService, t: m.Ticket, u: m.Usuario) -> dict:
    gestor = svc.es_gestor(u, t) or u.tiene(Permiso.TICKET_VER_TODOS)
    resumen = lambda x: {"id": x.id, "nombre": x.nombre, "correo": x.correo, "cargo": x.cargo} if x else None  # noqa: E731
    historial = svc.repo.historial(t.id) if gestor else [h for h in svc.repo.historial(t.id) if h.accion in ("CREACION", "CAMBIO_ESTADO", "CIERRE", "REAPERTURA")]
    return {
        **{k: getattr(t, k) for k in (
            "id", "numero", "asunto", "descripcion", "fecha_creacion", "solicitante_nombre", "solicitante_cargo", "correo", "telefono",
            "estado", "canal", "fecha_asignacion", "fecha_primera_respuesta", "fecha_resolucion", "fecha_cierre", "sla_respuesta_min",
            "sla_resolucion_min", "sla_respuesta_vence", "sla_resolucion_vence", "sla_minutos_consumidos", "sla_minutos_pausa",
            "sla_minutos_extension", "sla_respuesta_cumplido", "sla_resolucion_cumplido", "sla_incumplido", "sla_excluido",
            "cumplimiento_sla", "reaperturas", "version")},
        "solicitante": resumen(t.solicitante),
        "area": {"id": t.area.id, "nombre": t.area.nombre} if t.area else None,
        "cliente": {"id": t.cliente.id, "nombre": t.cliente.razon_social} if t.cliente else None,
        "categoria": {"id": t.categoria.id, "nombre": t.categoria.nombre},
        "subcategoria": {"id": t.subcategoria.id, "nombre": t.subcategoria.nombre},
        "prioridad": t.prioridad,
        "responsable": resumen(t.responsable),
        "estado_nombre": t.estado_rel.nombre,
        "sla_consumido_pct": float(t.sla_consumido_pct or 0),
        "sla_pausado": t.sla_pausa_desde is not None,
        "resumen_ia": t.resumen_ia if gestor else None,
        "riesgo_ia": float(t.riesgo_ia) if t.riesgo_ia is not None and gestor else None,
        "comentarios": [
            {"id": c.id, "usuario": resumen(c.usuario), "texto": c.texto, "es_interno": c.es_interno, "tipo": c.tipo,
             "minutos_invertidos": c.minutos_invertidos, "fecha": c.fecha}
            for c in svc.repo.comentarios(t.id, incluir_internos=gestor)
        ],
        "adjuntos": [
            {"id": a.id, "nombre_original": a.nombre_original, "tipo_mime": a.tipo_mime, "tamano_bytes": a.tamano_bytes,
             "usuario": resumen(a.usuario), "fecha": a.fecha} for a in svc.repo.adjuntos(t.id)
        ],
        "historial": [
            {"id": h.id, "accion": h.accion, "campo": h.campo, "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo,
             "detalle": h.detalle, "usuario": resumen(h.usuario), "fecha": h.fecha} for h in historial
        ],
        "escalamientos": [
            {"id": e.id, "nivel": e.nivel, "tipo": e.tipo, "motivo": e.motivo,
             "sla_consumido_pct": float(e.sla_consumido_pct) if e.sla_consumido_pct is not None else None, "fecha": e.fecha}
            for e in (svc.repo.escalamientos(t.id) if gestor else [])
        ],
        "acciones": svc.acciones(u, t),
    }


def responsables_disponibles(session: Session) -> list[m.Usuario]:
    return list(
        session.scalars(
            select(m.Usuario).join(m.Rol).where(m.Rol.codigo.in_([Rol.ANALISTA, Rol.SUPERVISOR]), m.Usuario.activo == True,
                                                 m.Usuario.eliminado == False).order_by(m.Usuario.nombre)
        ).unique()
    )
