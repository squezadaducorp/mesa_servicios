"""Tickets recurrentes: el worker crea solo los tickets programados (p. ej. mantenimiento preventivo mensual)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, ErrorAplicacion, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as es
from app.application.schemas import mejoras2 as s
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService
from app.application.services.sla_service import cargar_calendario
from app.core.config import settings
from app.core.security import utcnow
from app.domain import recurrencia as rc
from app.domain.enums import ESTADOS_ABIERTOS, AccionAuditoria, Permiso
from app.infrastructure.db import models as m

log = logging.getLogger(__name__)


def regla(r: m.TicketRecurrente | s.RecurrenteEntrada) -> rc.Regla:
    return rc.Regla(frecuencia=r.frecuencia, desde=r.desde, hora=r.hora, dia_semana=r.dia_semana, dia_mes=r.dia_mes,
                    semana_mes=r.semana_mes, hasta=r.hasta)


class RecurrentesService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)
        self.cal = cargar_calendario(session)

    def laborable(self, d) -> bool:
        return bool(self.cal.tramos_del_dia(d))

    def calcular_proxima(self, r: m.TicketRecurrente | s.RecurrenteEntrada, despues: datetime) -> tuple[datetime, rc.Ocurrencia] | None:
        return rc.proxima(regla(r), despues, self.laborable, settings.ZONA_HORARIA)

    def vista_previa(self, dto: s.RecurrenteEntrada, n: int = 6) -> dict:
        error = rc.validar(regla(dto))
        if error:
            raise ReglaNegocio(error)
        filas = rc.siguientes(regla(dto), utcnow(), self.laborable, settings.ZONA_HORARIA, n)
        return {"fechas": [f.isoformat() + "Z" for f, _ in filas],
                "movidas": [f"tocaba el {o.nominal:%d/%m} (no laborable)" if o.movida else "" for _, o in filas]}

    def salida(self, r: m.TicketRecurrente) -> dict:
        ultimo = self.session.get(m.Ticket, r.ultimo_ticket_id) if r.ultimo_ticket_id else None
        return {
            **{k: getattr(r, k) for k in ("id", "nombre", "asunto", "descripcion", "tareas", "categoria_id", "subcategoria_id", "prioridad_id",
                                          "responsable_id", "solicitante_id", "frecuencia", "dia_semana", "dia_mes", "semana_mes", "hora",
                                          "desde", "hasta", "omitir_si_abierto", "activo", "proxima_ejecucion", "ultima_ejecucion",
                                          "ultimo_ticket_id", "ultimo_resultado")},
            "categoria": r.categoria.nombre, "subcategoria": r.subcategoria.nombre, "prioridad": r.prioridad.nombre,
            "responsable": r.responsable.nombre if r.responsable else None,
            "descripcion_frecuencia": rc.describir(regla(r)), "ultimo_ticket_numero": ultimo.numero if ultimo else None,
        }

    def listar(self) -> list[m.TicketRecurrente]:
        return list(self.session.scalars(select(m.TicketRecurrente).order_by(m.TicketRecurrente.activo.desc(), m.TicketRecurrente.nombre)).unique())

    def obtener(self, rid: int) -> m.TicketRecurrente:
        r = self.session.get(m.TicketRecurrente, rid)
        if r is None:
            raise NoEncontrado("Programación no encontrada")
        return r

    def guardar(self, dto: s.RecurrenteEntrada, ctx: Contexto, rid: int | None = None) -> m.TicketRecurrente:
        u = ctx.usuario
        if not u.tiene(Permiso.RECURRENTES_GESTIONAR):
            raise Prohibido("No tiene permiso para programar tickets")
        error = rc.validar(regla(dto))
        if error:
            raise ReglaNegocio(error)
        sub = self.session.get(m.Subcategoria, dto.subcategoria_id)
        if sub is None or sub.categoria_id != dto.categoria_id:
            raise ReglaNegocio("La subcategoría no pertenece a la categoría")
        if self.session.get(m.Prioridad, dto.prioridad_id) is None:
            raise ReglaNegocio("Prioridad no válida")
        if dto.responsable_id:
            from app.application.services.ticket_service import TicketService

            TicketService(self.session)._validar_responsable(dto.responsable_id)
        solicitante_id = dto.solicitante_id or u.id
        if self.session.get(m.Usuario, solicitante_id) is None:
            raise ReglaNegocio("Solicitante no válido")
        if rid is None:
            r = m.TicketRecurrente(creado_por=u.id, fecha_creacion=utcnow())
            self.session.add(r)
        else:
            r = self.obtener(rid)
        datos = dto.model_dump()
        datos["solicitante_id"] = solicitante_id
        if dto.frecuencia in ("DIARIA", "SEMANAL"):
            datos["dia_mes"] = datos["semana_mes"] = None
        if dto.frecuencia == "DIARIA":
            datos["dia_semana"] = None
        if dto.frecuencia in rc.PASOS_MES and not dto.semana_mes:
            datos["dia_semana"] = None
        for k, v in datos.items():
            setattr(r, k, v.strip() if isinstance(v, str) else v)
        prox = self.calcular_proxima(r, max(utcnow(), r.ultima_ejecucion or utcnow()))
        r.proxima_ejecucion = prox[0] if prox and r.activo else None
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.RECURRENTE_MODIFICADO, "ticket_recurrente", r.id,
                                 {"nombre": r.nombre, "frecuencia": rc.describir(regla(r)), "activo": r.activo})
        self.session.refresh(r)
        return r

    def eliminar(self, rid: int, ctx: Contexto) -> None:
        if not ctx.usuario.tiene(Permiso.RECURRENTES_GESTIONAR):
            raise Prohibido("No tiene permiso para programar tickets")
        r = self.obtener(rid)
        r.activo, r.proxima_ejecucion = False, None
        self.auditoria.registrar(ctx, AccionAuditoria.RECURRENTE_MODIFICADO, "ticket_recurrente", r.id, {"nombre": r.nombre, "desactivado": True})

    # -------------------------------------------------------------- ejecutar
    def _descripcion(self, r: m.TicketRecurrente, fecha) -> str:
        texto = rc.rellenar_fecha(r.descripcion, fecha)
        tareas = [t.strip() for t in (r.tareas or "").splitlines() if t.strip()]
        if tareas:
            texto += "\n\nTareas:\n" + "\n".join(f"☐ {t}" for t in tareas)
        return texto + f"\n\n(Ticket creado automáticamente: {rc.describir(regla(r))})"

    def crear_ticket(self, r: m.TicketRecurrente, fecha, ctx: Contexto) -> m.Ticket:
        from app.application.services.ticket_service import TicketService

        dto = es.TicketCrear(
            asunto=rc.rellenar_fecha(r.asunto, fecha)[:200], descripcion=self._descripcion(r, fecha), categoria_id=r.categoria_id,
            subcategoria_id=r.subcategoria_id, prioridad_id=r.prioridad_id, solicitante_id=r.solicitante_id, responsable_id=r.responsable_id,
        )
        return TicketService(self.session).crear(dto, ctx, sistema=True, canal="PROGRAMADO", recurrente_id=r.id)

    def ejecutar_ahora(self, rid: int, ctx: Contexto) -> m.Ticket:
        if not ctx.usuario.tiene(Permiso.RECURRENTES_GESTIONAR):
            raise Prohibido("No tiene permiso para programar tickets")
        r = self.obtener(rid)
        hoy = datetime.now(ZoneInfo(settings.ZONA_HORARIA)).date()
        t = self.crear_ticket(r, hoy, ctx)
        r.ultimo_ticket_id, r.ultima_ejecucion, r.ultimo_resultado = t.id, utcnow(), f"Creado a mano: {t.numero}"
        return t

    def procesar(self, ahora: datetime | None = None) -> dict:
        """Crea los tickets cuya fecha ya llegó. Lo llama el worker en cada ciclo."""
        ahora = ahora or utcnow()
        R = m.TicketRecurrente
        pendientes = list(self.session.scalars(
            select(R).where(R.activo == True, R.proxima_ejecucion.is_not(None), R.proxima_ejecucion <= ahora)).unique())
        creados = omitidos = errores = 0
        for r in pendientes:
            local = r.proxima_ejecucion.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.ZONA_HORARIA)).date()
            ctx = Contexto(usuario=None, ip="worker", equipo="tickets recurrentes")
            anterior = self.session.get(m.Ticket, r.ultimo_ticket_id) if r.ultimo_ticket_id else None
            try:
                with self.session.begin_nested():
                    if r.omitir_si_abierto and anterior is not None and anterior.estado in ESTADOS_ABIERTOS and not anterior.eliminado:
                        r.ultimo_resultado = f"Omitido el {local:%d/%m/%Y}: {anterior.numero} sigue abierto"
                        omitidos += 1
                        destinatarios = [anterior.categoria.supervisor, anterior.responsable]
                        NotificacionService(self.session).notificar(
                            destinatarios, "RECURRENTE_OMITIDO", f"No se creó «{r.nombre}»",
                            f"{anterior.numero} del periodo anterior sigue abierto; ciérrelo o revise la programación.", anterior, "AVISO")
                    else:
                        t = self.crear_ticket(r, local, ctx)
                        r.ultimo_ticket_id, r.ultimo_resultado = t.id, f"Creado {t.numero}"
                        creados += 1
            except ErrorAplicacion as exc:
                r.ultimo_resultado = f"Error el {local:%d/%m/%Y}: {exc.mensaje}"[:300]
                errores += 1
                log.warning("Ticket recurrente %s: %s", r.id, exc.mensaje)
            r.ultima_ejecucion = ahora
            prox = self.calcular_proxima(r, max(ahora, r.proxima_ejecucion))
            r.proxima_ejecucion = prox[0] if prox else None
            if prox is None:
                r.activo = False
        self.session.flush()
        return {"creados": creados, "omitidos": omitidos, "errores": errores}
