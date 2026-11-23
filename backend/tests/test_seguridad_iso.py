"""Auditoría de seguridad 2026-11 y mejora 37 (ISO 27001 A.5.17, A.8.5): contraseñas, avisos de bloqueo,
cuenta de emergencia, plazo de gracia de la verificación en dos pasos y contraseña temporal."""
import pytest
from sqlalchemy import select

from app.application.services import formulario_service as fs
from app.core.config import settings
from app.core.security import datos_personales, validar_politica_clave
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API, CLAVE
from tests.test_cuarta_ronda import entrar, politica
from tests.test_formulario_web import enviar, solicitud


def cambiar(client, h, actual, nueva):
    return client.post(f"{API}/auth/cambiar-clave", json={"clave_actual": actual, "clave_nueva": nueva}, headers=h)


def token(client, usuario, clave=CLAVE):
    r = client.post(f"{API}/auth/login", json={"correo": f"{usuario}@aducorp.com.ec", "clave": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_claves_obvias_se_rechazan():
    assert validar_politica_clave("Aduc0rp#2027") and validar_politica_clave("P@ssw0rd!2026x")
    assert validar_politica_clave("Mi#Clave2026") and validar_politica_clave("Ab#123456789")
    personales = datos_personales("Luis Paredes", "luis.paredes@aducorp.com.ec")
    assert validar_politica_clave("Paredes#2026x", personales)
    assert not validar_politica_clave("Tortuga#Verde81", personales)


def test_no_repetir_ultimas_contrasenas(client):
    h = token(client, "luis.paredes")
    claves = ["Tortuga#Verde81", "Montaña#Azul82", "Rio-Claro#83x"]
    actual = CLAVE
    for c in claves:
        r = cambiar(client, h, actual, c)
        assert r.status_code == 200, r.text
        h, actual = {"Authorization": f"Bearer {r.json()['access_token']}"}, c
    r = cambiar(client, h, actual, "Tortuga#Verde81")          # de hace dos cambios
    assert r.status_code == 422 and "últimas 5" in r.json()["detail"]
    assert cambiar(client, h, actual, CLAVE).status_code == 422  # la original también
    with SessionLocal() as s:
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == "luis.paredes@aducorp.com.ec"))
        assert len(s.scalars(select(m.UsuarioClavePrevia).where(m.UsuarioClavePrevia.usuario_id == u.id)).all()) == 3


def test_bloqueo_avisa_al_usuario_por_correo(client):
    for _ in range(5):
        client.post(f"{API}/auth/login", json={"correo": "luis.paredes@aducorp.com.ec", "clave": "Mala#Clave1"})
    with SessionLocal() as s:
        aviso = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "CUENTA_BLOQUEADA"))
        assert aviso is not None and aviso.para == "luis.paredes@aducorp.com.ec" and "5 intentos" in aviso.cuerpo_html
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "CUENTA_BLOQUEADA"))


def test_ingreso_con_cuenta_de_emergencia_avisa_a_ti(client):
    with SessionLocal() as s:
        s.merge(m.Configuracion(clave="seguridad.correos_alerta", valor="squezada@aducorp.com.ec", descripcion="x"))
        s.commit()
    assert "access_token" in entrar(client, "admin").json()
    with SessionLocal() as s:
        aviso = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "LOGIN_EMERGENCIA"))
        assert aviso is not None and aviso.para == "squezada@aducorp.com.ec"
    # Un usuario normal no genera aviso
    entrar(client, "maria.andrade")
    with SessionLocal() as s:
        assert len(s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "LOGIN_EMERGENCIA")).all()) == 1


def test_plazo_de_gracia_para_la_verificacion(client, como, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    politica(client, como("admin"), obligatoria_admin=True, dias_gracia=7)
    r = entrar(client, "supervisor.operativo").json()          # supervisor sin 2FA: entra y ve cuántos días le quedan
    assert "access_token" in r, r
    assert r["usuario"]["dosf_dias_restantes"] == 7
    with SessionLocal() as s:                        # pasado el plazo se le exige al entrar
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == "supervisor.operativo@aducorp.com.ec"))
        from datetime import timedelta
        u.dosf_exigido_desde = u.dosf_exigido_desde - timedelta(days=8)
        s.commit()
    assert entrar(client, "supervisor.operativo").json()["segundo_paso"]["modo"] == "ACTIVAR"


def test_clave_temporal_bloquea_la_api(client, como):
    r = client.post(f"{API}/admin/usuarios/{_id('luis.paredes')}/restablecer-clave", headers=como("admin"))
    assert r.status_code == 200, r.text
    temporal = r.json()["clave_temporal"]
    h = token(client, "luis.paredes", temporal)
    assert client.get(f"{API}/tickets", headers=h).status_code == 403
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200
    r = cambiar(client, h, temporal, "Tortuga#Verde81")
    assert r.status_code == 200
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/tickets", headers=h2).status_code == 200


def _id(usuario):
    with SessionLocal() as s:
        return s.scalar(select(m.Usuario.id).where(m.Usuario.correo == f"{usuario}@aducorp.com.ec"))


@pytest.fixture
def sin_limites():
    fs.reiniciar_limites()
    yield
    fs.reiniciar_limites()


def test_acuse_del_formulario_no_repite_lo_que_escribio_la_persona(client, sin_limites):
    r = enviar(client, solicitud(nombre="Banco: su cuenta será bloqueada", asunto="Actualice su clave en http://falso.example"))
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        acuse = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACUSE_WEB"))
        assert "falso.example" not in acuse.asunto and "falso.example" not in acuse.cuerpo_html
        assert "Banco" not in acuse.cuerpo_html


def test_limite_global_del_formulario(client, sin_limites, monkeypatch):
    monkeypatch.setattr(settings, "FORMULARIO_WEB_MAX_GLOBAL_HORA", 2)
    for i in range(2):
        assert enviar(client, solicitud(correo=f"p{i}@empresa{i}.com")).status_code == 201
    assert enviar(client, solicitud(correo="otro@empresa9.com")).status_code == 429
