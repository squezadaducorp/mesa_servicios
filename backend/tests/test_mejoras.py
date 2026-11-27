"""Mejoras post-piloto: avisos antes de vencer, resumen diario, encuesta de satisfacción y ausencias con reemplazo."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.application.services.encuesta_service import token_encuesta
from app.application.services.resumen_service import ResumenDiarioService
from app.application.services.sla_service import SlaService
from app.core.security import utcnow
from app.domain.sla import ConfigAvisos, texto_minutos, umbrales_por_tiempo
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import crear_ticket

# Lunes 16/11/2026, hora de Ecuador (UTC-5): 09:00 local = 14:00 UTC
LUNES_0900 = datetime(2026, 11, 16, 14, 0)


def local(h: int, mi: int = 0) -> datetime:
    return datetime(2026, 11, 16, h + 5, mi)


def fijar_creacion(ticket_id: int, cuando: datetime) -> None:
    with SessionLocal() as s:
        t = s.get(m.Ticket, ticket_id)
        t.fecha_creacion = cuando
        SlaService(s).inicializar(t)
        s.commit()


def evaluar(ahora: datetime) -> dict:
    with SessionLocal() as s:
        stats = SlaService(s).evaluar_tickets_abiertos(ahora)
        s.commit()
        return stats


def notificaciones(s, tipo: str) -> list[m.Notificacion]:
    return list(s.scalars(select(m.Notificacion).where(m.Notificacion.tipo == tipo)))


# --------------------------------------------------------------- dominio
def test_umbrales_por_tiempo():
    avisos = ConfigAvisos(previo_1_min=120, previo_2_min=30)
    assert umbrales_por_tiempo(40, 200, 0, (75, 90, 100), avisos) == []
    assert umbrales_por_tiempo(60, 100, 0, (75, 90, 100), avisos) == [75]
    assert umbrales_por_tiempo(90, 25, 75, (75, 90, 100), avisos) == [90]
    assert umbrales_por_tiempo(100, 0, 90, (75, 90, 100), avisos) == [100]
    assert texto_minutos(95) == "1 h 35 min" and texto_minutos(120) == "2 h" and texto_minutos(40) == "40 min"


# ------------------------------------------------- 9. avisos antes de vencer
def test_avisos_por_tiempo_que_falta(client, como):
    t = crear_ticket(client, como("maria.andrade"))   # Urgente: 60 min respuesta, 240 min resolución
    fijar_creacion(t["id"], LUNES_0900)

    st = evaluar(local(9, 15))   # faltan 45 min para la 1.ª respuesta
    assert st["aviso_respuesta"] == 1 and st["aviso_75"] == 0
    assert evaluar(local(9, 20))["aviso_respuesta"] == 0   # una sola vez

    st = evaluar(local(11, 30))   # faltan 90 min laborables para resolver
    assert st["aviso_75"] == 1 and st["aviso_90"] == 0
    st = evaluar(local(12, 40))   # faltan 20 min
    assert st["aviso_90"] == 1 and st["vencidos"] == 0
    with SessionLocal() as s:
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "SLA_AVISO_1")) is not None
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "SLA_AVISO_2")) is not None
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "SLA_AVISO_RESPUESTA")) is not None
        titulos = [n.titulo for n in notificaciones(s, "SLA_90")]
        assert any("vence en 20 min" in x for x in titulos)
        motivos = [e.motivo for e in s.scalars(select(m.TicketEscalamiento))]
        assert "Faltan 20 min para vencer" in motivos


def test_avisos_por_porcentaje_si_se_configura(client, como):
    r = client.put(f"{API}/admin/sla/alertas", json={"valores": {"sla.avisar_por": "porcentaje"}}, headers=como("mesa.servicios"))
    assert r.status_code == 200, r.text
    t = crear_ticket(client, como("maria.andrade"))
    fijar_creacion(t["id"], LUNES_0900)
    assert evaluar(local(11, 30))["aviso_75"] == 0   # 150/240 = 62 %
    assert evaluar(local(12, 0))["aviso_75"] == 1    # 180/240 = 75 %


def test_configurar_alertas_valida(client, como):
    h = como("mesa.servicios")
    assert client.get(f"{API}/admin/sla/alertas", headers=h).json()["sla.aviso_previo_1_min"] == "120"
    r = client.put(f"{API}/admin/sla/alertas", json={"valores": {"sla.aviso_previo_2_min": "200"}}, headers=h)
    assert r.status_code == 422
    r = client.put(f"{API}/admin/sla/alertas", json={"valores": {"seguridad.max_intentos": "1"}}, headers=h)
    assert r.status_code == 422
    assert client.get(f"{API}/admin/sla/alertas", headers=como("david.medina")).status_code == 403


def test_listado_vence_en_y_filtro_vencidos(client, como):
    h = como("david.medina")
    t = crear_ticket(client, como("maria.andrade"))
    fresco = client.get(f"{API}/tickets", headers=h).json()["items"][0]
    assert fresco["vence_tipo"] in ("RESPUESTA", "RESOLUCION")
    with SessionLocal() as s:
        s.get(m.Ticket, t["id"]).fecha_creacion = utcnow() - timedelta(days=10)
        SlaService(s).recalcular(s.get(m.Ticket, t["id"]))
        s.commit()
    vencidos = client.get(f"{API}/tickets", params={"vence": "VENCIDOS"}, headers=h).json()
    assert vencidos["total"] == 1 and vencidos["items"][0]["vence_en_min"] < 0
    assert client.get(f"{API}/tickets", params={"vence": "HOY"}, headers=h).json()["total"] == 0
    assert client.get(f"{API}/tickets/alertas-sla", headers=h).status_code == 200


def test_resumen_diario(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    fijar_creacion(t["id"], local(8, 40))   # vence hoy a las 13:40 (Urgente)
    with SessionLocal() as s:
        svc = ResumenDiarioService(s)
        assert not svc.corresponde(local(8, 0))   # antes de la hora configurada
        r = svc.enviar(local(8, 45))
        s.commit()
        assert r["resumenes"] == 1 and r["tickets"] == 1
        correo = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "SLA_RESUMEN_DIARIO"))
        assert correo.para == "david.medina@aducorp.com.ec" and "ADU-" in correo.cuerpo_html
        assert ResumenDiarioService(s).enviar(local(9, 0)) == {"omitido": "no corresponde"}   # una vez al día


# ------------------------------------------------------ 1. encuesta
def resolver(client, como, t):
    url = f"{API}/tickets/{t['id']}"
    client.post(f"{url}/estado", json={"estado": "EN_PROCESO", "comentario": "Motivo de prueba"}, headers=como("david.medina"))
    r = client.post(f"{url}/estado", json={"estado": "RESUELTO", "comentario": "Motivo de prueba"}, headers=como("david.medina"))
    assert r.json()["estado"] == "RESUELTO"
    return url


def test_encuesta_en_el_portal(client, como):
    cliente = como("maria.andrade")
    t = crear_ticket(client, cliente)
    url = resolver(client, como, t)
    with SessionLocal() as s:
        invitacion = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ENCUESTA"))
        assert invitacion is not None and "/encuesta?t=" in invitacion.cuerpo_html
    d = client.get(url, headers=cliente).json()
    assert "calificar" in d["acciones"] and d["encuesta"] is None
    assert client.post(f"{url}/encuesta", json={"calificacion": 4}, headers=como("david.medina")).status_code == 403
    r = client.post(f"{url}/encuesta", json={"calificacion": 2, "comentario": "Tardaron mucho"}, headers=cliente)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "CERRADO" and d["encuesta"]["calificacion"] == 2 and "calificar" not in d["acciones"]
    assert client.post(f"{url}/encuesta", json={"calificacion": 5}, headers=cliente).status_code == 409
    with SessionLocal() as s:
        assert notificaciones(s, "ENCUESTA_BAJA")   # nota baja: aviso al supervisor
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ENCUESTA_BAJA")) is not None
    sat = client.get(f"{API}/reportes/dashboard", headers=como("gerencia")).json()["satisfaccion"]
    assert sat["total"] == 1 and sat["promedio"] == 2 and sat["distribucion"]["2"] == 1 and sat["respondidas_pct"] == 100.0
    assert sat["comentarios"][0]["comentario"] == "Tardaron mucho"


def test_encuesta_desde_el_correo(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    resolver(client, como, t)
    token = token_encuesta(t["id"])
    info = client.get(f"{API}/publico/encuesta", params={"t": token}).json()
    assert info["numero"] == t["numero"] and info["calificacion"] is None
    r = client.post(f"{API}/publico/encuesta", json={"token": token, "calificacion": 5})
    assert r.status_code == 200 and r.json()["puede_comentar"] is True
    r = client.post(f"{API}/publico/encuesta", json={"token": token, "calificacion": 5})   # volver a abrir el enlace
    assert r.status_code == 200
    r = client.post(f"{API}/publico/encuesta", json={"token": token, "comentario": "Excelente atención"})
    assert r.json()["comentario"] == "Excelente atención" and r.json()["puede_comentar"] is False
    assert client.post(f"{API}/publico/encuesta", json={"token": token, "calificacion": 1}).status_code == 409
    assert client.post(f"{API}/publico/encuesta", json={"token": "x" * 40, "calificacion": 3}).status_code == 422
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("david.medina")).json()
    assert d["estado"] == "CERRADO" and d["encuesta"]["origen"] == "CORREO"


# ------------------------------------------------------ 4. ausencias
def test_ausencia_reasigna_y_devuelve(client, como):
    analista = como("david.medina")
    t = crear_ticket(client, como("maria.andrade"))   # Clasificación Arancelaria → David Medina
    assert t["responsable"]["nombre"] == "David Medina"
    sugeridos = client.get(f"{API}/ausencias/reemplazos", headers=analista).json()
    assert sugeridos and all(x["nombre"] != "David Medina" for x in sugeridos)
    with SessionLocal() as s:
        denisse = s.scalar(select(m.Usuario).where(m.Usuario.correo == "denisse.quinga@aducorp.com.ec"))
    previa = client.get(f"{API}/ausencias/tickets", headers=analista).json()
    assert [x["numero"] for x in previa] == [t["numero"]]

    ahora = datetime.now(ZoneInfo("America/Guayaquil")).replace(tzinfo=None)
    body = {"reemplazo_id": denisse.id, "motivo": "VACACIONES", "desde": (ahora - timedelta(minutes=5)).isoformat(timespec="minutes"),
            "hasta": (ahora + timedelta(days=5)).isoformat(timespec="minutes")}
    r = client.post(f"{API}/ausencias", json=body, headers=analista)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["estado"] == "ACTIVA"
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()
    assert d["responsable"]["nombre"] == "Denisse Quinga"
    assert any("vacaciones" in (h["detalle"] or "") for h in d["historial"])
    # Los tickets nuevos de su categoría van al reemplazo
    assert crear_ticket(client, como("maria.andrade"))["responsable"]["nombre"] == "Denisse Quinga"
    # El reemplazo ve a quién cubre; no se puede registrar otra ausencia superpuesta
    cubro = client.get(f"{API}/ausencias/mias", headers=como("denisse.quinga")).json()
    assert cubro[0]["usuario"]["nombre"] == "David Medina" and cubro[0]["tickets_abiertos"] == 1
    assert client.post(f"{API}/ausencias", json=body, headers=analista).status_code == 422
    assert client.get(f"{API}/ausencias", headers=como("mesa.servicios")).json()[0]["id"] == a["id"]
    with SessionLocal() as s:
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "AUSENCIA_REASIGNADO")) is not None
    # «Volví antes»: se devuelve solo el ticket que se le había pasado
    r = client.post(f"{API}/ausencias/{a['id']}/cancelar", headers=analista)
    assert r.status_code == 200 and r.json()["estado"] == "FINALIZADA"
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()
    assert d["responsable"]["nombre"] == "David Medina"
    # Denisse conserva lectura del ticket que atendió («Tickets en los que participé»)
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("denisse.quinga")).status_code == 200


def test_ausencia_programada_la_activa_el_worker(client, como):
    analista = como("david.medina")
    t = crear_ticket(client, como("maria.andrade"))
    with SessionLocal() as s:
        denisse = s.scalar(select(m.Usuario).where(m.Usuario.correo == "denisse.quinga@aducorp.com.ec"))
    ahora = datetime.now(ZoneInfo("America/Guayaquil")).replace(tzinfo=None)
    r = client.post(f"{API}/ausencias", json={"reemplazo_id": denisse.id, "desde": (ahora + timedelta(days=1)).isoformat(timespec="minutes"),
                                             "hasta": (ahora + timedelta(days=3)).isoformat(timespec="minutes")}, headers=analista)
    assert r.json()["estado"] == "PROGRAMADA"
    assert client.post(f"{API}/ausencias", json={"usuario_id": denisse.id, "reemplazo_id": denisse.id, "desde": "2027-01-01T08:30",
                                                 "hasta": "2027-01-02T08:30"}, headers=analista).status_code == 403
    with SessionLocal() as s:
        a = s.get(m.UsuarioAusencia, r.json()["id"])
        a.desde, a.hasta = utcnow() - timedelta(hours=1), utcnow() + timedelta(days=1)
        s.commit()
    from app.worker import ciclo_ausencias

    assert ciclo_ausencias() == {"iniciadas": 1, "terminadas": 0}
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()["responsable"]["nombre"] == "Denisse Quinga"
    with SessionLocal() as s:
        s.get(m.UsuarioAusencia, r.json()["id"]).hasta = utcnow() - timedelta(minutes=1)
        s.commit()
    assert ciclo_ausencias() == {"iniciadas": 0, "terminadas": 1}
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()["responsable"]["nombre"] == "David Medina"


# ------------------------------------------- 13. alerta del servidor (sin base de datos)
def test_alerta_del_servidor(monkeypatch):
    from app import alerta

    enviados = []

    class Falso:
        def enviar(self, para, asunto, cuerpo_html, cc=None):
            enviados.append((para, asunto, cuerpo_html))

    monkeypatch.setattr(alerta, "enviador", lambda: Falso())
    assert alerta.main(["--para", "ti@aducorp.com.ec; jefe@aducorp.com.ec", "--asunto", "La Mesa no responde",
                        "--mensaje", "El contenedor «api» está detenido\nDisco 41 %"]) == 0
    para, asunto, html_ = enviados[0]
    assert para == "ti@aducorp.com.ec,jefe@aducorp.com.ec" and "La Mesa no responde" in asunto
    assert "<li" in html_ and "«api»" in html_
    assert alerta.main(["--para", " ", "--asunto", "x"]) == 2
