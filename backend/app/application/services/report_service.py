"""Indicadores gerenciales. Mismas definiciones que database/03_procedimientos.sql."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.sla_service import cargar_calendario
from app.application.services.ticket_service import limites_dia_utc
from app.core.config import settings
from app.domain.enums import ESTADOS_ABIERTOS, ESTADOS_CERRADOS, Permiso
from app.infrastructure.db import models as m


@dataclass
class FiltroReporte:
    desde: date
    hasta: date
    categoria_id: int | None = None
    responsable_id: int | None = None
    cliente_id: int | None = None
    estado: str | None = None
    sla: str | None = None   # CUMPLIDO | INCUMPLIDO | EN_CURSO


@dataclass
class Fila:
    id: int
    fecha: datetime          # local
    categoria_id: int
    categoria: str
    responsable_id: int | None
    responsable: str | None
    cliente_id: int | None
    cliente: str | None
    prioridad: str
    estado: str
    sla_ok: bool
    sla_ko: bool
    escalado: bool
    min_resp: int | None
    min_res: int | None
    pct: float

    @property
    def abierto(self) -> bool:
        return self.estado in ESTADOS_ABIERTOS

    @property
    def cerrado(self) -> bool:
        return self.estado in ESTADOS_CERRADOS


def _pct(ok: int, ko: int) -> float | None:
    return round(100.0 * ok / (ok + ko), 2) if ok + ko else None


def _horas(valores: list[int | None]) -> float | None:
    v = [x for x in valores if x is not None]
    return round(mean(v) / 60.0, 2) if v else None


class ReportService:
    def __init__(self, session: Session, usuario: m.Usuario):
        self.session = session
        self.usuario = usuario
        self.tz = ZoneInfo(settings.ZONA_HORARIA)

    # --------------------------------------------------------------- datos
    def _alcance_categorias(self) -> list[int] | None:
        u = self.usuario
        if u.tiene(Permiso.TICKET_VER_TODOS):
            return None
        return list(self.session.scalars(select(m.Categoria.id).where(m.Categoria.supervisor_id == u.id)))

    def filas(self, f: FiltroReporte) -> list[Fila]:
        T = m.Ticket
        desde, hasta = limites_dia_utc(f.desde, f.hasta)
        stmt = (
            select(T.id, T.fecha_creacion, T.categoria_id, m.Categoria.nombre, T.responsable_id, m.Usuario.nombre, T.cliente_id,
                   m.Cliente.razon_social, m.Prioridad.nombre, T.estado, T.sla_excluido, T.sla_incumplido, T.sla_resolucion_cumplido,
                   T.minutos_respuesta, T.minutos_resolucion, T.sla_consumido_pct)
            .join(m.Categoria, m.Categoria.id == T.categoria_id)
            .join(m.Prioridad, m.Prioridad.id == T.prioridad_id)
            .outerjoin(m.Usuario, m.Usuario.id == T.responsable_id)
            .outerjoin(m.Cliente, m.Cliente.id == T.cliente_id)
            .where(T.eliminado == False, T.fecha_creacion >= desde, T.fecha_creacion < hasta)
        )
        alcance = self._alcance_categorias()
        if alcance is not None:
            stmt = stmt.where(T.categoria_id.in_(alcance or [-1]))
        for campo in ("categoria_id", "responsable_id", "cliente_id"):
            if getattr(f, campo):
                stmt = stmt.where(getattr(T, campo) == getattr(f, campo))
        if f.estado:
            stmt = stmt.where(T.estado == f.estado)
        escalados = set(self.session.scalars(
            select(m.TicketEscalamiento.ticket_id).join(T, T.id == m.TicketEscalamiento.ticket_id)
            .where(m.TicketEscalamiento.nivel != 75, T.fecha_creacion >= desde, T.fecha_creacion < hasta)
        ))
        filas = []
        for r in self.session.execute(stmt):
            ok = (not r[10]) and (not r[11]) and bool(r[12])
            ko = (not r[10]) and bool(r[11])
            fila = Fila(r[0], r[1].replace(tzinfo=timezone.utc).astimezone(self.tz).replace(tzinfo=None), r[2], r[3], r[4], r[5], r[6], r[7],
                        r[8], r[9], ok, ko, r[0] in escalados, r[13], r[14], float(r[15] or 0))
            if f.sla == "CUMPLIDO" and not ok or f.sla == "INCUMPLIDO" and not ko or f.sla == "EN_CURSO" and (ok or ko):
                continue
            filas.append(fila)
        return filas

    # ----------------------------------------------------------- dashboard
    @staticmethod
    def resumen(filas: list[Fila]) -> dict:
        ok = sum(f.sla_ok for f in filas)
        ko = sum(f.sla_ko for f in filas)
        return {
            "tickets_totales": len(filas),
            "tickets_abiertos": sum(f.abierto for f in filas),
            "tickets_cerrados": sum(f.cerrado for f in filas),
            "tickets_escalados": sum(f.escalado for f in filas),
            "tickets_vencidos": ko,
            "sla_cumplido": ok,
            "sla_incumplido": ko,
            "cumplimiento_sla_pct": _pct(ok, ko),
            "tiempo_promedio_respuesta_h": _horas([f.min_resp for f in filas]),
            "tiempo_promedio_resolucion_h": _horas([f.min_res for f in filas]),
        }

    def dashboard(self, f: FiltroReporte) -> dict:
        filas = self.filas(f)
        dias = (f.hasta - f.desde).days + 1
        agrupacion = "DIA" if dias <= 45 else "SEMANA" if dias <= 200 else "MES"
        return {
            "filtro": {"desde": f.desde, "hasta": f.hasta},
            "widgets": self.resumen(filas),
            "por_estado": dict(Counter(f.estado for f in filas)),
            "por_prioridad": dict(Counter(f.prioridad for f in filas)),
            "tendencia": self._serie(filas, agrupacion),
            "agrupacion": agrupacion,
            "top_categorias": [{"nombre": n, "tickets": c} for n, c in Counter(f.categoria for f in filas).most_common(5)],
            "top_responsables": [{"nombre": n, "tickets": c} for n, c in Counter(f.responsable for f in filas if f.responsable).most_common(5)],
            "en_riesgo": self._en_riesgo(),
        }

    def _en_riesgo(self) -> list[dict]:
        T = m.Ticket
        stmt = (select(T).where(T.eliminado == False, T.estado.in_(["NUEVO", "ASIGNADO", "EN_PROCESO", "ESCALADO"]), T.sla_consumido_pct >= 75)
                .order_by(T.sla_consumido_pct.desc()).limit(10))
        alcance = self._alcance_categorias()
        if alcance is not None:
            stmt = stmt.where(T.categoria_id.in_(alcance or [-1]))
        return [
            {"id": t.id, "numero": t.numero, "asunto": t.asunto, "categoria": t.categoria.nombre,
             "responsable": t.responsable.nombre if t.responsable else None, "sla_consumido_pct": float(t.sla_consumido_pct),
             "vence": t.sla_resolucion_vence.isoformat() + "Z", "estado": t.estado}
            for t in self.session.scalars(stmt).unique()
        ]

    # ------------------------------------------------------------ tendencias
    @staticmethod
    def _periodo(d: datetime, agrupacion: str) -> str:
        if agrupacion == "DIA":
            return d.strftime("%Y-%m-%d")
        if agrupacion == "SEMANA":
            y, w, _ = d.isocalendar()
            return f"{y}-S{w:02d}"
        if agrupacion == "MES":
            return d.strftime("%Y-%m")
        return str(d.year)

    def _serie(self, filas: list[Fila], agrupacion: str) -> list[dict]:
        g: dict[str, dict] = defaultdict(lambda: {"tickets": 0, "cerrados": 0, "sla_cumplido": 0, "sla_incumplido": 0})
        for f in filas:
            p = g[self._periodo(f.fecha, agrupacion)]
            p["tickets"] += 1
            p["cerrados"] += f.cerrado
            p["sla_cumplido"] += f.sla_ok
            p["sla_incumplido"] += f.sla_ko
        return [{"periodo": k, **v, "cumplimiento_sla_pct": _pct(v["sla_cumplido"], v["sla_incumplido"])} for k, v in sorted(g.items())]

    def tendencia(self, f: FiltroReporte, agrupacion: str) -> list[dict]:
        return self._serie(self.filas(f), agrupacion)

    # ----------------------------------------------------------- categorías
    def por_categoria(self, f: FiltroReporte) -> list[dict]:
        filas = self.filas(f)
        backlog = Counter(
            self.session.scalars(select(m.Ticket.categoria_id).where(m.Ticket.eliminado == False, m.Ticket.estado.in_(list(ESTADOS_ABIERTOS))))
        )
        cats = self.session.scalars(select(m.Categoria).where(m.Categoria.eliminado == False).order_by(m.Categoria.orden)).unique()
        alcance = self._alcance_categorias()
        res = []
        for c in cats:
            if alcance is not None and c.id not in alcance:
                continue
            fc = [x for x in filas if x.categoria_id == c.id]
            r = self.resumen(fc)
            res.append({
                "categoria_id": c.id, "categoria": c.nombre, "color": c.color,
                "tickets_recibidos": r["tickets_totales"], "tickets_resueltos": r["tickets_cerrados"],
                "tickets_pendientes": r["tickets_abiertos"], "tickets_vencidos": r["tickets_vencidos"],
                "cumplimiento_sla_pct": r["cumplimiento_sla_pct"], "tiempo_promedio_respuesta_h": r["tiempo_promedio_respuesta_h"],
                "tiempo_promedio_resolucion_h": r["tiempo_promedio_resolucion_h"], "backlog": backlog.get(c.id, 0),
            })
        return res

    # --------------------------------------------------------- responsables
    def dias_laborables(self, desde: date, hasta: date) -> int:
        cal = cargar_calendario(self.session)
        n, d = 0, desde
        while d <= hasta:
            n += bool(cal.tramos_del_dia(d))
            d += timedelta(days=1)
        return max(n, 1)

    def por_responsable(self, f: FiltroReporte) -> list[dict]:
        filas = [x for x in self.filas(f) if x.responsable_id]
        dias = self.dias_laborables(f.desde, min(f.hasta, datetime.now(self.tz).date()))
        grupos: dict[int, list[Fila]] = defaultdict(list)
        for x in filas:
            grupos[x.responsable_id].append(x)
        res = []
        for uid, fs in grupos.items():
            r = self.resumen(fs)
            res.append({
                "responsable_id": uid, "responsable": fs[0].responsable, "tickets_asignados": len(fs),
                "tickets_cerrados": r["tickets_cerrados"], "tickets_abiertos": r["tickets_abiertos"],
                "sla_cumplido": r["sla_cumplido"], "sla_incumplido": r["sla_incumplido"], "cumplimiento_sla_pct": r["cumplimiento_sla_pct"],
                "productividad_dia": round(r["tickets_cerrados"] / dias, 2), "tiempo_promedio_resolucion_h": r["tiempo_promedio_resolucion_h"],
            })
        mejor = max((x["tickets_cerrados"] for x in res), default=0) or 1
        for x in res:
            x["puntaje"] = round(0.6 * (x["cumplimiento_sla_pct"] or 0) + 0.4 * 100.0 * x["tickets_cerrados"] / mejor, 2)
        res.sort(key=lambda x: x["puntaje"], reverse=True)
        for i, x in enumerate(res, 1):
            x["ranking"] = i
        return res

    # ------------------------------------------------------------- clientes
    def por_cliente(self, f: FiltroReporte) -> list[dict]:
        filas = [x for x in self.filas(f) if x.cliente_id]
        grupos: dict[int, list[Fila]] = defaultdict(list)
        for x in filas:
            grupos[x.cliente_id].append(x)
        res = []
        for cid, fs in grupos.items():
            r = self.resumen(fs)
            res.append({
                "cliente_id": cid, "cliente": fs[0].cliente, "tickets": len(fs), "cumplimiento_sla_pct": r["cumplimiento_sla_pct"],
                "categorias": [{"nombre": n, "tickets": c} for n, c in Counter(x.categoria for x in fs).most_common(3)],
                "tendencia": [{"periodo": p["periodo"], "tickets": p["tickets"]} for p in self._serie(fs, "MES")],
            })
        return sorted(res, key=lambda x: x["tickets"], reverse=True)
