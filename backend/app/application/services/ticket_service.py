"""Casos de uso del módulo de tickets."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.aprobacion_service import AprobacionService
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.encuesta_service import EncuestaService
from app.application.services.encuesta_service import a_salida as encuesta_salida
from app.application.services.ia_service import IaService
from app.application.services.inventario_service import InventarioService
from app.application.services.notificacion_service import NotificacionService, cuentas_sistema
from app.application.services.conocimiento_service import exigir_sin_internos
from app.application.services.proveedor_service import ProveedorService
from app.application.services.sla_service import SlaService
from app.application.services.tiempo_service import TiempoService
from app.application.services.visualizador_service import VisualizadorService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.archivos import contenido_valido
from app.domain.correos import MAX_COPIAS, separar, unir
from app.domain.enums import ESTADOS_PAUSA_SLA, AccionAuditoria, Estado, Permiso, Rol
from app.domain.reglas import TransicionInvalida, cuenta_como_primera_respuesta, es_reapertura, validar_transicion
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, TicketRepository, UsuarioRepository, coordinadores
from app.infrastructure.storage.local import AlmacenamientoLocal

MAX_ARCHIVOS_COMENTARIO = 10

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
        # Reasignar: mesa de servicio (ver todos), supervisor de la categoría o el responsable actual (traspasa su ticket)
        if u.tiene(Permiso.TICKET_ASIGNAR) and abierto and (
            u.tiene(Permiso.TICKET_VER_TODOS) or t.categoria.supervisor_id == u.id or t.responsable_id == u.id
        ):
            a.append("asignar")
        if gestor and u.tiene(Permiso.TICKET_CAMBIAR_ESTADO) and abierto:
            a.append("cambiar_estado")
        if gestor and u.tiene(Permiso.TICKET_ESCALAR) and abierto and estado != Estado.ESCALADO:
            a.append("escalar")
        if (gestor and u.tiene(Permiso.TICKET_CERRAR) and estado != Estado.CERRADO) or (propio and estado == Estado.RESUELTO):
            a.append("cerrar")
        if u.tiene(Permiso.TICKET_REABRIR) and estado in (Estado.RESUELTO, Estado.CERRADO) and (gestor or propio):
            a.append("reabrir")
        if propio and estado in (Estado.RESUELTO, Estado.CERRADO) and EncuestaService(self.session).puede_calificar(u, t):
            a.append("calificar")
        tarea = not gestor and not propio and self._tiene_tarea(u, t)   # analista con una tarea del catálogo en este ticket
        visualizador = VisualizadorService(self.session).es_visualizador(u, t)   # (34) comenta en público y nada más
        if u.tiene(Permiso.TICKET_COMENTAR) and (gestor or propio or tarea or visualizador):
            a.append("comentar")
            if gestor or tarea:
                a.append("nota_interna")
            if gestor:
                a.append("copias")
        if u.tiene(Permiso.TICKET_ADJUNTAR) and (gestor or propio or tarea or visualizador):
            a.append("adjuntar")
        if gestor and u.tiene(Permiso.TICKET_ESCALAR) and abierto and estado != Estado.POR_APROBAR \
                and ProveedorService(self.session).caso_abierto(t.id) is None:
            a.append("escalar_proveedor")
        if gestor or propio:
            a.append("clasificar")   # (42) el solicitante solo puede subirla a Confidencial
        if visualizador:
            a.append("dejar_seguir")
        elif not propio and t.responsable_id != u.id and t.clasificacion != "CONFIDENCIAL":
            a.append("seguir")
        if VisualizadorService.puede_gestionar(self, u, t) and t.clasificacion != "CONFIDENCIAL":
            a.append("visualizadores")
        if u.tiene(Permiso.SLA_MODIFICAR) and abierto:
            a.append("excepcion_sla")
        if u.tiene(Permiso.REGISTRO_ELIMINAR):
            a.append("eliminar")
        if u.tiene(Permiso.IA_USAR) and gestor:
            a.append("ia")
        if estado == Estado.POR_APROBAR:   # hasta que el jefe responda no se asigna, escala ni resuelve (sí se puede cancelar)
            a = [x for x in a if x not in ("asignar", "escalar", "cerrar")]
        if gestor and u.tiene(Permiso.TICKET_EDITAR):
            a.append("vincular")
        return a

    def _tiene_tarea(self, u: m.Usuario, t: m.Ticket) -> bool:
        return self.session.scalar(select(m.TicketTarea.id).where(m.TicketTarea.ticket_id == t.id,
                                                                  m.TicketTarea.responsable_id == u.id).limit(1)) is not None

    def cliente_por_correo(self, *correos: str | None) -> int | None:
        """Cliente cuya empresa usa el dominio del correo (p. ej. @aducorp.com.ec → Aducorp CIA LTDA). Ignora las cuentas técnicas."""
        from app.application.services.notificacion_service import cuentas_sistema
        from app.domain.correos import separar

        dominios = [c.strip().lower().rsplit("@", 1)[-1] for c in correos if c and "@" in c and c.strip().lower() not in cuentas_sistema()]
        if not dominios:
            return None
        clientes = list(self.session.scalars(select(m.Cliente).where(m.Cliente.activo == True, m.Cliente.eliminado == False,
                                                                        m.Cliente.dominios.is_not(None))))
        for d in dominios:
            for c in clientes:
                if d in separar(c.dominios):
                    return c.id
        return None

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
    def crear(self, dto: s.TicketCrear, ctx: Contexto, *, sistema: bool = False, canal: str | None = None,
              recurrente_id: int | None = None, aprobacion: tuple[str, int | None] | None = None,
              resolucion_min: int | None = None, al_crear=None) -> m.Ticket:
        """Registra un ticket. ``sistema`` lo usa el worker (tickets recurrentes): omite los permisos del usuario."""
        u: m.Usuario | None = ctx.usuario
        if not sistema and not u.tiene(Permiso.TICKET_CREAR):
            raise Prohibido("No tiene permiso para crear tickets")
        categoria = self.catalogo.categoria(dto.categoria_id)
        sub = self.catalogo.subcategoria(dto.subcategoria_id)
        if not categoria or not categoria.activo or categoria.eliminado:
            raise ReglaNegocio("Categoría no válida")
        if not sub or sub.categoria_id != categoria.id or not sub.activo or sub.eliminado:
            raise ReglaNegocio("La subcategoría no pertenece a la categoría seleccionada")

        solicitante, creado_por, motivo = u, None, None
        if sistema:
            solicitante = self.usuarios.get(dto.solicitante_id) if dto.solicitante_id else None
            if solicitante is None:
                raise ReglaNegocio("Solicitante no válido")
        elif dto.solicitante_id and dto.solicitante_id != u.id:
            solicitante = self.usuarios.get(dto.solicitante_id)
            if solicitante is None or not solicitante.activo or solicitante.eliminado:
                raise ReglaNegocio("Solicitante no válido")
            motivo = (dto.en_nombre_motivo or "").strip() or None
            if not self.es_mesa_registro(u):
                self.validar_en_nombre(u, solicitante, categoria, motivo, sub.id)
            creado_por = u

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
            if not sistema and not u.tiene(Permiso.TICKET_ASIGNAR):
                raise Prohibido("No tiene permiso para asignar responsables")
            responsable = self._validar_responsable(dto.responsable_id)
        else:
            responsable = self.ia.sugerir_responsable(categoria)
        equipo = self._validar_equipo(dto.equipo_id, u, solicitante) if dto.equipo_id else None

        cliente_id = dto.cliente_id or self.cliente_por_correo(str(dto.correo or ""), solicitante.correo)
        ahora = utcnow()
        resp_min, res_min = self.sla.minutos_sla(categoria.id, prioridad)
        if resolucion_min:   # plazo comprometido del servicio del catálogo
            res_min = max(resolucion_min, resp_min)
        t = m.Ticket(
            numero=self.repo.siguiente_numero(datetime.now(ZoneInfo(settings.ZONA_HORARIA)).year),
            asunto=dto.asunto.strip(), descripcion=dto.descripcion.strip(),
            solicitante_id=solicitante.id, solicitante_nombre=solicitante.nombre, solicitante_cargo=solicitante.cargo,
            area_id=solicitante.area_id, cliente_id=cliente_id, correo=str(dto.correo or solicitante.correo),
            telefono=dto.telefono or solicitante.telefono, categoria_id=categoria.id, subcategoria_id=sub.id,
            prioridad_id=prioridad.id, estado=Estado.NUEVO, canal=canal or dto.canal, fecha_creacion=ahora, fecha_actualizacion=ahora,
            sla_respuesta_min=resp_min, sla_resolucion_min=res_min, equipo_id=equipo.id if equipo else None,
            recurrente_id=recurrente_id, creado_por_id=creado_por.id if creado_por else None, en_nombre_motivo=motivo,
            clasificacion=categoria.clasificacion or "INTERNA",
        )
        self.sla.inicializar(t)
        self.repo.add(t)
        self.session.refresh(t)
        self._hist(t, u, "CREACION", None, None, t.numero, ahora=ahora)
        self._precargar_copias(t, categoria, ahora)
        VisualizadorService(self.session).precargar(self, t, categoria, ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_CREADO, "ticket", t.id, {"numero": t.numero, "categoria": categoria.nombre})
        if creado_por:
            self._hist(t, u, "EN_NOMBRE", "solicitante", None, solicitante.nombre,
                       f"Registrado por {u.nombre} en nombre de {solicitante.nombre}" + (f". Motivo: {motivo}" if motivo else ""), ahora)
            self.auditoria.registrar(ctx, AccionAuditoria.TICKET_CREADO_EN_NOMBRE, "ticket", t.id,
                                     {"numero": t.numero, "creado_por": u.nombre, "en_nombre_de": solicitante.nombre,
                                      "solicitante_id": solicitante.id, "motivo": motivo, "categoria": categoria.nombre})
        if dto.kb_vistos:
            from app.application.services.conocimiento_service import ConocimientoService

            ConocimientoService(self.session).registrar_vistos(t.id, dto.kb_vistos)

        self.notif.notificar([solicitante], "TICKET_CREADO", f"{t.numero} registrado",
                             f"{u.nombre} registró «{t.asunto}» en su nombre." if creado_por else f"Su solicitud «{t.asunto}» fue registrada.", t)
        if creado_por:   # el beneficiario siempre se entera, aunque no lo haya pedido
            self.notif.correo("TICKET_EN_NOMBRE", [solicitante], t, creado_por=u.nombre, motivo=motivo or "(sin motivo)")
        elif t.canal not in ("CORREO", "WEB", "PROGRAMADO"):   # correo y formulario público envían su propio acuse
            self.notif.correo("TICKET_CREADO", [solicitante], t)
        if dto.aviso_id:
            from app.application.services.aviso_service import AvisoService

            AvisoService(self.session).vincular_ticket(dto.aviso_id, t, solicitante)
        if al_crear is not None:   # p. ej. el catálogo guarda el formulario y las tareas antes de asignar
            al_crear(t)
        if not sistema and AprobacionService(self.session).iniciar(self, t, ctx, ahora, aprobacion):
            pass   # queda «Por aprobar»: se asigna cuando el jefe lo apruebe
        elif responsable:
            self._asignar(t, responsable, u if dto.responsable_id else None, "MANUAL" if dto.responsable_id else "AUTOMATICA",
                          "Asignación directa al registrar" if dto.responsable_id else f"Asignación automática ({categoria.modo_asignacion.lower()})", ctx, ahora,
                          teams=False)
        else:
            self.notif.notificar([self._supervisor(t), *coordinadores(self.session)], "TICKET_SIN_ASIGNAR",
                                 f"{t.numero} pendiente de asignación", f"«{t.asunto}» ({categoria.nombre}) no tiene responsable.", t, "AVISO")
        self.notif.teams("TICKET_CREADO", t)
        self.session.flush()
        return t

    # ================================================== en nombre de otra persona
    @staticmethod
    def es_mesa_registro(u: m.Usuario) -> bool:
        """La mesa de servicio registra tickets de llamadas o visitas a nombre de cualquier persona."""
        return u.tiene(Permiso.TICKET_VER_TODOS) and u.tiene(Permiso.TICKET_ASIGNAR)

    def delegacion_vigente(self, u: m.Usuario) -> m.UsuarioDelegacion | None:
        d = self.session.get(m.UsuarioDelegacion, u.id)
        if d is None:
            return None
        hoy = datetime.now(ZoneInfo(settings.ZONA_HORARIA)).date()
        return None if d.hasta and d.hasta < hoy else d

    def validar_en_nombre(self, u: m.Usuario, solicitante: m.Usuario, categoria: m.Categoria, motivo: str | None,
                          subcategoria_id: int | None = None) -> None:
        d = self.delegacion_vigente(u)
        if d is None:
            raise Prohibido("No tiene autorización para crear tickets en nombre de otra persona")
        if d.area_ids and solicitante.area_id not in d.area_ids:
            raise Prohibido(f"No está autorizado a crear tickets en nombre de personas de {solicitante.area.nombre if solicitante.area else 'esa área'}")
        if categoria.restringida_en_nombre and AprobacionService(self.session).regla_para(categoria.id, subcategoria_id) is None:
            # Con una regla de aprobación activa sí se puede: el jefe del beneficiario da el visto bueno antes de atenderlo.
            raise ReglaNegocio(f"«{categoria.nombre}» no se puede pedir en nombre de otra persona: debe solicitarlo {solicitante.nombre} "
                               "o la Mesa de Servicios")
        if not motivo or len(motivo) < 5:
            raise ReglaNegocio("Indique el motivo por el que crea el ticket en nombre de otra persona")

    def personas_en_nombre(self, u: m.Usuario) -> list[m.Usuario]:
        """Personas a cuyo nombre puede registrar tickets el usuario (vacío si no está autorizado)."""
        U = m.Usuario
        stmt = select(U).where(U.activo == True, U.eliminado == False, U.id != u.id).order_by(U.nombre)
        if not self.es_mesa_registro(u):
            d = self.delegacion_vigente(u)
            if d is None:
                return []
            if d.area_ids:
                stmt = stmt.where(U.area_id.in_(d.area_ids))
        return [x for x in self.session.scalars(stmt).unique() if x.correo.lower() not in cuentas_sistema()]

    def _validar_equipo(self, equipo_id: int, u: m.Usuario | None, solicitante: m.Usuario) -> m.Equipo:
        e = self.session.get(m.Equipo, equipo_id)
        if e is None or e.eliminado or e.estado == "BAJA":
            raise ReglaNegocio("Equipo no válido")
        from app.application.services.inventario_service import InventarioService

        if not InventarioService.ve_todo_al_registrar(u) and not InventarioService.disponible_para(e, solicitante):
            raise Prohibido("Ese equipo no está asignado a usted ni es compartido")
        return e

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
        if destino in (Estado.RESUELTO, Estado.CERRADO):
            self.exigir_sin_bloqueos(t)
        if actual == Estado.POR_APROBAR:
            AprobacionService(self.session).anular(t, f"Ticket cancelado por {u.nombre}")
        ahora = utcnow()
        self._aplicar_estado(t, actual, destino, u, ctx, ahora)
        if comentario and comentario.strip():
            c = self._agregar_comentario(t, u, comentario.strip(), False, "COMENTARIO", None, ahora)
            if self.es_gestor(u, t):
                c.copia_a = unir(self.responder_por_correo(t, u, comentario.strip(), self.copias(t)))
        return t

    def correo_solicitante(self, codigo: str, t: m.Ticket, *, cc: list[str] | None = None, **extra) -> bool:
        """Al usuario solicitante o, si el ticket vino de un remitente externo, a la dirección del correo original.
        `cc` son las personas en copia; devuelve si el correo quedó en cola."""
        cuenta = t.solicitante.correo.lower()
        if cuenta == settings.FORMULARIO_WEB_CORREO.lower():
            # Formulario público: el solicitante no tiene cuenta, el enlace lleva al formulario y no al ticket
            extra.setdefault("url", f"{settings.APP_URL.rstrip('/')}/solicitud")
            return self.notif.correo_directo(codigo, t.correo, t.solicitante_nombre, t, cc=cc, **extra)
        if settings.BUZON_ENABLED and cuenta == settings.BUZON_CORREO.lower():
            return self.notif.correo_directo(codigo, t.correo, t.correo, t, cc=cc, **extra)
        return self.notif.correo(codigo, [t.solicitante], t, cc=cc, **extra)

    def responder_por_correo(self, t: m.Ticket, autor: m.Usuario, texto: str, copias: list[str] | None = None) -> list[str]:
        """Los tickets que llegaron por correo reciben las respuestas del equipo en el mismo hilo de correo;
        los del formulario público, un aviso por correo (el solicitante no tiene cuenta para verlas).
        Las personas en copia reciben la respuesta en CC o, si el solicitante no recibe correo, en un aviso aparte.
        Devuelve los correos que quedaron en copia."""
        cc = self._cc_validos(t, copias)
        datos = {"comentario": texto[:4000], "autor": autor.nombre}
        enviado = False
        if settings.BUZON_ENABLED and t.canal == "CORREO":
            enviado = self.correo_solicitante("RESPUESTA_TICKET", t, cc=cc, **datos)
        elif t.canal == "WEB":
            enviado = self.correo_solicitante("RESPUESTA_WEB", t, cc=cc, **datos)
        if cc and not enviado and not self.notif.correo_copias("RESPUESTA_COPIA", cc, t, **datos):
            return []
        return cc

    # ======================================================= personas en copia
    def copias(self, t: m.Ticket) -> list[str]:
        return [c.correo for c in self.repo.copias(t.id)]

    def _cc_validos(self, t: m.Ticket, correos: list[str] | None) -> list[str]:
        """Quita al propio solicitante y a las cuentas técnicas; el resto ya viene validado."""
        excluir = {(t.correo or "").lower(), t.solicitante.correo.lower(), *cuentas_sistema()}
        return [c for c in (correos or []) if c.lower() not in excluir]

    def _precargar_copias(self, t: m.Ticket, categoria: m.Categoria, ahora: datetime) -> None:
        """Copia automática configurada en la categoría y en el cliente del ticket."""
        cliente = self.session.get(m.Cliente, t.cliente_id) if t.cliente_id else None
        vistos: set[str] = set()
        for origen, texto in (("CATEGORIA", categoria.correos_copia), ("CLIENTE", cliente.correos_copia if cliente else None)):
            for correo in self._cc_validos(t, separar(texto)):
                if correo not in vistos and len(vistos) < MAX_COPIAS:
                    vistos.add(correo)
                    self.session.add(m.TicketCopia(ticket_id=t.id, correo=correo, origen=origen, fecha=ahora))
        if vistos:
            self.session.flush()
            self._hist(t, None, "COPIAS", "copias", None, ", ".join(vistos), "Copia automática por categoría o cliente", ahora)

    def agregar_copias(self, t: m.Ticket, correos: list[str], origen: str, ahora: datetime | None = None) -> list[str]:
        """Suma correos a la lista del ticket sin quitar los existentes (lo usa el buzón con los CC del correo original)."""
        actuales = self.copias(t)
        nuevos = [c for c in self._cc_validos(t, correos) if c not in actuales][: max(0, MAX_COPIAS - len(actuales))]
        for correo in nuevos:
            self.session.add(m.TicketCopia(ticket_id=t.id, correo=correo, origen=origen, fecha=ahora or utcnow()))
        if nuevos:
            self.session.flush()
        return nuevos

    def actualizar_copias(self, ticket_id: int, correos: list[str], ctx: Contexto) -> m.Ticket:
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "copias")
        filas = self.repo.copias(t.id)
        antes = [f.correo for f in filas]
        despues = self._cc_validos(t, correos)
        if antes == despues:
            return t
        ahora = utcnow()
        for f in filas:
            if f.correo not in despues:
                self.session.delete(f)
        for correo in despues:
            if correo not in antes:
                self.session.add(m.TicketCopia(ticket_id=t.id, correo=correo, origen="MANUAL", agregado_por=u.id, fecha=ahora))
        self.session.flush()
        self._hist(t, u, "COPIAS", "copias", unir(antes), unir(despues), ahora=ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_MODIFICADO, "ticket", t.id,
                                 {"numero": t.numero, "copias_antes": antes, "copias_despues": despues})
        t.fecha_actualizacion = ahora
        return t

    def _aplicar_estado(self, t: m.Ticket, actual: Estado, destino: Estado, u: m.Usuario | None, ctx: Contexto, ahora: datetime) -> None:
        reapertura = es_reapertura(actual, destino)
        # 1) Reloj SLA
        if reapertura:
            self.sla.reabrir(t, ahora)
            t.reaperturas += 1
        elif t.sla_pausa_desde is not None and destino not in ESTADOS_PAUSA_SLA:
            # sale de un estado en pausa o de un escalamiento a proveedor (33), que también pausa nuestro SLA
            self.sla.reanudar(t, ahora)
        if actual == Estado.ESCALADO and destino != Estado.ESCALADO:
            ProveedorService(self.session).cerrar_abiertos(t, ahora)
        if destino in (Estado.PENDIENTE_CLIENTE, Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO):
            TiempoService(self.session).pausar_ticket(t.id, ahora)   # (31) el cronómetro se detiene solo
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
            self.correo_solicitante("TICKET_CERRADO", t, cc=self._cc_validos(t, self.copias(t)))
            self.notif.teams("TICKET_CERRADO", t)
        elif destino == Estado.RESUELTO:
            self.notif.notificar([solicitante], "TICKET_RESUELTO", f"{t.numero} resuelto",
                                 f"«{t.asunto}» fue resuelto. Califique la atención o reábralo si persiste.", t)
            EncuestaService(self.session).invitar(self, t)
        elif destino == Estado.PENDIENTE_CLIENTE:
            self.notif.notificar([solicitante], "PENDIENTE_CLIENTE", f"{t.numero} requiere su respuesta",
                                 f"El equipo necesita información para continuar con «{t.asunto}».", t, "AVISO")
        elif reapertura:
            self.notif.notificar([t.responsable, self._supervisor(t)], "TICKET_REABIERTO", f"{t.numero} reabierto",
                                 f"«{t.asunto}» fue reabierto ({t.reaperturas} reapertura(s)).", t, "AVISO")
        nombre = self.session.get(m.EstadoTicket, str(destino))
        nombre = nombre.nombre if nombre else str(destino)
        VisualizadorService(self.session).avisar(
            t, u.id if u else None, "CIERRE" if destino in (Estado.CERRADO, Estado.RESUELTO) else "ESTADO",
            f"{t.numero} pasó a «{nombre}»", f"«{t.asunto}» ahora está {nombre.lower()}.")

    def exigir_sin_bloqueos(self, t: m.Ticket) -> None:
        """Un ticket «Bloqueado por» otro no se resuelve hasta que el otro esté resuelto, cerrado o cancelado."""
        from app.application.services.vinculo_service import VinculoService

        abiertos = VinculoService(self.session).bloqueos_abiertos(t)
        if abiertos:
            raise ReglaNegocio("No se puede resolver: está bloqueado por " + ", ".join(x.numero for x in abiertos) + " que sigue abierto")

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
            self.exigir_sin_bloqueos(t)
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
    def comentar(self, ticket_id: int, dto: s.ComentarioEntrada, ctx: Contexto,
                 archivos: list[tuple[str, str, bytes]] | None = None) -> m.TicketComentario:
        """Agrega un comentario. `archivos` (nombre, tipo, contenido) son capturas o archivos que van con el comentario:
        se validan todos antes de guardar nada y quedan enlazados al comentario (y en la pestaña Adjuntos)."""
        u = ctx.usuario
        t = self.obtener(ticket_id, u)
        self._exigir(u, t, "comentar")
        if dto.es_interno and "nota_interna" not in self.acciones(u, t):
            raise Prohibido("Solo el equipo de la mesa puede registrar notas internas")
        archivos = archivos or []
        if archivos:
            self._exigir(u, t, "adjuntar")
            if len(archivos) > MAX_ARCHIVOS_COMENTARIO:
                raise ReglaNegocio(f"Puede adjuntar hasta {MAX_ARCHIVOS_COMENTARIO} archivos por comentario")
            max_mb, permitidas = self.reglas_adjuntos()
            for nombre, _, contenido in archivos:
                self.validar_archivo(nombre, contenido, max_mb, permitidas)
        texto = dto.texto.strip() or (f"Adjuntó {len(archivos)} archivo{'s' if len(archivos) != 1 else ''}" if archivos else "")
        if not texto:
            raise ReglaNegocio("Escriba un comentario")
        if not dto.es_interno:
            exigir_sin_internos(self.session, texto)
        ahora = utcnow()
        c = self._agregar_comentario(t, u, texto, dto.es_interno, dto.tipo, dto.minutos_invertidos, ahora)
        for nombre, tipo_mime, contenido in archivos:
            a = self.guardar_adjunto(t, u, nombre, tipo_mime, contenido, ctx)
            a.comentario_id = c.id
        if archivos:
            self.session.flush()
        es_solicitante = t.solicitante_id == u.id and not self.es_gestor(u, t)
        visualizadores = VisualizadorService(self.session)
        if not dto.es_interno:
            visualizadores.avisar(t, u.id, "RESPUESTA", f"{t.numero}: {u.nombre} respondió", f"{u.nombre}: {texto[:200]}")
        if not es_solicitante and not self.es_gestor(u, t) and not dto.es_interno and visualizadores.es_visualizador(u, t):
            # Comentario de un visualizador: lo leen el responsable y el solicitante
            self.notif.notificar([t.responsable, t.solicitante], "COMENTARIO", f"{t.numero}: comentario de {u.nombre}",
                                 f"{u.nombre} (visualizador): {texto[:200]}", t)
            t.fecha_actualizacion = ahora
            return c
        if es_solicitante:
            # Respuesta del cliente: el SLA se reanuda automáticamente
            if t.estado == Estado.PENDIENTE_CLIENTE:
                self._aplicar_estado(t, Estado.PENDIENTE_CLIENTE, Estado.EN_PROCESO, None, ctx, ahora)
                self._hist(t, u, "REANUDACION", None, None, None, "El solicitante respondió; SLA reanudado", ahora)
            self.notif.notificar([t.responsable], "COMENTARIO", f"{t.numero}: nuevo comentario", f"{u.nombre}: {texto[:200]}", t)
        else:
            if t.responsable and t.responsable_id != u.id:
                # Comenta otra persona del equipo (supervisor, mesa, tarea): el responsable se entera, también de notas internas
                que = "nota interna" if dto.es_interno else "comentario"
                self.notif.notificar([t.responsable], "COMENTARIO", f"{t.numero}: {que} de {u.nombre}",
                                     f"{u.nombre}: {texto[:200]}", t)
            if not dto.es_interno:
                self.sla.registrar_primera_respuesta(t, ahora)
                self.notif.notificar([t.solicitante], "COMENTARIO", f"{t.numero}: respuesta del equipo", f"{u.nombre}: {texto[:200]}", t)
                # Sin lista explícita se usan las personas en copia del ticket; una lista vacía no copia a nadie
                copias = self.copias(t) if dto.copia_a is None else dto.copia_a
                c.copia_a = unir(self.responder_por_correo(t, u, texto, copias))
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

    def reglas_adjuntos(self) -> tuple[int, set[str]]:
        """Tamaño máximo (MB) y extensiones permitidas según la configuración vigente."""
        config = self.catalogo.configuracion()
        max_mb = int(config.get("adjuntos.max_mb", settings.ADJUNTOS_MAX_MB))
        permitidas = {e.strip().lower() for e in config.get("adjuntos.extensiones", settings.ADJUNTOS_EXTENSIONES).split(",") if e.strip()}
        return max_mb, permitidas

    @staticmethod
    def validar_archivo(nombre: str, contenido: bytes, max_mb: int, permitidas: set[str]) -> str:
        """Comprueba extensión, tamaño y firma del contenido. Devuelve la extensión o lanza ReglaNegocio."""
        extension = Path(nombre).suffix.lower().lstrip(".")
        if extension not in permitidas:
            raise ReglaNegocio(f"Tipo de archivo no permitido (.{extension}). Permitidos: {', '.join(sorted(permitidas))}")
        if len(contenido) == 0:
            raise ReglaNegocio(f"El archivo {Path(nombre).name[:80]} está vacío")
        if len(contenido) > max_mb * 1024 * 1024:
            raise ReglaNegocio(f"El archivo {Path(nombre).name[:80]} supera el máximo de {max_mb} MB")
        if not contenido_valido(extension, contenido):
            raise ReglaNegocio(f"El contenido de {Path(nombre).name[:80]} no corresponde a su extensión o no está permitido")
        return extension

    def guardar_adjunto(self, t: m.Ticket, u: m.Usuario, nombre: str, tipo_mime: str, contenido: bytes, ctx: Contexto) -> m.TicketAdjunto:
        """Valida (extensión, tamaño, contenido) y guarda el archivo. También lo usan el buzón de correo y el formulario público."""
        max_mb, permitidas = self.reglas_adjuntos()
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

    def ve_internos(self, u: m.Usuario, t: m.Ticket) -> bool:
        """Gestores y quienes fueron responsables ven notas internas (y sus archivos)."""
        return self.es_gestor(u, t) or u.tiene(Permiso.TICKET_VER_TODOS) or self.repo.participo(u.id, t.id)

    def adjunto(self, ticket_id: int, adjunto_id: int, ctx: Contexto, vista: bool = False) -> tuple[m.TicketAdjunto, Path]:
        t = self.obtener(ticket_id, ctx.usuario)
        a = self.session.get(m.TicketAdjunto, adjunto_id)
        if a is None or a.ticket_id != t.id or a.eliminado:
            raise NoEncontrado("Adjunto no encontrado")
        if a.comentario_id and not self.ve_internos(ctx.usuario, t):
            c = self.session.get(m.TicketComentario, a.comentario_id)
            if c is not None and c.es_interno:
                raise NoEncontrado("Adjunto no encontrado")
        if vista:
            # Vista previa de una captura dentro del comentario: no se registra como descarga
            return a, self.almacenamiento.ruta(a.ruta_almacenamiento)
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
        stmt = self.repo.consulta_visible(u, incluir_participados=f.participe or f.siguiendo)
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
        if f.vence:
            ahora = utcnow()
            activos = [Estado.NUEVO, Estado.ASIGNADO, Estado.EN_PROCESO, Estado.ESCALADO]
            if f.vence == "HOY":
                _, fin_hoy = limites_dia_utc(None, datetime.now(ZoneInfo(settings.ZONA_HORARIA)).date())
                stmt = stmt.where(T.estado.in_(activos), T.sla_pausa_desde.is_(None), T.sla_excluido == False, or_(
                    (T.sla_resolucion_vence >= ahora) & (T.sla_resolucion_vence < fin_hoy),
                    T.fecha_primera_respuesta.is_(None) & (T.sla_respuesta_vence >= ahora) & (T.sla_respuesta_vence < fin_hoy)))
            else:
                stmt = stmt.where(T.estado.in_(activos), T.sla_excluido == False,
                                  or_(T.sla_incumplido == True, (T.sla_pausa_desde.is_(None)) & (T.sla_resolucion_vence < ahora)))
        if f.solo_mios:
            stmt = stmt.where(or_(T.responsable_id == u.id, T.solicitante_id == u.id))
        if f.participe:
            stmt = stmt.where(or_(T.responsable_id == u.id, T.creado_por_id == u.id, T.id.in_(self.repo.ids_participados(u.id))))
        if f.siguiendo:
            stmt = stmt.where(T.id.in_(select(m.TicketVisualizador.ticket_id).where(m.TicketVisualizador.usuario_id == u.id)))
        orden = {
            "fecha_desc": (T.fecha_creacion.desc(), T.id.desc()),
            "fecha_asc": (T.fecha_creacion.asc(), T.id.asc()),
            "sla_desc": (T.sla_consumido_pct.desc(), T.id.desc()),
            "prioridad": (T.prioridad_id.asc(), T.fecha_creacion.asc()),
            "vence": (case((T.fecha_primera_respuesta.is_(None) & (T.sla_respuesta_vence < T.sla_resolucion_vence), T.sla_respuesta_vence),
                           else_=T.sla_resolucion_vence).asc(), T.id.asc()),
        }[f.orden]
        return stmt.order_by(*orden)

    def listar(self, u: m.Usuario, f: s.FiltroTickets, pagina: int, tamano: int):
        return self.repo.paginar(self.consulta(u, f), pagina, tamano)

    def calificar(self, ticket_id: int, calificacion: int, comentario: str | None, ctx: Contexto) -> m.TicketEncuesta:
        t = self.obtener(ticket_id, ctx.usuario)
        return EncuestaService(self.session).registrar(self, t, calificacion, comentario, ctx.usuario, "PORTAL", ctx)

    def alertas_sla(self, u: m.Usuario) -> list[dict]:
        """Tickets propios (como responsable) a los que les quedan menos de sla.aviso_previo_2_min laborables."""
        from app.domain.sla import avisos_configurados

        limite = avisos_configurados(self.catalogo.configuracion()).previo_2_min
        ahora = utcnow()
        T = m.Ticket
        tickets = self.session.scalars(
            select(T).where(T.responsable_id == u.id, T.eliminado == False, T.sla_pausa_desde.is_(None),
                            T.estado.in_([Estado.NUEVO, Estado.ASIGNADO, Estado.EN_PROCESO, Estado.ESCALADO]),
                            T.sla_resolucion_vence > ahora - timedelta(days=1))
        ).unique()
        alertas = []
        for t in tickets:
            v = self.sla.proximo_vencimiento(t, ahora)
            if v and 0 < v[2] <= limite:
                alertas.append({"id": t.id, "numero": t.numero, "asunto": t.asunto, "prioridad": t.prioridad.nombre,
                                "prioridad_codigo": t.prioridad.codigo, "vence_tipo": v[0], "vence": v[1], "vence_en_min": v[2]})
        return sorted(alertas, key=lambda a: a["vence_en_min"])


# ================================================================ mapeos
def a_listado(t: m.Ticket, sla: SlaService | None = None, ahora: datetime | None = None) -> dict:
    v = sla.proximo_vencimiento(t, ahora or utcnow()) if sla else None
    return {
        "vence_tipo": v[0] if v else None, "vence_en_min": v[2] if v else None, "clasificacion": t.clasificacion or "INTERNA",
        "id": t.id, "numero": t.numero, "asunto": t.asunto, "fecha_creacion": t.fecha_creacion,
        "solicitante_nombre": t.solicitante_nombre, "cliente": t.cliente.razon_social if t.cliente else None,
        "categoria": t.categoria.nombre, "subcategoria": t.subcategoria.nombre, "prioridad": t.prioridad.nombre,
        "prioridad_codigo": t.prioridad.codigo, "responsable": t.responsable.nombre if t.responsable else None,
        "estado": t.estado, "estado_nombre": t.estado_rel.nombre, "sla_consumido_pct": float(t.sla_consumido_pct or 0),
        "sla_resolucion_vence": t.sla_resolucion_vence, "sla_incumplido": t.sla_incumplido, "cumplimiento_sla": t.cumplimiento_sla,
    }


def a_detalle(svc: TicketService, t: m.Ticket, u: m.Usuario) -> dict:
    from app.application.services.conocimiento_service import ConocimientoService

    gestor = svc.es_gestor(u, t) or u.tiene(Permiso.TICKET_VER_TODOS)
    # Quien fue responsable antes conserva la lectura completa (historial, notas internas), pero no las acciones.
    participante = not gestor and svc.repo.participo(u.id, t.id)
    lectura = gestor or participante or svc._tiene_tarea(u, t)   # quien tiene una tarea del catálogo ve las notas internas
    resumen = lambda x: {"id": x.id, "nombre": x.nombre, "correo": x.correo, "cargo": x.cargo} if x else None  # noqa: E731
    comentarios = svc.repo.comentarios(t.id, incluir_internos=lectura)
    visibles = {c.id for c in comentarios}
    adjuntos = svc.repo.adjuntos(t.id)
    archivo = lambda a: {"id": a.id, "nombre_original": a.nombre_original, "tipo_mime": a.tipo_mime,  # noqa: E731
                         "tamano_bytes": a.tamano_bytes, "usuario": resumen(a.usuario), "fecha": a.fecha, "comentario_id": a.comentario_id}
    historial = svc.repo.historial(t.id) if lectura else [h for h in svc.repo.historial(t.id) if h.accion in (
        "CREACION", "CAMBIO_ESTADO", "CIERRE", "REAPERTURA", "VISUALIZADOR", "ESCALAMIENTO_PROVEEDOR")]
    vis = VisualizadorService(svc.session)
    gestiona_vis = VisualizadorService.puede_gestionar(svc, u, t)
    visualizadores = vis.salida(t, u, gestiona_vis)
    ids_vis = {v["usuario_id"] for v in visualizadores} - {t.solicitante_id, t.responsable_id}
    prov = ProveedorService(svc.session)
    casos = prov._casos(ticket_id=t.id)
    caso = next((c for c in casos if c.estado == "ABIERTO"), None)
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
             "de_visualizador": c.usuario_id in ids_vis,
             "minutos_invertidos": c.minutos_invertidos, "fecha": c.fecha, "copia_a": separar(c.copia_a) if lectura else [],
             "adjuntos": [archivo(a) for a in adjuntos if a.comentario_id == c.id]}
            for c in comentarios
        ],
        "adjuntos": [archivo(a) for a in adjuntos if not a.comentario_id or a.comentario_id in visibles],
        "historial": [
            {"id": h.id, "accion": h.accion, "campo": h.campo, "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo,
             "detalle": h.detalle, "usuario": resumen(h.usuario), "fecha": h.fecha} for h in historial
        ],
        "escalamientos": [
            {"id": e.id, "nivel": e.nivel, "tipo": e.tipo, "motivo": e.motivo,
             "sla_consumido_pct": float(e.sla_consumido_pct) if e.sla_consumido_pct is not None else None, "fecha": e.fecha}
            for e in (svc.repo.escalamientos(t.id) if lectura else [])
        ],
        "copias": [{"correo": c.correo, "origen": c.origen} for c in svc.repo.copias(t.id)] if lectura else [],
        "acciones": svc.acciones(u, t),
        "solo_lectura_participante": participante,
        "encuesta": encuesta_salida(EncuestaService(svc.session).de_ticket(t.id)),
        "creado_por": resumen(t.creado_por),
        "en_nombre_motivo": t.en_nombre_motivo,
        "solo_lectura_creador": bool(t.creado_por_id == u.id and not gestor and t.solicitante_id != u.id),
        "equipo": InventarioService(svc.session).para_ticket(t),
        "recurrente_id": t.recurrente_id,
        "kb_vistos": ConocimientoService(svc.session).vistos(t.id) if lectura else [],
        "visualizadores": visualizadores,
        "es_visualizador": u.id in {v["usuario_id"] for v in visualizadores},
        "proveedor_caso": prov.caso_salida(caso) if caso else None,
        "proveedor_casos": [prov.caso_salida(c) for c in casos] if lectura else [],
        "facturable": bool(t.facturable),
        "clasificacion": t.clasificacion or "INTERNA",
        "retencion_legal": bool(t.retencion_legal),
        "fecha_depuracion": t.fecha_depuracion,
        **_extras_tercera_ronda(svc, t, u, lectura),
    }


def _extras_tercera_ronda(svc: TicketService, t: m.Ticket, u: m.Usuario, lectura: bool) -> dict:
    """Aprobaciones (21), tickets vinculados (22), avisos generales (24) y enlace de seguimiento (20)."""
    from app.application.services.aviso_service import AvisoService
    from app.application.services.seguimiento_service import SeguimientoService
    from app.application.services.catalogo_servicio_service import CatalogoServicioService
    from app.application.services.vinculo_service import VinculoService

    aprob = AprobacionService(svc.session)
    filas = aprob.de_ticket(t.id)
    propio = t.solicitante_id == u.id or t.creado_por_id == u.id
    pendiente = next((f for f in filas if f.estado == "PENDIENTE" and f.aprobador_id == u.id), None)
    vinculos = VinculoService(svc.session)
    return {
        "aprobaciones": [{k: v for k, v in aprob.salida(f).items() if k != "ticket"} for f in filas] if (lectura or propio or pendiente) else [],
        "aprobacion_pendiente_id": pendiente.id if pendiente else None,
        "vinculos": vinculos.de_ticket(t, u) if lectura else [],
        "duplicado_de": vinculos.duplicado_de(t),
        "avisos": AvisoService(svc.session).de_ticket(t.id),
        "seguimiento_url": SeguimientoService(svc.session).url(t) if lectura else None,
        "servicio": CatalogoServicioService(svc.session).de_ticket(t, u, svc.es_gestor(u, t)),
    }


def responsables_disponibles(session: Session) -> list[m.Usuario]:
    return list(
        session.scalars(
            select(m.Usuario).join(m.Rol).where(m.Rol.codigo.in_([Rol.ANALISTA, Rol.SUPERVISOR]), m.Usuario.activo == True,
                                                 m.Usuario.eliminado == False).order_by(m.Usuario.nombre)
        ).unique()
    )
