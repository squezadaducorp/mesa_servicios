"""Aprobaciones del jefe (mejora 21).

- Reglas por categoría (y opcionalmente subcategoría): quién aprueba en el nivel 1 y, si se quiere, en el nivel 2.
- Al crear un ticket que cae en una regla, queda «Por aprobar» con el SLA en pausa y el aprobador recibe aviso y correo.
- Aprobar pasa al siguiente nivel o libera el ticket (Nuevo + asignación automática). Rechazar lo cancela con el comentario.
- El worker manda un recordatorio y, si la regla lo indica, pasa la aprobación a otra persona cuando no hay respuesta.
- Si el aprobador está en modo ausente, la aprobación va a su reemplazo.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService, cuentas_sistema, fecha_local
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Estado
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import coordinadores, reemplazo_vigente

TIPOS = {"JEFE_DIRECTO": "Jefe directo del solicitante", "SUPERVISOR_CATEGORIA": "Supervisor de la categoría", "PERSONA": "Persona fija"}


class AprobacionService:
    def __init__(self, session: Session):
        self.session = session
        self.notif = NotificacionService(session)
        self.auditoria = AuditoriaService(session)

    # ============================================================= reglas
    def reglas(self) -> list[m.ReglaAprobacion]:
        R = m.ReglaAprobacion
        return list(self.session.scalars(select(R).order_by(R.activo.desc(), R.categoria_id, R.subcategoria_id)).unique())

    def regla_para(self, categoria_id: int, subcategoria_id: int | None) -> m.ReglaAprobacion | None:
        """Regla activa más específica: la de la subcategoría gana sobre la de toda la categoría."""
        R = m.ReglaAprobacion
        candidatas = list(self.session.scalars(select(R).where(R.activo == True, R.categoria_id == categoria_id,
                                                               or_(R.subcategoria_id.is_(None), R.subcategoria_id == subcategoria_id))).unique())
        return sorted(candidatas, key=lambda r: r.subcategoria_id is None)[0] if candidatas else None

    def guardar(self, dto, ctx: Contexto, regla_id: int | None = None) -> m.ReglaAprobacion:
        cat = self.session.get(m.Categoria, dto.categoria_id)
        if cat is None or cat.eliminado:
            raise ReglaNegocio("Categoría no válida")
        if dto.subcategoria_id:
            sub = self.session.get(m.Subcategoria, dto.subcategoria_id)
            if sub is None or sub.categoria_id != cat.id:
                raise ReglaNegocio("La subcategoría no pertenece a la categoría")
        for tipo, uid, nombre in ((dto.nivel1_tipo, dto.nivel1_usuario_id, "nivel 1"), (dto.nivel2_tipo, dto.nivel2_usuario_id, "nivel 2")):
            if tipo == "PERSONA":
                u = self.session.get(m.Usuario, uid) if uid else None
                if u is None or not u.activo or u.eliminado:
                    raise ReglaNegocio(f"Elija la persona que aprueba en el {nombre}")
        if dto.escalar_horas and not dto.escalar_a_id:
            raise ReglaNegocio("Indique a quién pasa la aprobación si no hay respuesta")
        R = m.ReglaAprobacion
        repetida = self.session.scalar(select(R.id).where(R.activo == True, R.categoria_id == dto.categoria_id,
                                                           R.subcategoria_id.is_(None) if not dto.subcategoria_id else R.subcategoria_id == dto.subcategoria_id,
                                                           R.id != (regla_id or 0)))
        if repetida and dto.activo:
            raise ReglaNegocio("Ya existe una regla activa para esa categoría y subcategoría")
        r = self.session.get(R, regla_id) if regla_id else R(creado_por=ctx.usuario.id)
        if r is None:
            raise NoEncontrado("Regla no encontrada")
        datos = dto.model_dump()
        if datos["nivel1_tipo"] != "PERSONA":
            datos["nivel1_usuario_id"] = None
        if datos["nivel2_tipo"] != "PERSONA":
            datos["nivel2_usuario_id"] = None
        if not datos["escalar_horas"]:
            datos["escalar_horas"], datos["escalar_a_id"] = None, None
        for k, v in datos.items():
            setattr(r, k, v)
        r.fecha_actualizacion = utcnow()
        if regla_id is None:
            self.session.add(r)
        self.session.flush()
        self.session.refresh(r)
        self.auditoria.registrar(ctx, AccionAuditoria.REGLA_APROBACION_MODIFICADA, "aprobacion_regla", r.id,
                                 {"categoria": r.categoria.nombre, "subcategoria": r.subcategoria.nombre if r.subcategoria else None,
                                  "activo": r.activo})
        return r

    def desactivar(self, regla_id: int, ctx: Contexto) -> None:
        r = self.session.get(m.ReglaAprobacion, regla_id)
        if r is None:
            raise NoEncontrado("Regla no encontrada")
        r.activo, r.fecha_actualizacion = False, utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.REGLA_APROBACION_MODIFICADA, "aprobacion_regla", r.id, {"activo": False})

    def jefes_directos(self) -> dict:
        """Cuántas personas tienen «Jefe directo» (lo usan las reglas JEFE_DIRECTO) y quiénes faltan."""
        U = m.Usuario
        usuarios = [u for u in self.session.scalars(select(U).where(U.activo == True, U.eliminado == False).order_by(U.nombre)).unique()
                    if u.correo.lower() not in cuentas_sistema()]
        faltan = [u for u in usuarios if not u.supervisor_id]
        return {"total": len(usuarios), "completos": len(usuarios) - len(faltan),
                "faltan": [{"id": u.id, "nombre": u.nombre, "area": u.area.nombre if u.area else None} for u in faltan]}

    # ================================================== resolver aprobador
    def _resolver(self, tipo: str | None, usuario_id: int | None, t: m.Ticket) -> m.Usuario | None:
        if tipo == "JEFE_DIRECTO":
            u = self.session.get(m.Usuario, t.solicitante.supervisor_id) if t.solicitante.supervisor_id else None
        elif tipo == "SUPERVISOR_CATEGORIA":
            u = t.categoria.supervisor
        elif tipo == "PERSONA":
            u = self.session.get(m.Usuario, usuario_id) if usuario_id else None
        else:
            return None
        return u if u and u.activo and not u.eliminado else None

    def _con_reemplazo(self, regla: m.ReglaAprobacion | None, u: m.Usuario) -> tuple[m.Usuario, m.Usuario | None]:
        if regla is None or regla.usar_reemplazo:
            r = reemplazo_vigente(self.session, u.id)
            if r is not None and r.id != u.id:
                return r, u
        return u, None

    # ============================================================ al crear
    def iniciar(self, svc, t: m.Ticket, ctx: Contexto, ahora: datetime, forzada: tuple[str, int | None] | None = None) -> bool:
        """Aplica la regla al ticket recién creado. Devuelve True si quedó «Por aprobar» (no se asigna todavía).

        ``forzada`` = (tipo, usuario_id): aprobación que pide un servicio del catálogo aunque la categoría no tenga regla
        (p. ej. el jefe directo de quien ingresa, elegido en el formulario). Una regla de la categoría siempre gana.
        """
        regla = self.regla_para(t.categoria_id, t.subcategoria_id)
        if regla is None and forzada:
            # Regla en memoria (no se guarda): un solo nivel, respeta el modo ausente y la auto-aprobación
            regla = m.ReglaAprobacion(nivel1_tipo=forzada[0], nivel1_usuario_id=forzada[1], usar_reemplazo=True, auto_si_aprobador=True,
                                      recordar_horas=4)
        if regla is None:
            return False
        return self._siguiente_nivel(svc, t, regla, 1, ctx, ahora)

    def _siguiente_nivel(self, svc, t: m.Ticket, regla: m.ReglaAprobacion, nivel: int, ctx: Contexto, ahora: datetime) -> bool:
        """Pide la aprobación del nivel indicado (o la da por aprobada si no aplica). True = el ticket espera una respuesta."""
        while nivel <= 2:
            tipo, uid = (regla.nivel1_tipo, regla.nivel1_usuario_id) if nivel == 1 else (regla.nivel2_tipo, regla.nivel2_usuario_id)
            if not tipo:
                return False
            aprobador = self._resolver(tipo, uid, t)
            if aprobador is None:
                svc._hist(t, None, "APROBACION", "aprobacion", None, "SIN_APROBADOR",
                          f"Nivel {nivel}: no hay {TIPOS.get(tipo, tipo).lower()} registrado; el ticket sigue sin esa aprobación", ahora)
                nivel += 1
                continue
            if regla.auto_si_aprobador and aprobador.id in {t.solicitante_id, t.creado_por_id}:
                self.session.add(m.TicketAprobacion(ticket_id=t.id, regla_id=regla.id, nivel=nivel, aprobador_id=aprobador.id, estado="APROBADO",
                                                    comentario="Aprobado automáticamente: quien pide es el aprobador",
                                                    fecha_solicitud=ahora, fecha_respuesta=ahora))
                svc._hist(t, aprobador, "APROBACION", "aprobacion", None, "APROBADO", f"Nivel {nivel}: aprobado automáticamente", ahora)
                nivel += 1
                continue
            destino, original = self._con_reemplazo(regla, aprobador)
            fila = m.TicketAprobacion(ticket_id=t.id, regla_id=regla.id, nivel=nivel, aprobador_id=destino.id,
                                      en_lugar_de_id=original.id if original else None, fecha_solicitud=ahora)
            self.session.add(fila)
            if t.estado != Estado.POR_APROBAR:
                actual = t.estado
                svc.sla.pausar(t, Estado.POR_APROBAR, None, ahora)
                t.estado = Estado.POR_APROBAR
                svc._hist(t, None, "CAMBIO_ESTADO", "estado", actual, Estado.POR_APROBAR, ahora=ahora)
            svc._hist(t, None, "APROBACION", "aprobacion", None, "PENDIENTE",
                      f"Nivel {nivel}: espera la aprobación de {destino.nombre}" + (f" (reemplazo de {original.nombre})" if original else ""), ahora)
            self.session.flush()
            self._avisar_aprobador(t, fila, destino)
            self.auditoria.registrar(ctx, AccionAuditoria.APROBACION_SOLICITADA, "ticket", t.id,
                                     {"numero": t.numero, "nivel": nivel, "aprobador": destino.nombre})
            return True
        return False

    def _urls(self, fila: m.TicketAprobacion) -> dict[str, str]:
        base = f"{settings.APP_URL.rstrip('/')}/aprobaciones?id={fila.id}"
        return {"url_aprobar": f"{base}&accion=aprobar", "url_rechazar": f"{base}&accion=rechazar"}

    def _avisar_aprobador(self, t: m.Ticket, fila: m.TicketAprobacion, aprobador: m.Usuario, recordatorio: bool = False) -> None:
        pedido = t.creado_por.nombre + f" (para {t.solicitante_nombre})" if t.creado_por else t.solicitante_nombre
        if recordatorio:
            self.notif.notificar([aprobador], "APROBACION_RECORDATORIO", f"{t.numero} sigue esperando su aprobación", f"«{t.asunto}»", t, "AVISO")
            self.notif.correo("APROBACION_RECORDATORIO", [aprobador], t, desde=fecha_local(fila.fecha_solicitud), **self._urls(fila))
            return
        self.notif.notificar([aprobador], "APROBACION_SOLICITADA", f"{t.numero} necesita su aprobación", f"{pedido}: «{t.asunto}»", t, "AVISO")
        detalle = (t.en_nombre_motivo or t.descripcion or "")[:600]
        self.notif.correo("APROBACION_SOLICITADA", [aprobador], t, pedido_por=pedido, detalle=detalle, **self._urls(fila))

    # ============================================================ responder
    def pendiente_de(self, aprobacion_id: int, u: m.Usuario) -> m.TicketAprobacion:
        fila = self.session.get(m.TicketAprobacion, aprobacion_id)
        if fila is None or fila.ticket.eliminado:
            raise NoEncontrado("Aprobación no encontrada")
        if fila.aprobador_id != u.id:
            raise Prohibido("Esta aprobación le corresponde a otra persona")
        return fila

    def responder(self, aprobacion_id: int, aprobar: bool, comentario: str | None, ctx: Contexto) -> m.TicketAprobacion:
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        fila = self.pendiente_de(aprobacion_id, u)
        if fila.estado != "PENDIENTE":
            raise ReglaNegocio("Esta solicitud ya fue respondida")
        comentario = (comentario or "").strip() or None
        if not aprobar and not comentario:
            raise ReglaNegocio("Indique el motivo del rechazo: se le enviará al solicitante")
        svc = TicketService(self.session)
        t, ahora = fila.ticket, utcnow()
        fila.estado, fila.comentario, fila.fecha_respuesta = ("APROBADO" if aprobar else "RECHAZADO"), comentario, ahora
        svc._hist(t, u, "APROBACION", "aprobacion", "PENDIENTE", fila.estado,
                  f"Nivel {fila.nivel}: {'aprobado' if aprobar else 'rechazado'} por {u.nombre}" + (f". {comentario}" if comentario else ""), ahora)
        self.auditoria.registrar(ctx, AccionAuditoria.APROBACION_RESPONDIDA, "ticket", t.id,
                                 {"numero": t.numero, "nivel": fila.nivel, "resultado": fila.estado, "comentario": comentario})
        if not aprobar:
            svc._aplicar_estado(t, Estado.POR_APROBAR, Estado.CANCELADO, u, ctx, ahora)
            svc._agregar_comentario(t, u, f"Solicitud rechazada por {u.nombre}: {comentario}", False, "COMENTARIO", None, ahora)
            self._resultado(svc, t, u, "rechazada", comentario)
            return fila
        regla = self.session.get(m.ReglaAprobacion, fila.regla_id) if fila.regla_id else None
        if regla and fila.nivel < 2 and self._siguiente_nivel(svc, t, regla, fila.nivel + 1, ctx, ahora):
            return fila
        self._liberar(svc, t, u, ctx, ahora)
        self._resultado(svc, t, u, "aprobada", comentario)
        return fila

    def _liberar(self, svc, t: m.Ticket, u: m.Usuario | None, ctx: Contexto, ahora: datetime) -> None:
        """Aprobado en todos los niveles: pasa a Nuevo (el SLA se reanuda) y se asigna como cualquier ticket."""
        from app.application.services.catalogo_servicio_service import CatalogoServicioService

        svc._aplicar_estado(t, Estado.POR_APROBAR, Estado.NUEVO, u, ctx, ahora)
        responsable = t.responsable or svc.ia.sugerir_responsable(t.categoria)
        if responsable:
            svc._asignar(t, responsable, None, "AUTOMATICA", "Asignación automática tras la aprobación", ctx, ahora)
        else:
            svc.notif.notificar([svc._supervisor(t), *coordinadores(self.session)], "TICKET_SIN_ASIGNAR", f"{t.numero} pendiente de asignación",
                                f"«{t.asunto}» fue aprobado y no tiene responsable.", t, "AVISO")
        CatalogoServicioService(self.session).avisar_tareas(t)   # solicitudes del catálogo: cada responsable recibe su tarea

    def _resultado(self, svc, t: m.Ticket, aprobador: m.Usuario, resultado: str, comentario: str | None) -> None:
        personas = [t.solicitante, t.creado_por]
        self.notif.notificar(personas, "APROBACION_RESULTADO", f"{t.numero}: solicitud {resultado}",
                             f"{aprobador.nombre} {'aprobó' if resultado == 'aprobada' else 'rechazó'} «{t.asunto}»." + (f" {comentario}" if comentario else ""), t,
                             "INFO" if resultado == "aprobada" else "AVISO")
        self.notif.correo("APROBACION_RESULTADO", personas, t, resultado=resultado, aprobador=aprobador.nombre, comentario=comentario or "")

    def anular(self, t: m.Ticket, motivo: str) -> None:
        """El ticket se canceló por otra vía: las aprobaciones pendientes dejan de pedirse."""
        for f in self.session.scalars(select(m.TicketAprobacion).where(m.TicketAprobacion.ticket_id == t.id,
                                                                       m.TicketAprobacion.estado == "PENDIENTE")):
            f.estado, f.comentario, f.fecha_respuesta = "ANULADO", motivo[:1000], utcnow()

    def reasignar_pendientes(self, de: m.Usuario, a: m.Usuario, motivo: str, ahora: datetime | None = None) -> int:
        """Pasa las aprobaciones pendientes de una persona a otra (traspaso de cartera o escalamiento)."""
        ahora = ahora or utcnow()
        filas = list(self.session.scalars(select(m.TicketAprobacion).where(m.TicketAprobacion.aprobador_id == de.id,
                                                                           m.TicketAprobacion.estado == "PENDIENTE")))
        for f in filas:
            self._pasar(f, a, motivo, ahora)
        return len(filas)

    def _pasar(self, f: m.TicketAprobacion, a: m.Usuario, motivo: str, ahora: datetime) -> m.TicketAprobacion:
        f.estado, f.comentario, f.fecha_respuesta = "REASIGNADO", motivo[:1000], ahora
        nueva = m.TicketAprobacion(ticket_id=f.ticket_id, regla_id=f.regla_id, nivel=f.nivel, aprobador_id=a.id,
                                   en_lugar_de_id=f.aprobador_id, fecha_solicitud=ahora)
        self.session.add(nueva)
        self.session.flush()
        self.session.add(m.TicketHistorial(ticket_id=f.ticket_id, accion="APROBACION", campo="aprobacion", valor_anterior=f.aprobador.nombre,
                                           valor_nuevo=a.nombre, detalle=f"Nivel {f.nivel}: pasa a {a.nombre}. {motivo}"[:500], fecha=ahora))
        self._avisar_aprobador(f.ticket, nueva, a)
        return nueva

    # ============================================================ consultas
    def bandeja(self, u: m.Usuario) -> dict:
        A = m.TicketAprobacion
        pendientes = list(self.session.scalars(select(A).where(A.aprobador_id == u.id, A.estado == "PENDIENTE")
                                               .order_by(A.fecha_solicitud)).unique())
        desde = utcnow() - timedelta(days=30)
        resp = list(self.session.scalars(select(A).where(A.aprobador_id == u.id, A.estado.in_(["APROBADO", "RECHAZADO"]),
                                                         A.fecha_respuesta >= desde)).unique())
        minutos = [int((f.fecha_respuesta - f.fecha_solicitud).total_seconds() // 60) for f in resp if f.fecha_respuesta]
        return {
            "pendientes": [self.salida(f) for f in pendientes],
            "aprobadas_30d": sum(f.estado == "APROBADO" for f in resp),
            "rechazadas_30d": sum(f.estado == "RECHAZADO" for f in resp),
            "minutos_respuesta_promedio": round(sum(minutos) / len(minutos)) if minutos else None,
            "recientes": [self.salida(f) for f in sorted(resp, key=lambda x: x.fecha_respuesta, reverse=True)[:10]],
        }

    def contar_pendientes(self, u: m.Usuario) -> int:
        A = m.TicketAprobacion
        return self.session.scalar(select(func.count()).select_from(A).where(A.aprobador_id == u.id, A.estado == "PENDIENTE")) or 0

    def de_ticket(self, ticket_id: int) -> list[m.TicketAprobacion]:
        A = m.TicketAprobacion
        return list(self.session.scalars(select(A).where(A.ticket_id == ticket_id).order_by(A.nivel, A.id)).unique())

    def salida(self, f: m.TicketAprobacion) -> dict:
        t = f.ticket
        return {
            "id": f.id, "nivel": f.nivel, "estado": f.estado, "comentario": f.comentario, "fecha_solicitud": f.fecha_solicitud,
            "fecha_respuesta": f.fecha_respuesta, "aprobador": f.aprobador.nombre, "aprobador_id": f.aprobador_id,
            "en_lugar_de": f.en_lugar_de.nombre if f.en_lugar_de else None,
            "regla": self._texto_regla(f.regla_id),
            "ticket": {"id": t.id, "numero": t.numero, "asunto": t.asunto, "descripcion": t.descripcion[:2000],
                       "categoria": t.categoria.nombre, "subcategoria": t.subcategoria.nombre, "estado": t.estado,
                       "solicitante": t.solicitante_nombre, "area": t.area.nombre if t.area else None,
                       "creado_por": t.creado_por.nombre if t.creado_por else None, "motivo": t.en_nombre_motivo,
                       "fecha_creacion": t.fecha_creacion},
        }

    def _texto_regla(self, regla_id: int | None) -> str | None:
        r = self.session.get(m.ReglaAprobacion, regla_id) if regla_id else None
        if r is None:
            return None
        donde = r.categoria.nombre + (f" › {r.subcategoria.nombre}" if r.subcategoria else "")
        return f"{donde} → {TIPOS.get(r.nivel1_tipo, r.nivel1_tipo).lower()}"

    def regla_salida(self, r: m.ReglaAprobacion) -> dict:
        nombre = lambda tipo, u: (u.nombre if tipo == "PERSONA" and u else TIPOS.get(tipo or "", None))  # noqa: E731
        return {
            "id": r.id, "categoria_id": r.categoria_id, "categoria": r.categoria.nombre, "subcategoria_id": r.subcategoria_id,
            "subcategoria": r.subcategoria.nombre if r.subcategoria else None, "nivel1_tipo": r.nivel1_tipo,
            "nivel1_usuario_id": r.nivel1_usuario_id, "nivel1": nombre(r.nivel1_tipo, r.nivel1_usuario), "nivel2_tipo": r.nivel2_tipo,
            "nivel2_usuario_id": r.nivel2_usuario_id, "nivel2": nombre(r.nivel2_tipo, r.nivel2_usuario), "recordar_horas": r.recordar_horas,
            "escalar_horas": r.escalar_horas, "escalar_a_id": r.escalar_a_id, "escalar_a": r.escalar_a.nombre if r.escalar_a else None,
            "usar_reemplazo": r.usar_reemplazo, "auto_si_aprobador": r.auto_si_aprobador, "activo": r.activo,
            "restringida_en_nombre": r.categoria.restringida_en_nombre,
        }

    # ============================================================== worker
    def procesar(self, ahora: datetime | None = None) -> dict:
        """Recordatorio a las `recordar_horas` hábiles y paso a `escalar_a` a las `escalar_horas` hábiles sin respuesta."""
        from app.application.services.sla_service import SlaService

        ahora = ahora or utcnow()
        cal = SlaService(self.session).cal
        A = m.TicketAprobacion
        recordados = escalados = 0
        for f in list(self.session.scalars(select(A).where(A.estado == "PENDIENTE")).unique()):
            regla = self.session.get(m.ReglaAprobacion, f.regla_id) if f.regla_id else None
            if regla is None or f.ticket.estado != Estado.POR_APROBAR:
                continue
            horas = cal.minutos_laborables(f.fecha_solicitud, ahora) / 60
            if regla.escalar_horas and regla.escalar_a and horas >= regla.escalar_horas and regla.escalar_a_id != f.aprobador_id:
                self._pasar(f, regla.escalar_a, f"Sin respuesta en {regla.escalar_horas} horas hábiles", ahora)
                escalados += 1
            elif not f.recordado and regla.recordar_horas and horas >= regla.recordar_horas:
                f.recordado = True
                self._avisar_aprobador(f.ticket, f, f.aprobador, recordatorio=True)
                recordados += 1
        return {"recordados": recordados, "escalados": escalados}
