"""Tercera ronda: aprobaciones del jefe, vínculos y duplicados, acciones en lote, traspaso, avisos generales y seguimiento sin cuenta."""
import json
import time

import pytest
from sqlalchemy import select

from app.api.v1.routers import publico
from app.application.services import formulario_service as fs
from app.application.services.aprobacion_service import AprobacionService
from app.application.services.seguimiento_service import token
from app.core.config import settings
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import crear_ticket, ids
from tests.test_segunda_ronda import area_id, correos, usuario_id


@pytest.fixture(autouse=True)
def limpio():
    fs.reiniciar_limites()
    publico.limitador_seguimiento.reiniciar()
    publico.limitador_respuestas.reiniciar()
    yield


def poner_jefe(usuario: str, jefe: str) -> None:
    with SessionLocal() as s:
        s.get(m.Usuario, usuario_id(usuario)).supervisor_id = usuario_id(jefe)
        s.commit()


def regla(client, ha, cat="CLASIF_ARANCEL", **extra) -> dict:
    cid, _ = ids(client, ha, cat, "Presentación DAI")
    r = client.post(f"{API}/aprobaciones/admin/reglas", json={"categoria_id": cid, **extra}, headers=ha)
    assert r.status_code == 201, r.text
    return r.json()


# ================================================================== 21 aprobaciones
def test_aprobacion_del_jefe_libera_el_ticket(client, como):
    ha, hm, hg = como("admin"), como("maria.andrade"), como("gerencia")
    poner_jefe("maria.andrade", "gerencia")
    regla(client, ha)
    assert client.get(f"{API}/aprobaciones/admin/reglas", headers=ha).json()["jefes"]["completos"] >= 1

    t = crear_ticket(client, hm)
    assert t["estado"] == "POR_APROBAR" and t["responsable"] is None
    assert t["aprobacion_pendiente_id"] is None   # quien pide no aprueba
    assert any("aprob" in c.asunto.lower() and c.para == "gerencia@aducorp.com.ec" for c in correos(t["numero"]))

    assert client.get(f"{API}/aprobaciones/conteo", headers=hg).json() == {"pendientes": 1, "es_aprobador": True}
    pend = client.get(f"{API}/aprobaciones", headers=hg).json()["pendientes"]
    assert [p["ticket"]["numero"] for p in pend] == [t["numero"]]
    # El jefe ve el ticket aunque no sea de su área
    d = client.get(f"{API}/tickets/{t['id']}", headers=hg).json()
    assert d["aprobacion_pendiente_id"] == pend[0]["id"]
    # Otro usuario no puede responder
    assert client.post(f"{API}/aprobaciones/{pend[0]['id']}/responder", json={"aprobar": True}, headers=como("luis.paredes")).status_code in (403, 404)

    r = client.post(f"{API}/aprobaciones/{pend[0]['id']}/responder", json={"aprobar": True}, headers=hg)
    assert r.status_code == 200, r.text and r.json()["estado"] == "APROBADO"
    d = client.get(f"{API}/tickets/{t['id']}", headers=hm).json()
    assert d["estado"] in ("NUEVO", "ASIGNADO") and d["aprobaciones"][0]["estado"] == "APROBADO"
    with SessionLocal() as s:
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "APROBACION_RESPONDIDA")) is not None


def test_rechazo_exige_motivo_y_cancela(client, como):
    ha, hm, hg = como("admin"), como("maria.andrade"), como("gerencia")
    poner_jefe("maria.andrade", "gerencia")
    regla(client, ha)
    t = crear_ticket(client, hm)
    aid = client.get(f"{API}/aprobaciones", headers=hg).json()["pendientes"][0]["id"]
    assert client.post(f"{API}/aprobaciones/{aid}/responder", json={"aprobar": False}, headers=hg).status_code == 422
    r = client.post(f"{API}/aprobaciones/{aid}/responder", json={"aprobar": False, "comentario": "No corresponde este mes"}, headers=hg)
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/tickets/{t['id']}", headers=hm).json()
    assert d["estado"] == "CANCELADO"
    assert any("No corresponde este mes" in c["texto"] for c in d["comentarios"])


def test_dos_niveles_y_autoaprobacion(client, como):
    ha, hm, hg = como("admin"), como("maria.andrade"), como("gerencia")
    poner_jefe("maria.andrade", "gerencia")
    regla(client, ha, nivel2_tipo="PERSONA", nivel2_usuario_id=usuario_id("mesa.servicios"))
    t = crear_ticket(client, hm)
    aid = client.get(f"{API}/aprobaciones", headers=hg).json()["pendientes"][0]["id"]
    client.post(f"{API}/aprobaciones/{aid}/responder", json={"aprobar": True}, headers=hg)
    assert client.get(f"{API}/tickets/{t['id']}", headers=hm).json()["estado"] == "POR_APROBAR"
    hms = como("mesa.servicios")
    aid2 = client.get(f"{API}/aprobaciones", headers=hms).json()["pendientes"][0]["id"]
    client.post(f"{API}/aprobaciones/{aid2}/responder", json={"aprobar": True}, headers=hms)
    assert client.get(f"{API}/tickets/{t['id']}", headers=hm).json()["estado"] in ("NUEVO", "ASIGNADO")

    # Si quien pide es el mismo aprobador, ese nivel se aprueba solo
    poner_jefe("supervisor.operativo", "supervisor.operativo")
    hs = como("supervisor.operativo")
    t2 = crear_ticket(client, hs)
    apr = client.get(f"{API}/tickets/{t2['id']}", headers=hs).json()["aprobaciones"]
    assert apr and apr[0]["estado"] == "APROBADO" and apr[1]["estado"] == "PENDIENTE"


def test_sin_regla_no_cambia_nada_y_cancelar_anula(client, como):
    hm = como("maria.andrade")
    t = crear_ticket(client, hm)
    assert t["estado"] != "POR_APROBAR" and t["aprobaciones"] == []
    poner_jefe("maria.andrade", "gerencia")
    regla(client, como("admin"))
    t2 = crear_ticket(client, hm)
    r = client.post(f"{API}/tickets/{t2['id']}/estado", json={"estado": "CANCELADO", "comentario": "Ya no lo necesita"}, headers=como("admin"))
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/aprobaciones/conteo", headers=como("gerencia")).json()["pendientes"] == 0


def test_recordatorio_del_worker(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    poner_jefe("maria.andrade", "gerencia")
    regla(client, ha, recordar_horas=1)
    crear_ticket(client, hm)
    with SessionLocal() as s:
        f = s.scalar(select(m.TicketAprobacion))
        f.fecha_solicitud = f.fecha_solicitud.replace(year=f.fecha_solicitud.year - 1)
        s.commit()
        r = AprobacionService(s).procesar(utcnow())
        s.commit()
        assert r["recordados"] == 1
        assert s.scalar(select(m.TicketAprobacion)).recordado


# ============================================================ 22 vínculos y duplicados
def test_unir_duplicados_y_bloqueos(client, como):
    hm, hl, ha = como("maria.andrade"), como("luis.paredes"), como("admin")
    a = crear_ticket(client, hm, asunto="ECUAPASS no carga la DAI", descripcion="El sistema ECUAPASS no carga la pantalla de la DAI.")
    b = crear_ticket(client, hl, asunto="ECUAPASS no carga DAI", descripcion="No puedo transmitir la DAI, ECUAPASS no carga.")
    posibles = client.get(f"{API}/tickets/{a['id']}/posibles-duplicados", headers=ha).json()
    assert b["id"] in [p["id"] for p in posibles]

    r = client.post(f"{API}/tickets/unir", json={"principal_id": a["id"], "duplicados": [b["id"]]}, headers=ha)
    assert r.status_code == 200, r.text
    principal = r.json()
    assert any(v["ticket"]["id"] == b["id"] for v in principal["vinculos"])
    dup = client.get(f"{API}/tickets/{b['id']}", headers=hl).json()
    assert dup["estado"] == "CANCELADO" and dup["duplicado_de"]["id"] == a["id"]

    # Bloqueado por: no se puede resolver mientras el otro siga abierto
    c = crear_ticket(client, hm, asunto="Actualizar certificado de firma")
    r = client.post(f"{API}/tickets/{c['id']}/vinculos", json={"relacionado": a["numero"], "tipo": "BLOQUEADO_POR"}, headers=ha)
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/tickets/{c['id']}/estado", json={"estado": "RESUELTO", "comentario": "Listo"}, headers=ha)
    assert r.status_code == 422 and a["numero"] in r.text
    # Descartar sugerencias
    assert client.post(f"{API}/tickets/{a['id']}/posibles-duplicados/{c['id']}/descartar", headers=ha).status_code == 200


# ================================================================ 23 lote y traspaso
def test_acciones_en_lote_con_error_parcial(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    t1, t2 = crear_ticket(client, hm), crear_ticket(client, hm)
    cat = client.get(f"{API}/catalogos", headers=ha).json()
    alta = next(p for p in cat["prioridades"] if p["id"] != t1["prioridad"]["id"])
    r = client.post(f"{API}/tickets/lote", json={"ids": [t1["id"], t2["id"], 999999], "accion": "PRIORIDAD", "prioridad_id": alta["id"]}, headers=ha)
    assert r.status_code == 200, r.text
    res = r.json()
    assert sorted(res["ok"]) == sorted([t1["numero"], t2["numero"]]) and len(res["errores"]) == 1
    assert client.get(f"{API}/tickets/{t1['id']}", headers=ha).json()["prioridad"]["id"] == alta["id"]
    # Repetir no cambia nada
    r = client.post(f"{API}/tickets/lote", json={"ids": [t1["id"]], "accion": "PRIORIDAD", "prioridad_id": alta["id"]}, headers=ha)
    assert r.json()["sin_cambio"] == [t1["numero"]]
    r = client.post(f"{API}/tickets/lote", json={"ids": [t1["id"], t2["id"]], "accion": "NOTA", "texto": "Revisar con aduana"}, headers=ha)
    assert len(r.json()["ok"]) == 2
    # Un cliente no puede cambiar prioridad en lote
    r = client.post(f"{API}/tickets/lote", json={"ids": [t1["id"]], "accion": "PRIORIDAD", "prioridad_id": t1["prioridad"]["id"]}, headers=hm)
    assert r.status_code == 200 and not r.json()["ok"]


def test_traspaso_de_cartera(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    t1, t2 = crear_ticket(client, hm), crear_ticket(client, hm)
    origen = t1["responsable"]["id"]
    otros = [u["id"] for u in client.get(f"{API}/admin/usuarios", headers=ha).json()["items"]
             if u["rol"] == "ANALISTA" and u["id"] != origen and u["activo"]][:2]
    body = {"modo": "EQUILIBRADO", "destinos": otros, "motivo": "Sale de vacaciones", "avisar": True}
    plan = client.post(f"{API}/admin/usuarios/{origen}/traspaso/vista-previa", json=body, headers=ha).json()
    assert plan["origen"]["abiertos"] >= 1 and all(f["destino_id"] in otros for f in plan["tickets"])
    r = client.post(f"{API}/admin/usuarios/{origen}/traspaso", json=body, headers=ha)
    assert r.status_code == 200, r.text and r.json()["tickets"] == plan["origen"]["abiertos"]
    assert client.get(f"{API}/tickets/{t1['id']}", headers=ha).json()["responsable"]["id"] in otros
    # A la cola
    t3 = crear_ticket(client, hm)
    origen3 = t3["responsable"]["id"]
    r = client.post(f"{API}/admin/usuarios/{origen3}/traspaso", json={"modo": "COLA", "motivo": "Cambio de puesto"}, headers=ha)
    assert r.status_code == 200, r.text
    assert (client.get(f"{API}/tickets/{t3['id']}", headers=ha).json()["responsable"] or {}).get("id") != origen3


# ================================================================== 24 avisos
def test_aviso_general_afectados_resolucion_y_constancia(client, como):
    hs, hm, hl = como("supervisor.operativo"), como("maria.andrade"), como("luis.paredes")
    r = client.post(f"{API}/avisos", json={"titulo": "ECUAPASS sin servicio", "mensaje": "El portal de la SENAE no responde.",
                                           "sistema": "ECUAPASS", "palabras_clave": "senae, dai", "mostrar_publico": True}, headers=hs)
    assert r.status_code == 201, r.text
    aviso = r.json()
    assert aviso["codigo"].startswith("AVISO-")
    assert client.post(f"{API}/avisos", json={"titulo": "x" * 6, "mensaje": "y" * 6, "sistema": "ZZ"}, headers=hm).status_code == 403

    assert [a["id"] for a in client.get(f"{API}/avisos/activos", headers=hm).json()] == [aviso["id"]]
    assert [a["id"] for a in client.get(f"{API}/avisos/coincidencias", params={"texto": "no puedo entrar a ecuapass"}, headers=hm).json()] == [aviso["id"]]
    assert client.post(f"{API}/avisos/{aviso['id']}/afecta", json={}, headers=hm).status_code == 200
    t = crear_ticket(client, hl, asunto="ECUAPASS caído", aviso_id=aviso["id"])
    assert [a["id"] for a in client.get(f"{API}/tickets/{t['id']}", headers=hl).json()["avisos"]] == [aviso["id"]]
    assert len(client.get(f"{API}/avisos/{aviso['id']}/afectados", headers=hs).json()) == 2
    assert client.get(f"{API}/publico/avisos").json()[0]["titulo"] == "ECUAPASS sin servicio"

    r = client.post(f"{API}/avisos/{aviso['id']}/actualizaciones", json={"estado": "RESUELTO", "texto": "Servicio restablecido."}, headers=hs)
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/tickets/{t['id']}", headers=hl).json()["estado"] == "RESUELTO"
    assert client.get(f"{API}/avisos/activos", headers=hm).json() == []
    assert len(correos("ECUAPASS")) >= 2
    pdf = client.get(f"{API}/avisos/{aviso['id']}/constancia", headers=hs)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    hist = client.get(f"{API}/avisos", headers=hs).json()
    assert hist["historial"][0]["id"] == aviso["id"]


# ============================================================ 20 seguimiento sin cuenta
def solicitud_publica(client) -> m.Ticket:
    datos = {"nombre": "María Pérez", "correo": "maria@importadora.com", "telefono": "0991234567", "empresa": "Importadora del Pacífico",
             "asunto": "Consulta sobre garantía aduanera", "descripcion": "Necesitamos renovar la garantía aduanera del trámite en ECUAPASS.",
             "token": fs.emitir_ficha(time.time() - 60)}
    r = client.post(f"{API}/publico/tickets", data={"datos": json.dumps(datos)})
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        t = s.scalar(select(m.Ticket).where(m.Ticket.numero == r.json()["numero"]))
        s.expunge(t)
        return t


def test_seguimiento_sin_cuenta(client, como):
    t = solicitud_publica(client)
    llave = token(t)
    with SessionLocal() as s:
        acuse = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACUSE_WEB"))
        assert f"/seguimiento/{t.id}/{llave}" in acuse.cuerpo_html
    assert client.get(f"{API}/publico/seguimiento/{t.id}", params={"t": "x" * 32}).status_code == 404
    assert client.get(f"{API}/publico/seguimiento/{t.id + 1}", params={"t": llave}).status_code == 404

    with SessionLocal() as s:
        resp = s.get(m.Ticket, t.id).responsable.correo.split("@")[0]
    hr = como(resp)
    client.post(f"{API}/tickets/{t.id}/comentarios", json={"texto": "Envíenos la póliza vigente."}, headers=hr)
    client.post(f"{API}/tickets/{t.id}/comentarios", json={"texto": "Nota secreta del equipo", "es_interno": True}, headers=hr)
    client.post(f"{API}/tickets/{t.id}/estado", json={"estado": "EN_PROCESO"}, headers=hr)
    client.post(f"{API}/tickets/{t.id}/estado", json={"estado": "PENDIENTE_CLIENTE", "comentario": "Esperamos la póliza"}, headers=hr)

    v = client.get(f"{API}/publico/seguimiento/{t.id}", params={"t": llave}).json()
    assert v["numero"] == t.numero and v["esperando_su_respuesta"] and v["puede_responder"]
    textos = [c["texto"] for c in v["conversacion"]]
    assert "Envíenos la póliza vigente." in textos and not any("secreta" in x for x in textos)
    assert detalle_url(client, hr, t.id).endswith(llave)

    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\n"
    r = client.post(f"{API}/publico/seguimiento/{t.id}/responder", data={"t": llave, "texto": "Adjunto la póliza."},
                    files=[("archivos", ("poliza.pdf", pdf, "application/pdf"))])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["estado"] == "EN_PROCESO" and v["adjuntos"][0]["nombre"] == "poliza.pdf"
    assert any(c["propio"] and c["texto"] == "Adjunto la póliza." for c in v["conversacion"])
    with SessionLocal() as s:
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "SEGUIMIENTO_PUBLICO_RESPUESTA")) is not None

    # Reenviar: misma respuesta siempre; solo envía si coinciden
    antes = len(correos(t.numero))
    r1 = client.post(f"{API}/publico/seguimiento/reenviar", json={"numero": t.numero, "correo": "otro@x.com"})
    r2 = client.post(f"{API}/publico/seguimiento/reenviar", json={"numero": t.numero, "correo": "MARIA@importadora.com"})
    assert r1.json() == r2.json()
    with SessionLocal() as s:
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "SEGUIMIENTO_ENLACE")).para == "maria@importadora.com"
    assert len(correos(t.numero)) == antes + 1


def detalle_url(client, h, tid) -> str:
    return client.get(f"{API}/tickets/{tid}", headers=h).json()["seguimiento_url"]


def test_seguimiento_tambien_para_usuarios_con_cuenta(client, como):
    """El acuse «Recibimos su solicitud» lleva el enlace de seguimiento a todo solicitante, también al personal con cuenta."""
    hm = como("maria.andrade")
    t = crear_ticket(client, hm)
    with SessionLocal() as s:
        tk = s.get(m.Ticket, t["id"])
        enlace = f"/seguimiento/{tk.id}/{token(tk)}"
        acuse = [c for c in s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.ticket_id == tk.id, m.ColaCorreo.plantilla == "TICKET_CREADO"))]
        assert len(acuse) == 1 and acuse[0].para == "maria.andrade@aducorp.com.ec"
        assert enlace in acuse[0].cuerpo_html
        r = client.get(f"{API}/publico/seguimiento/{tk.id}", params={"t": token(tk)})
        assert r.status_code == 200 and r.json()["numero"] == tk.numero
        # El aviso al responsable no lleva el botón: es personal del solicitante
        otros = s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.ticket_id == tk.id, m.ColaCorreo.plantilla != "TICKET_CREADO")).all()
        assert all(enlace not in c.cuerpo_html for c in otros)


def test_seguimiento_en_correo_del_beneficiario_en_nombre_de(client, como):
    ha = como("admin")
    cid, sid = ids(client, ha, "CLASIF_ARANCEL", "Presentación DAI")
    maria = usuario_id("maria.andrade")
    r = client.post(f"{API}/tickets", json={"asunto": "Registro telefónico", "descripcion": "Llamó para pedir apoyo con la DAI.",
                                            "categoria_id": cid, "subcategoria_id": sid, "solicitante_id": maria,
                                            "en_nombre_motivo": "Llamada telefónica"}, headers=ha)
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        tk = s.get(m.Ticket, r.json()["id"])
        aviso = s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.ticket_id == tk.id, m.ColaCorreo.para == "maria.andrade@aducorp.com.ec")).all()
        assert aviso and any(f"/seguimiento/{tk.id}/{token(tk)}" in c.cuerpo_html for c in aviso)


def test_seguimiento_se_puede_apagar(client, como):
    t = solicitud_publica(client)
    with SessionLocal() as s:
        c = s.scalar(select(m.Configuracion).where(m.Configuracion.clave == "seguimiento.activo"))
        c.valor = "no"
        s.commit()
    assert client.get(f"{API}/publico/seguimiento/{t.id}", params={"t": token(t)}).status_code == 404
    assert settings.APP_URL


# ============================================================ clientes por dominio de correo
def test_cliente_por_dominio_de_correo(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    t = crear_ticket(client, hm)
    assert t["cliente"]["nombre"] == "Aducorp CIA LTDA"   # personal @aducorp.com.ec
    otro = next(c for c in client.get(f"{API}/catalogos", headers=hm).json()["clientes"] if c["razon_social"] != "Aducorp CIA LTDA")
    assert crear_ticket(client, hm, cliente_id=otro["id"])["cliente"]["id"] == otro["id"]   # si elige otro, se respeta

    ext = solicitud_publica(client)   # maria@importadora.com: sin cliente con ese dominio
    assert ext.cliente_id is None

    # Se crea la empresa con su dominio: sus personas quedan asociadas solas
    cuerpo = {"razon_social": "Schryver del Ecuador SA", "ruc": "1790952150001", "dominios": ["@Importadora.com", "importadora.com.ec"]}
    r = client.post(f"{API}/admin/clientes", json=cuerpo, headers=ha)
    assert r.status_code == 201, r.text
    assert r.json()["dominios"] == ["importadora.com", "importadora.com.ec"]
    assert client.post(f"{API}/admin/clientes", json={"razon_social": "Otra", "dominios": ["gmail.com"]}, headers=ha).status_code == 422
    assert client.post(f"{API}/admin/clientes", json={"razon_social": "Otra", "dominios": ["importadora.com"]}, headers=ha).status_code == 422
    fs.reiniciar_limites()
    ext2 = solicitud_publica(client)
    assert ext2.cliente_id == r.json()["id"]


# ============================================================ inventario: cada uno ve solo lo suyo
def test_inventario_cada_usuario_ve_solo_sus_equipos(client, como):
    ha, hd, hg = como("admin"), como("david.medina"), como("gerencia")
    propio = client.post(f"{API}/inventario", json={"codigo": "ADU-PC-201", "tipo": "PORTATIL", "marca_modelo": "HP ProBook",
                                                    "usuario_id": usuario_id("david.medina")}, headers=ha).json()
    ajeno = client.post(f"{API}/inventario", json={"codigo": "ADU-PC-202", "tipo": "ESCRITORIO", "marca_modelo": "Dell Optiplex",
                                                   "usuario_id": usuario_id("maria.andrade")}, headers=ha).json()
    comun = client.post(f"{API}/inventario", json={"codigo": "ADU-IMP-01", "tipo": "IMPRESORA", "marca_modelo": "Epson",
                                                   "compartido": True}, headers=ha).json()
    # El analista solo ve el equipo asignado a él, en la lista y en la ficha
    assert [e["codigo"] for e in client.get(f"{API}/inventario", headers=hd).json()] == ["ADU-PC-201"]
    assert [e["codigo"] for e in client.get(f"{API}/inventario", params={"texto": "Dell"}, headers=hd).json()] == []
    assert client.get(f"{API}/inventario/{propio['id']}", headers=hd).status_code == 200
    assert client.get(f"{API}/inventario/{ajeno['id']}", headers=hd).status_code == 404
    assert client.get(f"{API}/inventario/{comun['id']}", headers=hd).status_code == 404
    # Gerencia tampoco ve el inventario completo; el administrador sí
    assert client.get(f"{API}/inventario", headers=hg).json() == []
    assert {"ADU-PC-201", "ADU-PC-202", "ADU-IMP-01"} <= {e["codigo"] for e in client.get(f"{API}/inventario", headers=ha).json()}
    # Al crear un ticket, el analista elige entre su equipo y los compartidos, no los de otras personas
    opciones = [o["codigo"] for o in client.get(f"{API}/inventario/opciones", headers=hd).json()]
    assert opciones == ["ADU-PC-201", "ADU-IMP-01"]
    assert [o["codigo"] for o in client.get(f"{API}/inventario/opciones", params={"solicitante_id": usuario_id("maria.andrade")},
                                            headers=hd).json()] == ["ADU-PC-201", "ADU-IMP-01"]
    cid, sid = ids(client, hd, "CLASIF_ARANCEL", "Presentación DAI")
    body = {"asunto": "Equipo lento", "descripcion": "El equipo está muy lento desde ayer.", "categoria_id": cid, "subcategoria_id": sid}
    assert client.post(f"{API}/tickets", json={**body, "equipo_id": ajeno["id"]}, headers=hd).status_code in (403, 422)
    assert client.post(f"{API}/tickets", json={**body, "equipo_id": propio["id"]}, headers=hd).status_code == 201
    # El administrador sigue eligiendo cualquier equipo al registrar en nombre de otra persona
    assert "ADU-PC-202" in [o["codigo"] for o in client.get(f"{API}/inventario/opciones", params={"solicitante_id": usuario_id("maria.andrade")},
                                                            headers=ha).json()]
    assert area_id
