"""Motor de SLA en horario laboral.

Python puro, sin dependencias de base de datos, para poder probarlo de forma aislada.

Convenciones:
- Las fechas que entran y salen son *naive* en UTC (como se guardan en SQL Server).
- El calendario se evalúa en la zona horaria configurada (America/Guayaquil por defecto).
- Los minutos de SLA son minutos laborables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

Tramo = tuple[time, time]

UMBRALES_ALERTA = (75, 90, 100)


@dataclass
class CalendarioLaboral:
    """Horario semanal por tramos + feriados + horarios especiales."""

    zona_horaria: str = "America/Guayaquil"
    # 0 = lunes … 6 = domingo
    tramos_semana: dict[int, list[Tramo]] = field(default_factory=dict)
    feriados: set[date] = field(default_factory=set)
    horarios_especiales: dict[date, list[Tramo]] = field(default_factory=dict)

    MAX_DIAS_BUSQUEDA = 3660

    @classmethod
    def por_defecto(cls) -> "CalendarioLaboral":
        """L-V 08:30-13:00 y 14:00-17:30 (8 h laborables)."""
        tramos = [(time(8, 30), time(13, 0)), (time(14, 0), time(17, 30))]
        return cls(tramos_semana={d: list(tramos) for d in range(5)})

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.zona_horaria)

    # ------------------------------------------------------------------ util
    def _a_local(self, utc_naive: datetime) -> datetime:
        return utc_naive.replace(tzinfo=timezone.utc).astimezone(self.tz)

    def _a_utc(self, local: datetime) -> datetime:
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    def tramos_del_dia(self, dia: date) -> list[Tramo]:
        if dia in self.feriados:
            return []
        if dia in self.horarios_especiales:
            return self.horarios_especiales[dia]
        return self.tramos_semana.get(dia.weekday(), [])

    def es_laborable(self, momento_utc: datetime) -> bool:
        local = self._a_local(momento_utc)
        return any(i <= local.time() < f for i, f in self.tramos_del_dia(local.date()))

    def _intervalos(self, dia: date) -> list[tuple[datetime, datetime]]:
        tz = self.tz
        return [
            (datetime.combine(dia, i, tzinfo=tz), datetime.combine(dia, f, tzinfo=tz))
            for i, f in sorted(self.tramos_del_dia(dia))
        ]

    # ------------------------------------------------------------- cálculos
    def minutos_laborables(self, inicio_utc: datetime, fin_utc: datetime) -> int:
        """Minutos laborables completos entre dos instantes (0 si fin <= inicio)."""
        if fin_utc <= inicio_utc:
            return 0
        inicio, fin = self._a_local(inicio_utc), self._a_local(fin_utc)
        total = timedelta()
        dia = inicio.date()
        while dia <= fin.date():
            for a, b in self._intervalos(dia):
                desde, hasta = max(a, inicio), min(b, fin)
                if hasta > desde:
                    total += hasta - desde
            dia += timedelta(days=1)
        return int(total.total_seconds() // 60)

    def sumar_minutos(self, inicio_utc: datetime, minutos: int) -> datetime:
        """Instante (UTC) en que se cumplen `minutos` laborables desde `inicio_utc`."""
        inicio = self._a_local(inicio_utc)
        restante = timedelta(minutes=max(minutos, 0))
        dia = inicio.date()
        for _ in range(self.MAX_DIAS_BUSQUEDA):
            for a, b in self._intervalos(dia):
                desde = max(a, inicio)
                if b <= desde:
                    continue
                disponible = b - desde
                if restante <= disponible:
                    # Con 0 minutos restantes, el vencimiento es el inicio del siguiente tramo laborable.
                    return self._a_utc(desde + restante)
                restante -= disponible
            dia += timedelta(days=1)
        raise ValueError("El calendario laboral no tiene horas hábiles configuradas")


# ---------------------------------------------------------------------------
# Estado de SLA de un ticket
# ---------------------------------------------------------------------------
@dataclass
class DatosSla:
    """Subconjunto de campos del ticket que necesita el motor."""

    fecha_creacion: datetime
    sla_respuesta_min: int
    sla_resolucion_min: int
    sla_minutos_pausa: int = 0
    sla_minutos_extension: int = 0
    sla_pausa_desde: datetime | None = None
    fecha_primera_respuesta: datetime | None = None
    fecha_resolucion: datetime | None = None


@dataclass
class ResultadoSla:
    minutos_consumidos: int
    porcentaje: float
    respuesta_vence: datetime
    resolucion_vence: datetime
    pausado: bool


def calcular_sla(datos: DatosSla, ahora: datetime, cal: CalendarioLaboral) -> ResultadoSla:
    """Consumo actual del SLA de resolución y fechas de vencimiento.

    - Mientras el ticket está en pausa, el consumo se congela en el inicio de la pausa.
    - Las pausas cerradas (sla_minutos_pausa) desplazan los vencimientos.
    """
    referencia = datos.sla_pausa_desde or datos.fecha_resolucion or ahora
    transcurridos = cal.minutos_laborables(datos.fecha_creacion, referencia)
    consumidos = max(transcurridos - datos.sla_minutos_pausa, 0)
    total = datos.sla_resolucion_min + datos.sla_minutos_extension
    porcentaje = round(100.0 * consumidos / total, 2) if total > 0 else 0.0
    resolucion_vence = cal.sumar_minutos(datos.fecha_creacion, total + datos.sla_minutos_pausa)
    respuesta_vence = cal.sumar_minutos(datos.fecha_creacion, datos.sla_respuesta_min + datos.sla_minutos_pausa)
    return ResultadoSla(
        minutos_consumidos=consumidos,
        porcentaje=porcentaje,
        respuesta_vence=respuesta_vence,
        resolucion_vence=resolucion_vence,
        pausado=datos.sla_pausa_desde is not None,
    )


def umbrales_configurados(config: dict[str, str]) -> tuple[int, int, int]:
    """Umbrales de aviso definidos en Configuración (sla.umbral_aviso_1/2); si no son válidos, 75/90."""
    try:
        u1, u2 = int(config.get("sla.umbral_aviso_1", UMBRALES_ALERTA[0])), int(config.get("sla.umbral_aviso_2", UMBRALES_ALERTA[1]))
    except ValueError:
        return UMBRALES_ALERTA
    return (u1, u2, 100) if 0 < u1 < u2 < 100 else UMBRALES_ALERTA


def nuevos_umbrales(porcentaje: float, nivel_actual: int, umbrales: tuple[int, int, int] = UMBRALES_ALERTA) -> list[int]:
    """Umbrales de alerta (aviso 1, aviso 2 y 100 %) alcanzados que aún no se notificaron."""
    return [u for u in umbrales if porcentaje >= u and nivel_actual < u]


# ---------------------------------------------------------------------------
# Avisos previos por tiempo que falta
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigAvisos:
    """Cómo se avisa antes de vencer (Configuración sla.*)."""

    por_tiempo: bool = True        # True: avisos 1 y 2 por minutos que faltan; False: por % consumido (umbral_aviso_1/2)
    previo_1_min: int = 120        # 1.er aviso al responsable
    previo_2_min: int = 30         # 2.º aviso al responsable, supervisor y coordinación (+ aviso en pantalla)
    respuesta_min: int = 60        # aviso previo de 1.ª respuesta (0 = desactivado)


def _entero(config: dict[str, str], clave: str, defecto: int) -> int:
    try:
        return max(int(str(config.get(clave, defecto)).strip()), 0)
    except ValueError:
        return defecto


def avisos_configurados(config: dict[str, str]) -> ConfigAvisos:
    p1, p2 = _entero(config, "sla.aviso_previo_1_min", 120), _entero(config, "sla.aviso_previo_2_min", 30)
    if p2 >= p1 or p2 == 0:   # valores incoherentes: se vuelve a los recomendados
        p1, p2 = 120, 30
    return ConfigAvisos(
        por_tiempo=str(config.get("sla.avisar_por", "tiempo")).strip().lower() != "porcentaje",
        previo_1_min=p1, previo_2_min=p2, respuesta_min=_entero(config, "sla.aviso_respuesta_min", 60),
    )


def umbrales_por_tiempo(porcentaje: float, restante_min: int, nivel_actual: int, umbrales: tuple[int, int, int],
                        avisos: ConfigAvisos) -> list[int]:
    """Como nuevos_umbrales, pero los avisos 1 y 2 se disparan por minutos laborables que faltan para vencer.
    El 100 % (vencido) sigue dependiendo del consumo."""
    alcanzados = []
    if restante_min <= avisos.previo_1_min:
        alcanzados.append(umbrales[0])
    if restante_min <= avisos.previo_2_min:
        alcanzados.append(umbrales[1])
    if porcentaje >= 100:
        alcanzados.append(umbrales[2])
    return [u for u in alcanzados if nivel_actual < u]


def texto_minutos(minutos: int) -> str:
    """120 → «2 h», 95 → «1 h 35 min», 40 → «40 min»."""
    minutos = max(int(minutos), 0)
    h, mi = divmod(minutos, 60)
    if not h:
        return f"{mi} min"
    return f"{h} h" if not mi else f"{h} h {mi} min"
