from datetime import date, datetime, time

from app.domain.sla import CalendarioLaboral, DatosSla, calcular_sla, nuevos_umbrales, umbrales_configurados

# Ecuador = UTC-5 sin horario de verano: 08:30 local = 13:30 UTC
CAL = CalendarioLaboral.por_defecto()


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi)


def test_minutos_en_mismo_tramo():
    # Lunes 19-oct-2026 09:00 a 10:30 local
    assert CAL.minutos_laborables(utc(2026, 10, 19, 14), utc(2026, 10, 19, 15, 30)) == 90


def test_minutos_excluyen_almuerzo():
    # 12:00 a 15:00 local = 60 (12-13) + 60 (14-15)
    assert CAL.minutos_laborables(utc(2026, 10, 19, 17), utc(2026, 10, 19, 20)) == 120


def test_minutos_excluyen_fin_de_semana():
    # Viernes 23-oct 17:00 local a lunes 26-oct 09:00 local = 30 + 30
    assert CAL.minutos_laborables(utc(2026, 10, 23, 22), utc(2026, 10, 26, 14)) == 60


def test_sumar_cruza_noche():
    # Urgente 4 h desde lunes 16:00 local: 1.5 h ese día, 2.5 h el martes -> martes 11:00 local
    vence = CAL.sumar_minutos(utc(2026, 10, 19, 21), 240)
    assert vence == utc(2026, 10, 20, 16)


def test_sumar_desde_fuera_de_horario():
    # Creado sábado: 1 h desde el lunes 08:30 -> 09:30 local
    assert CAL.sumar_minutos(utc(2026, 10, 24, 15), 60) == utc(2026, 10, 26, 14, 30)


def test_feriado_y_horario_especial():
    cal = CalendarioLaboral.por_defecto()
    cal.feriados.add(date(2026, 11, 2))
    cal.horarios_especiales[date(2026, 11, 3)] = [(time(8, 30), time(10, 30))]
    # Viernes 30-oct 17:00 local + 3 h: 30 min viernes, lunes feriado, martes 2 h (especial), resto miércoles 08:30+30
    assert cal.sumar_minutos(utc(2026, 10, 30, 22), 180) == utc(2026, 11, 4, 14)


def test_calcular_sla_con_pausa():
    datos = DatosSla(
        fecha_creacion=utc(2026, 10, 19, 14),   # lunes 09:00 local
        sla_respuesta_min=60,
        sla_resolucion_min=240,
        sla_minutos_pausa=60,
    )
    r = calcular_sla(datos, utc(2026, 10, 19, 17), CAL)   # 12:00 local -> 180 transcurridos
    assert r.minutos_consumidos == 120
    assert r.porcentaje == 50.0
    # 240 + 60 de pausa = 300 min desde 09:00 -> 09:00-13:00 (240) + 14:00-15:00 (60)
    assert r.resolucion_vence == utc(2026, 10, 19, 20)


def test_calcular_sla_congelado_en_pausa():
    datos = DatosSla(utc(2026, 10, 19, 14), 60, 240, sla_pausa_desde=utc(2026, 10, 19, 15))
    r = calcular_sla(datos, utc(2026, 10, 21, 15), CAL)
    assert r.minutos_consumidos == 60 and r.pausado


def test_umbrales():
    assert nuevos_umbrales(80, 0) == [75]
    assert nuevos_umbrales(120, 75) == [90, 100]
    assert nuevos_umbrales(95, 90) == []


def test_umbrales_configurables():
    assert umbrales_configurados({"sla.umbral_aviso_1": "60", "sla.umbral_aviso_2": "85"}) == (60, 85, 100)
    assert umbrales_configurados({"sla.umbral_aviso_1": "95", "sla.umbral_aviso_2": "80"}) == (75, 90, 100)   # orden inválido
    assert umbrales_configurados({"sla.umbral_aviso_1": "x"}) == (75, 90, 100)
    assert nuevos_umbrales(70, 0, (60, 85, 100)) == [60]
