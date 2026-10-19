"""Buzón compartido de Exchange Online (soporte@): crea tickets desde correos y agrega las respuestas al ticket.

Reglas:
* Un correo sin número de ticket en el asunto crea un ticket (canal CORREO): la IA lo clasifica, se asigna
  responsable y se envía el acuse de recepción con [ADU-AAAA-NNNNNN] en el asunto.
* Un correo cuyo asunto contiene el número de un ticket abierto o resuelto se agrega como comentario;
  si el ticket está cerrado o cancelado se crea uno nuevo relacionado.
* Los adjuntos pasan por la misma validación que los subidos desde la web.
* Cada mensaje se procesa una sola vez (tabla correos_entrantes) y queda marcado como leído en el buzón.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, ErrorAplicacion
from app.application.schemas import esquemas as s
from app.application.services.ticket_service import TicketService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado, Rol
from app.infrastructure.db import models as m
from app.infrastructure.m365.graph import ClienteGraph
from app.infrastructure.repositories.repositorios import UsuarioRepository

log = logging.getLogger(__name__)

PATRON_TICKET = re.compile(r"\bADU-\d{4}-\d{6}\b", re.IGNORECASE)
PREFIJOS_RESPUESTA = re.compile(r"^\s*((re|rv|fw|fwd|reenviar|respuesta)\s*:\s*)+", re.IGNORECASE)
CAMPOS = "id,internetMessageId,subject,from,receivedDateTime,hasAttachments,uniqueBody,body,internetMessageHeaders"
NOMBRE_BUZON = "Buzón de soporte (remitentes externos)"


def _hora(valor: str | None) -> datetime | None:
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)


def es_automatico(msg: dict) -> bool:
    """Respuestas automáticas, rebotes y listas: no deben crear tickets (evita bucles)."""
    cab = {h.get("name", "").lower(): h.get("value", "").lower() for h in msg.get("internetMessageHeaders") or []}
    if cab.get("auto-submitted", "no") != "no" or cab.get("precedence") in ("bulk", "junk", "list", "auto_reply"):
        return True
    asunto = (msg.get("subject") or "").lower()
    return asunto.startswith(("respuesta automática", "automatic reply", "undeliverable", "no se puede entregar"))


def texto_de(msg: dict) -> str:
    """Solo la parte nueva del mensaje (uniqueBody) en texto plano, sin la cadena citada."""
    texto = ((msg.get("uniqueBody") or {}).get("content") or (msg.get("body") or {}).get("content") or "").strip()
    texto = re.sub(r"\r\n?", "\n", texto)
    return re.sub(r"\n{3,}", "\n\n", texto)[:8000]


class BuzonService:
    def __init__(self, session: Session, graph: ClienteGraph | None = None):
        self.session = session
        self.graph = graph or ClienteGraph()
        self.tickets = TicketService(session)
        self.usuarios = UsuarioRepository(session)
        self.buzon = settings.BUZON_CORREO.lower()

    # ------------------------------------------------------------- lectura
    def procesar(self) -> dict:
        stats = {"leidos": 0, "creados": 0, "actualizados": 0, "ignorados": 0, "errores": 0}
        mensajes = self.graph.get(f"/users/{self.buzon}/mailFolders/inbox/messages",
                                  {"$filter": "isRead eq false", "$top": str(settings.BUZON_LOTE), "$select": CAMPOS},
                                  {"Prefer": 'outlook.body-content-type="text"'}).get("value", [])
        for msg in sorted(mensajes, key=lambda x: x.get("receivedDateTime") or ""):
            stats["leidos"] += 1
            resultado, ticket = self._procesar_seguro(msg)
            stats[{"CREADO": "creados", "ACTUALIZADO": "actualizados", "IGNORADO": "ignorados"}.get(resultado, "errores")] += 1
            try:
                cambios = {"isRead": True}
                if ticket is not None:
                    cambios["categories"] = [f"Mesa {ticket.numero}"]
                self.graph.patch(f"/users/{self.buzon}/messages/{msg['id']}", cambios)
            except Exception:
                log.exception("No se pudo marcar como leído el mensaje %s", msg.get("id"))
        return stats

    def _procesar_seguro(self, msg: dict) -> tuple[str, m.Ticket | None]:
        message_id = (msg.get("internetMessageId") or msg["id"])[:300]
        if self.session.scalar(select(m.CorreoEntrante.id).where(m.CorreoEntrante.message_id == message_id)):
            return "IGNORADO", None
        remitente = ((msg.get("from") or {}).get("emailAddress") or {})
        base = dict(message_id=message_id, graph_id=msg["id"][:300], remitente=(remitente.get("address") or "?")[:150],
                    asunto=(msg.get("subject") or "(sin asunto)")[:250], fecha_recepcion=_hora(msg.get("receivedDateTime")))
        try:
            resultado, ticket, detalle = self._procesar(msg, remitente)
            self.session.add(m.CorreoEntrante(**base, ticket_id=ticket.id if ticket else None, resultado=resultado,
                                              detalle=detalle, fecha_proceso=utcnow()))
            self.session.commit()
            return resultado, ticket
        except Exception as exc:
            self.session.rollback()
            log.exception("Error procesando el correo %s", message_id)
            self.session.add(m.CorreoEntrante(**base, resultado="ERROR", detalle=str(exc)[:1000], fecha_proceso=utcnow()))
            self.session.commit()
            return "ERROR", None

    def _procesar(self, msg: dict, remitente: dict) -> tuple[str, m.Ticket | None, str | None]:
        correo = (remitente.get("address") or "").lower().strip()
        nombre = remitente.get("name") or correo
        if not correo or correo == self.buzon:
            return "IGNORADO", None, "Remitente vacío o el propio buzón"
        if es_automatico(msg):
            return "IGNORADO", None, "Respuesta automática o rebote"
        asunto = PREFIJOS_RESPUESTA.sub("", msg.get("subject") or "").strip() or "(sin asunto)"
        texto = texto_de(msg) or "(correo sin texto)"
        numero = PATRON_TICKET.search(msg.get("subject") or "")
        existente = self.session.scalar(select(m.Ticket).where(m.Ticket.numero == numero.group(0).upper(), m.Ticket.eliminado == False)) if numero else None
        if existente is not None and Estado(existente.estado) not in (Estado.CERRADO, Estado.CANCELADO):
            detalle = self._agregar_respuesta(existente, correo, nombre, texto, msg)
            return "ACTUALIZADO", existente, detalle
        relacionado = f"\n\nRelacionado con el ticket {existente.numero}, que ya estaba cerrado." if existente is not None else ""
        t, detalle = self._crear_ticket(correo, nombre, asunto, texto + relacionado, msg)
        return "CREADO", t, detalle

    # -------------------------------------------------------------- tickets
    def _solicitante(self, correo: str, nombre: str) -> m.Usuario:
        u = self.usuarios.por_correo(correo)
        if u is not None and u.activo:
            return u
        dominio = correo.rsplit("@", 1)[-1]
        if u is None and dominio in {d.lower() for d in settings.BUZON_DOMINIOS_INTERNOS}:
            # Colaborador interno que aún no ingresó a la Mesa: se crea como Cliente interno (ingresará con Microsoft)
            u = self.usuarios.add(m.Usuario(nombre=nombre[:150], correo=correo, origen_autenticacion="ENTRA" if settings.entra_activo else "LOCAL",
                                            rol_id=self.usuarios.rol_por_codigo(Rol.CLIENTE).id, fecha_creacion=utcnow()))
            self.session.refresh(u)
            return u
        return self._usuario_buzon()

    def _usuario_buzon(self) -> m.Usuario:
        u = self.usuarios.por_correo(self.buzon)
        if u is None:
            u = self.usuarios.add(m.Usuario(nombre=NOMBRE_BUZON, correo=self.buzon, origen_autenticacion="LOCAL", cargo="Cuenta de sistema",
                                            rol_id=self.usuarios.rol_por_codigo(Rol.CLIENTE).id, fecha_creacion=utcnow()))
            self.session.refresh(u)
        return u

    def _clasificar(self, asunto: str, texto: str) -> tuple[int, int, str | None]:
        clasif, _ = self.tickets.ia.clasificar(f"{asunto}. {texto}")
        if clasif:
            return clasif[0].categoria_id, clasif[0].subcategoria_id, None
        for c in self.tickets.catalogo.categorias():
            subs = [x for x in c.subcategorias if x.activo and not x.eliminado]
            if subs:
                return c.id, subs[0].id, "La IA no reconoció la categoría; se usó la primera del catálogo. Revise la clasificación."
        raise ErrorAplicacion("No hay categorías activas para registrar el ticket")

    def _crear_ticket(self, correo: str, nombre: str, asunto: str, texto: str, msg: dict) -> tuple[m.Ticket, str | None]:
        solicitante = self._solicitante(correo, nombre)
        externo = solicitante.correo.lower() == self.buzon
        categoria_id, subcategoria_id, aviso = self._clasificar(asunto, texto)
        descripcion = (f"Remitente: {nombre} <{correo}>\n\n{texto}" if externo else texto).ljust(10, ".")
        dto = s.TicketCrear(asunto=asunto[:200].ljust(5, "."), descripcion=descripcion, categoria_id=categoria_id,
                            subcategoria_id=subcategoria_id, canal="CORREO", correo=correo)
        ctx = Contexto(usuario=solicitante, ip="buzon", equipo=f"Exchange Online · {self.buzon}")
        t = self.tickets.crear(dto, ctx)
        avisos = [aviso] if aviso else []
        avisos += self._adjuntos(t, solicitante, msg, ctx)
        if avisos:
            self.tickets._agregar_comentario(t, self._usuario_buzon(), "\n".join(avisos), True, "SISTEMA", None, utcnow())
        self.session.flush()
        self.session.refresh(t)
        self.tickets.notif.correo_directo("ACUSE_CORREO", correo, nombre, t)
        return t, "; ".join(avisos) or None

    def _agregar_respuesta(self, t: m.Ticket, correo: str, nombre: str, texto: str, msg: dict) -> str | None:
        u = self.usuarios.por_correo(correo)
        autor = None
        if u is not None and u.activo and "comentar" in self.tickets.acciones(u, t):
            autor = u
        elif correo == (t.correo or "").lower():
            autor = t.solicitante          # remitente externo del ticket original
        ahora = utcnow()
        if autor is not None:
            ctx = Contexto(usuario=autor, ip="buzon", equipo=f"Exchange Online · {self.buzon}")
            cuerpo = texto if autor.correo.lower() == correo else f"Respuesta por correo de {nombre} <{correo}>:\n\n{texto}"
            self.tickets.comentar(t.id, s.ComentarioEntrada(texto=cuerpo), ctx)
            avisos = self._adjuntos(t, autor, msg, ctx)
        else:
            # Un tercero escribió citando el número: queda como nota interna para que el equipo decida
            sistema = self._usuario_buzon()
            ctx = Contexto(usuario=sistema, ip="buzon", equipo=f"Exchange Online · {self.buzon}")
            self.tickets._agregar_comentario(t, sistema, f"Correo de {nombre} <{correo}> (no participa en el ticket):\n\n{texto}",
                                             True, "COMENTARIO", None, ahora)
            self.tickets.notif.notificar([t.responsable], "COMENTARIO", f"{t.numero}: correo de un tercero", f"{nombre}: {texto[:200]}", t)
            avisos = self._adjuntos(t, sistema, msg, ctx)
        if avisos:
            self.tickets._agregar_comentario(t, self._usuario_buzon(), "\n".join(avisos), True, "SISTEMA", None, ahora)
        t.fecha_actualizacion = ahora
        return "; ".join(avisos) or None

    def _adjuntos(self, t: m.Ticket, autor: m.Usuario, msg: dict, ctx: Contexto) -> list[str]:
        if not msg.get("hasAttachments"):
            return []
        rechazados = []
        for a in self.graph.paginar(f"/users/{self.buzon}/messages/{msg['id']}/attachments"):
            if a.get("@odata.type") != "#microsoft.graph.fileAttachment" or a.get("isInline"):
                continue   # imágenes de firmas y elementos adjuntos de Outlook
            try:
                self.tickets.guardar_adjunto(t, autor, a.get("name") or "adjunto", a.get("contentType") or "",
                                             base64.b64decode(a.get("contentBytes") or ""), ctx)
            except ErrorAplicacion as exc:
                rechazados.append(f"Adjunto «{a.get('name')}» no guardado: {exc.mensaje}")
        return rechazados
