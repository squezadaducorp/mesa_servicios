"""Panel gerencial y su PDF mensual (mejora 32).

- Pantalla «Panel gerencial»: indicadores del mes con la variación frente al mes anterior, tickets de los últimos 6 meses
  y cumplimiento del SLA por área. Filtro por mes y por área.
- PDF de 3 páginas con el diseño de Aducorp: 1) resumen ejecutivo, indicadores, gráficos y «lo que necesita atención de
  Gerencia»; 2) SLA por área y prioridad, satisfacción con comentarios y tickets más largos; 3) cambios implementados,
  problemas abiertos y, si están en uso, proveedores y horas de trabajo por área.
- Envío automático por correo el primer día hábil (o el día 1) del mes a la hora configurada, con el PDF del mes anterior.
  La configuración vive en la tabla `configuracion` (panel.envio_*); cada envío queda en `panel_envios`.
"""
from __future__ import annotations

import calendar
import html
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.doughnut import Doughnut
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.export_service import LOGO
from app.application.services.reportes_programados_service import Periodo, ReportesProgramadosService
from app.application.services.sla_service import cargar_calendario
from app.application.services.ticket_service import limites_dia_utc
from app.core.config import settings
from app.core.security import utcnow
from app.domain import recurrencia as rc
from app.domain.enums import AccionAuditoria, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base
from app.infrastructure.repositories.repositorios import CatalogoRepository

TZ = ZoneInfo(settings.ZONA_HORARIA)
MESES = rc.MESES
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
SECCIONES = ("indicadores", "tendencia", "sla_area", "satisfaccion", "problemas", "cambios", "proveedores", "horas")
NOMBRE_SECCION = {"indicadores": "Indicadores", "tendencia": "Tendencia 6 meses", "sla_area": "SLA por área", "satisfaccion": "Satisfacción",
                  "problemas": "Problemas abiertos", "cambios": "Cambios del mes", "proveedores": "Proveedores", "horas": "Horas por área"}
CLAVES = {"activo": "panel.envio_activo", "destinatarios": "panel.envio_para", "cuando": "panel.envio_cuando", "hora": "panel.envio_hora",
          "secciones": "panel.envio_secciones", "comentario": "panel.comentario"}
NAVY, AZUL, CELESTE, NARANJA, VERDE, ROJO, GRIS = "#10203C", "#1367AC", "#70A9CE", "#F5A623", "#2E7D32", "#C62828", "#5A6577"
META_SLA = 95.0


def nombre_mes(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1].capitalize()} {anio}"


def duracion(minutos: float | None) -> str:
    if minutos is None:
        return "-"
    minutos = int(round(minutos))
    h, mi = divmod(minutos, 60)
    if h >= 48:
        return f"{h // 24} días" if h % 24 < 6 else f"{h // 24} d {h % 24} h"
    return f"{h} h {mi:02d} min" if h else f"{mi} min"


def coma(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


class PanelService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ============================================================ permisos y config
    @staticmethod
    def puede_ver(u: m.Usuario) -> bool:
        return u.tiene(Permiso.PANEL_VER)

    @staticmethod
    def puede_configurar(u: m.Usuario) -> bool:
        return u.tiene(Permiso.PANEL_VER) and u.tiene(Permiso.REPORTES_PROGRAMAR)

    def _exigir(self, u: m.Usuario) -> None:
        if not self.puede_ver(u):
            raise Prohibido("El panel gerencial es para Gerencia y la administración de la Mesa")

    def config(self) -> dict:
        c = CatalogoRepository(self.session).configuracion()
        secciones = [x for x in (c.get(CLAVES["secciones"]) or ",".join(SECCIONES)).split(",") if x in SECCIONES]
        return {"activo": (c.get(CLAVES["activo"]) or "no").lower() in ("si", "sí", "true", "1"),
                "destinatarios": [x.strip() for x in (c.get(CLAVES["destinatarios"]) or "").replace(";", ",").split(",") if x.strip()],
                "cuando": c.get(CLAVES["cuando"]) or "PRIMER_HABIL", "hora": c.get(CLAVES["hora"]) or "08:00",
                "secciones": secciones, "comentario": c.get(CLAVES["comentario"]) or ""}

    def _poner(self, clave: str, valor: str, u: m.Usuario | None) -> None:
        fila = self.session.get(m.Configuracion, clave)
        if fila is None:
            fila = m.Configuracion(clave=clave, valor=valor, descripcion="Panel gerencial (envío mensual del PDF)")
            self.session.add(fila)
        fila.valor, fila.fecha_actualizacion, fila.actualizado_por = valor, utcnow(), u.id if u else None

    def guardar_config(self, dto, ctx: Contexto) -> dict:
        u = ctx.usuario
        if not self.puede_configurar(u):
            raise Prohibido("No tiene permiso para programar el envío del panel")
        if dto.activo and not dto.destinatarios:
            raise ReglaNegocio("Indique al menos un destinatario")
        self._poner(CLAVES["activo"], "si" if dto.activo else "no", u)
        self._poner(CLAVES["destinatarios"], ", ".join(str(x) for x in dto.destinatarios), u)
        self._poner(CLAVES["cuando"], dto.cuando, u)
        self._poner(CLAVES["hora"], dto.hora, u)
        self._poner(CLAVES["secciones"], ",".join(dict.fromkeys(dto.secciones)), u)
        self._poner(CLAVES["comentario"], (dto.comentario or "").strip(), u)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.PANEL_ENVIO_CONFIGURADO, "configuracion", None,
                                 {"activo": dto.activo, "destinatarios": ", ".join(str(x) for x in dto.destinatarios)})
        return self.config()

    # ============================================================ datos
    @staticmethod
    def periodo(anio: int, mes: int) -> Periodo:
        return Periodo(date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1]))

    def _resueltos(self, p: Periodo, areas: list[int] | None) -> list[m.Ticket]:
        T = m.Ticket
        ini, fin = limites_dia_utc(p.desde, p.hasta)
        stmt = select(T).where(T.eliminado == False, T.fecha_resolucion >= ini, T.fecha_resolucion < fin)
        if areas:
            stmt = stmt.where(T.area_id.in_(areas))
        return list(self.session.scalars(stmt).unique())

    def _recibidos(self, p: Periodo, areas: list[int] | None) -> int:
        T = m.Ticket
        ini, fin = limites_dia_utc(p.desde, p.hasta)
        stmt = select(func.count(T.id)).where(T.eliminado == False, T.fecha_creacion >= ini, T.fecha_creacion < fin)
        if areas:
            stmt = stmt.where(T.area_id.in_(areas))
        return self.session.scalar(stmt) or 0

    @staticmethod
    def _tiempo_medio(tickets: list[m.Ticket]) -> float | None:
        v = [t.minutos_resolucion for t in tickets if t.minutos_resolucion is not None]
        return sum(v) / len(v) if v else None

    def datos(self, anio: int, mes: int, area_id: int | None = None, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        areas = [area_id] if area_id else None
        p = self.periodo(anio, mes)
        ant = p.anterior()
        rp = ReportesProgramadosService(self.session)
        d, previo = rp.datos(p, areas, ahora), rp.datos(ant, areas, ahora)
        res, res_prev = self._resueltos(p, areas), self._resueltos(ant, areas)
        tm, tm_prev = self._tiempo_medio(res), self._tiempo_medio(res_prev)

        # Tendencia: tickets recibidos en los últimos 6 meses (incluido el del panel)
        serie = []
        a, mm = anio, mes
        for _ in range(6):
            serie.append({"anio": a, "mes": mm, "etiqueta": MESES_CORTOS[mm - 1], "tickets": self._recibidos(self.periodo(a, mm), areas)})
            a, mm = (a - 1, 12) if mm == 1 else (a, mm - 1)
        serie.reverse()

        # Tickets por tipo (categoría): las 3 más pedidas + otros
        cats = Counter(t.categoria.nombre for t in d["tickets_nuevos"]).most_common()
        total = d["nuevos"] or 1
        tipos = [{"nombre": n, "cantidad": c, "pct": round(100 * c / total)} for n, c in cats[:3]]
        if len(cats) > 3:
            otros = sum(c for _, c in cats[3:])
            tipos.append({"nombre": "Otros", "cantidad": otros, "pct": round(100 * otros / total)})

        # SLA por área y prioridad (tickets resueltos en el mes con SLA evaluado)
        matriz: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        prioridades: dict[str, int] = {}
        for t in res:
            if t.sla_excluido or t.sla_resolucion_cumplido is None:
                continue
            fila = matriz[t.area.nombre if t.area else "Sin área"]
            prioridades[t.prioridad.nombre] = t.prioridad.orden
            fila[t.prioridad.nombre][1] += 1
            fila[t.prioridad.nombre][0] += int(bool(t.sla_resolucion_cumplido) and not t.sla_incumplido)
        orden_prio = sorted(prioridades, key=lambda n: prioridades[n])
        sla_prioridad = [{"area": area, "valores": {pr: (round(100 * v[0] / v[1]) if v[1] else None) for pr, v in fila.items()}}
                         for area, fila in sorted(matriz.items())]

        # Satisfacción: comentarios destacados del mes
        ini, fin = limites_dia_utc(p.desde, p.hasta)
        E = m.TicketEncuesta
        enc = [e for e in self.session.scalars(select(E).where(E.fecha >= ini, E.fecha < fin, E.comentario.is_not(None)))
               if (e.comentario or "").strip()]
        if areas:
            ids = {t.id for t in d["tickets_nuevos"]} | {t.id for t in res}
            enc = [e for e in enc if e.ticket_id in ids]
        mejores = sorted([e for e in enc if e.calificacion >= 4], key=lambda e: (-e.calificacion, e.fecha))[:3]
        peores = sorted([e for e in enc if e.calificacion <= 2], key=lambda e: (e.calificacion, e.fecha))[:3]
        comentarios = [{"calificacion": e.calificacion, "comentario": e.comentario.strip()[:300]} for e in mejores + peores]

        largos = sorted((t for t in res if t.minutos_resolucion is not None), key=lambda t: -t.minutos_resolucion)[:5]

        # Cambios y problemas
        C, A = m.Cambio, m.CambioAprobacion
        implementados = list(self.session.scalars(select(C).where(C.fecha_implementado >= ini, C.fecha_implementado < fin)
                                                  .order_by(C.fecha_implementado)).unique())
        pend_ger = list(self.session.scalars(select(C).join(A, A.cambio_id == C.id).where(A.rol == "GERENCIA", A.estado == "PENDIENTE")).unique())
        from app.application.services.problema_service import ABIERTOS as PRB_ABIERTOS, NOMBRE_ESTADO as PRB_NOMBRE, ProblemaService

        P = m.Problema
        psvc = ProblemaService(self.session)
        problemas = [{"numero": x.numero, "titulo": x.titulo, "estado": PRB_NOMBRE[x.estado], "incidentes": psvc._conteo(x.id),
                      "dias": (ahora - x.fecha_creacion).days, "cambio": x.cambio.numero if x.cambio else None,
                      "ventana": x.cambio.ventana_inicio if x.cambio else None}
                     for x in self.session.scalars(select(P).where(P.estado.in_(PRB_ABIERTOS)).order_by(P.fecha_creacion)).unique()]

        atencion = []
        for c in pend_ger[:3]:
            espera = self.session.scalar(select(func.min(A.fecha_solicitud)).where(A.cambio_id == c.id, A.estado == "PENDIENTE"))
            atencion.append({"titulo": f"Aprobar {c.numero}.", "texto": f"{c.titulo}" + (f" (espera desde el {_local(espera):%d/%m})." if espera else ".")})
        for x in sorted(problemas, key=lambda x: -x["incidentes"])[:2]:
            if x["incidentes"] >= 3 or x["dias"] >= 14:
                extra = f" Se corrige con {x['cambio']}" + (f" el {_local(x['ventana']):%d/%m}." if x["ventana"] else ".") if x["cambio"] else ""
                atencion.append({"titulo": f"Problema {x['numero']}.", "texto": f"{x['titulo']}: {x['incidentes']} incidentes, abierto hace {x['dias']} días.{extra}"})
        if d["vencidos_abiertos"]:
            atencion.append({"titulo": f"{len(d['vencidos_abiertos'])} tickets vencidos siguen abiertos.",
                             "texto": "Superaron el plazo de solución y aún no se resuelven."})

        def var_pct(a: int, b: int) -> float | None:
            return round(100 * (a - b) / b) if b else None

        sat, sat_prev = d["satisfaccion"], previo["satisfaccion"]
        datos = {
            "anio": anio, "mes": mes, "titulo": nombre_mes(anio, mes), "mes_anterior": MESES[ant.desde.month - 1],
            "area": self.session.get(m.Area, area_id).nombre if area_id and self.session.get(m.Area, area_id) else None,
            "kpis": {
                "recibidos": d["nuevos"], "recibidos_var": var_pct(d["nuevos"], previo["nuevos"]),
                "resueltos": d["resueltos"], "abiertos": d["abiertos"],
                "cumplimiento": d["cumplimiento"],
                "cumplimiento_var": round(d["cumplimiento"] - previo["cumplimiento"], 1) if d["cumplimiento"] is not None and previo["cumplimiento"] is not None else None,
                "satisfaccion": sat, "satisfaccion_var": round(sat - sat_prev, 1) if sat is not None and sat_prev is not None else None,
                "encuestas": d["encuestas"],
                "tiempo_medio_min": round(tm) if tm is not None else None,
                "tiempo_medio_var": round(tm - tm_prev) if tm is not None and tm_prev is not None else None,
            },
            "serie": serie, "tipos": tipos,
            "areas": [{"area": x["area"], "pct": x["pct"], "nuevos": x["nuevos"], "resueltos": x["resueltos"], "vencidos": x["vencidos"]}
                      for x in d["areas"]],
            "prioridades": orden_prio, "sla_prioridad": sla_prioridad, "comentarios": comentarios,
            "largos": [{"numero": t.numero, "asunto": t.asunto, "area": t.area.nombre if t.area else "", "duracion": duracion(t.minutos_resolucion),
                        "responsable": t.responsable.nombre if t.responsable else ""} for t in largos],
            "cambios": [{"numero": c.numero, "titulo": c.titulo, "resultado": c.resultado, "fecha": _iso(c.fecha_implementado)} for c in implementados],
            "problemas": problemas, "atencion": atencion, "meta_sla": META_SLA,
        }
        datos.update(self.extras(p, areas, ahora))
        return datos

    def extras(self, p: Periodo, areas: list[int] | None, ahora: datetime) -> dict:
        """Secciones de proveedores y horas de trabajo (mejoras 31 y 33). Vacías si esas mejoras no están instaladas."""
        return {"proveedores": [], "horas_area": [], "horas_total": None}

    # ============================================================ PDF
    def resumen_texto(self, d: dict, comentario: str | None) -> str:
        k = d["kpis"]
        partes = [f"En {MESES[d['mes'] - 1]} la Mesa recibió <b>{k['recibidos']} tickets</b>"]
        if k["recibidos_var"] is not None and k["recibidos_var"] != 0:
            partes.append(f" ({abs(k['recibidos_var'])} % {'más' if k['recibidos_var'] > 0 else 'menos'} que {d['mes_anterior']})")
        partes.append(f" y resolvió {k['resueltos']}.")
        if k["cumplimiento"] is not None:
            partes.append(f" Cumplió el <b>{coma(k['cumplimiento'], 0) if k['cumplimiento'] == int(k['cumplimiento']) else coma(k['cumplimiento'])} %</b> de los plazos")
            partes.append(" (meta 95 %)." if k["cumplimiento"] < META_SLA else ", sobre la meta del 95 %.")
        if k["satisfaccion"] is not None:
            partes.append(f" La satisfacción {'subió' if (k['satisfaccion_var'] or 0) > 0 else 'bajó' if (k['satisfaccion_var'] or 0) < 0 else 'quedó'}"
                          f" {'a' if k['satisfaccion_var'] else 'en'} <b>{coma(k['satisfaccion'])} de 5</b>.")
        if comentario:
            partes.append(" " + html.escape(comentario.strip()))
        return "".join(partes)

    def pdf(self, d: dict, secciones: list[str] | None = None, comentario: str | None = None, generado: datetime | None = None) -> bytes:
        secciones = list(secciones or SECCIONES)
        generado = (generado or utcnow()).replace(tzinfo=timezone.utc).astimezone(TZ)
        buf = io.BytesIO()
        titulo = "Informe de la Mesa de Servicios"
        sub = d["titulo"] + (f" · {d['area']}" if d["area"] else " · para Gerencia General")
        dominio = settings.APP_URL.split("//")[-1].rstrip("/")
        W, H = A4
        M = 1.6 * cm

        def cabecera(c, doc):
            c.saveState()
            if doc.page == 1:
                c.setFillColor(colors.HexColor(NAVY))
                c.rect(0, H - 3.4 * cm, W, 3.4 * cm, fill=1, stroke=0)
                if LOGO.exists():   # logotipo horizontal sobre una placa blanca para que se lea sobre el azul
                    c.setFillColor(colors.white)
                    c.roundRect(M, H - 2.45 * cm, 4.3 * cm, 1.3 * cm, 6, fill=1, stroke=0)
                    c.drawImage(str(LOGO), M + 0.25 * cm, H - 2.2 * cm, width=3.8 * cm, height=0.8 * cm, mask="auto", preserveAspectRatio=True)
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(M + 4.9 * cm, H - 1.6 * cm, titulo)
                c.setFillColor(colors.HexColor(CELESTE))
                c.setFont("Helvetica", 11)
                c.drawString(M + 4.9 * cm, H - 2.3 * cm, sub)
                c.setFillColor(colors.HexColor("#C9D6EA"))
                c.setFont("Helvetica", 8.5)
                c.drawRightString(W - M, H - 1.55 * cm, "ADUCORP CIA. LTDA.")
                c.drawRightString(W - M, H - 2.0 * cm, f"Generado {generado:%d/%m/%Y %H:%M}")
            else:
                c.setFillColor(colors.HexColor(NAVY))
                c.setFont("Helvetica-Bold", 10)
                c.drawString(M, H - 1.2 * cm, f"{titulo} · {d['titulo']}")
                c.setStrokeColor(colors.HexColor("#E3E8F0"))
                c.line(M, H - 1.45 * cm, W - M, H - 1.45 * cm)
            c.setStrokeColor(colors.HexColor("#E3E8F0"))
            c.line(M, 1.5 * cm, W - M, 1.5 * cm)
            c.setFillColor(colors.HexColor("#8A94A6"))
            c.setFont("Helvetica", 8)
            c.drawString(M, 1.0 * cm, f"Mesa de Servicios ADUCORP · {dominio}")
            c.drawRightString(W - M, 1.0 * cm, f"Página {doc.page}")
            c.restoreState()

        doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=2 * cm,
                              title=f"Panel Mesa {d['titulo']}", author="Mesa de Servicios ADUCORP")
        doc.addPageTemplates([
            PageTemplate("portada", [Frame(M, 2 * cm, W - 2 * M, H - 3.4 * cm - 2.6 * cm, id="f1", leftPadding=0, rightPadding=0)], onPage=cabecera),
            PageTemplate("resto", [Frame(M, 2 * cm, W - 2 * M, H - 2 * cm - 2.2 * cm, id="f2", leftPadding=0, rightPadding=0)], onPage=cabecera),
        ])
        st = {
            "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor(NAVY), spaceBefore=8, spaceAfter=6),
            "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=14, textColor=colors.HexColor("#1F2A3D"), alignment=TA_LEFT),
            "s": ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor(GRIS)),
            "k": ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor(NAVY)),
            "c": ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#1F2A3D")),
        }
        ancho = W - 2 * M
        k = d["kpis"]
        e: list = [NextPageTemplate("resto")]

        def kpi(nombre: str, valor: str, var: str, color: str) -> Table:
            t = Table([[Paragraph(nombre, st["s"])], [Paragraph(f'<b>{valor}</b>', st["k"])],
                       [Paragraph(f'<font color="{color}"><b>{var or "&nbsp;"}</b></font>', st["s"])]], colWidths=[ancho / 4 - 8],
                      rowHeights=[16, 26, 16])
            t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E3E8F0")),
                                   ("LINEABOVE", (0, 0), (-1, 0), 2.5, colors.HexColor(AZUL)), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            return t

        def signo(v, sufijo="", invertir=False, dec=0):
            if v is None:
                return "", GRIS
            bueno = (v < 0) if invertir else (v > 0)
            txt = ("+" if v > 0 else "-" if v < 0 else "") + (coma(abs(v), dec) if dec else f"{abs(v):.0f}") + sufijo
            return txt, (VERDE if bueno else ROJO if v != 0 else GRIS)

        # ---------------------------------------------------------------- página 1
        e.append(Paragraph("Resumen ejecutivo", st["h"]))
        e.append(Paragraph(self.resumen_texto(d, comentario), st["p"]))
        e.append(Spacer(1, 10))
        if "indicadores" in secciones:
            v1, c1 = signo(k["recibidos_var"], f" % vs. {d['mes_anterior']}")
            v2, c2 = signo(k["cumplimiento_var"], " pts", dec=1)
            v3, c3 = signo(k["satisfaccion_var"], "", dec=1)
            v4, c4 = signo(k["tiempo_medio_var"], " min", invertir=True)
            fila = [kpi("Tickets recibidos", str(k["recibidos"]), v1, GRIS),
                    kpi("Cumplimiento SLA", f"{coma(k['cumplimiento'])} %" if k["cumplimiento"] is not None else "-", v2, c2),
                    kpi("Satisfacción", f"{coma(k['satisfaccion'])} / 5" if k["satisfaccion"] is not None else "-", v3, c3),
                    kpi("Tiempo medio de solución", duracion(k["tiempo_medio_min"]), v4, c4)]
            t = Table([fila], colWidths=[ancho / 4] * 4)
            t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
            e += [t, Spacer(1, 12)]
        if "tendencia" in secciones:
            e.append(Table([[Paragraph("Tickets por mes", st["h"]), Paragraph("Tickets por tipo", st["h"])],
                            [self._barras(d["serie"], ancho / 2 - 10), self._dona(d["tipos"], k["recibidos"], ancho / 2 - 10)]],
                           colWidths=[ancho / 2, ancho / 2],
                           style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        e.append(Spacer(1, 8))
        aten = [Paragraph("Lo que necesita atención de Gerencia", st["h"])]
        if d["atencion"]:
            for x in d["atencion"]:
                aten.append(Table([["", Paragraph(f"<b>{html.escape(x['titulo'])}</b> {html.escape(x['texto'])}", st["p"])]], colWidths=[6, ancho - 6],
                                  style=[("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E8590C")), ("LEFTPADDING", (1, 0), (1, 0), 8),
                                         ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
                aten.append(Spacer(1, 5))
        else:
            aten.append(Paragraph("Nada pendiente: no hay aprobaciones, problemas largos ni tickets vencidos que requieran a Gerencia.", st["p"]))
        e.append(KeepTogether(aten))

        # ---------------------------------------------------------------- página 2
        e.append(PageBreak())
        if "sla_area" in secciones:
            e.append(Paragraph("Cumplimiento del SLA por área y prioridad", st["h"]))
            if d["sla_prioridad"]:
                cab = ["Área"] + d["prioridades"] + ["Total"]
                tot = {x["area"]: x["pct"] for x in d["areas"]}
                filas = [cab] + [[x["area"]] + [self._pct(x["valores"].get(pr)) for pr in d["prioridades"]] + [self._pct(tot.get(x["area"]))]
                                 for x in d["sla_prioridad"]]
                e.append(self._tabla(filas, [ancho * 0.34] + [ancho * 0.66 / (len(cab) - 1)] * (len(cab) - 1), st, colorear=True))
            else:
                e.append(Paragraph("Sin tickets resueltos con SLA evaluado en el mes.", st["p"]))
            e.append(Spacer(1, 10))
        if "satisfaccion" in secciones:
            e.append(Paragraph("Satisfacción", st["h"]))
            if k["satisfaccion"] is not None:
                e.append(Paragraph(f"<b>{coma(k['satisfaccion'])} de 5</b> en {k['encuestas']} encuestas.", st["p"]))
                for x in d["comentarios"]:
                    e.append(Paragraph(f'<font color="{VERDE if x["calificacion"] >= 4 else ROJO}"><b>{x["calificacion"]}/5</b></font> '
                                       f'«{html.escape(x["comentario"])}»', st["c"]))
                    e.append(Spacer(1, 3))
            else:
                e.append(Paragraph("Sin encuestas respondidas en el mes.", st["p"]))
            e.append(Spacer(1, 10))
        e.append(Paragraph("Tickets que más tardaron en resolverse", st["h"]))
        if d["largos"]:
            e.append(self._tabla([["Ticket", "Asunto", "Área", "Responsable", "Tiempo"]] +
                                 [[x["numero"], Paragraph(html.escape(x["asunto"]), st["c"]), x["area"], x["responsable"], x["duracion"]] for x in d["largos"]],
                                 [ancho * 0.18, ancho * 0.38, ancho * 0.15, ancho * 0.17, ancho * 0.12], st))
        else:
            e.append(Paragraph("Sin tickets resueltos en el mes.", st["p"]))

        # ---------------------------------------------------------------- página 3
        e.append(PageBreak())
        if "cambios" in secciones:
            e.append(Paragraph("Cambios implementados", st["h"]))
            if d["cambios"]:
                res = {"EXITOSO": "Exitoso", "CON_PROBLEMAS": "Con problemas", "REVERTIDO": "Revertido"}
                e.append(self._tabla([["Cambio", "Descripción", "Fecha", "Resultado"]] +
                                     [[x["numero"], Paragraph(html.escape(x["titulo"]), st["c"]), _local_iso(x["fecha"]), res.get(x["resultado"] or "", "En revisión")]
                                      for x in d["cambios"]], [ancho * 0.18, ancho * 0.52, ancho * 0.13, ancho * 0.17], st))
            else:
                e.append(Paragraph("No se implementaron cambios en el mes.", st["p"]))
            e.append(Spacer(1, 10))
        if "problemas" in secciones:
            e.append(Paragraph("Problemas abiertos", st["h"]))
            if d["problemas"]:
                e.append(self._tabla([["Problema", "Descripción", "Estado", "Incidentes", "Días"]] +
                                     [[x["numero"], Paragraph(html.escape(x["titulo"]), st["c"]), x["estado"], str(x["incidentes"]), str(x["dias"])]
                                      for x in d["problemas"]], [ancho * 0.18, ancho * 0.44, ancho * 0.18, ancho * 0.11, ancho * 0.09], st))
            else:
                e.append(Paragraph("No hay problemas abiertos.", st["p"]))
            e.append(Spacer(1, 10))
        e += self.pdf_extras(d, secciones, st, ancho)
        doc.build(e)
        return buf.getvalue()

    def pdf_extras(self, d: dict, secciones: list[str], st: dict, ancho: float) -> list:
        """Proveedores y horas por área (mejoras 31 y 33)."""
        return []

    @staticmethod
    def _pct(v) -> str:
        return "-" if v is None else f"{coma(v, 0) if v == int(v) else coma(v)} %"

    @staticmethod
    def _tabla(filas: list[list], anchos: list[float], st: dict, colorear: bool = False) -> Table:
        t = Table(filas, colWidths=anchos, repeatRows=1)
        estilo = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FB")]),
                  ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#E3E8F0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        if colorear:
            for r, fila in enumerate(filas[1:], 1):
                for c, v in enumerate(fila[1:], 1):
                    if isinstance(v, str) and v.endswith("%"):
                        n = float(v.replace(" %", "").replace(",", "."))
                        estilo.append(("TEXTCOLOR", (c, r), (c, r), colors.HexColor(VERDE if n >= META_SLA else "#B57400" if n >= 90 else ROJO)))
        t.setStyle(TableStyle(estilo))
        return t

    @staticmethod
    def _barras(serie: list[dict], ancho: float) -> Drawing:
        alto = 150
        dr = Drawing(ancho, alto)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 6, 18, ancho - 12, alto - 36
        bc.data = [[x["tickets"] for x in serie]]
        bc.categoryAxis.categoryNames = [x["etiqueta"] for x in serie]
        bc.categoryAxis.labels.fontName, bc.categoryAxis.labels.fontSize = "Helvetica", 8
        bc.categoryAxis.labels.fillColor = colors.HexColor(GRIS)
        bc.categoryAxis.strokeColor = colors.HexColor("#E3E8F0")
        bc.valueAxis.visible = False
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max([x["tickets"] for x in serie] + [1]) * 1.18
        bc.bars.strokeColor = None
        bc.barSpacing, bc.groupSpacing = 0, 8
        bc.bars[0].fillColor = colors.HexColor(CELESTE)
        bc.bars[(0, len(serie) - 1)].fillColor = colors.HexColor(AZUL)
        bc.barLabelFormat = "%d"
        bc.barLabels.fontName, bc.barLabels.fontSize, bc.barLabels.nudge = "Helvetica-Bold", 8, 7
        bc.barLabels.fillColor = colors.HexColor(NAVY)
        dr.add(bc)
        return dr

    @staticmethod
    def _dona(tipos: list[dict], total: int, ancho: float) -> Drawing:
        alto = 150
        dr = Drawing(ancho, alto)
        paleta = [AZUL, CELESTE, NARANJA, "#97A3B6"]
        if not tipos:
            dr.add(String(10, alto / 2, "Sin tickets en el mes", fontName="Helvetica", fontSize=9, fillColor=colors.HexColor(GRIS)))
            return dr
        d = Doughnut()
        d.x, d.y, d.width, d.height = 4, 14, 110, 110
        d.data = [max(x["cantidad"], 0.0001) for x in tipos]
        d.labels = None
        d.innerRadiusFraction = 0.55
        d.strokeColor = colors.white
        d.slices.strokeWidth = 1
        for i in range(len(tipos)):
            d.slices[i].fillColor = colors.HexColor(paleta[i % len(paleta)])
        dr.add(d)
        dr.add(String(59, 64, str(total), fontName="Helvetica-Bold", fontSize=14, fillColor=colors.HexColor(NAVY), textAnchor="middle"))
        y = 108
        for i, x in enumerate(tipos):
            dr.add(Rect(124, y - 1, 7, 7, fillColor=colors.HexColor(paleta[i % len(paleta)]), strokeColor=None))
            nombre = x["nombre"] if len(x["nombre"]) <= 24 else x["nombre"][:23] + "…"
            dr.add(String(136, y, f"{nombre} · {x['pct']} %", fontName="Helvetica", fontSize=8, fillColor=colors.HexColor("#1F2A3D")))
            y -= 18
        return dr

    # ============================================================ envío por correo
    def archivo(self, anio: int, mes: int) -> str:
        return f"Panel-Mesa-{MESES[mes - 1].capitalize()}-{anio}.pdf"

    def enviar(self, anio: int, mes: int, para: list[str], *, prueba_de: m.Usuario | None = None, ahora: datetime | None = None) -> m.PanelEnvio:
        ahora = ahora or utcnow()
        cfg = self.config()
        d = self.datos(anio, mes, ahora=ahora)
        contenido = self.pdf(d, cfg["secciones"], cfg["comentario"], ahora)
        archivo = self.archivo(anio, mes)
        k = d["kpis"]
        base = settings.APP_URL.rstrip("/")
        cuerpo = (f'<p>Adjunto el informe de la Mesa de Servicios de <b>{html.escape(d["titulo"])}</b>.</p>'
                  f'<ul><li>Tickets recibidos: <b>{k["recibidos"]}</b></li>'
                  f'<li>Cumplimiento del SLA: <b>{self._pct(k["cumplimiento"])}</b></li>'
                  f'<li>Satisfacción: <b>{coma(k["satisfaccion"]) + " de 5" if k["satisfaccion"] is not None else "sin encuestas"}</b></li></ul>'
                  + (f'<p>{html.escape(cfg["comentario"])}</p>' if cfg["comentario"] else "")
                  + f'<p style="text-align:center;margin-top:18px"><a href="{base}/panel" style="background:#1367AC;color:#fff;padding:10px 18px;'
                    f'border-radius:6px;text-decoration:none;font-weight:600">Ver el panel en la Mesa</a></p>')
        destino = ", ".join(para)
        correo = m.ColaCorreo(para=destino[:500], asunto=f"{'[PRUEBA] ' if prueba_de else ''}Informe de la Mesa de Servicios · {d['titulo']}",
                              cuerpo_html=plantilla_base(cuerpo), plantilla="PANEL_MENSUAL", estado="PENDIENTE", proximo_intento=ahora,
                              fecha_creacion=ahora, adjunto_nombre=archivo, adjunto=contenido)
        self.session.add(correo)
        self.session.flush()
        envio = m.PanelEnvio(periodo=f"{anio}-{mes:02d}", archivo=archivo, fecha=ahora, destinatarios=destino[:1000], es_prueba=prueba_de is not None,
                             correo_id=correo.id, enviado_por=prueba_de.id if prueba_de else None)
        self.session.add(envio)
        self.session.flush()
        return envio

    def enviar_prueba(self, anio: int, mes: int, ctx: Contexto) -> m.PanelEnvio:
        if not self.puede_configurar(ctx.usuario):
            raise Prohibido("No tiene permiso para enviar el panel")
        return self.enviar(anio, mes, [ctx.usuario.correo], prueba_de=ctx.usuario)

    def envios(self, limite: int = 12) -> list[dict]:
        E = m.PanelEnvio
        salida = []
        for e in self.session.scalars(select(E).order_by(E.fecha.desc()).limit(limite)):
            correo = self.session.get(m.ColaCorreo, e.correo_id) if e.correo_id else None
            salida.append({"id": e.id, "periodo": e.periodo, "archivo": e.archivo, "fecha": _iso(e.fecha), "destinatarios": e.destinatarios,
                           "es_prueba": e.es_prueba, "estado": correo.estado if correo else None})
        return salida

    def pdf_envio(self, envio_id: int, u: m.Usuario) -> tuple[str, bytes]:
        self._exigir(u)
        e = self.session.get(m.PanelEnvio, envio_id)
        correo = self.session.get(m.ColaCorreo, e.correo_id) if e and e.correo_id else None
        if e is None or correo is None or not correo.adjunto:
            raise NoEncontrado("El PDF de ese envío ya no está disponible")
        return e.archivo, correo.adjunto

    def dia_envio(self, anio: int, mes: int, cuando: str) -> date:
        d = date(anio, mes, 1)
        if cuando == "DIA_1":
            return d
        cal = cargar_calendario(self.session)
        for _ in range(15):
            if cal.tramos_del_dia(d):
                return d
            d += timedelta(days=1)
        return date(anio, mes, 1)

    def proximo_envio(self, ahora: datetime | None = None) -> str | None:
        cfg = self.config()
        if not cfg["activo"]:
            return None
        local = (ahora or utcnow()).replace(tzinfo=timezone.utc).astimezone(TZ)
        hh, mm = (int(x) for x in cfg["hora"].split(":"))
        anio, mes = local.year, local.month
        for _ in range(2):
            dia = self.dia_envio(anio, mes, cfg["cuando"])
            momento = datetime(dia.year, dia.month, dia.day, hh, mm, tzinfo=TZ)
            ant = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
            ya = self.session.scalar(select(m.PanelEnvio.id).where(m.PanelEnvio.periodo == f"{ant[0]}-{ant[1]:02d}", m.PanelEnvio.es_prueba == False))
            if momento >= local or not ya:
                return momento.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
            anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        return None

    def procesar(self, ahora: datetime | None = None) -> dict:
        """Lo llama el worker: envía el PDF del mes anterior el día y hora configurados (una sola vez por mes)."""
        ahora = ahora or utcnow()
        cfg = self.config()
        if not cfg["activo"] or not cfg["destinatarios"]:
            return {"enviado": False}
        local = ahora.replace(tzinfo=timezone.utc).astimezone(TZ)
        dia = self.dia_envio(local.year, local.month, cfg["cuando"])
        hh, mm = (int(x) for x in cfg["hora"].split(":"))
        if local.date() < dia or (local.date() == dia and (local.hour, local.minute) < (hh, mm)) or (local.date() - dia).days > 6:
            return {"enviado": False}
        anio, mes = (local.year - 1, 12) if local.month == 1 else (local.year, local.month - 1)
        periodo = f"{anio}-{mes:02d}"
        if self.session.scalar(select(m.PanelEnvio.id).where(m.PanelEnvio.periodo == periodo, m.PanelEnvio.es_prueba == False)):
            return {"enviado": False}
        self.enviar(anio, mes, cfg["destinatarios"], ahora=ahora)
        if cfg["comentario"]:   # el comentario de TI es de ese mes: se limpia para no repetirlo el próximo
            self._poner(CLAVES["comentario"], "", None)
        return {"enviado": True, "periodo": periodo}


def _local(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc).astimezone(TZ)


def _local_iso(v: str | None) -> str:
    if not v:
        return ""
    return _local(datetime.fromisoformat(v.rstrip("Z"))).strftime("%d/%m/%Y")
