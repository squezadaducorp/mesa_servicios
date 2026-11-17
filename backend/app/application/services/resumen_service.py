"""Resumen diario por correo: a cada responsable, los tickets que le vencen hoy (Configuración sla.resumen_diario_hora)."""
from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.services.notificacion_service import NotificacionService
from app.application.services.sla_service import ESTADOS_ACTIVOS_SLA, SlaService
from app.application.services.ticket_service import limites_dia_utc
from app.core.config import settings
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base
from app.infrastructure.repositories.repositorios import CatalogoRepository

CLAVE_ULTIMO = "sla.resumen_diario_ultimo"
COLORES = {"vencido": "#C62828", "urgente": "#E65100", "normal": "#B57400"}


def hora_configurada(valor: str | None) -> time | None:
    """«08:30» → time(8, 30). Vacío o inválido = resumen desactivado."""
    try:
        h, mi = (int(x) for x in (valor or "").strip().split(":"))
        return time(h, mi)
    except ValueError:
        return None


class ResumenDiarioService:
    def __init__(self, session: Session):
        self.session = session
        self.sla = SlaService(session)
        self.notif = NotificacionService(session)
        self.tz = ZoneInfo(settings.ZONA_HORARIA)

    def corresponde(self, ahora: datetime) -> bool:
        """Día laborable, pasada la hora configurada y sin resumen enviado hoy."""
        config = CatalogoRepository(self.session).configuracion()
        hora = hora_configurada(config.get("sla.resumen_diario_hora", "08:30"))
        local = ahora.replace(tzinfo=timezone.utc).astimezone(self.tz)
        if hora is None or local.time() < hora or not self.sla.cal.tramos_del_dia(local.date()):
            return False
        return config.get(CLAVE_ULTIMO, "") != local.date().isoformat()

    def enviar(self, ahora: datetime | None = None, forzar: bool = False) -> dict:
        ahora = ahora or utcnow()
        if not forzar and not self.corresponde(ahora):
            return {"omitido": "no corresponde"}
        hoy = ahora.replace(tzinfo=timezone.utc).astimezone(self.tz).date()
        marca = self.session.get(m.Configuracion, CLAVE_ULTIMO)
        if marca is None:
            marca = m.Configuracion(clave=CLAVE_ULTIMO, valor="", descripcion="Uso interno: último día en que se envió el resumen diario")
            self.session.add(marca)
        marca.valor, marca.fecha_actualizacion = hoy.isoformat(), ahora
        self.session.flush()

        _, fin_hoy = limites_dia_utc(None, hoy)
        T = m.Ticket
        tickets = self.session.scalars(
            select(T).where(T.eliminado == False, T.responsable_id.is_not(None), T.estado.in_(list(ESTADOS_ACTIVOS_SLA)),
                            T.sla_pausa_desde.is_(None), T.sla_excluido == False,
                            or_(T.sla_resolucion_vence < fin_hoy, T.fecha_primera_respuesta.is_(None) & (T.sla_respuesta_vence < fin_hoy)))
            .order_by(T.sla_resolucion_vence)
        ).unique().all()
        por_usuario: dict[int, list[tuple[m.Ticket, str, datetime, int]]] = defaultdict(list)
        for t in tickets:
            v = self.sla.proximo_vencimiento(t, ahora)
            if v is None:
                continue
            tipo, vence, falta = v
            if vence >= fin_hoy and tipo == "RESOLUCION":
                continue
            por_usuario[t.responsable_id].append((t, tipo, vence, falta))

        enviados = 0
        for usuario_id, filas in por_usuario.items():
            u = self.session.get(m.Usuario, usuario_id)
            if u is None or not u.activo:
                continue
            filas.sort(key=lambda f: f[3])
            n = len(filas)
            self.notif.notificar([u], "SLA_RESUMEN_DIARIO", f"Hoy vencen {n} de sus tickets",
                                 "Resumen del día · también enviado por correo", None, "INFO")
            self.session.add(m.ColaCorreo(
                para=u.correo, asunto=f"Hoy vencen {n} de sus tickets · {hoy:%d/%m/%Y}"[:250],
                cuerpo_html=plantilla_base(self._cuerpo(u, filas)), plantilla="SLA_RESUMEN_DIARIO", estado="PENDIENTE",
                proximo_intento=ahora, fecha_creacion=ahora))
            enviados += 1
        self.session.flush()
        return {"resumenes": enviados, "tickets": sum(len(f) for f in por_usuario.values())}

    def _cuerpo(self, u: m.Usuario, filas) -> str:
        base = settings.APP_URL.rstrip("/")
        lineas = []
        for t, tipo, vence, falta in filas:
            color = COLORES["vencido"] if falta < 0 else COLORES["urgente"] if falta <= 120 else COLORES["normal"]
            hora = vence.replace(tzinfo=timezone.utc).astimezone(self.tz).strftime("%H:%M")
            plazo = ("venció " if falta < 0 else "vence ") + hora
            que = " (1.ª respuesta)" if tipo == "RESPUESTA" else ""
            lineas.append(
                f'<tr><td style="border-left:4px solid {color};padding:6px 10px">'
                f'<a href="{base}/tickets/{t.id}" style="color:#1367AC;font-weight:600;text-decoration:none">{t.numero}</a><br>'
                f'<span style="font-size:12px;color:#5A6577">{html.escape(t.asunto)}{que} · {html.escape(t.prioridad.nombre)}</span></td>'
                f'<td align="right" style="padding:6px 10px;font-weight:700;color:{color};white-space:nowrap">{plazo}</td></tr>')
        return (f"<p>Buenos días, {html.escape(u.nombre.split()[0])}. Estos tickets vencen hoy en horario laboral:</p>"
                f'<table width="100%" cellpadding="0" cellspacing="6">{"".join(lineas)}</table>'
                f'<p style="text-align:center;margin-top:18px"><a href="{base}/tickets?vence=HOY" '
                f'style="background:#1367AC;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">'
                f"Abrir mis tickets por vencer</a></p>"
                f'<p style="font-size:12px;color:#5A6577">Si no tiene tickets por vencer, este correo no se envía.</p>')
