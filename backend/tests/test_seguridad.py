"""Pruebas de endurecimiento de seguridad (Fase 6)."""
from app.application.services.export_service import csv_bytes, seguro
from app.domain.archivos import contenido_valido, mime_descarga
from tests.conftest import API, CLAVE
from tests.test_api import crear_ticket


def test_limite_de_intentos_de_login(client, db):
    from app.core.config import settings

    for _ in range(settings.LOGIN_MAX_POR_MINUTO):
        client.post(f"{API}/auth/login", json={"correo": "nadie@aducorp.com.ec", "clave": "x"})
    r = client.post(f"{API}/auth/login", json={"correo": "admin@aducorp.com.ec", "clave": CLAVE})
    assert r.status_code == 429


def test_ip_de_proxy_solo_desde_proxy_confiable(client, db):
    from app.infrastructure.db import models as m
    from app.infrastructure.db.session import SessionLocal

    # El cliente de pruebas se considera proxy confiable: se toma X-Real-IP
    client.post(f"{API}/auth/login", json={"correo": "admin@aducorp.com.ec", "clave": CLAVE}, headers={"X-Real-IP": "10.1.2.3"})
    with SessionLocal() as s:
        ultima = s.query(m.Auditoria).order_by(m.Auditoria.id.desc()).first()
        assert ultima.ip == "10.1.2.3"


def test_ip_no_confiable_ignora_cabeceras():
    from starlette.requests import Request

    from app.api.deps import ip_cliente

    req = Request({"type": "http", "headers": [(b"x-forwarded-for", b"1.1.1.1")], "client": ("203.0.113.9", 5000)})
    assert ip_cliente(req) == "203.0.113.9"
    req = Request({"type": "http", "headers": [(b"x-forwarded-for", b"1.1.1.1, 172.18.0.2")], "client": ("172.18.0.5", 5000)})
    assert ip_cliente(req) == "1.1.1.1"


def test_firma_de_archivos():
    assert contenido_valido("pdf", b"%PDF-1.7 ...")
    assert not contenido_valido("pdf", b"<html><script>")
    assert not contenido_valido("txt", b"MZ\x90\x00")          # ejecutable renombrado
    assert not contenido_valido("png", b"GIF89a")
    assert contenido_valido("txt", b"hola")
    assert mime_descarga("text/html") == "application/octet-stream"
    assert mime_descarga("application/pdf") == "application/pdf"


def test_adjunto_con_contenido_falso_y_descarga_segura(client, como):
    h = como("maria.andrade")
    t = crear_ticket(client, h)
    url = f"{API}/tickets/{t['id']}/adjuntos"
    r = client.post(url, files={"archivo": ("factura.pdf", b"<html><script>alert(1)</script>", "application/pdf")}, headers=h)
    assert r.status_code == 422
    r = client.post(url, files={"archivo": ("nota.txt", b"texto plano", "text/html")}, headers=h)
    assert r.status_code == 201
    adj = r.json()["adjuntos"][0]
    r = client.get(f"{url}/{adj['id']}", headers=h)
    assert r.headers["content-type"].startswith("application/octet-stream")
    assert r.headers["content-disposition"].startswith("attachment")


def test_otro_cliente_no_ve_ni_adjunta(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    otro = como("luis.paredes")
    assert client.get(f"{API}/tickets/{t['id']}", headers=otro).status_code in (403, 404)
    r = client.post(f"{API}/tickets/{t['id']}/adjuntos", files={"archivo": ("a.pdf", b"%PDF-1", "application/pdf")}, headers=otro)
    assert r.status_code in (403, 404)


def test_inyeccion_de_formulas_en_exportaciones():
    assert seguro("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert seguro("+5") == "'+5" and seguro("normal") == "normal" and seguro(5) == 5
    assert b"'=1+1" in csv_bytes([("a", "A")], [{"a": "=1+1"}])


def test_cabeceras_de_seguridad(client, db):
    r = client.get(f"{API}/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_token_manipulado_es_rechazado(client, como):
    h = como("maria.andrade")
    token = h["Authorization"].split()[1]
    cabecera, cuerpo, firma = token.split(".")
    malo = f"{cabecera}.{cuerpo}.{firma[:-2]}xx"
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {malo}"}).status_code == 401
    import base64, json
    sin_firma = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {sin_firma}.{cuerpo}."}).status_code == 401


def test_usuario_desactivado_pierde_acceso_inmediato(client, como):
    h = como("maria.andrade")
    admin = como("admin")
    uid = client.get(f"{API}/auth/me", headers=h).json()["id"]
    assert client.patch(f"{API}/admin/usuarios/{uid}", json={"activo": False}, headers=admin).status_code == 200
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401


def test_politica_de_bloqueo_desde_configuracion(client, como):
    r = client.put(f"{API}/admin/configuracion", headers=como("admin"), json={"valores": {"seguridad.max_intentos": "2"}})
    assert r.status_code == 200, r.text
    for _ in range(2):
        assert client.post(f"{API}/auth/login", json={"correo": "gerencia@aducorp.com.ec", "clave": "mala"}).status_code == 401
    r = client.post(f"{API}/auth/login", json={"correo": "gerencia@aducorp.com.ec", "clave": CLAVE})
    assert r.status_code == 401 and "bloqueada" in r.json()["detail"]
