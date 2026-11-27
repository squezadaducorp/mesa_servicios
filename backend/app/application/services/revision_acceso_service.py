"""Revisión de accesos y bajas por inactividad (ISO 27001, mejora 38; controles A.5.15, A.5.18 y A.8.2).

- Campaña trimestral (meses de ``accesos.meses_revision``, por defecto marzo, junio, septiembre y diciembre):
  el worker la abre el día 1 con una foto de cada cuenta activa (rol, último ingreso y alertas).
  La revisa el Coordinador de Sistemas (``accesos.revisor_correo``): marca Mantener, Ajustar o Dar de baja cada cuenta.
  Los jefes directos ya no revisan accesos (siguen aprobando solicitudes del catálogo). Si el correo del revisor no
  corresponde a una cuenta activa, las cuentas quedan para TI (cualquier administrador).
- TI aprueba la campaña: las bajas se aplican (la cuenta se desactiva, nunca se borra) y el acta en PDF
  se envía a ``accesos.informe_correo`` como evidencia para la auditoría.
- Bajas automáticas: tras ``accesos.dias_inactividad`` días sin entrar, con aviso ``accesos.dias_aviso_baja``
  días antes a la persona y a su jefe. Quedan fuera las cuentas técnicas, la cuenta de emergencia,
  ``accesos.excluidos`` y quien está de vacaciones o con permiso registrado.
"""
from __future__ import annotations

import html
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Permiso, Rol
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, RefreshTokenRepository

CONFIG = {
    "accesos.revisor_correo": ("squezada@aducorp.com.ec", "Correo del Coordinador de Sistemas, que revisa todos los accesos en la campaña trimestral"),
    "accesos.informe_correo": ("squezada@aducorp.com.ec", "Correo que recibe el acta de la revisión de accesos y el aviso de bajas por inactividad"),
    "accesos.meses_revision": ("3,6,9,12", "Meses en que se abre la revisión trimestral de accesos (día 1), separados por coma"),
    "accesos.dias_plazo": ("15", "Días que tiene el Coordinador de Sistemas para revisar los accesos"),
    "accesos.dias_alerta": ("60", "Días sin ingresar a partir de los cuales la revisión marca la cuenta"),
    "accesos.bajas_automaticas": ("si", "Desactivar las cuentas que no ingresan en los días configurados (si/no)"),
    "accesos.dias_inactividad": ("90", "Días sin ingresar tras los que se desactiva la cuenta"),
    "accesos.dias_aviso_baja": ("7", "Días de anticipación del aviso de baja por inactividad"),
    "accesos.excluidos": ("", "Correos que nunca se desactivan por inactividad (cuentas de servicio), separados por coma"),
}
DECISIONES = ("MANTENER", "AJUSTAR", "BAJA")
ALERTAS = {
    "INACTIVO": "Más de {dias} días sin ingresar",
    "NUNCA": "Nunca ingresó",
    "ADMIN": "Rol con privilegios de administración",
    "SIN_2FA": "Sin verificación en dos pasos",
    "SUPERVISOR_SIN_EQUIPO": "Supervisor sin personal a cargo",
    "SIN_JEFE": "Sin jefe directo registrado",
    "EMERGENCIA": "Cuenta de emergencia",
}
ROLES_ADMIN = {Rol.SUPER_ADMIN, Rol.ADMIN_MESA}


def _si(v: str | None) -> bool:
    return (v or "").strip().lower() in ("si", "sí", "true", "1", "s")


def _lista(v: str | None) -> list[str]:
    return [c.strip().lower() for c in (v or "").replace(";", ",").split(",") if c.strip()]


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def _local(d: datetime | None, formato: str = "%d/%m/%Y") -> str:
    if d is None:
        return "—"
    return d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime(formato)


class RevisionAccesoService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ------------------------------------------------------------ configuración
    def config(self) -> dict[str, str]:
        guardada = CatalogoRepository(self.session).configuracion()
        return {k: guardada.get(k, defecto) for k, (defecto, _) in CONFIG.items()}

    def _entero(self, clave: str) -> int:
        try:
            return max(0, int(self.config()[clave]))
        except ValueError:
            return int(CONFIG[clave][0])

    @staticmethod
    def es_admin(u: m.Usuario) -> bool:
        return Permiso.USUARIO_ADMINISTRAR in u.permisos

    def _excluidos(self) -> set[str]:
        from app.application.services.dos_pasos_service import DosPasosService
        from app.application.services.notificacion_service import cuentas_sistema

        return cuentas_sistema() | set(DosPasosService(self.session).politica()["exentos"]) | set(_lista(self.config()["accesos.excluidos"]))

    def _correo(self, para: str | list[str], asunto: str, cuerpo: str, plantilla: str, adjunto: tuple[str, bytes] | None = None) -> None:
        from app.application.services.notificacion_service import cuentas_sistema
        from app.infrastructure.email.smtp import plantilla_base

        destinos = [c for c in ([para] if isinstance(para, str) else para) if c and c.lower() not in cuentas_sistema()]
        if not destinos:
            return
        self.session.add(m.ColaCorreo(
            para=", ".join(dict.fromkeys(destinos))[:500], asunto=asunto[:250], cuerpo_html=plantilla_base(cuerpo), plantilla=plantilla,
            estado="PENDIENTE", proximo_intento=utcnow(), fecha_creacion=utcnow(),
            adjunto_nombre=adjunto[0] if adjunto else None, adjunto=adjunto[1] if adjunto else None,
        ))

    def revisor(self) -> m.Usuario | None:
        """Cuenta activa del Coordinador de Sistemas que revisa los accesos (None: lo revisa TI)."""
        correo = (self.config()["accesos.revisor_correo"] or "").strip().lower()
        if not correo:
            return None
        return self.session.scalar(select(m.Usuario).where(
            func.lower(m.Usuario.correo) == correo, m.Usuario.activo == True, m.Usuario.eliminado == False))

    def _cuentas(self) -> list[m.Usuario]:
        excluidas = _sistema()   # buzón y formulario: no son personas
        return [u for u in self.session.scalars(
            select(m.Usuario).where(m.Usuario.activo == True, m.Usuario.eliminado == False).order_by(m.Usuario.nombre)).unique()
            if u.correo.lower() not in excluidas]

    # ------------------------------------------------------------ campañas
    @staticmethod
    def periodo(ahora: datetime) -> str:
        local = ahora.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.ZONA_HORARIA))
        return f"{local:%Y-%m}"

    def _alertas(self, u: m.Usuario, ahora: datetime, con_equipo: set[int], exentos: set[str]) -> list[str]:
        from app.application.services.dos_pasos_service import DosPasosService

        dias = self._entero("accesos.dias_alerta")
        a = []
        if u.ultimo_login is None:
            if (ahora - (u.fecha_creacion or ahora)).days >= 14:
                a.append("NUNCA")
        elif dias and (ahora - u.ultimo_login).days >= dias:
            a.append("INACTIVO")
        if u.rol.codigo in ROLES_ADMIN:
            a.append("ADMIN")
        if u.correo.lower() in exentos:
            a.append("EMERGENCIA")
        elif not u.dosf_metodo and DosPasosService(self.session).exigida(u):
            a.append("SIN_2FA")
        if u.rol.codigo == Rol.SUPERVISOR and u.id not in con_equipo:
            a.append("SUPERVISOR_SIN_EQUIPO")
        if not u.supervisor_id:
            a.append("SIN_JEFE")
        return a

    def abrir(self, ctx: Contexto | None = None, ahora: datetime | None = None) -> m.RevisionAcceso:
        ahora = ahora or utcnow()
        periodo = self.periodo(ahora)
        if self.session.scalar(select(m.RevisionAcceso.id).where(m.RevisionAcceso.periodo == periodo)):
            raise ReglaNegocio(f"Ya existe la revisión de accesos de {periodo}")
        if self.session.scalar(select(m.RevisionAcceso.id).where(m.RevisionAcceso.estado == "ABIERTA")):
            raise ReglaNegocio("Hay una revisión de accesos abierta: apruébela antes de abrir otra")
        r = m.RevisionAcceso(periodo=periodo, estado="ABIERTA", fecha_creacion=ahora,
                             fecha_limite=ahora + timedelta(days=self._entero("accesos.dias_plazo") or 15),
                             creada_por=getattr(ctx.usuario, "id", None) if ctx else None)
        self.session.add(r)
        self.session.flush()
        cuentas = self._cuentas()
        con_equipo = {u.supervisor_id for u in cuentas if u.supervisor_id}
        con_equipo |= set(self.session.scalars(select(m.Categoria.supervisor_id).where(m.Categoria.supervisor_id.is_not(None))))
        exentos = set(_lista(",".join(self._exentos())))
        revisor = self.revisor()
        for u in cuentas:
            # jefe_id guarda quién revisa: el Coordinador de Sistemas (su propia cuenta la revisa otro administrador)
            quien = revisor if revisor is not None and revisor.id != u.id else None
            self.session.add(m.RevisionAccesoItem(
                revision_id=r.id, usuario_id=u.id, jefe_id=quien.id if quien else None, rol=u.rol.nombre[:100],
                ultimo_login=u.ultimo_login, alertas=",".join(self._alertas(u, ahora, con_equipo, exentos)) or None))
        self.session.flush()
        self.auditoria.registrar(ctx or Contexto(ip="worker"), AccionAuditoria.REVISION_ACCESO_ABIERTA, "revision_acceso", r.id,
                                 {"periodo": periodo, "cuentas": len(cuentas)})
        self._avisar_revisor(r, recordatorio=False)
        return r

    def _exentos(self) -> list[str]:
        from app.application.services.dos_pasos_service import DosPasosService

        return list(DosPasosService(self.session).politica()["exentos"])

    def items(self, revision_id: int) -> list[m.RevisionAccesoItem]:
        return list(self.session.scalars(
            select(m.RevisionAccesoItem).where(m.RevisionAccesoItem.revision_id == revision_id)
            .order_by(m.RevisionAccesoItem.jefe_id, m.RevisionAccesoItem.id)).unique())

    def _avisar_revisor(self, r: m.RevisionAcceso, recordatorio: bool) -> int:
        por_jefe: dict[int | None, list[m.RevisionAccesoItem]] = {}
        for i in self.items(r.id):
            if i.decision is None:
                por_jefe.setdefault(i.jefe_id, []).append(i)
        url = f"{settings.APP_URL}/cumplimiento"
        enviados = 0
        for jefe_id, lista in por_jefe.items():
            if jefe_id is None:
                continue   # sin revisor asignado: las revisa TI desde la Mesa
            jefe = lista[0].jefe
            filas = "".join(f"<li>{html.escape(i.usuario.nombre)} · {html.escape(i.rol)}</li>" for i in lista[:30])
            mas = f"<li>… y {len(lista) - 30} más</li>" if len(lista) > 30 else ""
            titulo = "Recordatorio: revise" if recordatorio else "Revise"
            cuerpo = (f"<p>Hola {html.escape(jefe.nombre)}:</p>"
                      f"<p>Como Coordinador de Sistemas, le corresponde la revisión trimestral de accesos ({r.periodo}). "
                      f"Confirme si estas {len(lista)} cuentas deben seguir con su acceso a la Mesa de Servicios tal como está:</p>"
                      f"<ul>{filas}{mas}</ul>"
                      f"<p>Tiene hasta el <b>{_local(r.fecha_limite)}</b>. Le toma un par de minutos: "
                      f"<a href=\"{url}\">abrir la revisión de accesos</a>.</p>"
                      "<p style='font-size:12px;color:#5A6577'>Esta revisión es un control de la norma ISO 27001: "
                      "nadie debe conservar accesos que ya no necesita.</p>")
            self._correo(jefe.correo, f"{titulo} los accesos de la Mesa de Servicios ({r.periodo})", cuerpo, "REVISION_ACCESO")
            enviados += 1
        return enviados

    def listar(self) -> list[dict]:
        filas = self.session.execute(
            select(m.RevisionAccesoItem.revision_id, func.count(), func.count(m.RevisionAccesoItem.decision))
            .group_by(m.RevisionAccesoItem.revision_id)).all()
        conteo = {rid: (total, hechas) for rid, total, hechas in filas}
        return [self._resumen(r, *conteo.get(r.id, (0, 0)))
                for r in self.session.scalars(select(m.RevisionAcceso).order_by(m.RevisionAcceso.fecha_creacion.desc())).unique()]

    def _resumen(self, r: m.RevisionAcceso, total: int, hechas: int) -> dict:
        return {"id": r.id, "periodo": r.periodo, "estado": r.estado, "fecha_creacion": iso(r.fecha_creacion),
                "fecha_limite": iso(r.fecha_limite), "fecha_aprobacion": iso(r.fecha_aprobacion),
                "aprobada_por": r.aprobador.nombre if r.aprobador else None, "observacion": r.observacion,
                "total": total, "revisadas": hechas}

    def _item(self, i: m.RevisionAccesoItem) -> dict:
        dias = self._entero("accesos.dias_alerta")
        return {"id": i.id, "usuario_id": i.usuario_id, "nombre": i.usuario.nombre, "correo": i.usuario.correo,
                "cargo": i.usuario.cargo, "area": i.usuario.area.nombre if i.usuario.area else None, "rol": i.rol,
                "jefe_id": i.jefe_id, "jefe": i.jefe.nombre if i.jefe else None, "ultimo_login": iso(i.ultimo_login),
                "alertas": [{"codigo": c, "texto": ALERTAS.get(c, c).format(dias=dias)} for c in (i.alertas or "").split(",") if c],
                "decision": i.decision, "comentario": i.comentario, "decidido_por": i.decisor.nombre if i.decisor else None,
                "fecha_decision": iso(i.fecha_decision), "aplicado": i.aplicado, "activo": i.usuario.activo}

    def detalle(self, revision_id: int, u: m.Usuario) -> dict:
        r = self.session.get(m.RevisionAcceso, revision_id)
        if r is None:
            raise NoEncontrado("Revisión de accesos no encontrada")
        todos = self.items(r.id)
        visibles = todos if self.es_admin(u) else [i for i in todos if i.jefe_id == u.id]
        if not visibles and not self.es_admin(u):
            raise Prohibido("La revisión de accesos la hace el Coordinador de Sistemas")
        return {**self._resumen(r, len(todos), sum(1 for i in todos if i.decision)), "items": [self._item(i) for i in visibles]}

    def pendientes(self, u: m.Usuario) -> dict:
        """Lo que le toca revisar a esta persona en la campaña abierta (para el menú y el aviso)."""
        r = self.session.scalar(select(m.RevisionAcceso).where(m.RevisionAcceso.estado == "ABIERTA"))
        if r is None:
            return {"revision_id": None, "pendientes": 0}
        stmt = select(func.count()).select_from(m.RevisionAccesoItem).where(
            m.RevisionAccesoItem.revision_id == r.id, m.RevisionAccesoItem.decision.is_(None))
        if not self.es_admin(u):
            stmt = stmt.where(m.RevisionAccesoItem.jefe_id == u.id)
        else:
            stmt = stmt.where(m.RevisionAccesoItem.jefe_id.is_(None))
        mios = self.session.scalar(select(func.count()).select_from(m.RevisionAccesoItem).where(
            m.RevisionAccesoItem.revision_id == r.id, m.RevisionAccesoItem.jefe_id == u.id))
        return {"revision_id": r.id if (mios or self.es_admin(u)) else None, "periodo": r.periodo,
                "fecha_limite": iso(r.fecha_limite), "pendientes": self.session.scalar(stmt) or 0}

    def decidir(self, item_id: int, decision: str, comentario: str | None, ctx: Contexto) -> dict:
        u = ctx.usuario
        i = self.session.get(m.RevisionAccesoItem, item_id)
        if i is None:
            raise NoEncontrado("Persona no encontrada en la revisión")
        r = self.session.get(m.RevisionAcceso, i.revision_id)
        if r.estado != "ABIERTA":
            raise ReglaNegocio("La revisión ya fue aprobada")
        if i.jefe_id != u.id and not self.es_admin(u):
            raise Prohibido("Solo el Coordinador de Sistemas o TI pueden revisar este acceso")
        if decision not in DECISIONES:
            raise ReglaNegocio("Decisión no válida")
        comentario = (comentario or "").strip() or None
        if decision != "MANTENER" and not comentario:
            raise ReglaNegocio("Indique qué hay que ajustar o por qué se da de baja")
        if decision == "BAJA" and i.usuario_id == u.id:
            raise ReglaNegocio("No puede dar de baja su propia cuenta")
        i.decision, i.comentario, i.decidido_por, i.fecha_decision = decision, comentario, u.id, utcnow()
        self.auditoria.registrar(ctx, AccionAuditoria.REVISION_ACCESO_DECISION, "usuario", i.usuario_id,
                                 {"revision": r.periodo, "decision": decision, "comentario": comentario})
        self.session.flush()
        return self._item(i)

    def aprobar(self, revision_id: int, observacion: str | None, ctx: Contexto) -> dict:
        r = self.session.get(m.RevisionAcceso, revision_id)
        if r is None:
            raise NoEncontrado("Revisión de accesos no encontrada")
        if r.estado != "ABIERTA":
            raise ReglaNegocio("La revisión ya fue aprobada")
        items = self.items(r.id)
        faltan = [i for i in items if i.decision is None]
        if faltan:
            raise ReglaNegocio(f"Faltan {len(faltan)} personas por revisar: márquelas antes de aprobar")
        ahora = utcnow()
        bajas = 0
        for i in items:
            if i.decision == "BAJA" and i.usuario.activo and i.usuario_id != ctx.usuario.id:
                self._desactivar(i.usuario, ahora)
                i.aplicado, bajas = True, bajas + 1
        r.estado, r.aprobada_por, r.fecha_aprobacion = "APROBADA", ctx.usuario.id, ahora
        r.observacion = (observacion or "").strip()[:1000] or None
        self.session.flush()
        self.session.refresh(r)
        ajustes = [i for i in items if i.decision == "AJUSTAR"]
        self.auditoria.registrar(ctx, AccionAuditoria.REVISION_ACCESO_APROBADA, "revision_acceso", r.id,
                                 {"periodo": r.periodo, "cuentas": len(items), "bajas": bajas, "ajustes": len(ajustes)})
        pdf = self.acta_pdf(r.id)
        lista = "".join(f"<li><b>{html.escape(i.usuario.nombre)}</b>: {html.escape(i.comentario or '')}</li>" for i in ajustes)
        cuerpo = (f"<p>Se aprobó la revisión de accesos <b>{r.periodo}</b>.</p>"
                  f"<p>Cuentas revisadas: <b>{len(items)}</b><br>Dadas de baja: <b>{bajas}</b><br>Con ajustes pendientes: <b>{len(ajustes)}</b></p>"
                  + (f"<p>Ajustes que TI debe hacer:</p><ul>{lista}</ul>" if ajustes else "")
                  + "<p>Adjuntamos el acta en PDF. Guárdela como evidencia del control A.5.18 de ISO 27001.</p>")
        self._correo(_lista(self.config()["accesos.informe_correo"]), f"Acta de revisión de accesos {r.periodo}", cuerpo,
                     "ACTA_REVISION_ACCESO", (f"revision-accesos-{r.periodo}.pdf", pdf))
        return self.detalle(r.id, ctx.usuario)

    def _desactivar(self, u: m.Usuario, ahora: datetime) -> None:
        u.activo, u.fecha_actualizacion = False, ahora
        RefreshTokenRepository(self.session).revocar_usuario(u.id, ahora)

    # ------------------------------------------------------------ acta PDF
    def acta_pdf(self, revision_id: int) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        r = self.session.get(m.RevisionAcceso, revision_id)
        if r is None:
            raise NoEncontrado("Revisión de accesos no encontrada")
        items = self.items(r.id)
        normal = ParagraphStyle("n", fontName="Helvetica", fontSize=8, leading=10)
        titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#0B2E59"))
        sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#5A6577"))
        e = lambda v: html.escape(v or "")   # noqa: E731
        decisiones = {d: sum(1 for i in items if i.decision == d) for d in DECISIONES}
        partes = [
            Paragraph("Acta de revisión de accesos · Mesa de Servicios ADUCORP", titulo),
            Paragraph(f"Periodo {r.periodo} · abierta el {_local(r.fecha_creacion)} · "
                      + (f"aprobada el {_local(r.fecha_aprobacion, '%d/%m/%Y %H:%M')} por {e(r.aprobador.nombre if r.aprobador else '')}"
                         if r.fecha_aprobacion else "pendiente de aprobación")
                      + " · Control ISO 27001 A.5.18", sub),
            Spacer(1, 0.3 * cm),
            Paragraph(f"Cuentas revisadas: <b>{len(items)}</b> · Mantener: <b>{decisiones['MANTENER']}</b> · "
                      f"Ajustar: <b>{decisiones['AJUSTAR']}</b> · Dar de baja: <b>{decisiones['BAJA']}</b>", normal),
        ]
        if r.observacion:
            partes.append(Paragraph(f"Observación: {e(r.observacion)}", normal))
        partes.append(Spacer(1, 0.3 * cm))
        dias = self._entero("accesos.dias_alerta")
        datos = [["Persona", "Rol", "Revisor", "Último ingreso", "Alertas", "Decisión", "Comentario", "Revisó"]]
        for i in items:
            alertas = ", ".join(ALERTAS.get(c, c).format(dias=dias) for c in (i.alertas or "").split(",") if c)
            decision = {"MANTENER": "Mantener", "AJUSTAR": "Ajustar", "BAJA": "Dar de baja"}.get(i.decision or "", "Pendiente")
            if i.decision == "BAJA" and i.aplicado:
                decision += " (aplicada)"
            datos.append([Paragraph(f"{e(i.usuario.nombre)}<br/><font color='#5A6577'>{e(i.usuario.correo)}</font>", normal),
                          Paragraph(e(i.rol), normal), Paragraph(e(i.jefe.nombre if i.jefe else "TI"), normal),
                          Paragraph(_local(i.ultimo_login) if i.ultimo_login else "Nunca", normal), Paragraph(e(alertas), normal),
                          Paragraph(decision, normal), Paragraph(e(i.comentario), normal),
                          Paragraph(f"{e(i.decisor.nombre if i.decisor else '')}<br/>{_local(i.fecha_decision)}" if i.decisor else "", normal)])
        tabla = Table(datos, colWidths=[5 * cm, 2.6 * cm, 3.2 * cm, 2.2 * cm, 4.6 * cm, 2.4 * cm, 4.2 * cm, 3 * cm], repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2E59")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DAE1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
        ]))
        partes.append(tabla)
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm,
                          bottomMargin=1.2 * cm, title=f"Revisión de accesos {r.periodo}").build(partes)
        return buf.getvalue()

    # ------------------------------------------------------------ inactividad
    def _ausentes(self, ahora: datetime) -> set[int]:
        return set(self.session.scalars(select(m.UsuarioAusencia.usuario_id).where(
            m.UsuarioAusencia.estado.in_(("PROGRAMADA", "ACTIVA")), m.UsuarioAusencia.desde <= ahora, m.UsuarioAusencia.hasta >= ahora)))

    def inactivos(self, ahora: datetime | None = None) -> list[dict]:
        """Cuentas que se acercan a la baja automática o ya la cumplen (vista previa para TI)."""
        ahora = ahora or utcnow()
        limite, aviso = self._entero("accesos.dias_inactividad"), self._entero("accesos.dias_aviso_baja")
        if not limite:
            return []
        excluidos, ausentes = self._excluidos(), self._ausentes(ahora)
        filas = []
        for u in self._cuentas():
            ref = u.ultimo_login or u.fecha_creacion or ahora
            dias = (ahora - ref).days
            if dias < max(0, limite - aviso - 14):
                continue
            motivo = ("Excluida" if u.correo.lower() in excluidos else "De vacaciones o permiso" if u.id in ausentes else None)
            filas.append({"id": u.id, "nombre": u.nombre, "correo": u.correo, "rol": u.rol.nombre,
                          "ultimo_login": iso(u.ultimo_login), "dias": dias, "aviso_enviado": iso(u.aviso_inactividad),
                          "baja_el": iso(ref + timedelta(days=limite)), "excluida": motivo})
        return sorted(filas, key=lambda f: -f["dias"])

    def procesar_inactividad(self, ahora: datetime) -> dict:
        cfg = self.config()
        limite, aviso = self._entero("accesos.dias_inactividad"), self._entero("accesos.dias_aviso_baja")
        if not _si(cfg["accesos.bajas_automaticas"]) or not limite:
            return {"omitido": "bajas automáticas apagadas"}
        excluidos, ausentes = self._excluidos(), self._ausentes(ahora)
        informe = _lista(cfg["accesos.informe_correo"])
        avisos = bajas = 0
        ctx = Contexto(ip="worker", equipo="baja por inactividad")
        for u in self._cuentas():
            if u.correo.lower() in excluidos or u.id in ausentes:
                continue
            ref = u.ultimo_login or u.fecha_creacion or ahora
            dias = (ahora - ref).days
            jefe = self.session.get(m.Usuario, u.supervisor_id) if u.supervisor_id else None
            jefe_correo = jefe.correo if jefe and jefe.activo and jefe.id != u.id else None
            if dias >= limite - aviso and (u.aviso_inactividad is None or u.aviso_inactividad < ref):
                u.aviso_inactividad = ahora
                fecha = _local(ahora + timedelta(days=max(aviso, limite - dias)))
                cuerpo = (f"<p>Hola {html.escape(u.nombre)}:</p><p>Hace {dias} días que no entra a la Mesa de Servicios. "
                          f"Por seguridad, las cuentas sin uso se desactivan a los {limite} días.</p>"
                          f"<p>Si todavía la necesita, <b>entre antes del {fecha}</b> en <a href=\"{settings.APP_URL}\">{settings.APP_URL}</a> "
                          "y no tendrá que hacer nada más.</p>")
                self._correo([u.correo] + ([jefe_correo] if jefe_correo else []),
                             f"Su cuenta de la Mesa de Servicios se desactivará el {fecha}", cuerpo, "AVISO_INACTIVIDAD")
                avisos += 1
            elif dias >= limite and u.aviso_inactividad and u.aviso_inactividad >= ref \
                    and (ahora - u.aviso_inactividad).days >= aviso:
                self._desactivar(u, ahora)
                self.auditoria.registrar(ctx, AccionAuditoria.BAJA_INACTIVIDAD, "usuario", u.id, {"dias_sin_ingresar": dias}, usuario=u)
                cuerpo = (f"<p>Se desactivó la cuenta de <b>{html.escape(u.nombre)}</b> ({html.escape(u.correo)}) en la Mesa de Servicios "
                          f"porque no ingresó en {dias} días.</p><p>Si la persona todavía la necesita, TI puede reactivarla en "
                          "Administración › Usuarios.</p>")
                self._correo(informe + ([jefe_correo] if jefe_correo else []), f"Cuenta desactivada por inactividad: {u.nombre}",
                             cuerpo, "BAJA_INACTIVIDAD")
                bajas += 1
        return {"avisos": avisos, "bajas": bajas}

    # ------------------------------------------------------------ worker
    def procesar(self, ahora: datetime | None = None) -> dict:
        """Una vez al día: abre la campaña del trimestre, recuerda al revisor y aplica las bajas por inactividad."""
        ahora = ahora or utcnow()
        hoy = _local(ahora, "%Y-%m-%d")
        marca = self.session.get(m.Configuracion, "accesos.ultimo_proceso")
        if marca is not None and marca.valor == hoy:
            return {"omitido": "ya se procesó hoy"}
        if marca is None:
            marca = m.Configuracion(clave="accesos.ultimo_proceso", valor=hoy,
                                    descripcion="Último día en que el worker revisó accesos e inactividad (no editar)")
            self.session.add(marca)
        marca.valor, marca.fecha_actualizacion = hoy, ahora
        r: dict = {}
        mes = int(_local(ahora, "%m"))
        meses = {int(x) for x in _lista(self.config()["accesos.meses_revision"]) if x.isdigit()}
        abierta = self.session.scalar(select(m.RevisionAcceso).where(m.RevisionAcceso.estado == "ABIERTA"))
        if mes in meses and abierta is None and not self.session.scalar(
                select(m.RevisionAcceso.id).where(m.RevisionAcceso.periodo == self.periodo(ahora))):
            r["revision"] = self.abrir(None, ahora).periodo
        elif abierta is not None and not abierta.recordatorio and ahora >= abierta.fecha_limite - timedelta(days=3):
            abierta.recordatorio = True
            r["recordatorios"] = self._avisar_revisor(abierta, recordatorio=True)
        r["inactividad"] = self.procesar_inactividad(ahora)
        return r


def _sistema() -> set[str]:
    from app.application.services.notificacion_service import cuentas_sistema

    return cuentas_sistema()
