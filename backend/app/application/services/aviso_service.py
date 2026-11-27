"""Avisos generales: caídas que afectan a muchos a la vez (mejora 24).

- La mesa publica el aviso (ECUAPASS, internet, correo…) y lo actualiza por etapas: Investigando → Causa identificada →
  Monitoreando → Resuelto.
- Todos lo ven arriba de la pantalla (filtrado por área si se indicó) y pulsan «A mí también me afecta» en lugar de crear
  un ticket igual. Si de todas formas crean uno, el ticket queda vinculado al aviso.
- Cada actualización avisa a los afectados; al resolverlo se avisa a todos y se resuelven los tickets vinculados.
- El historial de caídas y la constancia en PDF sirven para explicar a un cliente un retraso del día de la caída.
"""
from __future__ import annotations

import html
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService, cuentas_sistema, fecha_local
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import ESTADOS_ABIERTOS, AccionAuditoria, Estado
from app.infrastructure.ai.local import normalizar
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base
from app.infrastructure.repositories.repositorios import CatalogoRepository

ESTADOS = {"INVESTIGANDO": "Investigando", "IDENTIFICADO": "Causa identificada", "MONITOREANDO": "Monitoreando", "RESUELTO": "Resuelto"}


def duracion(inicio: datetime, fin: datetime | None) -> str:
    minutos = int(((fin or utcnow()) - inicio).total_seconds() // 60)
    h, mi = divmod(max(minutos, 0), 60)
    return f"{h} h {mi:02d} min" if h else f"{mi} min"


class AvisoService:
    def __init__(self, session: Session):
        self.session = session
        self.notif = NotificacionService(session)
        self.auditoria = AuditoriaService(session)

    # ============================================================ consultas
    def get(self, aviso_id: int) -> m.AvisoGeneral:
        a = self.session.get(m.AvisoGeneral, aviso_id)
        if a is None:
            raise NoEncontrado("Aviso no encontrado")
        return a

    def activos(self, u: m.Usuario | None = None, publico: bool = False) -> list[m.AvisoGeneral]:
        A = m.AvisoGeneral
        stmt = select(A).where(A.estado != "RESUELTO").order_by(A.inicio.desc())
        avisos = list(self.session.scalars(stmt).unique())
        if publico:
            return [a for a in avisos if a.mostrar_publico]
        if u is None:
            return avisos
        gestiona = u.tiene("avisos.gestionar")
        return [a for a in avisos if gestiona or not a.area_ids or u.area_id in a.area_ids]

    def historial(self, anio: int | None = None) -> list[m.AvisoGeneral]:
        A = m.AvisoGeneral
        stmt = select(A).order_by(A.inicio.desc())
        avisos = list(self.session.scalars(stmt).unique())
        if anio:
            tz = ZoneInfo(settings.ZONA_HORARIA)
            avisos = [a for a in avisos if a.inicio.replace(tzinfo=timezone.utc).astimezone(tz).year == anio]
        return avisos

    def afectados(self, aviso_id: int) -> list[m.AvisoAfectado]:
        F = m.AvisoAfectado
        return list(self.session.scalars(select(F).where(F.aviso_id == aviso_id).order_by(F.fecha)).unique())

    def actualizaciones(self, aviso_id: int) -> list[m.AvisoActualizacion]:
        X = m.AvisoActualizacion
        return list(self.session.scalars(select(X).where(X.aviso_id == aviso_id).order_by(X.fecha, X.id)).unique())

    def _conteos(self, aviso_id: int) -> tuple[int, int, int]:
        F = m.AvisoAfectado
        personas = self.session.scalar(select(func.count()).select_from(F).where(F.aviso_id == aviso_id)) or 0
        tickets = self.session.scalar(select(func.count()).select_from(F).where(F.aviso_id == aviso_id, F.ticket_id.is_not(None))) or 0
        comentarios = self.session.scalar(select(func.count()).select_from(F).where(F.aviso_id == aviso_id, F.comentario.is_not(None))) or 0
        return personas, tickets, comentarios

    def salida(self, a: m.AvisoGeneral, u: m.Usuario | None = None, detalle: bool = False) -> dict:
        personas, tickets, comentarios = self._conteos(a.id)
        d = {
            "id": a.id, "codigo": a.codigo, "titulo": a.titulo, "mensaje": a.mensaje, "sistema": a.sistema, "palabras_clave": a.palabras_clave,
            "area_ids": a.area_ids, "mostrar_publico": a.mostrar_publico, "estado": a.estado, "estado_nombre": ESTADOS[a.estado],
            "inicio": a.inicio, "fin": a.fin, "duracion": duracion(a.inicio, a.fin), "proxima_novedad": a.proxima_novedad,
            "ticket_maestro": {"id": a.ticket_maestro.id, "numero": a.ticket_maestro.numero} if a.ticket_maestro else None,
            "afectados": personas, "tickets": tickets, "con_comentario": comentarios,
            "ultima_actualizacion": a.fecha_actualizacion or a.inicio,
            "me_afecta": bool(u and self.session.get(m.AvisoAfectado, (a.id, u.id))),
        }
        if detalle:
            d["actualizaciones"] = [{"id": x.id, "estado": x.estado, "estado_nombre": ESTADOS[x.estado], "texto": x.texto,
                                     "usuario": x.usuario.nombre if x.usuario else None, "fecha": x.fecha} for x in self.actualizaciones(a.id)]
        return d

    def salida_publica(self, a: m.AvisoGeneral) -> dict:
        return {"id": a.id, "titulo": a.titulo, "mensaje": a.mensaje, "estado_nombre": ESTADOS[a.estado], "inicio": a.inicio,
                "ultima_actualizacion": a.fecha_actualizacion or a.inicio}

    def lista_afectados(self, aviso_id: int) -> list[dict]:
        return [{"usuario_id": f.usuario_id, "nombre": f.usuario.nombre, "area": f.usuario.area.nombre if f.usuario.area else None,
                 "comentario": f.comentario, "ticket_id": f.ticket_id,
                 "ticket_numero": self.session.get(m.Ticket, f.ticket_id).numero if f.ticket_id else None, "fecha": f.fecha}
                for f in self.afectados(aviso_id)]

    def de_ticket(self, ticket_id: int) -> list[dict]:
        F = m.AvisoAfectado
        ids = set(self.session.scalars(select(F.aviso_id).where(F.ticket_id == ticket_id)))
        ids |= set(self.session.scalars(select(m.AvisoGeneral.id).where(m.AvisoGeneral.ticket_maestro_id == ticket_id)))
        return [{"id": a.id, "codigo": a.codigo, "titulo": a.titulo, "estado": a.estado, "estado_nombre": ESTADOS[a.estado],
                 "maestro": a.ticket_maestro_id == ticket_id} for a in (self.get(i) for i in sorted(ids))]

    def coincidencias(self, texto: str, u: m.Usuario) -> list[dict]:
        """Avisos activos que parecen ser lo que la persona está por reportar (por sistema, título o palabras clave)."""
        t = f" {normalizar(texto)} "
        salida = []
        for a in self.activos(u):
            claves = [normalizar(a.sistema)] + [normalizar(x) for x in (a.palabras_clave or "").split(",")]
            if any(c and f" {c} " in t for c in claves):
                salida.append(self.salida(a, u))
        return salida

    # ============================================================== gestión
    def crear(self, dto, ctx: Contexto) -> m.AvisoGeneral:
        ahora = utcnow()
        inicio = dto.inicio.replace(tzinfo=None) if dto.inicio else ahora
        if inicio > ahora:
            inicio = ahora
        a = m.AvisoGeneral(titulo=dto.titulo.strip(), mensaje=dto.mensaje.strip(), sistema=dto.sistema.strip(),
                           palabras_clave=(dto.palabras_clave or "").strip() or None, areas=",".join(str(i) for i in dto.area_ids) or None,
                           mostrar_publico=dto.mostrar_publico, ticket_maestro_id=self._maestro(dto.ticket_maestro_id, dto.ticket_maestro),
                           proxima_novedad=dto.proxima_novedad, inicio=inicio, creado_por=ctx.usuario.id, fecha_actualizacion=ahora)
        self.session.add(a)
        self.session.flush()
        self.session.add(m.AvisoActualizacion(aviso_id=a.id, estado=a.estado, texto=a.mensaje, usuario_id=ctx.usuario.id, fecha=ahora))
        self.auditoria.registrar(ctx, AccionAuditoria.AVISO_GENERAL, "aviso", a.id, {"operacion": "publicar", "titulo": a.titulo, "sistema": a.sistema})
        # Quien ya tenía un ticket abierto del ticket maestro queda como afectado
        if a.ticket_maestro_id:
            t = self.session.get(m.Ticket, a.ticket_maestro_id)
            self._afectar(a, t.solicitante, None, t.id, ahora)
        self.session.flush()
        return a

    def _maestro(self, ticket_id: int | None, numero: str | None = None) -> int | None:
        if not ticket_id and not (numero or "").strip():
            return None
        if ticket_id:
            t = self.session.get(m.Ticket, ticket_id)
        else:
            from app.infrastructure.repositories.repositorios import TicketRepository

            n = numero.strip().upper()
            t = TicketRepository(self.session).por_numero(n) or (self.session.get(m.Ticket, int(n)) if n.isdigit() else None)
        if t is None or t.eliminado:
            raise ReglaNegocio("Ticket maestro no válido")
        return t.id

    def editar(self, aviso_id: int, dto, ctx: Contexto) -> m.AvisoGeneral:
        a = self.get(aviso_id)
        a.titulo, a.mensaje, a.sistema = dto.titulo.strip(), dto.mensaje.strip(), dto.sistema.strip()
        a.palabras_clave = (dto.palabras_clave or "").strip() or None
        a.areas = ",".join(str(i) for i in dto.area_ids) or None
        a.mostrar_publico, a.proxima_novedad = dto.mostrar_publico, dto.proxima_novedad
        a.ticket_maestro_id = self._maestro(dto.ticket_maestro_id, dto.ticket_maestro)
        a.fecha_actualizacion = utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.AVISO_GENERAL, "aviso", a.id, {"operacion": "editar"})
        return a

    def actualizar(self, aviso_id: int, dto, ctx: Contexto) -> m.AvisoGeneral:
        from app.application.services.ticket_service import ROLES_ATIENDEN, TicketService

        a = self.get(aviso_id)
        if a.estado == "RESUELTO":
            raise ReglaNegocio("El aviso ya está resuelto")
        u, ahora = ctx.usuario, utcnow()
        a.estado, a.fecha_actualizacion = dto.estado, ahora
        a.proxima_novedad = None if dto.estado == "RESUELTO" else (dto.proxima_novedad or a.proxima_novedad)
        self.session.add(m.AvisoActualizacion(aviso_id=a.id, estado=dto.estado, texto=dto.texto.strip(), usuario_id=u.id, fecha=ahora))
        resueltos = 0
        if dto.estado == "RESUELTO":
            a.fin = ahora
            if dto.resolver_tickets:
                svc = TicketService(self.session)
                ids = {f.ticket_id for f in self.afectados(a.id) if f.ticket_id} | ({a.ticket_maestro_id} if a.ticket_maestro_id else set())
                for tid in ids:
                    t = self.session.get(m.Ticket, tid)
                    if t is None or t.eliminado or t.estado not in {e.value for e in ESTADOS_ABIERTOS} or t.estado == Estado.POR_APROBAR:
                        continue
                    if t.responsable_id is None and u.rol.codigo in ROLES_ATIENDEN:
                        svc._asignar(t, u, u, "MANUAL", f"Resuelto con el aviso {a.codigo}", ctx, ahora)
                    svc._agregar_comentario(t, u, f"Resuelto junto con el aviso general «{a.titulo}»: {dto.texto.strip()}", False,
                                            "COMENTARIO", None, ahora)
                    svc._aplicar_estado(t, Estado(t.estado), Estado.RESUELTO, u, ctx, ahora,
                                        motivo=f"Resuelto junto con el aviso general «{a.titulo}»")
                    resueltos += 1
        if dto.avisar:
            self._avisar_afectados(a, dto.texto.strip())
        self.auditoria.registrar(ctx, AccionAuditoria.AVISO_GENERAL, "aviso", a.id,
                                 {"operacion": "actualizar", "estado": dto.estado, "tickets_resueltos": resueltos, "avisar": dto.avisar})
        self.session.flush()
        return a

    def _avisar_afectados(self, a: m.AvisoGeneral, texto: str) -> None:
        personas = [f.usuario for f in self.afectados(a.id) if f.usuario.activo and f.usuario.correo.lower() not in cuentas_sistema()]
        if not personas:
            return
        resuelto = a.estado == "RESUELTO"
        titulo = f"{'Resuelto' if resuelto else 'Novedad'}: {a.titulo}"
        self.notif.notificar(personas, "AVISO_GENERAL", titulo, texto, None, "INFO" if resuelto else "AVISO")
        ahora = utcnow()
        url = f"{settings.APP_URL.rstrip('/')}/dashboard"
        cuerpo = (f"<p>Hola,</p><p>{'Se resolvió' if resuelto else 'Hay una novedad sobre'} el aviso <b>{html.escape(a.titulo)}</b> "
                  f"({html.escape(a.sistema)}), que usted marcó como «me afecta».</p>"
                  f"<p style='padding:12px;background:#F4F8FC;border-radius:8px'>{html.escape(texto)}</p>"
                  f"<p>Estado: <b>{ESTADOS[a.estado]}</b> · desde {fecha_local(a.inicio)}"
                  + (f" hasta {fecha_local(a.fin)} ({duracion(a.inicio, a.fin)})" if a.fin else "") + "</p>"
                  f"<p><a href='{url}'>Abrir la Mesa de Servicios</a></p>")
        for p in personas:
            self.session.add(m.ColaCorreo(para=p.correo, asunto=f"[{a.codigo}] {titulo}"[:250], cuerpo_html=plantilla_base(cuerpo),
                                          plantilla="AVISO_GENERAL", estado="PENDIENTE", proximo_intento=ahora, fecha_creacion=ahora))

    # ============================================================ afectados
    def _afectar(self, a: m.AvisoGeneral, u: m.Usuario, comentario: str | None, ticket_id: int | None, ahora: datetime) -> m.AvisoAfectado:
        f = self.session.get(m.AvisoAfectado, (a.id, u.id))
        if f is None:
            f = m.AvisoAfectado(aviso_id=a.id, usuario_id=u.id, comentario=comentario, ticket_id=ticket_id, fecha=ahora)
            self.session.add(f)
        else:
            f.comentario = comentario or f.comentario
            f.ticket_id = f.ticket_id or ticket_id
        return f

    def me_afecta(self, aviso_id: int, comentario: str | None, ctx: Contexto) -> m.AvisoGeneral:
        a = self.get(aviso_id)
        if a.estado == "RESUELTO":
            raise ReglaNegocio("Este aviso ya se resolvió")
        if a not in self.activos(ctx.usuario):
            raise NoEncontrado("Aviso no encontrado")
        self._afectar(a, ctx.usuario, (comentario or "").strip() or None, None, utcnow())
        self.session.flush()
        return a

    def ya_no_afecta(self, aviso_id: int, ctx: Contexto) -> None:
        f = self.session.get(m.AvisoAfectado, (aviso_id, ctx.usuario.id))
        if f is not None and f.ticket_id is None:
            self.session.delete(f)
            self.session.flush()

    def vincular_ticket(self, aviso_id: int, t: m.Ticket, solicitante: m.Usuario) -> None:
        a = self.session.get(m.AvisoGeneral, aviso_id)
        if a is None or a.estado == "RESUELTO":
            return
        self._afectar(a, solicitante, None, t.id, utcnow())
        self.session.add(m.TicketHistorial(ticket_id=t.id, accion="AVISO", campo="aviso", valor_nuevo=a.codigo,
                                           detalle=f"Parte del aviso general «{a.titulo}»"[:500], fecha=utcnow()))
        self.session.flush()

    # ============================================================ constancia
    def constancia_pdf(self, aviso_id: int, ctx: Contexto) -> tuple[str, bytes]:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        a = self.get(aviso_id)
        empresa = CatalogoRepository(self.session).configuracion().get("empresa.nombre", "ADUCORP")
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                                title=f"Constancia {a.codigo}")
        e = getSampleStyleSheet()
        texto = lambda x: Paragraph(html.escape(str(x)), e["BodyText"])  # noqa: E731
        partes = []
        try:
            from pathlib import Path

            logo = Path(__file__).resolve().parents[2] / "assets" / "logo-aducorp.png"
            if logo.exists():
                partes.append(Image(str(logo), width=4.2 * cm, height=1.6 * cm, kind="proportional"))
        except Exception:   # el logo es opcional
            pass
        partes += [Spacer(1, 8), Paragraph(f"Constancia de interrupción de servicio · {a.codigo}", e["Title"]),
                   Paragraph(html.escape(empresa), e["Heading3"]), Spacer(1, 6)]
        datos = [["Sistema afectado", a.sistema], ["Descripción", a.titulo], ["Inicio", f"{fecha_local(a.inicio)} (hora Ecuador)"],
                 ["Fin", f"{fecha_local(a.fin)} (hora Ecuador)" if a.fin else "En curso"], ["Duración", duracion(a.inicio, a.fin)],
                 ["Personas afectadas registradas", str(self._conteos(a.id)[0])]]
        tabla = Table([[texto(k), texto(v)] for k, v in datos], colWidths=[5.5 * cm, 11 * cm])
        tabla.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF5FC")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CFD8E3")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        partes += [tabla, Spacer(1, 14), Paragraph("Actualizaciones", e["Heading3"])]
        filas = [["Fecha", "Etapa", "Detalle"]] + [
            [texto(fecha_local(x.fecha)), texto(ESTADOS[x.estado]), texto(x.texto)] for x in self.actualizaciones(a.id)]
        t2 = Table(filas, colWidths=[3.2 * cm, 3.3 * cm, 10 * cm], repeatRows=1)
        t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10203C")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CFD8E3")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        partes += [t2, Spacer(1, 18),
                   Paragraph(f"Emitida el {fecha_local(utcnow())} por {html.escape(ctx.usuario.nombre)} desde la Mesa de Servicios.", e["Italic"])]
        doc.build(partes)
        self.auditoria.registrar(ctx, AccionAuditoria.EXPORTACION, "aviso", a.id, {"constancia": a.codigo})
        return f"constancia-{a.codigo}.pdf", buf.getvalue()
