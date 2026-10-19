"""Microsoft Teams: tarjetas adaptables de los tickets, avisos en canales y acciones desde Teams.

* El worker publica los avisos encolados (cola_teams) en el canal general «Mesa de Servicios» y en el canal
  vinculado a la categoría del ticket.
* Los canales se vinculan escribiendo al bot dentro del canal: «@Mesa vincular general» o
  «@Mesa vincular Clasificación Arancelaria».
* Los botones Aceptar, Escalar y Cambiar estado (Action.Execute) llegan como invoke «adaptiveCard/action» y se
  ejecutan con los permisos del usuario de la Mesa vinculado a la cuenta de Teams (objectId de Entra ID).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, ErrorAplicacion
from app.application.schemas import esquemas as s
from app.application.services.ticket_service import TicketService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.m365.teams import ConectorBot

log = logging.getLogger(__name__)

TITULOS = {
    "TICKET_CREADO": ("Nuevo ticket", "accent"),
    "TICKET_ASIGNADO": ("Ticket asignado", "accent"),
    "TICKET_ESCALADO": ("Ticket escalado", "warning"),
    "SLA_75": ("SLA al 75 %", "warning"),
    "SLA_90": ("SLA al 90 %", "attention"),
    "SLA_VENCIDO": ("SLA vencido", "attention"),
    "TICKET_CERRADO": ("Ticket cerrado", "good"),
    "ACTUALIZADO": ("Ticket actualizado", "accent"),
}
ESTADOS_TEAMS = [(Estado.EN_PROCESO, "En proceso"), (Estado.PENDIENTE_CLIENTE, "Pendiente cliente"),
                 (Estado.RESUELTO, "Resuelto"), (Estado.CERRADO, "Cerrado")]
AYUDA = ("Comandos de la Mesa de Servicios:\n\n"
         "- **vincular general**: este canal recibe los avisos de todos los tickets.\n"
         "- **vincular <categoría>**: este canal recibe los avisos de esa categoría (por ejemplo «vincular Legal Aduanero»).\n"
         "- **desvincular**: este canal deja de recibir avisos.\n"
         "- **ticket ADU-2026-000123**: muestra la tarjeta del ticket.")


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def sla_restante(t: m.Ticket) -> str:
    if t.estado in (Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO):
        return "Cumplido" if not t.sla_incumplido else "Incumplido"
    total = (t.sla_resolucion_min or 0) + (t.sla_minutos_extension or 0)
    restante = total - (t.sla_minutos_consumidos or 0)
    if restante <= 0 or t.sla_incumplido:
        return f"Vencido ({float(t.sla_consumido_pct or 0):.0f} %)"
    h, mnt = divmod(int(restante), 60)
    pausa = " · en pausa" if t.sla_pausa_desde else ""
    return f"{h} h {mnt:02d} min laborables ({float(t.sla_consumido_pct or 0):.0f} % consumido){pausa}"


def tarjeta(t: m.Ticket, evento: str, detalle: str | None = None, aviso: tuple[str, str] | None = None) -> dict:
    """Adaptive Card 1.5 con los datos del ticket y las acciones disponibles según su estado."""
    titulo, color = TITULOS.get(evento, TITULOS["ACTUALIZADO"])
    cuerpo: list[dict] = []
    if aviso:
        cuerpo.append({"type": "Container", "style": aviso[1], "items": [{"type": "TextBlock", "text": aviso[0], "wrap": True, "weight": "Bolder"}]})
    cuerpo += [
        {"type": "Container", "style": color, "bleed": True, "items": [
            {"type": "TextBlock", "text": titulo.upper(), "size": "Small", "weight": "Bolder", "spacing": "None"},
            {"type": "TextBlock", "text": f"{t.numero} · {t.asunto}", "size": "Medium", "weight": "Bolder", "wrap": True},
        ]},
        {"type": "FactSet", "facts": [
            {"title": "Prioridad", "value": t.prioridad.nombre if t.prioridad else "—"},
            {"title": "Cliente", "value": t.cliente.nombre if t.cliente else "—"},
            {"title": "Responsable", "value": t.responsable.nombre if t.responsable else "Sin asignar"},
            {"title": "Estado", "value": t.estado_rel.nombre if t.estado_rel else t.estado},
            {"title": "SLA restante", "value": sla_restante(t)},
            {"title": "Categoría", "value": f"{t.categoria.nombre} › {t.subcategoria.nombre}" if t.subcategoria else t.categoria.nombre},
            {"title": "Solicitante", "value": t.solicitante_nombre},
        ]},
    ]
    if detalle:
        cuerpo.append({"type": "TextBlock", "text": detalle, "wrap": True, "isSubtle": True})
    datos = {"ticket_id": t.id}
    acciones: list[dict] = []
    if t.estado not in (Estado.CERRADO, Estado.CANCELADO):
        if t.estado in (Estado.NUEVO, Estado.ASIGNADO, Estado.ESCALADO):
            acciones.append({"type": "Action.Execute", "title": "Aceptar", "verb": "aceptar", "data": datos, "style": "positive"})
        if t.estado not in (Estado.ESCALADO, Estado.RESUELTO):
            acciones.append({"type": "Action.ShowCard", "title": "Escalar", "card": {"type": "AdaptiveCard", "body": [
                {"type": "Input.Text", "id": "motivo", "label": "Motivo del escalamiento", "isMultiline": True, "isRequired": True,
                 "errorMessage": "Indique el motivo"}],
                "actions": [{"type": "Action.Execute", "title": "Escalar", "verb": "escalar", "data": datos}]}})
        acciones.append({"type": "Action.ShowCard", "title": "Cambiar estado", "card": {"type": "AdaptiveCard", "body": [
            {"type": "Input.ChoiceSet", "id": "estado", "label": "Nuevo estado", "isRequired": True, "errorMessage": "Elija un estado",
             "choices": [{"title": n, "value": e.value} for e, n in ESTADOS_TEAMS if e != t.estado]},
            {"type": "Input.Text", "id": "comentario", "label": "Comentario para el solicitante", "isMultiline": True}],
            "actions": [{"type": "Action.Execute", "title": "Guardar", "verb": "estado", "data": datos}]}})
    acciones.append({"type": "Action.OpenUrl", "title": "Abrir en la Mesa", "url": f"{settings.APP_URL.rstrip('/')}/tickets/{t.id}"})
    return {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.5",
            "body": cuerpo, "actions": acciones}


def actividad_tarjeta(card: dict, texto: str) -> dict:
    return {"type": "message", "summary": texto, "text": "",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}


class TeamsService:
    def __init__(self, session: Session, conector: ConectorBot | None = None):
        self.session = session
        self.conector = conector or ConectorBot()
        self.tickets = TicketService(session)

    # ------------------------------------------------------- envío de avisos
    def canales_para(self, t: m.Ticket) -> list[m.TeamsCanal]:
        return list(self.session.scalars(select(m.TeamsCanal).where(
            m.TeamsCanal.activo == True, (m.TeamsCanal.categoria_id == None) | (m.TeamsCanal.categoria_id == t.categoria_id))).unique())  # noqa: E711

    def procesar_cola(self, lote: int = 50) -> dict:
        enviados = errores = 0
        pendientes = self.session.scalars(select(m.ColaTeams).where(
            m.ColaTeams.estado.in_(["PENDIENTE", "ERROR"]), m.ColaTeams.proximo_intento <= utcnow(), m.ColaTeams.intentos < 6)
            .order_by(m.ColaTeams.id).limit(lote)).all()
        for item in pendientes:
            t = self.session.get(m.Ticket, item.ticket_id)
            canales = self.canales_para(t) if t else []
            if not canales:
                item.estado, item.ultimo_error = "DESCARTADO", "No hay canales de Teams vinculados para este ticket"
                self.session.commit()
                continue
            try:
                actividad = actividad_tarjeta(tarjeta(t, item.evento, item.detalle), f"{TITULOS.get(item.evento, ('', ''))[0]}: {t.numero}")
                for c in canales:
                    self.conector.enviar(c.service_url, c.conversation_id, actividad)
                item.estado, item.fecha_envio = "ENVIADO", utcnow()
                enviados += 1
            except Exception as exc:   # reintento con backoff exponencial, igual que los correos
                item.intentos += 1
                item.estado, item.ultimo_error = ("DESCARTADO" if item.intentos >= 6 else "ERROR"), str(exc)[:1000]
                item.proximo_intento = utcnow() + timedelta(minutes=2 ** (item.intentos - 1))
                errores += 1
                log.warning("Error publicando en Teams el aviso %s: %s", item.id, exc)
            self.session.commit()
        return {"enviados": enviados, "errores": errores}

    # ------------------------------------------------ actividades entrantes
    def usuario_de(self, actividad: dict) -> m.Usuario | None:
        oid = (actividad.get("from") or {}).get("aadObjectId")
        if not oid:
            return None
        u = self.session.scalars(select(m.Usuario).where(m.Usuario.entra_oid == oid, m.Usuario.eliminado == False)).first()
        return u if u and u.activo else None

    def procesar(self, actividad: dict) -> dict | None:
        """Devuelve el cuerpo de la respuesta HTTP (solo para invoke); los mensajes se contestan por el conector."""
        tipo = actividad.get("type")
        if tipo == "invoke" and actividad.get("name") == "adaptiveCard/action":
            return self._accion_tarjeta(actividad)
        if tipo == "message":
            self._mensaje(actividad)
        return None

    def _responder(self, actividad: dict, contenido: dict | str) -> None:
        respuesta = {"type": "message", "text": contenido} if isinstance(contenido, str) else contenido
        respuesta["replyToId"] = actividad.get("id")
        self.conector.enviar(actividad["serviceUrl"], actividad["conversation"]["id"], respuesta)

    def _mensaje(self, actividad: dict) -> None:
        texto = _normalizar(re.sub(r"<at>.*?</at>", "", actividad.get("text") or ""))
        if texto.startswith("ticket"):
            numero = texto.replace("ticket", "").strip().upper()
            u = self.usuario_de(actividad)
            t = self.session.scalar(select(m.Ticket).where(m.Ticket.numero == numero, m.Ticket.eliminado == False))
            if u is None or t is None or not self.tickets.repo.puede_ver(u, t.id):
                self._responder(actividad, f"No encontré el ticket {numero} o no tiene acceso a él.")
            else:
                self._responder(actividad, actividad_tarjeta(tarjeta(t, "ACTUALIZADO"), t.numero))
            return
        if texto.startswith("vincular") or texto.startswith("desvincular"):
            self._responder(actividad, self._vincular(actividad, texto))
            return
        self._responder(actividad, AYUDA)

    def _vincular(self, actividad: dict, texto: str) -> str:
        datos_canal = actividad.get("channelData") or {}
        canal = datos_canal.get("channel") or {}
        if not canal.get("id"):
            return "Este comando se usa dentro de un canal de un equipo de Teams."
        u = self.usuario_de(actividad)
        if u is None or not (u.tiene(Permiso.SISTEMA_ADMINISTRAR) or u.tiene(Permiso.CATEGORIA_ADMINISTRAR)):
            return "Solo un administrador de la Mesa puede vincular canales."
        existente = self.session.scalar(select(m.TeamsCanal).where(m.TeamsCanal.conversation_id == canal["id"]))
        if texto.startswith("desvincular"):
            if existente:
                existente.activo = False
                self.session.commit()
            return "Listo: este canal ya no recibirá avisos de la Mesa."
        destino = texto.replace("vincular", "", 1).strip()
        categoria = None
        if destino not in ("general", "mesa", "mesa de servicios", "todos"):
            categoria = next((c for c in self.tickets.catalogo.categorias() if _normalizar(c.nombre) == destino), None)
            if categoria is None:
                nombres = ", ".join(c.nombre for c in self.tickets.catalogo.categorias())
                return f"No encontré la categoría «{destino}». Categorías: {nombres}, o «general»."
        nombre = canal.get("name") or "General"
        if existente is None:
            existente = m.TeamsCanal(conversation_id=canal["id"], fecha_creacion=utcnow())
            self.session.add(existente)
        existente.nombre, existente.service_url = nombre[:150], actividad["serviceUrl"]
        existente.team_id = ((datos_canal.get("team") or {}).get("id") or "")[:300] or None
        existente.categoria_id, existente.activo, existente.vinculado_por = (categoria.id if categoria else None), True, u.id
        self.tickets.auditoria.registrar(Contexto(usuario=u, ip="teams"), "TEAMS_CANAL", "teams_canal", canal["id"][:40],
                                         {"canal": nombre, "categoria": categoria.nombre if categoria else "general"})
        self.session.commit()
        return (f"Listo: este canal recibirá los avisos de **{categoria.nombre}**." if categoria
                else "Listo: este canal recibirá los avisos de todos los tickets de la Mesa.")

    def _accion_tarjeta(self, actividad: dict) -> dict:
        accion = (actividad.get("value") or {}).get("action") or {}
        datos, verbo = accion.get("data") or {}, accion.get("verb")
        t = self.session.get(m.Ticket, int(datos.get("ticket_id") or 0))
        if t is None or t.eliminado:
            return self._respuesta_error("El ticket ya no existe.")
        u = self.usuario_de(actividad)
        if u is None:
            return self._respuesta(t, ("Su cuenta de Teams no está vinculada a un usuario de la Mesa. Ingrese una vez a la Mesa "
                                       "con «Iniciar sesión con Microsoft» y vuelva a intentarlo.", "attention"))
        ctx = Contexto(usuario=u, ip="teams", equipo="Microsoft Teams")
        try:
            if verbo == "aceptar":
                t = self.tickets.aceptar(t.id, ctx)
                mensaje = f"{u.nombre} aceptó el ticket y comenzó la atención."
            elif verbo == "escalar":
                t = self.tickets.escalar(t.id, s.EscalarEntrada(motivo=(datos.get("motivo") or "").strip()), ctx)
                mensaje = f"{u.nombre} escaló el ticket."
            elif verbo == "estado":
                destino, comentario = datos.get("estado"), (datos.get("comentario") or "").strip() or None
                if destino == Estado.CERRADO:
                    t = self.tickets.cerrar(t.id, comentario, ctx)
                else:
                    t = self.tickets.cambiar_estado(t.id, destino, comentario, ctx)
                mensaje = f"{u.nombre} cambió el estado a {t.estado_rel.nombre if t.estado_rel else t.estado}."
            else:
                return self._respuesta_error("Acción no reconocida.")
            self.session.commit()
        except ErrorAplicacion as exc:
            self.session.rollback()
            t = self.session.get(m.Ticket, t.id)
            return self._respuesta(t, (exc.mensaje, "attention"))
        except Exception as exc:   # validación de datos (motivo vacío, estado inválido)
            self.session.rollback()
            log.warning("Acción de Teams rechazada: %s", exc)
            t = self.session.get(m.Ticket, t.id)
            return self._respuesta(t, ("No se pudo aplicar la acción. Revise los datos e intente de nuevo.", "attention"))
        self.session.refresh(t)
        return self._respuesta(t, (mensaje, "good"))

    @staticmethod
    def _respuesta(t: m.Ticket, aviso: tuple[str, str]) -> dict:
        return {"statusCode": 200, "type": "application/vnd.microsoft.card.adaptive", "value": tarjeta(t, "ACTUALIZADO", aviso=aviso)}

    @staticmethod
    def _respuesta_error(mensaje: str) -> dict:
        return {"statusCode": 400, "type": "application/vnd.microsoft.error", "value": {"code": "BadRequest", "message": mensaje}}
