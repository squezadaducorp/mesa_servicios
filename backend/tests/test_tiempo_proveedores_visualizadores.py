"""Control de tiempo (31), proveedores y contratos (33), visualizadores (34) y artículos internos/externos (35)."""
from datetime import date, timedelta

from sqlalchemy import select

from app.application.services.panel_service import PanelService
from app.application.services.proveedor_service import ProveedorService
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API, login
from tests.test_api import crear_ticket
from tests.test_segunda_ronda import correos


def responsable(client, ha, t) -> tuple[str, dict]:
    d = client.get(f"{API}/tickets/{t['id']}", headers=ha).json()
    correo = d["responsable"]["correo"]
    return correo.split("@")[0], d


def mover(modelo, fila_id: int, **campos) -> None:
    with SessionLocal() as s:
        f = s.get(modelo, fila_id)
        for k, v in campos.items():
            setattr(f, k, v)
        s.commit()


# ================================================================== 31 control de tiempo
def test_cronometro_registros_y_reporte(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    t1, t2 = crear_ticket(client, hm), crear_ticket(client, hm, asunto="Otra DAI por transmitir")
    analista, _ = responsable(client, ha, t1)
    hr = como(analista)
    # El solicitante no registra tiempo
    assert client.get(f"{API}/tiempo/ticket/{t1['id']}", headers=hm).status_code == 403

    r = client.post(f"{API}/tiempo/ticket/{t1['id']}/iniciar", json={"actividad": "Diagnóstico en sitio"}, headers=hr)
    assert r.status_code == 200, r.text
    activo = r.json()["activo"]
    assert activo["estado"] == "CORRIENDO" and activo["actividad"] == "Diagnóstico en sitio"
    mover(m.TiempoRegistro, activo["id"], corriendo_desde=utcnow() - timedelta(minutes=42))
    assert client.get(f"{API}/tiempo/activo", headers=hr).json()["activo"]["minutos"] == 42

    # Un cronómetro a la vez: al iniciar en otro ticket, el primero se pausa solo
    otro, _ = responsable(client, ha, t2)
    if otro == analista:
        client.post(f"{API}/tiempo/ticket/{t2['id']}/iniciar", json={"actividad": "Revisión"}, headers=hr)
        assert client.get(f"{API}/tiempo/ticket/{t1['id']}", headers=hr).json()["activo"]["estado"] == "PAUSADO"
        client.post(f"{API}/tiempo/registros/{activo['id']}/reanudar", headers=hr)

    # A mano y ajustes del ticket
    d = client.post(f"{API}/tiempo/ticket/{t1['id']}/manual", json={"actividad": "Pausar OneDrive en 4 equipos", "minutos": 25},
                    headers=hr).json()
    d = client.put(f"{API}/tiempo/ticket/{t1['id']}/ajustes", json={"estimado_min": 120, "facturable": True}, headers=hr).json()
    assert d["total_min"] == 67 and d["estimado_min"] == 120 and d["facturable"] is True

    # Pasar a «Pendiente cliente» pausa el cronómetro
    r = client.post(f"{API}/tickets/{t1['id']}/estado", json={"estado": "PENDIENTE_CLIENTE", "comentario": "¿Le pasa a todo el equipo?"},
                    headers=hr)
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/tiempo/ticket/{t1['id']}", headers=hr).json()
    assert d["activo"]["estado"] == "PAUSADO" and d["en_atencion"] is False
    assert client.post(f"{API}/tiempo/registros/{activo['id']}/reanudar", headers=hr).status_code == 422
    r = client.post(f"{API}/tiempo/registros/{activo['id']}/detener", headers=hr).json()
    assert r["registro"]["estado"] == "GUARDADO" and r["registro"]["minutos"] == 42
    # Corrige sus minutos; otro analista no puede
    reg = next(x for x in d["registros"] if x["manual"])
    assert client.put(f"{API}/tiempo/registros/{reg['id']}", json={"minutos": 30}, headers=hr).json()["registro"]["minutos"] == 30
    with SessionLocal() as s:
        ajeno = next(u.correo.split("@")[0] for u in s.scalars(select(m.Usuario)).unique()
                     if u.rol.codigo == "ANALISTA" and not u.correo.startswith(analista + "@"))
    assert client.put(f"{API}/tiempo/registros/{reg['id']}", json={"minutos": 1}, headers=como(ajeno)).status_code == 403

    # Reporte semanal (supervisores y administración)
    assert client.get(f"{API}/tiempo/reporte", headers=hr).status_code == 403
    rep = client.get(f"{API}/tiempo/reporte", headers=ha).json()
    assert rep["kpis"]["tickets"] >= 1 and rep["kpis"]["minutos"] >= 72 and rep["kpis"]["facturable_min"] >= 72
    fila = next(a for a in rep["analistas"] if a["nombre"] == d["registros"][0]["usuario"]["nombre"])
    assert fila["min_incidentes"] >= 72 and fila["ocupacion_pct"] is not None
    assert rep["areas"] and rep["categorias"]
    x = client.get(f"{API}/tiempo/reporte/excel", headers=ha)
    assert x.status_code == 200 and x.content[:2] == b"PK"


def test_cerrar_sesion_pausa_el_cronometro(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    t = crear_ticket(client, hm)
    analista, _ = responsable(client, ha, t)
    r = client.post(f"{API}/auth/login", json={"correo": f"{analista}@aducorp.com.ec", "clave": "Aducorp2026!"}).json()
    h = {"Authorization": f"Bearer {r['access_token']}"}
    client.post(f"{API}/tiempo/ticket/{t['id']}/iniciar", json={"actividad": "Atención"}, headers=h)
    assert client.post(f"{API}/auth/logout", json={"refresh_token": r["refresh_token"]}, headers=h).status_code == 200
    h2 = login(client, analista)
    assert client.get(f"{API}/tiempo/activo", headers=h2).json()["activo"]["estado"] == "PAUSADO"


# ================================================================== 33 proveedores
PROVEEDOR = {"nombre": "Netlife", "servicio": "Internet corporativo Guayaquil", "telefono": "1700 NETLIFE",
             "correo": "soporte.empresas@netlife.ec", "correos_copia": ["ejecutivo@netlife.ec"], "contacto": "Ing. Paúl Reyes 099 812 4471",
             "contrato_numero": "CT-2025-031", "atencion_24x7": True, "plazo_horas": 4, "valor_mensual": 189,
             "multa_pct_hora": 5, "contrato_detalle": "20 Mbps simétrico"}


def test_escalar_a_proveedor_pausa_sla_y_mide_plazo(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    assert client.post(f"{API}/proveedores", json=PROVEEDOR, headers=hm).status_code == 403
    p = client.post(f"{API}/proveedores", json={**PROVEEDOR, "contrato_vence": str(date.today() + timedelta(days=200))}, headers=ha)
    assert p.status_code == 201, p.text
    p = p.json()
    t = crear_ticket(client, hm, asunto="Sin internet en la oficina de Guayaquil")
    analista, _ = responsable(client, ha, t)
    hr = como(analista)
    d = client.get(f"{API}/tickets/{t['id']}", headers=hr).json()
    assert "escalar_proveedor" in d["acciones"]
    opciones = client.get(f"{API}/proveedores/ticket/{t['id']}", headers=hr).json()
    netlife = next(x for x in opciones["proveedores"] if x["id"] == p["id"])
    assert netlife["caida_mes"] == 1 and netlife["plazo"] == "4 h" and "Teléfono 1700 NETLIFE" in netlife["medios"]

    r = client.post(f"{API}/proveedores/ticket/{t['id']}/escalar",
                    json={"proveedor_id": p["id"], "numero_caso": "NL-4471829", "reporte": "Enlace de fibra caído desde 10:05",
                          "medio": "Teléfono 1700 NETLIFE", "contacto": "Ing. Paúl Reyes", "enviar_correo": True}, headers=hr)
    assert r.status_code == 201, r.text
    caso = r.json()
    assert caso["correo_enviado"] and correos("Reporte de falla · Netlife")
    d = client.get(f"{API}/tickets/{t['id']}", headers=hm).json()   # el solicitante ve en manos de quién está
    assert d["estado"] == "ESCALADO" and d["sla_pausado"] and d["proveedor_caso"]["numero_caso"] == "NL-4471829"
    assert "escalar_proveedor" not in client.get(f"{API}/tickets/{t['id']}", headers=hr).json()["acciones"]

    # El proveedor se pasa del plazo: aviso al responsable y multa reclamable
    inicio = utcnow() - timedelta(hours=5, minutes=30)
    mover(m.ProveedorCaso, caso["id"], fecha_reporte=inicio, vence=inicio + timedelta(hours=4))
    with SessionLocal() as s:
        assert ProveedorService(s).procesar()["avisos_plazo"] == 1
        s.commit()
    r = client.post(f"{API}/proveedores/casos/{caso['id']}/resolver", json={"solucion": "Cambiaron el ONT"}, headers=hr)
    assert r.status_code == 200, r.text
    assert r.json()["cumplido"] is False and r.json()["multa"] == 18.9   # 189 × 5 % × 2 h (1 h 30 min fuera de plazo)
    d = client.get(f"{API}/tickets/{t['id']}", headers=hr).json()
    assert d["estado"] == "EN_PROCESO" and not d["sla_pausado"] and d["proveedor_caso"] is None

    ficha = client.get(f"{API}/proveedores/{p['id']}", headers=ha).json()
    assert ficha["caidas_anio"] == 1 and ficha["fuera_plazo_anio"] == 1 and ficha["multas_anio"] == 18.9
    assert ficha["cumplimiento"] == "AL_LIMITE"
    lista = client.get(f"{API}/proveedores", headers=ha).json()
    assert lista["proveedores"][0]["casos_abiertos"] == 0 and lista["alertas"] == []
    with SessionLocal() as s:
        hoy = date.today()
        datos = PanelService(s).datos(hoy.year, hoy.month)
        assert datos["proveedores"][0]["nombre"] == "Netlife" and datos["proveedores"][0]["fuera"] == 1


def test_resolver_ticket_escalado_cierra_el_caso(client, como):
    ha, hm = como("admin"), como("maria.andrade")
    p = client.post(f"{API}/proveedores", json={**PROVEEDOR, "atencion_24x7": False, "plazo_horas": 8}, headers=ha).json()
    t = crear_ticket(client, hm)
    analista, _ = responsable(client, ha, t)
    hr = como(analista)
    client.post(f"{API}/proveedores/ticket/{t['id']}/escalar", json={"proveedor_id": p["id"], "reporte": "Falla del enlace"}, headers=hr)
    r = client.post(f"{API}/tickets/{t['id']}/estado", json={"estado": "RESUELTO", "comentario": "Ya funciona"}, headers=hr)
    assert r.status_code == 200, r.text
    with SessionLocal() as s:
        c = s.scalar(select(m.ProveedorCaso).where(m.ProveedorCaso.ticket_id == t["id"]))
        assert c.estado == "RESUELTO" and c.cumplido is True


def test_contrato_por_vencer_avisa_una_vez(client, como):
    ha = como("admin")
    client.post(f"{API}/proveedores", json={**PROVEEDOR, "contrato_vence": str(date.today() + timedelta(days=20))}, headers=ha)
    with SessionLocal() as s:
        assert ProveedorService(s).procesar()["avisos_contrato"] == 1
        s.commit()
    with SessionLocal() as s:
        assert ProveedorService(s).procesar()["avisos_contrato"] == 0
    assert len(correos("Contrato con Netlife vence en 20 días")) == 1
    alerta = client.get(f"{API}/proveedores", headers=ha).json()["alertas"][0]
    assert alerta["dias"] == 20 and alerta["avisado"]


# ================================================================== 34 visualizadores
def test_visualizador_ve_comenta_y_recibe_avisos(client, como):
    ha, hm, hl = como("admin"), como("maria.andrade"), como("luis.paredes")
    t = crear_ticket(client, hm)
    analista, d = responsable(client, ha, t)
    hr = como(analista)
    client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Nota solo para TI", "es_interno": True}, headers=hr)
    assert client.get(f"{API}/tickets/{t['id']}", headers=hl).status_code == 404   # Luis no lo ve por su rol

    candidatos = client.get(f"{API}/tickets/{t['id']}/visualizadores/candidatos?q=luis", headers=hr).json()
    luis = next(x for x in candidatos if x["nombre"].startswith("Luis"))
    r = client.post(f"{API}/tickets/{t['id']}/visualizadores", json={"usuario_id": luis["id"], "avisos_correo": "TODO"}, headers=hr)
    assert r.status_code == 200, r.text
    assert r.json()["visualizadores"][0]["nombre"].startswith("Luis")
    assert any("como visualizador" in (h["detalle"] or "") for h in r.json()["historial"])
    # Un cliente no agrega visualizadores a tickets ajenos
    assert client.post(f"{API}/tickets/{t['id']}/visualizadores", json={"usuario_id": luis["id"]}, headers=hl).status_code == 403

    d = client.get(f"{API}/tickets/{t['id']}", headers=hl).json()
    assert d["es_visualizador"] and "comentar" in d["acciones"] and "dejar_seguir" in d["acciones"]
    assert "cambiar_estado" not in d["acciones"] and "nota_interna" not in d["acciones"] and "calificar" not in d["acciones"]
    assert all(not c["es_interno"] for c in d["comentarios"])
    assert client.post(f"{API}/tickets/{t['id']}/estado", json={"estado": "EN_PROCESO"}, headers=hl).status_code == 403
    assert client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Nota", "es_interno": True}, headers=hl).status_code == 403
    r = client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Es urgente: la DAI sale hoy"}, headers=hl)
    assert r.status_code in (200, 201), r.text
    d = client.get(f"{API}/tickets/{t['id']}", headers=hr).json()
    assert next(c for c in d["comentarios"] if c["texto"].startswith("Es urgente"))["de_visualizador"]

    # Lista «Siguiendo» y avisos por correo
    assert [x["id"] for x in client.get(f"{API}/tickets?siguiendo=true", headers=hl).json()["items"]] == [t["id"]]
    antes = len(correos("Novedad en un ticket que sigue"))
    client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Reinstalé el controlador del token"}, headers=hr)
    assert len(correos("Novedad en un ticket que sigue")) == antes + 1   # TODO: también las respuestas
    client.put(f"{API}/tickets/{t['id']}/visualizadores/{luis['id']}", json={"avisos_correo": "ESTADO"}, headers=hl)
    client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Sigo revisando"}, headers=hr)
    assert len(correos("Novedad en un ticket que sigue")) == antes + 1   # ESTADO: las respuestas solo en la campana
    client.post(f"{API}/tickets/{t['id']}/estado", json={"estado": "RESUELTO", "comentario": "Listo"}, headers=hr)
    assert len(correos("Novedad en un ticket que sigue")) == antes + 2

    # Dejar de seguir: ya no lo ve
    r = client.delete(f"{API}/tickets/{t['id']}/visualizadores/{luis['id']}", headers=hl)
    assert r.status_code == 200 and r.json()["visible"] is False
    assert client.get(f"{API}/tickets/{t['id']}", headers=hl).status_code == 404


def test_seguir_y_visualizadores_por_categoria(client, como):
    ha, hm, hg = como("admin"), como("maria.andrade"), como("gerencia")
    t = crear_ticket(client, hm)
    d = client.get(f"{API}/tickets/{t['id']}", headers=hg).json()
    assert "seguir" in d["acciones"]
    d = client.post(f"{API}/tickets/{t['id']}/seguir", json={"avisos_correo": "NINGUNO"}, headers=hg).json()
    assert d["es_visualizador"] and d["visualizadores"][0]["origen"] == "SEGUIR"

    # La categoría agrega visualizadores a cada ticket nuevo
    cat = client.get(f"{API}/admin/categorias", headers=ha).json()
    cat = cat[0] if isinstance(cat, list) else cat["items"][0]
    luis = client.get(f"{API}/admin/usuarios?texto=luis", headers=ha).json()["items"][0]
    cuerpo = {k: cat[k] for k in ("codigo", "nombre", "descripcion", "palabras_clave", "color", "orden", "modo_asignacion", "activo",
                                  "correos_copia", "pide_equipo", "restringida_en_nombre")}
    cuerpo.update(supervisor_id=cat["supervisor"]["id"] if cat.get("supervisor") else None, visualizadores=[luis["id"]],
                  responsables=[{"usuario_id": r["usuario_id"], "es_principal": r["es_principal"]} for r in cat["responsables"]])
    r = client.put(f"{API}/admin/categorias/{cat['id']}", json=cuerpo, headers=ha)
    assert r.status_code == 200, r.text
    sub = cat["subcategorias"][0]["nombre"]
    t2 = crear_ticket(client, hm, cat=cat["codigo"], sub=sub)
    d = client.get(f"{API}/tickets/{t2['id']}", headers=como("luis.paredes")).json()
    assert d["es_visualizador"] and d["visualizadores"][0]["origen"] == "CATEGORIA"


# ================================================================== 35 artículos internos y externos
def articulo(client, h, **extra):
    body = {"titulo": "Reinstalar el controlador del token ePass2003", "sintoma": "La firma de la DAI falla con el token",
            "solucion": "1. Desinstalar ePass2003 Token Manager. 2. Instalar la versión 1.1.22. 3. Volver a vincular el token.",
            "palabras_clave": "token, firma, epass, dai", "estado": "PUBLICADO", "visibilidad": "INTERNO", **extra}
    return client.post(f"{API}/conocimiento", json=body, headers=h)


def test_articulos_internos_para_todo_el_personal(client, como):
    ha, hm, hs = como("admin"), como("maria.andrade"), como("supervisor.tecnico")
    t = crear_ticket(client, hm)
    analista, _ = responsable(client, ha, t)
    hr = como(analista)

    interno = articulo(client, hr)
    assert interno.status_code == 201, interno.text
    interno = interno.json()
    # Un analista no publica externos; un supervisor sí
    assert articulo(client, hr, visibilidad="EXTERNO").status_code == 403
    assert articulo(client, hr, visibilidad="EXTERNO", estado="BORRADOR").status_code == 201
    externo = articulo(client, hs, visibilidad="EXTERNO", titulo="Cómo volver a firmar la DAI con el token",
                       solucion="Desconecte el token, reinicie el equipo y vuelva a firmar. Si sigue, responda al ticket.",
                       articulo_relacionado_id=interno["id"])
    assert externo.status_code == 201, externo.text
    externo = externo.json()
    assert client.get(f"{API}/conocimiento/{interno['id']}", headers=hr).json()["articulo_relacionado_id"] == externo["id"]

    # El solicitante solo ve los externos, también en las sugerencias
    assert client.get(f"{API}/conocimiento/{interno['id']}", headers=hm).status_code == 404
    vistos = {a["id"] for a in client.get(f"{API}/conocimiento", headers=hm).json()}
    assert externo["id"] in vistos and interno["id"] not in vistos
    sug = client.post(f"{API}/conocimiento/sugerir", json={"texto": "no puedo firmar la dai con el token"}, headers=hm).json()
    assert interno["id"] not in {a["id"] for a in sug}
    assert client.get(f"{API}/conocimiento/{externo['id']}", headers=hm).json()["articulo_relacionado_id"] is None

    # Una respuesta al solicitante no lleva el enlace de un artículo interno (en una nota interna sí)
    texto = f"Siga estos pasos: https://mesa.aducorp.com.ec/conocimiento?articulo={interno['id']}"
    assert client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": texto}, headers=hr).status_code == 422
    assert client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": texto, "es_interno": True}, headers=hr).status_code in (200, 201)

    # Todo el personal de Aducorp (no solo TI) ve los internos publicados; escribe quien tenga kb.gestionar
    hg = como("gerencia")
    assert client.get(f"{API}/conocimiento/{interno['id']}", headers=hg).status_code == 200
    assert articulo(client, hg).status_code == 403
    borrador = articulo(client, hr, estado="BORRADOR", titulo="Borrador del procedimiento del token").json()
    assert client.get(f"{API}/conocimiento/{borrador['id']}", headers=hg).status_code == 404   # los borradores, solo quien escribe
    assert client.get(f"{API}/conocimiento/{borrador['id']}", headers=hr).status_code == 200
