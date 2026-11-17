"""Reportes programados: resumen por correo para gerencia (abiertos, vencidos, cumplimiento del SLA por área)."""
from __future__ import annotations

import html
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import mejoras2 as s
from app.application.services import export_service as ex
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.sla_service import cargar_calendario
from app.application.services.ticket_service import limites_dia_utc
from app.core.config import settings
from app.core.security import utcnow
from app.domain import recurrencia as rc
from app.domain.enums import ESTADOS_ABIERTOS, AccionAuditoria, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base

NAVY, AZUL = "#10203C", "#1367AC"
META_SLA = 95.0
MESES = rc.MESES


@dataclass
class Periodo:
    desde: date
    hasta: date

    @property
    def texto(self) -> str:
        if self.desde == self.hasta:
            return f"{self.desde:%d/%m/%Y}"
        if self.desde.month == self.hasta.month:
            return f"del {self.desde.day} al {self.hasta.day} de {MESES[self.hasta.month - 1]} de {self.hasta.year}"
        return f"del {self.desde:%d/%m/%Y} al {self.hasta:%d/%m/%Y}"

    def anterior(self) -> "Periodo":
        dias = (self.hasta - self.desde).days + 1
        if self.desde.day == 1 and dias >= 28:   # mes calendario
            fin = self.desde - timedelta(days=1)
            return Periodo(fin.replace(day=1), fin)
        return Periodo(self.desde - timedelta(days=dias), self.desde - timedelta(days=1))


def periodo_para(frecuencia: str, hoy: date) -> Periodo:
    """Periodo que cubre el envío de ``hoy``: el día anterior, la semana anterior (lun-dom) o el mes anterior."""
    if frecuencia == "DIARIA":
        ayer = hoy - timedelta(days=1)
        return Periodo(ayer, ayer)
    if frecuencia == "MENSUAL":
        fin = hoy.replace(day=1) - timedelta(days=1)
        return Periodo(fin.replace(day=1), fin)
    lunes = hoy - timedelta(days=hoy.weekday()) - timedelta(days=7)
    return Periodo(lunes, lunes + timedelta(days=6))


def _pct(ok: int, total: int) -> float | None:
    return round(100.0 * ok / total, 1) if total else None


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f} %".replace(".", ",")


def _color(v: float | None) -> str:
    if v is None:
        return "#5A6577"
    return "#2E7D32" if v >= META_SLA else "#B57400" if v >= 90 else "#C62828"


def regla(r: m.ReporteProgramado | s.ReporteEntrada, desde: date) -> rc.Regla:
    return rc.Regla(frecuencia={"DIARIA": "DIARIA", "SEMANAL": "SEMANAL", "MENSUAL": "MENSUAL"}[r.frecuencia], desde=desde, hora=r.hora,
                    dia_semana=r.dia_semana if r.frecuencia == "SEMANAL" else None,
                    dia_mes=(r.dia_mes or 1) if r.frecuencia == "MENSUAL" else None)


class ReportesProgramadosService:
    def __init__(self, session: Session):
        self.session = session
        self.tz = ZoneInfo(settings.ZONA_HORARIA)
        self.auditoria = AuditoriaService(session)
        self.cal = cargar_calendario(session)

    # ----------------------------------------------------------- calendario
    def _laborable(self, frecuencia: str):
        # El diario solo sale en días laborables; el semanal y el mensual salen aunque sea feriado.
        return (lambda d: bool(self.cal.tramos_del_dia(d))) if frecuencia == "DIARIA" else (lambda d: True)

    def calcular_proximo(self, r: m.ReporteProgramado, despues: datetime) -> datetime | None:
        hoy = despues.replace(tzinfo=timezone.utc).astimezone(self.tz).date()
        prox = rc.proxima(regla(r, hoy), despues, self._laborable(r.frecuencia), settings.ZONA_HORARIA)
        return prox[0] if prox else None

    def descripcion(self, r: m.ReporteProgramado) -> str:
        return rc.describir(regla(r, date.today()))

    def salida(self, r: m.ReporteProgramado) -> dict:
        return {
            **{k: getattr(r, k) for k in ("id", "nombre", "frecuencia", "dia_semana", "dia_mes", "hora", "adjuntar_excel", "activo",
                                          "proximo_envio", "ultimo_envio")},
            "destinatarios": [c.strip() for c in r.destinatarios.split(",") if c.strip()],
            "secciones": [x for x in r.secciones.split(",") if x],
            "areas": [int(x) for x in (r.areas or "").split(",") if x.strip().isdigit()] or None,
            "descripcion_frecuencia": self.descripcion(r),
        }

    # ------------------------------------------------------------ CRUD
    def _exigir(self, u: m.Usuario) -> None:
        if not u.tiene(Permiso.REPORTES_PROGRAMAR):
            raise Prohibido("No tiene permiso para programar reportes")

    def listar(self) -> list[m.ReporteProgramado]:
        return list(self.session.scalars(select(m.ReporteProgramado).order_by(m.ReporteProgramado.nombre)))

    def obtener(self, rid: int) -> m.ReporteProgramado:
        r = self.session.get(m.ReporteProgramado, rid)
        if r is None:
            raise NoEncontrado("Reporte no encontrado")
        return r

    def guardar(self, dto: s.ReporteEntrada, ctx: Contexto, rid: int | None = None) -> m.ReporteProgramado:
        self._exigir(ctx.usuario)
        if dto.frecuencia == "SEMANAL" and not dto.dia_semana:
            raise ReglaNegocio("Indique el día de la semana")
        if rid is None:
            r = m.ReporteProgramado(creado_por=ctx.usuario.id, fecha_creacion=utcnow())
            self.session.add(r)
        else:
            r = self.obtener(rid)
        r.nombre, r.frecuencia, r.hora = dto.nombre.strip(), dto.frecuencia, dto.hora
        r.dia_semana = dto.dia_semana if dto.frecuencia == "SEMANAL" else None
        r.dia_mes = (dto.dia_mes or 1) if dto.frecuencia == "MENSUAL" else None
        r.destinatarios = ", ".join(str(c) for c in dto.destinatarios)
        r.secciones = ",".join(dict.fromkeys(dto.secciones))
        r.areas = ",".join(str(a) for a in dto.areas) if dto.areas else None
        r.adjuntar_excel, r.activo = dto.adjuntar_excel, dto.activo
        r.proximo_envio = self.calcular_proximo(r, utcnow()) if r.activo else None
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.REPORTE_PROGRAMADO_MODIFICADO, "reporte_programado", r.id,
                                 {"nombre": r.nombre, "destinatarios": r.destinatarios, "activo": r.activo})
        return r

    def eliminar(self, rid: int, ctx: Contexto) -> None:
        self._exigir(ctx.usuario)
        r = self.obtener(rid)
        self.auditoria.registrar(ctx, AccionAuditoria.REPORTE_PROGRAMADO_MODIFICADO, "reporte_programado", r.id, {"nombre": r.nombre, "eliminado": True})
        for e in self.session.scalars(select(m.ReporteEnvio).where(m.ReporteEnvio.reporte_id == r.id)):
            self.session.delete(e)
        self.session.delete(r)

    def envios(self, rid: int, limite: int = 10) -> list[dict]:
        filas = self.session.scalars(select(m.ReporteEnvio).where(m.ReporteEnvio.reporte_id == rid)
                                     .order_by(m.ReporteEnvio.fecha.desc()).limit(limite))
        salida = []
        for e in filas:
            correo = self.session.get(m.ColaCorreo, e.correo_id) if e.correo_id else None
            salida.append({"id": e.id, "fecha": e.fecha, "periodo": e.periodo, "destinatarios": e.destinatarios, "es_prueba": e.es_prueba,
                           "estado": correo.estado if correo else None})
        return salida

    # ------------------------------------------------------------ datos
    def _tickets(self, areas: list[int] | None):
        stmt = select(m.Ticket).where(m.Ticket.eliminado == False)
        if areas:
            stmt = stmt.where(m.Ticket.area_id.in_(areas))
        return stmt

    def datos(self, p: Periodo, areas: list[int] | None = None, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        T = m.Ticket
        ini, fin = limites_dia_utc(p.desde, p.hasta)
        nuevos = list(self.session.scalars(self._tickets(areas).where(T.fecha_creacion >= ini, T.fecha_creacion < fin)).unique())
        resueltos = list(self.session.scalars(self._tickets(areas).where(T.fecha_resolucion >= ini, T.fecha_resolucion < fin)).unique())
        abiertos = list(self.session.scalars(self._tickets(areas).where(T.estado.in_(list(ESTADOS_ABIERTOS)))).unique())
        incumpl = list(self.session.scalars(
            select(m.SlaIncumplimiento).where(m.SlaIncumplimiento.tipo == "RESOLUCION", m.SlaIncumplimiento.fecha_registro >= ini,
                                              m.SlaIncumplimiento.fecha_registro < fin)))
        ids_area = {t.id: t.area_id for t in self.session.scalars(self._tickets(areas).where(T.id.in_([i.ticket_id for i in incumpl]))).unique()} if incumpl else {}
        vencidos_periodo = [i for i in incumpl if i.ticket_id in ids_area]
        evaluados = [t for t in resueltos if not t.sla_excluido and t.sla_resolucion_cumplido is not None]
        cumplidos = [t for t in evaluados if t.sla_resolucion_cumplido and not t.sla_incumplido]

        por_area: dict[int | None, dict] = defaultdict(lambda: {"nuevos": 0, "resueltos": 0, "abiertos": 0, "vencidos": 0, "ok": 0, "eval": 0})
        for t in nuevos:
            por_area[t.area_id]["nuevos"] += 1
        for t in resueltos:
            por_area[t.area_id]["resueltos"] += 1
        for t in evaluados:
            por_area[t.area_id]["eval"] += 1
        for t in cumplidos:
            por_area[t.area_id]["ok"] += 1
        for t in abiertos:
            por_area[t.area_id]["abiertos"] += 1
        for i in vencidos_periodo:
            por_area[ids_area[i.ticket_id]]["vencidos"] += 1
        nombres = {a.id: a.nombre for a in self.session.scalars(select(m.Area))}
        filas_area = sorted(
            ({"area": nombres.get(a, "Sin área"), **v, "pct": _pct(v["ok"], v["eval"])} for a, v in por_area.items()),
            key=lambda f: -f["nuevos"])

        vencidos_abiertos = sorted((t for t in abiertos if t.sla_incumplido or (t.sla_resolucion_vence and t.sla_resolucion_vence < ahora
                                                                                 and t.sla_pausa_desde is None and not t.sla_excluido)),
                                   key=lambda t: t.sla_resolucion_vence)
        categorias = Counter(t.categoria.nombre for t in nuevos).most_common(5)
        enc = list(self.session.scalars(select(m.TicketEncuesta).where(m.TicketEncuesta.fecha >= ini, m.TicketEncuesta.fecha < fin)))
        if areas:
            ids = {t.id for t in self.session.scalars(self._tickets(areas).where(T.id.in_([e.ticket_id for e in enc]))).unique()} if enc else set()
            enc = [e for e in enc if e.ticket_id in ids]
        resp: dict[str, dict] = defaultdict(lambda: {"resueltos": 0, "ok": 0, "eval": 0, "abiertos": 0})
        for t in resueltos:
            resp[t.responsable.nombre if t.responsable else "Sin asignar"]["resueltos"] += 1
        for t in evaluados:
            k = t.responsable.nombre if t.responsable else "Sin asignar"
            resp[k]["eval"] += 1
            resp[k]["ok"] += int(t in cumplidos)
        for t in abiertos:
            resp[t.responsable.nombre if t.responsable else "Sin asignar"]["abiertos"] += 1
        recurrentes = [t for t in abiertos if t.recurrente_id]
        return {
            "periodo": p, "nuevos": len(nuevos), "resueltos": len(resueltos), "abiertos": len(abiertos), "vencidos": len(vencidos_periodo),
            "cumplimiento": _pct(len(cumplidos), len(evaluados)), "areas": filas_area, "vencidos_abiertos": vencidos_abiertos,
            "categorias": categorias, "encuestas": len(enc),
            "satisfaccion": round(sum(e.calificacion for e in enc) / len(enc), 1) if enc else None,
            "notas_bajas": sum(1 for e in enc if e.calificacion <= 2),
            "responsables": sorted(({"responsable": k, **v, "pct": _pct(v["ok"], v["eval"])} for k, v in resp.items()), key=lambda f: -f["resueltos"]),
            "recurrentes": recurrentes, "tickets_nuevos": nuevos,
        }

    # ------------------------------------------------------------ correo
    def _kpi(self, titulo: str, valor: str, sub: str, color: str) -> str:
        return (f'<td align="center" style="border:1px solid #E3E8F0;border-radius:8px;padding:10px 4px;width:20%">'
                f'<div style="font-size:11px;color:#5A6577">{titulo}</div>'
                f'<div style="font-size:24px;font-weight:800;color:{color};line-height:1.3">{valor}</div>'
                f'<div style="font-size:11px;color:#5A6577">{sub}</div></td>')

    @staticmethod
    def _variacion(actual: int, anterior: int) -> str:
        if anterior == 0:
            return "sin datos previos" if actual else "igual"
        d = actual - anterior
        return f"{'+' if d > 0 else '−' if d < 0 else ''}{abs(d)} vs. periodo anterior"

    def html(self, r: m.ReporteProgramado, d: dict, previo: dict | None) -> str:
        sec = set(r.secciones.split(","))
        base = settings.APP_URL.rstrip("/")
        p: Periodo = d["periodo"]
        th = 'style="text-align:left;background:#F8FAFD;color:#10203C;padding:6px 8px;font-size:12px;border-bottom:1px solid #E3E8F0"'
        td = 'style="padding:6px 8px;font-size:13px;border-bottom:1px solid #EEF1F6"'
        partes = [f'<p style="font-size:16px;font-weight:700;color:{NAVY};margin:0">{html.escape(r.nombre)}</p>'
                  f'<p style="color:#5A6577;margin:2px 0 16px">Periodo {html.escape(p.texto)}</p>']
        if "totales" in sec:
            comp = "comparacion" in sec and previo is not None
            v = (lambda k: self._variacion(d[k], previo[k])) if comp else (lambda k: "")
            partes.append('<table width="100%" cellspacing="6" cellpadding="0"><tr>'
                          + self._kpi("Tickets nuevos", str(d["nuevos"]), v("nuevos"), AZUL)
                          + self._kpi("Resueltos", str(d["resueltos"]), v("resueltos"), "#2E7D32")
                          + self._kpi("Abiertos hoy", str(d["abiertos"]), "", "#5E35B1")
                          + self._kpi("Vencidos (SLA)", str(d["vencidos"]), v("vencidos"), "#C62828")
                          + self._kpi("Cumplimiento SLA", _fmt_pct(d["cumplimiento"]), f"Meta {META_SLA:.0f} %", _color(d["cumplimiento"]))
                          + "</tr></table>")
        if "sla_area" in sec and d["areas"]:
            filas = "".join(
                f'<tr><td {td}><b>{html.escape(a["area"])}</b></td><td {td} align="right">{a["nuevos"]}</td><td {td} align="right">{a["resueltos"]}</td>'
                f'<td {td} align="right">{a["abiertos"]}</td><td {td} align="right" style="color:{"#C62828" if a["vencidos"] else "inherit"}">{a["vencidos"]}</td>'
                f'<td {td} align="right"><b style="color:{_color(a["pct"])}">{_fmt_pct(a["pct"])}</b></td></tr>' for a in d["areas"])
            partes.append(f'<p style="font-weight:700;color:{NAVY};margin:18px 0 6px">Por área</p>'
                          f'<table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #E3E8F0"><tr><th {th}>Área</th>'
                          f'<th {th}>Nuevos</th><th {th}>Resueltos</th><th {th}>Abiertos</th><th {th}>Vencidos</th><th {th}>SLA</th></tr>{filas}</table>')
        if "vencidos" in sec:
            lista = d["vencidos_abiertos"][:15]
            if lista:
                filas = "".join(
                    f'<tr><td {td}><a href="{base}/tickets/{t.id}" style="color:{AZUL};font-weight:600;text-decoration:none">{t.numero}</a></td>'
                    f'<td {td}>{html.escape(t.asunto[:70])}</td><td {td}>{html.escape(t.responsable.nombre if t.responsable else "Sin asignar")}</td>'
                    f'<td {td} align="right" style="color:#C62828">{ex._local(t.sla_resolucion_vence)}</td></tr>' for t in lista)
                mas = f'<p style="font-size:12px;color:#5A6577">y {len(d["vencidos_abiertos"]) - 15} más en el Excel adjunto.</p>' if len(d["vencidos_abiertos"]) > 15 else ""
                partes.append(f'<p style="font-weight:700;color:{NAVY};margin:18px 0 6px">Tickets vencidos que siguen abiertos ({len(d["vencidos_abiertos"])})</p>'
                              f'<table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #E3E8F0"><tr><th {th}>Ticket</th>'
                              f'<th {th}>Asunto</th><th {th}>Responsable</th><th {th}>Venció</th></tr>{filas}</table>{mas}')
            else:
                partes.append('<p style="margin:18px 0 6px;color:#2E7D32"><b>No hay tickets vencidos abiertos.</b></p>')
        cajas = []
        if "categorias" in sec and d["categorias"]:
            cajas.append("<b>Lo más pedido</b><br>" + " · ".join(f"{i}. {html.escape(n)} ({c})" for i, (n, c) in enumerate(d["categorias"], 1)))
        if "satisfaccion" in sec:
            cajas.append("<b>Satisfacción</b><br>" + (f"{d['satisfaccion']:.1f} de 5 en {d['encuestas']} encuestas · {d['notas_bajas']} notas bajas".replace(".", ",", 1)
                                                      if d["encuestas"] else "Sin encuestas en el periodo"))
        if cajas:
            partes.append('<table width="100%" cellspacing="6" cellpadding="0" style="margin-top:12px"><tr>' + "".join(
                f'<td valign="top" style="background:#F4F6FA;border-radius:8px;padding:10px 12px;font-size:13px">{c}</td>' for c in cajas) + "</tr></table>")
        if "responsables" in sec and d["responsables"]:
            filas = "".join(f'<tr><td {td}>{html.escape(x["responsable"])}</td><td {td} align="right">{x["resueltos"]}</td>'
                            f'<td {td} align="right">{x["abiertos"]}</td><td {td} align="right" style="color:{_color(x["pct"])}">{_fmt_pct(x["pct"])}</td></tr>'
                            for x in d["responsables"][:15])
            partes.append(f'<p style="font-weight:700;color:{NAVY};margin:18px 0 6px">Por responsable</p>'
                          f'<table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #E3E8F0"><tr><th {th}>Responsable</th>'
                          f'<th {th}>Resueltos</th><th {th}>Abiertos</th><th {th}>SLA</th></tr>{filas}</table>')
        if "recurrentes" in sec and d["recurrentes"]:
            partes.append(f'<p style="font-weight:700;color:{NAVY};margin:18px 0 6px">Tickets programados sin cerrar</p><p style="font-size:13px">'
                          + "<br>".join(f'{t.numero} · {html.escape(t.asunto)}' for t in d["recurrentes"][:15]) + "</p>")
        partes.append(f'<p style="text-align:center;margin-top:20px"><a href="{base}/indicadores" style="background:{AZUL};color:#fff;'
                      f'padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">Ver indicadores en la Mesa</a></p>')
        return "".join(partes)

    def excel(self, d: dict) -> bytes:
        p: Periodo = d["periodo"]
        areas = [{**a, "pct": a["pct"] if a["pct"] is not None else ""} for a in d["areas"]]
        hojas = [
            ("Por área", [("area", "Área"), ("nuevos", "Nuevos"), ("resueltos", "Resueltos"), ("abiertos", "Abiertos"),
                          ("vencidos", "Vencidos"), ("pct", "Cumplimiento SLA %")], areas),
            ("Vencidos abiertos", ex.COLUMNAS_TICKETS, [ex.fila_ticket(t) for t in d["vencidos_abiertos"]]),
            ("Tickets nuevos", ex.COLUMNAS_TICKETS, [ex.fila_ticket(t) for t in d["tickets_nuevos"]]),
            ("Por responsable", [("responsable", "Responsable"), ("resueltos", "Resueltos"), ("abiertos", "Abiertos"), ("pct", "Cumplimiento SLA %")],
             [{**x, "pct": x["pct"] if x["pct"] is not None else ""} for x in d["responsables"]]),
        ]
        return ex.excel(hojas, f"Periodo {p.texto}")

    def enviar(self, r: m.ReporteProgramado, *, ahora: datetime | None = None, prueba_para: m.Usuario | None = None) -> m.ReporteEnvio:
        ahora = ahora or utcnow()
        hoy = ahora.replace(tzinfo=timezone.utc).astimezone(self.tz).date()
        p = periodo_para(r.frecuencia, hoy)
        areas = [int(x) for x in (r.areas or "").split(",") if x.strip().isdigit()] or None
        d = self.datos(p, areas, ahora)
        previo = self.datos(p.anterior(), areas, ahora) if "comparacion" in r.secciones else None
        para = prueba_para.correo if prueba_para else r.destinatarios
        asunto = f"{'[PRUEBA] ' if prueba_para else ''}{r.nombre} · {p.texto}"
        correo = m.ColaCorreo(para=para, asunto=asunto[:250], cuerpo_html=plantilla_base(self.html(r, d, previo)), plantilla="REPORTE_PROGRAMADO",
                              estado="PENDIENTE", proximo_intento=ahora, fecha_creacion=ahora)
        if r.adjuntar_excel:
            correo.adjunto_nombre = f"{r.nombre[:60].replace(' ', '-')}-{p.desde:%Y-%m-%d}.xlsx"
            correo.adjunto = self.excel(d)
        self.session.add(correo)
        self.session.flush()
        envio = m.ReporteEnvio(reporte_id=r.id, fecha=ahora, periodo=p.texto[:100], destinatarios=para[:1000], es_prueba=prueba_para is not None,
                               correo_id=correo.id, enviado_por=prueba_para.id if prueba_para else None)
        self.session.add(envio)
        if not prueba_para:
            r.ultimo_envio = ahora
        self.session.flush()
        return envio

    def enviar_prueba(self, rid: int, ctx: Contexto) -> m.ReporteEnvio:
        self._exigir(ctx.usuario)
        return self.enviar(self.obtener(rid), prueba_para=ctx.usuario)

    def vista_previa(self, rid: int, ctx: Contexto) -> str:
        self._exigir(ctx.usuario)
        r = self.obtener(rid)
        hoy = utcnow().replace(tzinfo=timezone.utc).astimezone(self.tz).date()
        p = periodo_para(r.frecuencia, hoy)
        areas = [int(x) for x in (r.areas or "").split(",") if x.strip().isdigit()] or None
        d = self.datos(p, areas)
        return plantilla_base(self.html(r, d, self.datos(p.anterior(), areas) if "comparacion" in r.secciones else None))

    def procesar(self, ahora: datetime | None = None) -> dict:
        """Envía los reportes cuya hora ya llegó. Lo llama el worker."""
        ahora = ahora or utcnow()
        R = m.ReporteProgramado
        enviados = 0
        for r in self.session.scalars(select(R).where(R.activo == True, R.proximo_envio.is_not(None), R.proximo_envio <= ahora)):
            self.enviar(r, ahora=ahora)
            r.proximo_envio = self.calcular_proximo(r, ahora)
            enviados += 1
        self.session.flush()
        return {"enviados": enviados}
