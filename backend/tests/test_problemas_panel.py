"""Cuarta ronda, parte 2a: gestión de problemas (30) y panel gerencial con PDF mensual (32)."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.application.services.panel_service import PanelService
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import crear_ticket
from tests.test_segunda_ronda import correos


def ticket_vpn(client, h, n: int) -> dict:
    return crear_ticket(client, h, asunto=f"La VPN se desconecta a cada rato {n}",
                        descripcion="Desde la mañana la VPN se desconecta y pierdo la conexión al sistema contable.")


def asignado(client, ha, t) -> dict:
    return client.get(f"{API}/tickets/{t['id']}", headers=ha).json()


# ================================================================== 30 problemas
def test_patron_detectado_crea_problema_con_los_tickets(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    tickets = [ticket_vpn(client, hm, i) for i in range(5)]
    crear_ticket(client, hm)   # otro asunto: no entra al patrón
    r = client.get(f"{API}/problemas", headers=ha).json()
    assert r["gestor"] and len(r["patrones"]) == 1
    patron = r["patrones"][0]
    assert patron["cantidad"] == 5 and {t["id"] for t in patron["tickets"]} == {t["id"] for t in tickets}

    nuevo = client.post(f"{API}/problemas", json={"titulo": "La VPN se desconecta", "tickets": [t["id"] for t in patron["tickets"]],
                                                   "desde_patron": True, "categoria_id": patron["categoria_id"],
                                                   "subcategoria_id": patron["subcategoria_id"]}, headers=ha)
    assert nuevo.status_code == 201, nuevo.text
    p = nuevo.json()
    assert p["numero"].startswith("PRB-") and p["numero"].endswith("-001") and p["origen"] == "PATRON"
    assert p["impacto"]["incidentes"] == 5 and p["impacto"]["personas"] == 1
    # Los tickets agrupados ya no forman patrón
    assert client.get(f"{API}/problemas", headers=ha).json()["patrones"] == []


def test_ignorar_patron(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    for i in range(5):
        ticket_vpn(client, hm, i)
    firma = client.get(f"{API}/problemas", headers=ha).json()["patrones"][0]["firma"]
    assert client.post(f"{API}/problemas/patrones/ignorar", json={"firma": firma}, headers=ha).status_code == 200
    assert client.get(f"{API}/problemas", headers=ha).json()["patrones"] == []


def test_ciclo_de_vida_error_conocido_y_cierre_avisa(client, como):
    ha, hm, hs = como("admin"), como("maria.andrade"), como("supervisor.operativo")
    t1 = ticket_vpn(client, hm, 1)
    p = client.post(f"{API}/problemas", json={"titulo": "La VPN se desconecta", "tickets": [t1["id"]],
                                               "palabras_clave": "vpn se desconecta"}, headers=hs).json()
    base = {"titulo": p["titulo"], "palabras_clave": "vpn se desconecta"}
    # Sin causa no puede ser error conocido
    r = client.post(f"{API}/problemas/{p['id']}/estado", json={"estado": "ERROR_CONOCIDO"}, headers=hs)
    assert r.status_code == 422 or r.status_code == 400
    analisis = {**base, "porques": [{"pregunta": "¿Por qué se desconecta?", "respuesta": "El firewall corta sesiones a los 10 min"}],
                "causa_raiz": "Tiempo de sesión del firewall muy corto", "solucion_temporal": "Reconectar la VPN desde el ícono de la bandeja."}
    p = client.put(f"{API}/problemas/{p['id']}", json=analisis, headers=hs).json()
    assert p["estado"] == "EN_ANALISIS" and p["porques"][0]["respuesta"].startswith("El firewall")
    p = client.post(f"{API}/problemas/{p['id']}/estado", json={"estado": "ERROR_CONOCIDO"}, headers=hs).json()
    assert p["estado"] == "ERROR_CONOCIDO" and p["fecha_causa"]
    # Publicar la solución temporal en la base de conocimiento
    p = client.post(f"{API}/problemas/{p['id']}/publicar", headers=hs).json()
    assert p["articulo"]["estado"] == "PUBLICADO"
    assert client.get(f"{API}/problemas", headers=hs).json()["resumen"]["errores_conocidos"] == 1

    # Un ticket nuevo parecido muestra la coincidencia al analista responsable
    t2 = ticket_vpn(client, hm, 2)
    d = asignado(client, ha, t2)
    analista = d["responsable"]["correo"].split("@")[0]
    hx = como(analista)
    info = client.get(f"{API}/problemas/ticket/{t2['id']}", headers=hx).json()
    assert [c["numero"] for c in info["coincidencias"]] == [p["numero"]]
    # El solicitante no ve nada de problemas
    assert client.get(f"{API}/problemas/ticket/{t2['id']}", headers=hm).json() == {"problemas": [], "coincidencias": []}
    assert client.get(f"{API}/problemas", headers=hm).status_code == 403
    # Vincular y responder con la solución: comentario público + incidente evitado
    info = client.post(f"{API}/problemas/{p['id']}/aplicar/{t2['id']}", json={"responder": True}, headers=hx).json()
    assert info["coincidencias"] == [] and info["problemas"][0]["numero"] == p["numero"]
    comentarios = client.get(f"{API}/tickets/{t2['id']}", headers=hm).json()["comentarios"]
    assert any("Reconectar la VPN" in c["texto"] and not c["es_interno"] for c in comentarios)
    assert client.get(f"{API}/problemas", headers=hs).json()["resumen"]["evitados_mes"] == 1

    # Solución en cambio exige un CAM
    assert client.post(f"{API}/problemas/{p['id']}/estado", json={"estado": "SOLUCION_EN_CAMBIO"}, headers=hs).status_code == 422
    # Cerrar avisa a la solicitante (una sola vez aunque tenga dos tickets)
    p = client.put(f"{API}/problemas/{p['id']}", json={**analisis, "solucion_definitiva": "Se amplió la sesión del firewall a 8 horas"},
                   headers=hs).json()
    p = client.post(f"{API}/problemas/{p['id']}/estado", json={"estado": "CERRADO", "avisar": True}, headers=hs).json()
    assert p["estado"] == "CERRADO" and p["impacto"]["incidentes"] == 2 and p["impacto"]["evitados"] == 1
    with SessionLocal() as s:
        avisos = [c for c in s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "PROBLEMA_RESUELTO"))]
    assert len(avisos) == 1 and avisos[0].para == "maria.andrade@aducorp.com.ec"


def test_no_es_esto_y_permisos(client, como):
    ha, hm, hs = como("admin"), como("maria.andrade"), como("supervisor.operativo")
    p = client.post(f"{API}/problemas", json={"titulo": "La VPN se desconecta", "palabras_clave": "vpn"}, headers=hs).json()
    client.put(f"{API}/problemas/{p['id']}", json={"titulo": p["titulo"], "palabras_clave": "vpn", "causa_raiz": "Firewall",
                                                   "solucion_temporal": "Reconectar la VPN."}, headers=hs)
    client.post(f"{API}/problemas/{p['id']}/estado", json={"estado": "ERROR_CONOCIDO"}, headers=hs)
    t = ticket_vpn(client, hm, 1)
    assert client.get(f"{API}/problemas/ticket/{t['id']}", headers=ha).json()["coincidencias"]
    assert client.post(f"{API}/problemas/{p['id']}/descartar/{t['id']}", headers=ha).json()["coincidencias"] == []
    # Analista ve la lista pero no gestiona; Gerencia también ve
    hx = como(asignado(client, ha, t)["responsable"]["correo"].split("@")[0])
    r = client.get(f"{API}/problemas", headers=hx).json()
    assert r["gestor"] is False and r["patrones"] == []
    assert client.post(f"{API}/problemas", json={"titulo": "Otro problema"}, headers=hx).status_code == 403
    assert client.get(f"{API}/problemas/{p['id']}", headers=como("gerencia")).status_code == 200
    # Vincular por número desde el detalle del problema
    r = client.post(f"{API}/problemas/{p['id']}/tickets", json={"ticket": t["numero"]}, headers=hs).json()
    assert r["impacto"]["incidentes"] == 1
    r = client.delete(f"{API}/problemas/{p['id']}/tickets/{t['id']}", headers=hs).json()
    assert r["impacto"]["incidentes"] == 0


# ================================================================== 32 panel gerencial
def test_panel_y_pdf(client, como):
    ha, hm, hg = como("admin"), como("maria.andrade"), como("gerencia")
    for _ in range(3):
        crear_ticket(client, hm)
    r = client.get(f"{API}/panel", headers=hg)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kpis"]["recibidos"] == 3 and len(d["serie"]) == 6 and d["serie"][-1]["tickets"] == 3
    assert d["tipos"][0]["cantidad"] == 3 and d["puede_configurar"] is False
    assert client.get(f"{API}/panel", headers=hm).status_code == 403
    assert client.get(f"{API}/panel", headers=como("supervisor.operativo")).status_code == 403
    pdf = client.get(f"{API}/panel/pdf", headers=hg)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.count(b"/Type /Page") - pdf.content.count(b"/Type /Pages") == 3


def test_envio_mensual_del_pdf(client, como):
    ha, hg = como("admin"), como("gerencia")
    assert client.put(f"{API}/panel/envio", json={"activo": True, "destinatarios": ["gerencia@aducorp.com.ec"]}, headers=hg).status_code == 403
    r = client.put(f"{API}/panel/envio", json={"activo": True, "destinatarios": []}, headers=ha)
    assert r.status_code == 422
    r = client.put(f"{API}/panel/envio", json={"activo": True, "destinatarios": ["gerencia@aducorp.com.ec", "directorio@aducorp.com.ec"],
                                               "cuando": "DIA_1", "hora": "08:00", "comentario": "Pendiente: firewall Quito"}, headers=ha)
    assert r.status_code == 200, r.text
    assert r.json()["config"]["activo"] and r.json()["proximo"]

    with SessionLocal() as s:
        svc = PanelService(s)
        # 1 de diciembre de 2026, 07:00 en Ecuador (12:00 UTC): todavía no es la hora
        assert svc.procesar(datetime(2026, 12, 1, 12, 0)) == {"enviado": False}
        # 08:05 → envía el PDF de noviembre una sola vez
        assert svc.procesar(datetime(2026, 12, 1, 13, 5)) == {"enviado": True, "periodo": "2026-11"}
        s.commit()
        assert svc.procesar(datetime(2026, 12, 1, 14, 0)) == {"enviado": False}
        assert svc.config()["comentario"] == ""   # el comentario del mes se limpia tras el envío
        s.commit()
    c = correos("Noviembre 2026")
    assert len(c) == 1 and c[0].adjunto_nombre == "Panel-Mesa-Noviembre-2026.pdf" and "directorio@aducorp.com.ec" in c[0].para

    envios = client.get(f"{API}/panel/envio", headers=hg).json()["envios"]
    assert envios[0]["periodo"] == "2026-11"
    pdf = client.get(f"{API}/panel/envios/{envios[0]['id']}/pdf", headers=hg)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    # Prueba: va solo a quien la pide
    r = client.post(f"{API}/panel/envio/prueba?anio=2026&mes=10", headers=ha)
    assert r.status_code == 200 and "admin@" in r.json()["mensaje"]


def test_primer_dia_habil(client, como):
    with SessionLocal() as s:
        svc = PanelService(s)
        # 1 de noviembre de 2026 es domingo → primer día hábil lunes 2 (si no es feriado) o el siguiente
        dia = svc.dia_envio(2026, 11, "PRIMER_HABIL")
        assert dia.weekday() < 5 and dia.day >= 2
        assert svc.dia_envio(2026, 11, "DIA_1").day == 1
