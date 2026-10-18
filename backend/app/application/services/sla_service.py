"""Aplicación del motor de SLA a los tickets: pausas, hitos, recálculo y escalamiento automático."""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.domain.enums import Estado
from app.domain.sla import CalendarioLaboral, DatosSla, calcular_sla, nuevos_umbrales, umbrales_configurados
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, TicketRepository, UsuarioRepository, coordinadores

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, CalendarioLaboral]] = {}
_TTL_SEG = 60


def invalidar_calendario() -> None:
    _CACHE.clear()


def cargar_calendario(session: Session) -> CalendarioLaboral:
    clave = str(session.bind.url)
    hit = _CACHE.get(clave)
    if hit and _time.monotonic() - hit[0] < _TTL_SEG:
        return hit[1]
    repo = CatalogoRepository(session)
    horario = repo.horario_predeterminado()
    if horario is None or not horario.tramos:
        cal = CalendarioLaboral.por_defecto()
    else:
        cal = CalendarioLaboral(zona_horaria=horario.zona_horaria)
        for tr in horario.tramos:
            cal.tramos_semana.setdefault(tr.dia_semana - 1, []).append((tr.hora_inicio, tr.hora_fin))
    for exc in repo.excepciones_calendario():
        if horario and exc.horario_id not in (None, horario.id):
            continue
        if exc.tipo == "FERIADO":
            cal.feriados.add(exc.fecha)
        elif exc.hora_inicio and exc.hora_fin:
            cal.horarios_especiales.setdefault(exc.fecha, []).append((exc.hora_inicio, exc.hora_fin))
    _CACHE[clave] = (_time.monotonic(), cal)
    return cal


class SlaService:
    def __init__(self, session: Session):
        self.session = session
        self.cal = cargar_calendario(session)
        self.tickets = TicketRepository(session)

    # -------------------------------------------------------------- políticas
    def minutos_sla(self, categoria_id: int, prioridad: m.Prioridad) -> tuple[int, int]:
        pol = CatalogoRepository(self.session).politica(categoria_id, prioridad.id)
        if pol:
            return pol.sla_respuesta_min, pol.sla_resolucion_min
        return prioridad.sla_respuesta_min, prioridad.sla_resolucion_min

    @staticmethod
    def _datos(t: m.Ticket) -> DatosSla:
        return DatosSla(
            fecha_creacion=t.fecha_creacion,
            sla_respuesta_min=t.sla_respuesta_min,
            sla_resolucion_min=t.sla_resolucion_min,
            sla_minutos_pausa=t.sla_minutos_pausa or 0,
            sla_minutos_extension=t.sla_minutos_extension or 0,
            sla_pausa_desde=t.sla_pausa_desde,
            fecha_primera_respuesta=t.fecha_primera_respuesta,
            fecha_resolucion=t.fecha_resolucion,
        )

    def recalcular(self, t: m.Ticket, ahora: datetime | None = None) -> None:
        """Actualiza consumo, porcentaje y vencimientos del ticket."""
        ahora = ahora or utcnow()
        r = calcular_sla(self._datos(t), ahora, self.cal)
        t.sla_minutos_consumidos = r.minutos_consumidos
        t.sla_consumido_pct = Decimal(str(min(r.porcentaje, 99999)))
        t.sla_resolucion_vence = r.resolucion_vence
        if t.fecha_primera_respuesta is None:   # una vez respondido, el vencimiento de respuesta queda fijo
            t.sla_respuesta_vence = r.respuesta_vence

    def inicializar(self, t: m.Ticket) -> None:
        t.sla_respuesta_vence = self.cal.sumar_minutos(t.fecha_creacion, t.sla_respuesta_min)
        t.sla_resolucion_vence = self.cal.sumar_minutos(t.fecha_creacion, t.sla_resolucion_min)
        self.recalcular(t, t.fecha_creacion)

    # ------------------------------------------------------------------ pausa
    def pausar(self, t: m.Ticket, estado: str, usuario_id: int | None, ahora: datetime) -> None:
        if t.sla_pausa_desde is not None:
            pausa = self.tickets.pausa_abierta(t.id)
            if pausa:
                pausa.estado = estado
            return
        self.recalcular(t, ahora)
        t.sla_pausa_desde = ahora
        self.session.add(m.SlaPausa(ticket_id=t.id, estado=estado, inicio=ahora, usuario_id=usuario_id))

    def reanudar(self, t: m.Ticket, ahora: datetime) -> None:
        if t.sla_pausa_desde is None:
            return
        minutos = self.cal.minutos_laborables(t.sla_pausa_desde, ahora)
        t.sla_minutos_pausa = (t.sla_minutos_pausa or 0) + minutos
        pausa = self.tickets.pausa_abierta(t.id)
        if pausa:
            pausa.fin, pausa.minutos_laborables = ahora, minutos
        t.sla_pausa_desde = None
        self.recalcular(t, ahora)

    # ------------------------------------------------------------------ hitos
    def registrar_primera_respuesta(self, t: m.Ticket, ahora: datetime) -> None:
        if t.fecha_primera_respuesta is not None:
            return
        self.recalcular(t, ahora)
        t.fecha_primera_respuesta = ahora
        pausa_previa = t.sla_minutos_pausa or 0
        t.minutos_respuesta = max(self.cal.minutos_laborables(t.fecha_creacion, ahora) - pausa_previa, 0)
        t.sla_respuesta_cumplido = ahora <= t.sla_respuesta_vence
        if not t.sla_respuesta_cumplido and not self.tickets.existe_incumplimiento(t.id, "RESPUESTA"):
            self._registrar_incumplimiento(t, "RESPUESTA", t.sla_respuesta_vence, ahora)

    def registrar_resolucion(self, t: m.Ticket, ahora: datetime) -> None:
        self.recalcular(t, ahora)
        t.fecha_resolucion = ahora
        t.minutos_resolucion = t.sla_minutos_consumidos
        limite = t.sla_resolucion_min + (t.sla_minutos_extension or 0)
        t.sla_resolucion_cumplido = (not t.sla_incumplido) and t.sla_minutos_consumidos <= limite

    def reabrir(self, t: m.Ticket, ahora: datetime) -> None:
        """El tiempo en Resuelto/Cerrado no cuenta; el reloj continúa desde el consumo previo."""
        self.reanudar(t, ahora)
        t.fecha_resolucion = None
        t.fecha_cierre = None
        t.sla_resolucion_cumplido = None
        t.minutos_resolucion = None
        self.recalcular(t, ahora)

    def _registrar_incumplimiento(self, t: m.Ticket, tipo: str, vencimiento: datetime, ahora: datetime) -> None:
        self.session.add(
            m.SlaIncumplimiento(ticket_id=t.id, tipo=tipo, responsable_id=t.responsable_id, categoria_id=t.categoria_id,
                                prioridad_id=t.prioridad_id, fecha_vencimiento=vencimiento, fecha_registro=ahora)
        )

    # ------------------------------------------------------- motor periódico
    def evaluar_tickets_abiertos(self, ahora: datetime | None = None) -> dict[str, int]:
        """Recalcula el SLA de los tickets abiertos y dispara los escalamientos (75/90/100 % por defecto). Lo invoca el worker."""
        from app.application.services.notificacion_service import NotificacionService

        ahora = ahora or utcnow()
        notif = NotificacionService(self.session)
        usuarios = UsuarioRepository(self.session)
        coord = coordinadores(self.session)
        umbrales = umbrales_configurados(CatalogoRepository(self.session).configuracion())
        stats = {"evaluados": 0, "aviso_75": 0, "aviso_90": 0, "vencidos": 0, "respuesta_vencida": 0}

        for t in self.tickets.abiertos_para_sla():
            stats["evaluados"] += 1
            self.recalcular(t, ahora)

            # Incumplimiento de primera respuesta (se registra una vez)
            if (t.fecha_primera_respuesta is None and t.sla_pausa_desde is None and ahora > t.sla_respuesta_vence
                    and t.sla_respuesta_cumplido is None):
                t.sla_respuesta_cumplido = False
                if not self.tickets.existe_incumplimiento(t.id, "RESPUESTA"):
                    self._registrar_incumplimiento(t, "RESPUESTA", t.sla_respuesta_vence, ahora)
                stats["respuesta_vencida"] += 1

            if t.sla_pausa_desde is not None:
                continue
            supervisor = t.categoria.supervisor or (usuarios.get(t.responsable.supervisor_id) if t.responsable and t.responsable.supervisor_id else None)
            for umbral in nuevos_umbrales(float(t.sla_consumido_pct), t.sla_nivel_alerta or 0, umbrales):
                t.sla_nivel_alerta = umbral
                pct = float(t.sla_consumido_pct)
                if umbral == umbrales[0]:
                    stats["aviso_75"] += 1
                    destino = t.responsable or supervisor
                    notif.notificar([destino], "SLA_75", f"{t.numero}: SLA al {umbral} %",
                                    f"«{t.asunto}» consumió el {pct:.0f} % de su SLA.", t, "AVISO")
                    notif.correo("SLA_75", [destino], t)
                    escalado_a = destino
                elif umbral == umbrales[1]:
                    stats["aviso_90"] += 1
                    notif.notificar([supervisor, *coord], "SLA_90", f"{t.numero}: SLA al {umbral} %",
                                    f"«{t.asunto}» ({t.responsable.nombre if t.responsable else 'sin responsable'}) está por vencer.", t, "AVISO")
                    notif.correo("SLA_90", [supervisor], t)
                    escalado_a = supervisor
                else:
                    stats["vencidos"] += 1
                    t.sla_incumplido = True
                    if not self.tickets.existe_incumplimiento(t.id, "RESOLUCION"):
                        self._registrar_incumplimiento(t, "RESOLUCION", t.sla_resolucion_vence, ahora)
                    anterior = t.estado
                    if t.estado != Estado.ESCALADO:
                        t.estado = Estado.ESCALADO
                        self.session.add(m.TicketHistorial(ticket_id=t.id, accion="CAMBIO_ESTADO", campo="estado", valor_anterior=anterior,
                                                           valor_nuevo=Estado.ESCALADO, detalle="Escalamiento automático por SLA vencido", fecha=ahora))
                    notif.notificar([t.responsable, supervisor, *coord], "SLA_VENCIDO", f"{t.numero}: SLA incumplido",
                                    f"«{t.asunto}» venció su SLA y fue escalado automáticamente.", t, "CRITICO")
                    notif.correo("SLA_VENCIDO", [supervisor, *coord], t)
                    escalado_a = supervisor
                self.session.add(
                    m.TicketEscalamiento(ticket_id=t.id, nivel=umbral, tipo="AUTOMATICO", escalado_a=escalado_a.id if escalado_a else None,
                                         motivo=f"SLA consumido al {umbral} %", sla_consumido_pct=t.sla_consumido_pct, fecha=ahora)
                )
        self.session.flush()
        return stats
