"""Cálculo de fechas de tickets recurrentes y de reportes programados (sin dependencias de base de datos)."""
from __future__ import annotations

import calendar
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

PASOS_MES = {"MENSUAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ORDINAL = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto", -1: "último"}


@dataclass
class Regla:
    frecuencia: str                 # DIARIA | SEMANAL | MENSUAL | TRIMESTRAL | SEMESTRAL | ANUAL
    desde: date
    hora: time = time(8, 30)
    dia_semana: int | None = None   # 1 = lunes … 7 = domingo
    dia_mes: int | None = None      # 1..31, -1 = último día del mes
    semana_mes: int | None = None   # 1..4, -1 = última; con dia_semana («primer lunes»)
    hasta: date | None = None


@dataclass
class Ocurrencia:
    nominal: date      # la fecha que «tocaba»
    efectiva: date     # la fecha real (siguiente día laborable si tocaba en feriado o fin de semana)

    @property
    def movida(self) -> bool:
        return self.nominal != self.efectiva


def validar(r: Regla) -> str | None:
    """Mensaje de error si la regla está incompleta; None si es válida."""
    if r.hasta and r.hasta < r.desde:
        return "La fecha «hasta» es anterior a «desde»"
    if r.frecuencia == "SEMANAL" and not r.dia_semana:
        return "Indique el día de la semana"
    if r.frecuencia in PASOS_MES:
        if r.semana_mes and not r.dia_semana:
            return "Indique el día de la semana (p. ej. «primer lunes»)"
        if not r.semana_mes and not r.dia_mes:
            return "Indique el día del mes o la semana («primer lunes»)"
    return None


def _dia_del_mes(anio: int, mes: int, r: Regla) -> date:
    ultimo = calendar.monthrange(anio, mes)[1]
    if r.semana_mes and r.dia_semana:
        wd = r.dia_semana - 1
        if r.semana_mes == -1:
            d = date(anio, mes, ultimo)
            return d - timedelta(days=(d.weekday() - wd) % 7)
        primero = date(anio, mes, 1)
        return primero + timedelta(days=(wd - primero.weekday()) % 7 + 7 * (r.semana_mes - 1))
    dia = ultimo if (r.dia_mes or 1) == -1 else min(r.dia_mes or 1, ultimo)
    return date(anio, mes, dia)


def nominales(r: Regla) -> Iterator[date]:
    """Fechas que «tocan» según la regla, desde ``r.desde`` en adelante."""
    if r.frecuencia == "DIARIA":
        d = r.desde
        while True:
            yield d
            d += timedelta(days=1)
    elif r.frecuencia == "SEMANAL":
        d = r.desde + timedelta(days=((r.dia_semana or 1) - 1 - r.desde.weekday()) % 7)
        while True:
            yield d
            d += timedelta(days=7)
    else:
        paso = PASOS_MES[r.frecuencia]
        base = r.desde.year * 12 + r.desde.month - 1
        k = 0
        while True:
            indice = base + k * paso
            d = _dia_del_mes(indice // 12, indice % 12 + 1, r)
            if d >= r.desde:
                yield d
            k += 1


def ocurrencias(r: Regla, laborable: Callable[[date], bool], limite: int = 400) -> Iterator[Ocurrencia]:
    """Fechas efectivas: si la fecha cae en día no laborable se pasa al siguiente laborable.

    En la frecuencia diaria los días no laborables simplemente se omiten.
    """
    vistos: set[date] = set()
    for n, nominal in enumerate(nominales(r)):
        if n > limite * 40:
            return
        if r.hasta and nominal > r.hasta:
            return
        efectiva = nominal
        if r.frecuencia == "DIARIA":
            if not laborable(nominal):
                continue
        else:
            for _ in range(31):
                if laborable(efectiva):
                    break
                efectiva += timedelta(days=1)
        if efectiva in vistos:
            continue
        vistos.add(efectiva)
        yield Ocurrencia(nominal, efectiva)


def proxima(r: Regla, despues_utc: datetime, laborable: Callable[[date], bool], tz: str) -> tuple[datetime, Ocurrencia] | None:
    """Próximo momento (UTC, sin zona) estrictamente posterior a ``despues_utc``."""
    zona = ZoneInfo(tz)
    for o in ocurrencias(r, laborable):
        momento = datetime.combine(o.efectiva, r.hora, tzinfo=zona).astimezone(timezone.utc).replace(tzinfo=None)
        if momento > despues_utc:
            return momento, o
    return None


def siguientes(r: Regla, despues_utc: datetime, laborable: Callable[[date], bool], tz: str, n: int = 6) -> list[tuple[datetime, Ocurrencia]]:
    filas = []
    zona = ZoneInfo(tz)
    for o in ocurrencias(r, laborable):
        momento = datetime.combine(o.efectiva, r.hora, tzinfo=zona).astimezone(timezone.utc).replace(tzinfo=None)
        if momento > despues_utc:
            filas.append((momento, o))
            if len(filas) >= n:
                break
    return filas


def describir(r: Regla) -> str:
    """«Mensual · primer lunes · 08:30»."""
    hora = r.hora.strftime("%H:%M")
    nombre = {"DIARIA": "Diario (días laborables)", "SEMANAL": "Semanal", "MENSUAL": "Mensual", "TRIMESTRAL": "Trimestral",
              "SEMESTRAL": "Semestral", "ANUAL": "Anual"}[r.frecuencia]
    if r.frecuencia == "DIARIA":
        return f"{nombre} · {hora}"
    if r.frecuencia == "SEMANAL":
        return f"{nombre} · {DIAS[(r.dia_semana or 1) - 1]} · {hora}"
    if r.semana_mes and r.dia_semana:
        cuando = f"{ORDINAL.get(r.semana_mes, '')} {DIAS[r.dia_semana - 1]}"
    else:
        cuando = "último día" if r.dia_mes == -1 else f"día {r.dia_mes}"
    if r.frecuencia == "ANUAL":
        cuando += f" de {MESES[r.desde.month - 1]}"
    return f"{nombre} · {cuando} · {hora}"


def rellenar_fecha(texto: str, d: date) -> str:
    """Reemplaza {mes}, {año} y {fecha} en el asunto o la descripción del ticket recurrente."""
    return (texto.replace("{mes}", MESES[d.month - 1]).replace("{año}", str(d.year)).replace("{anio}", str(d.year))
            .replace("{fecha}", d.strftime("%d/%m/%Y")))
