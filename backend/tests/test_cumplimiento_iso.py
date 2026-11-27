"""ISO 27001: revisión de accesos y bajas por inactividad (38); clasificación y retención (42)."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.application.services.retencion_service import RetencionService
from app.application.services.revision_acceso_service import RevisionAccesoService
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import crear_ticket

DOM = "@aducorp.com.ec"


def _usuario(s, local):
    return s.scalar(select(m.Usuario).where(m.Usuario.correo == local + DOM))


def _jefe(local_jefe, *locales):
    with SessionLocal() as s:
        jefe = _usuario(s, local_jefe)
        for l in locales:
            _usuario(s, l).supervisor_id = jefe.id
        s.commit()


# ================================================================== 38 revisión de accesos
def _revisor(local):
    with SessionLocal() as s:
        s.merge(m.Configuracion(clave="accesos.revisor_correo", valor=local + DOM))
        s.commit()


def test_revision_de_accesos_la_hace_el_coordinador_no_los_jefes(client, como):
    _jefe("supervisor.operativo", "maria.andrade", "luis.paredes")   # el jefe directo sigue registrado
    _revisor("supervisor.tecnico")
    ha, hj, hc = como("admin"), como("supervisor.operativo"), como("supervisor.tecnico")
    r = client.post(f"{API}/accesos/revisiones", headers=ha)
    assert r.status_code == 201, r.text
    rev = r.json()
    assert client.post(f"{API}/accesos/revisiones", headers=ha).status_code == 422   # una abierta a la vez
    with SessionLocal() as s:   # un solo correo, al Coordinador de Sistemas, con todas las cuentas
        avisos = s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "REVISION_ACCESO")).all()
        assert [a.para for a in avisos] == ["supervisor.tecnico" + DOM]
        assert "Luis Alberto Paredes" in avisos[0].cuerpo_html and "Coordinador de Sistemas" in avisos[0].cuerpo_html

    # El jefe directo ya no revisa accesos
    assert client.get(f"{API}/accesos/pendientes", headers=hj).json()["revision_id"] is None
    assert client.get(f"{API}/accesos/revisiones/{rev['id']}", headers=hj).status_code == 403
    todos = client.get(f"{API}/accesos/revisiones/{rev['id']}", headers=ha).json()["items"]
    luis = next(i for i in todos if i["correo"].startswith("luis"))
    assert client.put(f"{API}/accesos/items/{luis['id']}", json={"decision": "MANTENER"}, headers=hj).status_code == 403

    # El Coordinador ve todas las cuentas menos la suya (esa la revisa otro administrador)
    p = client.get(f"{API}/accesos/pendientes", headers=hc).json()
    assert p["revision_id"] == rev["id"] and p["pendientes"] == len(todos) - 1
    mios = client.get(f"{API}/accesos/revisiones/{rev['id']}", headers=hc).json()["items"]
    assert len(mios) == len(todos) - 1 and "supervisor.tecnico" + DOM not in {i["correo"] for i in mios}
    maria = next(i for i in mios if i["correo"].startswith("maria"))
    assert client.put(f"{API}/accesos/items/{luis['id']}", json={"decision": "BAJA"}, headers=hc).status_code == 422   # pide motivo
    assert client.put(f"{API}/accesos/items/{luis['id']}", json={"decision": "BAJA", "comentario": "Ya no trabaja en ADUCORP"},
                      headers=hc).status_code == 200
    assert client.put(f"{API}/accesos/items/{maria['id']}", json={"decision": "MANTENER"}, headers=hc).status_code == 200

    r = client.post(f"{API}/accesos/revisiones/{rev['id']}/aprobar", json={}, headers=ha)
    assert r.status_code == 422 and "Faltan" in r.json()["detail"]
    for i in client.get(f"{API}/accesos/revisiones/{rev['id']}", headers=ha).json()["items"]:
        if i["decision"] is None:
            client.put(f"{API}/accesos/items/{i['id']}", json={"decision": "MANTENER"}, headers=ha)
    r = client.post(f"{API}/accesos/revisiones/{rev['id']}/aprobar", json={"observacion": "Sin novedades"}, headers=ha)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "APROBADA"
    with SessionLocal() as s:
        assert _usuario(s, "luis.paredes").activo is False and _usuario(s, "maria.andrade").activo is True
        acta = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACTA_REVISION_ACCESO"))
        assert acta.para == "squezada" + DOM and acta.adjunto.startswith(b"%PDF")
    pdf = client.get(f"{API}/accesos/revisiones/{rev['id']}/acta", headers=ha)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"{API}/accesos/revisiones", headers=hj).status_code == 403


def test_sin_cuenta_del_coordinador_la_revision_queda_para_ti(client, como):
    _jefe("supervisor.operativo", "maria.andrade")
    r = client.post(f"{API}/accesos/revisiones", headers=como("admin")).json()   # squezada@ no existe en las pruebas
    assert all(i["jefe_id"] is None for i in r["items"])
    assert client.get(f"{API}/accesos/pendientes", headers=como("supervisor.operativo")).json()["revision_id"] is None
    with SessionLocal() as s:
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "REVISION_ACCESO")) is None


def test_worker_abre_la_revision_del_trimestre_una_vez(client):
    diciembre = datetime(2026, 12, 1, 14, 0)
    with SessionLocal() as s:
        r = RevisionAccesoService(s).procesar(diciembre)
        s.commit()
        assert r["revision"] == "2026-12"
        assert RevisionAccesoService(s).procesar(diciembre + timedelta(hours=2))["omitido"]   # una vez al día
        rev = s.scalar(select(m.RevisionAcceso))
        cuentas = s.scalars(select(m.RevisionAccesoItem).where(m.RevisionAccesoItem.revision_id == rev.id)).all()
        correos = {i.usuario.correo for i in cuentas}
        assert "admin" + DOM in correos and not any(c.startswith("mesaservicios@") for c in correos)
        admin = next(i for i in cuentas if i.usuario.correo == "admin" + DOM)
        assert "ADMIN" in admin.alertas and "EMERGENCIA" in admin.alertas
    with SessionLocal() as s:   # enero no es mes de revisión
        assert "revision" not in RevisionAccesoService(s).procesar(datetime(2027, 1, 5, 14, 0))


def test_baja_por_inactividad_con_aviso_previo(client):
    with SessionLocal() as s:
        u = _usuario(s, "maria.andrade")
        u.ultimo_login = utcnow() - timedelta(days=85)
        _usuario(s, "luis.paredes").ultimo_login = utcnow() - timedelta(days=100)
        admin = _usuario(s, "admin")
        admin.ultimo_login = utcnow() - timedelta(days=200)   # cuenta de emergencia: nunca se desactiva
        s.commit()
        svc = RevisionAccesoService(s)
        r = svc.procesar_inactividad(utcnow())
        s.commit()
        assert r == {"avisos": 2, "bajas": 0}   # aviso primero, aunque ya pasó el plazo
        avisos = s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "AVISO_INACTIVIDAD")).all()
        assert {a.para for a in avisos} == {"maria.andrade" + DOM, "luis.paredes" + DOM}
        assert svc.procesar_inactividad(utcnow() + timedelta(days=2)) == {"avisos": 0, "bajas": 0}
        r = svc.procesar_inactividad(utcnow() + timedelta(days=8))
        s.commit()
        assert r == {"avisos": 0, "bajas": 2}
        assert not _usuario(s, "luis.paredes").activo and _usuario(s, "admin").activo
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "BAJA_INACTIVIDAD"))
        baja = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "BAJA_INACTIVIDAD"))
        assert "squezada" + DOM in baja.para


def test_quien_vuelve_a_entrar_no_se_desactiva(client):
    with SessionLocal() as s:
        u = _usuario(s, "maria.andrade")
        u.ultimo_login = utcnow() - timedelta(days=86)
        s.commit()
        svc = RevisionAccesoService(s)
        assert svc.procesar_inactividad(utcnow())["avisos"] == 1
        u.ultimo_login = utcnow()   # entró después del aviso
        s.commit()
        assert svc.procesar_inactividad(utcnow() + timedelta(days=8)) == {"avisos": 0, "bajas": 0}
        assert _usuario(s, "maria.andrade").activo


# ================================================================== 42 clasificación y retención
def test_ticket_confidencial_restringe_visualizadores_correos_y_kb(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    t = crear_ticket(client, hm)
    assert client.get(f"{API}/tickets/{t['id']}", headers=hm).json()["clasificacion"] == "INTERNA"
    d = client.get(f"{API}/tickets/{t['id']}", headers=ha).json()
    hr = como(d["responsable"]["correo"].split("@")[0])
    with SessionLocal() as s:
        luis = _usuario(s, "luis.paredes")
        s.add(m.TicketVisualizador(ticket_id=t["id"], usuario_id=luis.id, agregado_por=luis.id))
        s.commit()
    hl = como("luis.paredes")
    assert client.get(f"{API}/tickets/{t['id']}", headers=hl).status_code == 200

    r = client.put(f"{API}/tickets/{t['id']}/clasificacion", json={"clasificacion": "CONFIDENCIAL"}, headers=hm)   # el solicitante la sube
    assert r.status_code == 200 and r.json()["clasificacion"] == "CONFIDENCIAL"
    assert client.get(f"{API}/tickets/{t['id']}", headers=hl).status_code == 404   # el visualizador deja de verlo
    # Bajarla: el solicitante no puede; quien atiende sí, con motivo
    assert client.put(f"{API}/tickets/{t['id']}/clasificacion", json={"clasificacion": "INTERNA", "motivo": "No aplica"},
                      headers=hm).status_code == 403
    assert client.put(f"{API}/tickets/{t['id']}/clasificacion", json={"clasificacion": "INTERNA"}, headers=hr).status_code == 422

    with SessionLocal() as s:   # una persona en copia recibe las respuestas por correo
        s.query(m.ColaCorreo).delete()
        s.add(m.TicketCopia(ticket_id=t["id"], correo="jefe.comercial@aducorp.com.ec"))
        s.commit()
    client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Su liquidación de haberes es USD 4.250", "es_interno": False}, headers=hr)
    with SessionLocal() as s:
        correos = s.scalars(select(m.ColaCorreo)).all()
        assert correos and all("4.250" not in c.cuerpo_html and "Transmisión de DAI" not in c.asunto for c in correos)
        assert any("Ticket confidencial" in c.asunto for c in correos)
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "CLASIFICACION_CAMBIADA"))

    r = client.put(f"{API}/tickets/{t['id']}/clasificacion", json={"clasificacion": "INTERNA", "motivo": "No contiene datos personales"},
                   headers=hr)
    assert r.status_code == 200 and r.json()["clasificacion"] == "INTERNA"
    h = client.get(f"{API}/tickets/{t['id']}", headers=ha).json()["historial"]
    assert any(x["accion"] == "CLASIFICACION" and x["detalle"] == "No contiene datos personales" for x in h)


def test_categoria_define_la_clasificacion_inicial(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    with SessionLocal() as s:
        c = s.scalar(select(m.Categoria).where(m.Categoria.codigo == "CLASIF_ARANCEL"))
        c.clasificacion = "CONFIDENCIAL"
        s.commit()
    t = crear_ticket(client, hm)
    assert client.get(f"{API}/tickets/{t['id']}", headers=ha).json()["clasificacion"] == "CONFIDENCIAL"


def test_retencion_depura_solo_lo_vencido_y_sin_retencion_legal(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    viejo, legal, nuevo = (crear_ticket(client, hm) for _ in range(3))
    client.post(f"{API}/tickets/{viejo['id']}/adjuntos", files={"archivo": ("factura.pdf", b"%PDF-1.4 prueba", "application/pdf")}, headers=hm)
    hace6 = utcnow() - timedelta(days=365 * 6)
    with SessionLocal() as s:
        for tid in (viejo["id"], legal["id"]):
            t = s.get(m.Ticket, tid)
            t.estado, t.fecha_cierre = "CERRADO", hace6
        s.commit()
    assert client.put(f"{API}/tickets/{legal['id']}/retencion-legal", json={"activa": True, "motivo": "Reclamo SENAE 2031"},
                      headers=ha).status_code == 200
    assert client.put(f"{API}/tickets/{legal['id']}/retencion-legal", json={"activa": True, "motivo": "x"},
                      headers=hm).status_code == 403
    r = client.get(f"{API}/retencion", headers=ha).json()
    assert r["anios"] == 5 and r["por_depurar"] == 1 and r["muestra"][0]["id"] == viejo["id"]
    assert client.post(f"{API}/retencion/depurar", json={"confirmacion": "si"}, headers=ha).status_code == 422
    r = client.post(f"{API}/retencion/depurar", json={"confirmacion": "DEPURAR"}, headers=ha).json()
    assert r == {"depurados": 1, "adjuntos": 1, "restantes": 0}
    with SessionLocal() as s:
        t = s.get(m.Ticket, viejo["id"])
        assert t.fecha_depuracion and t.asunto == "[Depurado]" and "depurado" in t.descripcion
        assert all(a.eliminado for a in s.scalars(select(m.TicketAdjunto).where(m.TicketAdjunto.ticket_id == t.id)))
        assert s.get(m.Ticket, legal["id"]).fecha_depuracion is None and s.get(m.Ticket, nuevo["id"]).fecha_depuracion is None
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "DEPURACION_RETENCION"))
        # aviso del primer día del mes: no hay nada más por depurar
        assert RetencionService(s).procesar(datetime(2027, 1, 1, 15, 0)) == {"por_depurar": 0}
