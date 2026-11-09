"""Formulario público /solicitud: personas sin cuenta registran tickets (ficha anti-spam, trampa y límites)."""
import time

import pytest
from sqlalchemy import select

from app.application.services import formulario_service as fs
from app.core.config import settings
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API


@pytest.fixture(autouse=True)
def limpio():
    fs.reiniciar_limites()
    yield
    fs.reiniciar_limites()


def ficha_madura() -> str:
    return fs.emitir_ficha(time.time() - 60)


def solicitud(**cambios) -> dict:
    datos = {"nombre": "María Pérez", "correo": "maria@importadora.com", "telefono": "0991234567", "empresa": "Importadora del Pacífico",
             "asunto": "Consulta sobre garantía aduanera", "descripcion": "Necesitamos renovar la garantía aduanera del trámite en ECUAPASS.",
             "token": ficha_madura()}
    datos.update(cambios)
    return datos


def test_formulario_entrega_categorias_y_ficha(client):
    r = client.get(f"{API}/publico/formulario")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["habilitado"] and d["categorias"] and d["categorias"][0]["subcategorias"]
    assert fs.ficha_valida(d["token"], time.time() + 10)


def test_registra_ticket_sin_cuenta_con_acuse_y_respuestas(client, como):
    r = client.post(f"{API}/publico/tickets", json=solicitud())
    assert r.status_code == 201, r.text
    numero = r.json()["numero"]
    with SessionLocal() as s:
        t = s.scalar(select(m.Ticket).where(m.Ticket.numero == numero))
        assert t.canal == "WEB" and t.correo == "maria@importadora.com" and t.solicitante_nombre == "María Pérez"
        assert t.solicitante.correo == settings.FORMULARIO_WEB_CORREO and t.solicitante.clave_hash is None
        assert "Importadora del Pacífico" in t.descripcion and t.responsable is not None
        acuse = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACUSE_WEB"))
        assert acuse.para == "maria@importadora.com"
        assert not s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.para == settings.FORMULARIO_WEB_CORREO))
        tid, responsable = t.id, t.responsable.correo.split("@")[0]

    r = client.post(f"{API}/tickets/{tid}/comentarios", json={"texto": "Envíenos la póliza vigente."}, headers=como(responsable))
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/tickets/{tid}/comentarios", json={"texto": "Nota solo para el equipo", "es_interno": True}, headers=como(responsable))
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        resp = list(s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "RESPUESTA_WEB")))
        assert len(resp) == 1 and resp[0].para == "maria@importadora.com" and "póliza vigente" in resp[0].cuerpo_html
        assert not s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.para == settings.FORMULARIO_WEB_CORREO))


def test_categoria_elegida_por_el_solicitante(client):
    form = client.get(f"{API}/publico/formulario").json()
    cat = form["categorias"][-1]
    r = client.post(f"{API}/publico/tickets", json=solicitud(categoria_id=cat["id"], subcategoria_id=cat["subcategorias"][0]["id"]))
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        assert s.scalar(select(m.Ticket).where(m.Ticket.numero == r.json()["numero"])).categoria_id == cat["id"]


@pytest.mark.parametrize("cambios", [
    lambda: {"token": "123.abc"},                                   # firma falsa
    lambda: {"token": fs.emitir_ficha()},                           # enviado al instante (robot)
    lambda: {"token": fs.emitir_ficha(time.time() - 3 * 3600)},     # ficha vencida
    lambda: {"sitio_web": "http://spam.example"},                   # campo trampa lleno
])
def test_rechaza_robots(client, cambios):
    r = client.post(f"{API}/publico/tickets", json=solicitud(**cambios()))
    assert r.status_code == 422, r.text
    with SessionLocal() as s:
        assert not s.scalar(select(m.Ticket).where(m.Ticket.canal == "WEB"))


def test_limite_por_hora(client, monkeypatch):
    monkeypatch.setattr(fs, "limitador_ip", fs.Limitador(2, 3600))
    for i in range(2):
        assert client.post(f"{API}/publico/tickets", json=solicitud(correo=f"p{i}@x.com")).status_code == 201
    r = client.post(f"{API}/publico/tickets", json=solicitud(correo="otro@x.com"))
    assert r.status_code == 429


def test_formulario_deshabilitado(client, monkeypatch):
    monkeypatch.setattr(settings, "FORMULARIO_WEB_ENABLED", False)
    assert client.get(f"{API}/publico/formulario").status_code == 404
    assert client.post(f"{API}/publico/tickets", json=solicitud()).status_code == 404
