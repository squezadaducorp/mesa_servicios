"""Formulario público /solicitud: personas sin cuenta registran tickets (ficha anti-spam, trampa, límites y adjuntos)."""
import json
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


def enviar(client, datos: dict, archivos: list[tuple[str, bytes, str]] | None = None):
    files = [("archivos", a) for a in (archivos or [])]
    return client.post(f"{API}/publico/tickets", data={"datos": json.dumps(datos)}, files=files or None)


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_formulario_entrega_categorias_y_ficha(client):
    r = client.get(f"{API}/publico/formulario")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["habilitado"] and d["categorias"] and d["categorias"][0]["subcategorias"]
    assert fs.ficha_valida(d["token"], time.time() + 10)


def test_registra_ticket_sin_cuenta_con_acuse_y_respuestas(client, como):
    r = enviar(client, solicitud())
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
    r = enviar(client, solicitud(categoria_id=cat["id"], subcategoria_id=cat["subcategorias"][0]["id"]))
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
    r = enviar(client, solicitud(**cambios()))
    assert r.status_code == 422, r.text
    with SessionLocal() as s:
        assert not s.scalar(select(m.Ticket).where(m.Ticket.canal == "WEB"))


def test_limite_por_hora(client, monkeypatch):
    monkeypatch.setattr(fs, "limitador_ip", fs.Limitador(2, 3600))
    for i in range(2):
        assert enviar(client, solicitud(correo=f"p{i}@x.com")).status_code == 201
    r = enviar(client, solicitud(correo="otro@x.com"))
    assert r.status_code == 429


def test_formulario_deshabilitado(client, monkeypatch):
    monkeypatch.setattr(settings, "FORMULARIO_WEB_ENABLED", False)
    assert client.get(f"{API}/publico/formulario").status_code == 404
    assert enviar(client, solicitud()).status_code == 404


def test_formulario_informa_reglas_de_adjuntos(client):
    d = client.get(f"{API}/publico/formulario").json()
    assert d["adjuntos_max"] == settings.FORMULARIO_WEB_ADJUNTOS_MAX
    assert "pdf" in d["adjuntos_extensiones"] and "zip" not in d["adjuntos_extensiones"]


def test_registra_solicitud_con_adjuntos(client):
    r = enviar(client, solicitud(), [("poliza.pdf", PDF, "application/pdf"), ("captura.png", PNG, "image/png")])
    assert r.status_code == 201, r.text
    assert r.json()["adjuntos"] == 2
    with SessionLocal() as s:
        t = s.scalar(select(m.Ticket).where(m.Ticket.numero == r.json()["numero"]))
        adj = list(s.scalars(select(m.TicketAdjunto).where(m.TicketAdjunto.ticket_id == t.id)))
        assert sorted(a.nombre_original for a in adj) == ["captura.png", "poliza.pdf"]
        assert all(a.subido_por == t.solicitante_id for a in adj)


@pytest.mark.parametrize("archivos", [
    [("virus.pdf", b"MZ\x90\x00" + b"\x00" * 32, "application/pdf")],          # ejecutable renombrado
    [("datos.zip", b"PK\x03\x04" + b"\x00" * 32, "application/zip")],           # extensión no admitida en el público
    [("vacio.pdf", b"", "application/pdf")],
    [(f"a{i}.pdf", PDF, "application/pdf") for i in range(4)],                    # más archivos que el máximo
])
def test_rechaza_adjuntos_no_validos_sin_crear_ticket(client, archivos):
    r = enviar(client, solicitud(), archivos)
    assert r.status_code == 422, r.text
    with SessionLocal() as s:
        assert not s.scalar(select(m.Ticket).where(m.Ticket.canal == "WEB"))


def test_rechaza_adjunto_grande(client, monkeypatch):
    monkeypatch.setattr(settings, "FORMULARIO_WEB_ADJUNTOS_MAX_MB", 1)
    r = enviar(client, solicitud(), [("grande.pdf", PDF + b"0" * (1024 * 1024), "application/pdf")])
    assert r.status_code == 422 and "1 MB" in r.text


def test_datos_mal_formados(client):
    r = client.post(f"{API}/publico/tickets", data={"datos": "{no es json"})
    assert r.status_code == 422
