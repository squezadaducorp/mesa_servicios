"""Control de tiempo (31): cronómetro y registros a mano por ticket, problema o cambio, y reporte semanal de horas.

- Cada persona tiene a lo sumo un cronómetro corriendo: al iniciar otro, el anterior se pausa solo.
- El cronómetro se pausa solo cuando el ticket pasa a «Pendiente cliente», se resuelve, se cierra o se cancela,
  y cuando la persona cierra sesión.
- El reporte suma lo registrado en la semana (lunes a domingo, hora de Ecuador) por analista, área solicitante y categoría.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.conocimiento_service import es_mesa
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

TZ = ZoneInfo(settings.ZONA_HORARIA)
TIPOS = ("ticket", "problema", "cambio")
# Estados del ticket que detienen el cronómetro (el trabajo queda en espera o terminó)
ESTADOS_PAUSA = {Estado.PENDIENTE_CLIENTE, Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def segundos(r: m.TiempoRegistro, ahora: datetime | None = None) -> int:
    extra = 0
    if r.estado == "CORRIENDO" and r.corriendo_desde:
        extra = max(int(((ahora or utcnow()) - r.corriendo_desde).total_seconds()), 0)
    return (r.segundos or 0) + extra


def minutos(r: m.TiempoRegistro, ahora: datetime | None = None) -> int:
    return round(segundos(r, ahora) / 60)


def a_utc(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None)


def local(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc).astimezone(TZ)


def lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def nombre_semana(desde: date) -> str:
    hasta = desde + timedelta(days=4)
    if desde.month == hasta.month:
        return f"Semana {desde.day} al {hasta.day} de {MESES[hasta.month - 1]}"
    return f"Semana {desde.day} de {MESES[desde.month - 1]} al {hasta.day} de {MESES[hasta.month - 1]}"


class TiempoService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------ objetos
    def _objeto(self, tipo: str, objeto_id: int, u: m.Usuario):
        """Devuelve el ticket, problema o cambio si la persona puede registrar tiempo en él."""
        if tipo not in TIPOS:
            raise NoEncontrado("Tipo no válido")
        if tipo == "ticket":
            from app.application.services.ticket_service import TicketService

            svc = TicketService(self.session)
            t = svc.obtener(objeto_id, u)
            if "nota_interna" not in svc.acciones(u, t) and not u.tiene(Permiso.TICKET_VER_TODOS):
                raise Prohibido("Solo el equipo que atiende el ticket registra tiempo")
            return t
        if not es_mesa(u):
            raise Prohibido("Solo el equipo de TI registra tiempo")
        if tipo == "problema":
            from app.application.services.problema_service import ProblemaService

            return ProblemaService(self.session).obtener(objeto_id, u)
        from app.application.services.cambio_service import CambioService

        return CambioService(self.session).obtener(objeto_id, u)

    @staticmethod
    def _columna(tipo: str):
        return {"ticket": m.TiempoRegistro.ticket_id, "problema": m.TiempoRegistro.problema_id, "cambio": m.TiempoRegistro.cambio_id}[tipo]

    def _registro(self, registro_id: int, u: m.Usuario) -> m.TiempoRegistro:
        r = self.session.get(m.TiempoRegistro, registro_id)
        if r is None:
            raise NoEncontrado("Registro no encontrado")
        if r.usuario_id != u.id and not self._supervisa(u):
            raise Prohibido("Solo puede cambiar sus propios registros")
        return r

    @staticmethod
    def _supervisa(u: m.Usuario) -> bool:
        return u.tiene(Permiso.TIEMPO_REPORTE)

    def _corriendo(self, usuario_id: int) -> list[m.TiempoRegistro]:
        R = m.TiempoRegistro
        return list(self.session.scalars(select(R).where(R.usuario_id == usuario_id, R.estado == "CORRIENDO")).unique())

    # --------------------------------------------------------- cronómetro
    def _pausar(self, r: m.TiempoRegistro, ahora: datetime) -> None:
        if r.estado == "CORRIENDO":
            r.segundos = segundos(r, ahora)
            r.corriendo_desde = None
            r.estado = "PAUSADO"
            r.fecha_actualizacion = ahora

    def iniciar(self, tipo: str, objeto_id: int, actividad: str, ctx: Contexto) -> m.TiempoRegistro:
        u = ctx.usuario
        obj = self._objeto(tipo, objeto_id, u)
        if tipo == "ticket" and Estado(obj.estado) in ESTADOS_PAUSA:
            raise ReglaNegocio("El ticket no está en atención: cámbielo a «En proceso» para medir el tiempo")
        ahora = utcnow()
        for r in self._corriendo(u.id):   # un cronómetro a la vez
            self._pausar(r, ahora)
        r = m.TiempoRegistro(usuario_id=u.id, actividad=(actividad or "").strip()[:200] or "Atención", estado="CORRIENDO",
                             segundos=0, corriendo_desde=ahora, fecha=ahora, fecha_actualizacion=ahora,
                             **{f"{tipo}_id": objeto_id})
        self.session.add(r)
        self.session.flush()
        return r

    def pausar(self, registro_id: int, ctx: Contexto) -> m.TiempoRegistro:
        r = self._registro(registro_id, ctx.usuario)
        if r.estado != "CORRIENDO":
            raise ReglaNegocio("El cronómetro no está corriendo")
        self._pausar(r, utcnow())
        return r

    def reanudar(self, registro_id: int, ctx: Contexto) -> m.TiempoRegistro:
        r = self._registro(registro_id, ctx.usuario)
        if r.usuario_id != ctx.usuario.id:
            raise Prohibido("Solo quien lo inició puede reanudarlo")
        if r.estado != "PAUSADO":
            raise ReglaNegocio("El cronómetro no está en pausa")
        if r.ticket_id:
            t = self.session.get(m.Ticket, r.ticket_id)
            if Estado(t.estado) in ESTADOS_PAUSA:
                raise ReglaNegocio("El ticket no está en atención: cámbielo a «En proceso» para seguir midiendo")
        ahora = utcnow()
        for otro in self._corriendo(r.usuario_id):
            self._pausar(otro, ahora)
        r.estado, r.corriendo_desde, r.fecha_actualizacion = "CORRIENDO", ahora, ahora
        return r

    def detener(self, registro_id: int, ctx: Contexto) -> m.TiempoRegistro:
        r = self._registro(registro_id, ctx.usuario)
        if r.estado == "GUARDADO":
            raise ReglaNegocio("El registro ya está guardado")
        ahora = utcnow()
        self._pausar(r, ahora)
        r.estado = "GUARDADO"
        if r.segundos < 60:
            r.segundos = 60   # se guarda al menos un minuto
        return r

    def manual(self, tipo: str, objeto_id: int, actividad: str, mins: int, fecha: date | None, ctx: Contexto) -> m.TiempoRegistro:
        u = ctx.usuario
        self._objeto(tipo, objeto_id, u)
        if mins <= 0 or mins > 24 * 60:
            raise ReglaNegocio("Indique entre 1 minuto y 24 horas")
        ahora = utcnow()
        cuando = ahora
        if fecha:
            if fecha > local(ahora).date():
                raise ReglaNegocio("No se registra tiempo en fechas futuras")
            cuando = a_utc(datetime(fecha.year, fecha.month, fecha.day, 9, 0, tzinfo=TZ)) if fecha != local(ahora).date() else ahora
        r = m.TiempoRegistro(usuario_id=u.id, actividad=actividad.strip()[:200], estado="GUARDADO", segundos=mins * 60, manual=True,
                             fecha=cuando, fecha_actualizacion=ahora, **{f"{tipo}_id": objeto_id})
        self.session.add(r)
        self.session.flush()
        return r

    def editar(self, registro_id: int, actividad: str | None, mins: int | None, ctx: Contexto) -> m.TiempoRegistro:
        r = self._registro(registro_id, ctx.usuario)
        if actividad is not None and actividad.strip():
            r.actividad = actividad.strip()[:200]
        if mins is not None:
            if r.estado != "GUARDADO":
                raise ReglaNegocio("Detenga el cronómetro antes de corregir los minutos")
            if mins <= 0 or mins > 24 * 60:
                raise ReglaNegocio("Indique entre 1 minuto y 24 horas")
            r.segundos = mins * 60
        r.fecha_actualizacion = utcnow()
        return r

    def borrar(self, registro_id: int, ctx: Contexto) -> None:
        r = self._registro(registro_id, ctx.usuario)
        self.session.delete(r)

    def ajustes(self, ticket_id: int, estimado_min: int | None, facturable: bool | None, ctx: Contexto) -> m.Ticket:
        t = self._objeto("ticket", ticket_id, ctx.usuario)
        if estimado_min is not None:
            t.tiempo_estimado_min = estimado_min if estimado_min > 0 else None
        if facturable is not None:
            t.facturable = facturable
        return t

    # ----------------------------------------------------- pausas automáticas
    def pausar_ticket(self, ticket_id: int, ahora: datetime | None = None) -> int:
        """El ticket pasó a Pendiente cliente, Resuelto, Cerrado o Cancelado."""
        R = m.TiempoRegistro
        ahora = ahora or utcnow()
        filas = list(self.session.scalars(select(R).where(R.ticket_id == ticket_id, R.estado == "CORRIENDO")).unique())
        for r in filas:
            self._pausar(r, ahora)
        return len(filas)

    def pausar_usuario(self, usuario_id: int) -> int:
        """La persona cerró sesión (o la cerró la inactividad)."""
        filas = self._corriendo(usuario_id)
        ahora = utcnow()
        for r in filas:
            self._pausar(r, ahora)
        return len(filas)

    # ------------------------------------------------------------- salidas
    def _titulo(self, r: m.TiempoRegistro) -> tuple[str, str, str]:
        """(tipo, número, ruta) del objeto del registro."""
        if r.ticket_id:
            t = self.session.get(m.Ticket, r.ticket_id)
            return "ticket", t.numero, f"/tickets/{t.id}"
        if r.problema_id:
            p = self.session.get(m.Problema, r.problema_id)
            return "problema", p.numero, f"/problemas/{p.id}"
        c = self.session.get(m.Cambio, r.cambio_id)
        return "cambio", c.numero, f"/cambios/{c.id}"

    def salida(self, r: m.TiempoRegistro, u: m.Usuario, ahora: datetime | None = None) -> dict:
        tipo, numero, ruta = self._titulo(r)
        return {
            "id": r.id, "actividad": r.actividad, "estado": r.estado, "segundos": segundos(r, ahora), "minutos": minutos(r, ahora),
            "corriendo_desde": iso(r.corriendo_desde), "manual": r.manual, "fecha": iso(r.fecha),
            "desde_texto": f"{local(r.corriendo_desde):%H:%M}" if r.corriendo_desde else None,
            "usuario": {"id": r.usuario.id, "nombre": r.usuario.nombre},
            "propio": r.usuario_id == u.id, "editable": r.usuario_id == u.id or self._supervisa(u),
            "tipo": tipo, "numero": numero, "ruta": ruta,
        }

    def activo(self, u: m.Usuario) -> dict | None:
        """Cronómetro de la barra superior: el que corre o, si no, el último en pausa de hoy."""
        R = m.TiempoRegistro
        corriendo = self._corriendo(u.id)
        r = corriendo[0] if corriendo else self.session.scalar(
            select(R).where(R.usuario_id == u.id, R.estado == "PAUSADO", R.fecha_actualizacion >= utcnow() - timedelta(hours=12))
            .order_by(R.fecha_actualizacion.desc()).limit(1))
        return self.salida(r, u) if r else None

    def del_objeto(self, tipo: str, objeto_id: int, u: m.Usuario) -> dict:
        obj = self._objeto(tipo, objeto_id, u)
        R = m.TiempoRegistro
        filas = list(self.session.scalars(select(R).where(self._columna(tipo) == objeto_id).order_by(R.fecha.desc(), R.id.desc())).unique())
        ahora = utcnow()
        total = sum(segundos(r, ahora) for r in filas)
        mio = next((r for r in filas if r.usuario_id == u.id and r.estado in ("CORRIENDO", "PAUSADO")), None)
        salida = {
            "registros": [self.salida(r, u, ahora) for r in filas], "total_min": round(total / 60),
            "activo": self.salida(mio, u, ahora) if mio else None,
        }
        if tipo == "ticket":
            salida.update(estimado_min=obj.tiempo_estimado_min, facturable=bool(obj.facturable),
                          en_atencion=Estado(obj.estado) not in ESTADOS_PAUSA)
        else:
            salida.update(estimado_min=None, facturable=False, en_atencion=True)
        return salida

    # -------------------------------------------------------------- reporte
    def _horas_semana(self) -> float:
        try:
            return float(CatalogoRepository(self.session).configuracion().get("tiempo.horas_semana", "40"))
        except ValueError:
            return 40.0

    def registros_entre(self, desde_utc: datetime, hasta_utc: datetime) -> list[m.TiempoRegistro]:
        R = m.TiempoRegistro
        return list(self.session.scalars(select(R).where(R.fecha >= desde_utc, R.fecha < hasta_utc)).unique())

    def horas_por_area(self, desde_utc: datetime, hasta_utc: datetime) -> tuple[list[dict], int]:
        """Minutos por área solicitante (para el reporte y el panel gerencial)."""
        ahora = utcnow()
        por_area: dict[str, int] = defaultdict(int)
        total = 0
        for r in self.registros_entre(desde_utc, hasta_utc):
            s = segundos(r, ahora)
            total += s
            nombre = "Trabajo interno de TI"
            if r.ticket_id:
                t = self.session.get(m.Ticket, r.ticket_id)
                nombre = t.area.nombre if t.area else "Sin área"
            por_area[nombre] += s
        filas = [{"nombre": k, "minutos": round(v / 60), "pct": round(100 * v / total) if total else 0}
                 for k, v in sorted(por_area.items(), key=lambda x: -x[1])]
        return filas, round(total / 60)

    def reporte(self, u: m.Usuario, desde: date | None = None) -> dict:
        if not self._supervisa(u):
            raise Prohibido("No tiene permiso para ver el reporte de horas")
        hoy = local(utcnow()).date()
        inicio = lunes(desde or hoy)
        d_utc = a_utc(datetime(inicio.year, inicio.month, inicio.day, tzinfo=TZ))
        h_utc = d_utc + timedelta(days=7)
        ahora = utcnow()
        filas = self.registros_entre(d_utc, h_utc)
        analistas: dict[int, dict] = {}
        categorias: dict[str, int] = defaultdict(int)
        tickets: set[int] = set()
        facturable = 0
        total = 0
        for r in filas:
            s = segundos(r, ahora)
            total += s
            a = analistas.setdefault(r.usuario_id, {"id": r.usuario_id, "nombre": r.usuario.nombre, "tickets": set(),
                                                    "seg_incidentes": 0, "seg_cambios": 0})
            if r.ticket_id:
                t = self.session.get(m.Ticket, r.ticket_id)
                tickets.add(r.ticket_id)
                a["tickets"].add(r.ticket_id)
                a["seg_incidentes"] += s
                categorias[t.categoria.nombre] += s
                if t.facturable:
                    facturable += s
            else:
                a["seg_cambios"] += s
                categorias["Cambios y problemas"] += s
        disponibles = self._horas_semana()
        lista = []
        for a in sorted(analistas.values(), key=lambda x: -(x["seg_incidentes"] + x["seg_cambios"])):
            seg = a["seg_incidentes"] + a["seg_cambios"]
            n = len(a["tickets"])
            lista.append({"id": a["id"], "nombre": a["nombre"], "tickets": n, "minutos": round(seg / 60),
                          "min_incidentes": round(a["seg_incidentes"] / 60), "min_cambios": round(a["seg_cambios"] / 60),
                          "horas_por_ticket": round(a["seg_incidentes"] / 3600 / n, 1) if n else None,
                          "ocupacion_pct": round(100 * seg / 3600 / disponibles) if disponibles else None})
        areas, _ = self.horas_por_area(d_utc, h_utc)
        min_tickets = sum(a["min_incidentes"] for a in lista)
        semanas = [lunes(hoy) - timedelta(weeks=i) for i in range(12)]
        return {
            "desde": inicio, "hasta": inicio + timedelta(days=6), "nombre": nombre_semana(inicio),
            "semanas": [{"desde": s, "nombre": nombre_semana(s)} for s in semanas],
            "horas_disponibles": disponibles,
            "kpis": {"minutos": round(total / 60), "tickets": len(tickets),
                     "promedio_min": round(min_tickets / len(tickets)) if tickets else None,
                     "ocupacion_pct": round(100 * total / 3600 / (disponibles * len(lista))) if lista and disponibles else None,
                     "facturable_min": round(facturable / 60)},
            "analistas": lista, "areas": areas,
            "categorias": [{"nombre": k, "minutos": round(v / 60)} for k, v in sorted(categorias.items(), key=lambda x: -x[1])][:8],
        }

    def excel(self, u: m.Usuario, desde: date | None = None) -> tuple[str, bytes]:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        rep = self.reporte(u, desde)
        d_utc = a_utc(datetime(rep["desde"].year, rep["desde"].month, rep["desde"].day, tzinfo=TZ))
        filas = sorted(self.registros_entre(d_utc, d_utc + timedelta(days=7)), key=lambda r: r.fecha)
        wb = Workbook()
        ws = wb.active
        ws.title = "Registros"
        ws.append([f"Control de tiempo · {rep['nombre']} · Mesa de Servicios ADUCORP"])
        ws["A1"].font = Font(bold=True, size=14, color="10203C")
        ws.append([])
        cab = ["Fecha", "Analista", "Tipo", "Número", "Asunto", "Área solicitante", "Categoría", "Actividad", "Minutos", "Horas",
               "Facturable", "Forma"]
        ws.append(cab)
        for col in range(1, len(cab) + 1):
            c = ws.cell(row=3, column=col)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="10203C")
        ahora = utcnow()
        for r in filas:
            tipo, numero, _ = self._titulo(r)
            asunto = area = categoria = ""
            facturable = False
            if r.ticket_id:
                t = self.session.get(m.Ticket, r.ticket_id)
                asunto, area, categoria, facturable = t.asunto, t.area.nombre if t.area else "", t.categoria.nombre, bool(t.facturable)
            elif r.problema_id:
                asunto = self.session.get(m.Problema, r.problema_id).titulo
            else:
                asunto = self.session.get(m.Cambio, r.cambio_id).titulo
            mins = minutos(r, ahora)
            ws.append([local(r.fecha).replace(tzinfo=None), r.usuario.nombre, tipo.capitalize(), numero, asunto, area, categoria,
                       r.actividad, mins, round(mins / 60, 2), "Sí" if facturable else "No",
                       "A mano" if r.manual else ("Cronómetro (en curso)" if r.estado != "GUARDADO" else "Cronómetro")])
            ws.cell(row=ws.max_row, column=1).number_format = "dd/mm/yyyy hh:mm"
        for i, ancho in enumerate([16, 22, 10, 18, 40, 20, 22, 36, 9, 8, 10, 18], 1):
            ws.column_dimensions[get_column_letter(i)].width = ancho
        ws.freeze_panes = "A4"
        ws.auto_filter.ref = f"A3:{get_column_letter(len(cab))}{max(ws.max_row, 3)}"
        res = wb.create_sheet("Por analista")
        res.append(["Analista", "Tickets", "Horas", "Incidentes y solicitudes (h)", "Cambios y problemas (h)", "h/ticket",
                    f"Ocupación (de {rep['horas_disponibles']:g} h)"])
        for a in rep["analistas"]:
            res.append([a["nombre"], a["tickets"], round(a["minutos"] / 60, 1), round(a["min_incidentes"] / 60, 1),
                        round(a["min_cambios"] / 60, 1), a["horas_por_ticket"], (a["ocupacion_pct"] or 0) / 100])
            res.cell(row=res.max_row, column=7).number_format = "0%"
        for i, ancho in enumerate([24, 9, 8, 24, 22, 9, 18], 1):
            res.column_dimensions[get_column_letter(i)].width = ancho
        for c in res[1]:
            c.font = Font(bold=True)
        ar = wb.create_sheet("Por área")
        ar.append(["Área solicitante", "Horas", "%"])
        for a in rep["areas"]:
            ar.append([a["nombre"], round(a["minutos"] / 60, 1), a["pct"] / 100])
            ar.cell(row=ar.max_row, column=3).number_format = "0%"
        ar.column_dimensions["A"].width = 28
        salida = io.BytesIO()
        wb.save(salida)
        return f"Horas-{rep['desde']:%Y-%m-%d}.xlsx", salida.getvalue()
