"""Personas en copia (CC): lista por ticket, copia por comentario, copia automática por categoría/cliente y buzón."""
import pytest
from sqlalchemy import select

from app.application.services.buzon_service import BuzonService
from app.core.config import settings
from app.domain.correos import normalizar_correos
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import catalogo, crear_ticket
from tests.test_m365 import GraphFalso, m365, mensaje  # noqa: F401  (fixture)


def correos(plantilla):
    with SessionLocal() as s:
        return list(s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == plantilla).order_by(m.ColaCorreo.id)))


def test_normalizar_correos():
    assert normalizar_correos(" Jefe@Cliente.com; otro@x.ec , jefe@cliente.com ") == ["jefe@cliente.com", "otro@x.ec"]
    assert normalizar_correos(["a@b.co", "c@d.com"]) == ["a@b.co", "c@d.com"]
    for malo in ("sin-arroba", "a@b", "a@@b.com", "a b@c.com,"):
        with pytest.raises(ValueError):
            normalizar_correos(malo if " " not in malo else ["a b@c.com"])
    with pytest.raises(ValueError):
        normalizar_correos([f"u{i}@x.com" for i in range(11)])


def test_lista_de_copias_del_ticket(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    url = f"{API}/tickets/{t['id']}"
    david, maria = como("david.medina"), como("maria.andrade")
    assert "copias" in client.get(url, headers=david).json()["acciones"]
    assert "copias" not in client.get(url, headers=maria).json()["acciones"]

    r = client.put(f"{url}/copias", json={"correos": ["Jefe@Cliente.com", "bodega@cliente.com", "maria.andrade@aducorp.com.ec"]}, headers=david)
    assert r.status_code == 200, r.text
    # El propio solicitante no se copia a sí mismo
    assert [c["correo"] for c in r.json()["copias"]] == ["jefe@cliente.com", "bodega@cliente.com"]
    assert any(h["accion"] == "COPIAS" for h in r.json()["historial"])

    # Quitar uno
    r = client.put(f"{url}/copias", json={"correos": ["jefe@cliente.com"]}, headers=david)
    assert [c["correo"] for c in r.json()["copias"]] == ["jefe@cliente.com"]

    # Validación y permisos
    assert client.put(f"{url}/copias", json={"correos": ["no-es-correo"]}, headers=david).status_code == 422
    assert client.put(f"{url}/copias", json={"correos": ["x@y.com"]}, headers=maria).status_code == 403
    # El solicitante no ve la lista
    assert client.get(url, headers=maria).json()["copias"] == []


def test_comentario_copia_y_trazabilidad(client, como):
    t = crear_ticket(client, como("maria.andrade"))   # ticket del portal: el solicitante no recibe la respuesta por correo
    url = f"{API}/tickets/{t['id']}"
    david = como("david.medina")
    client.put(f"{url}/copias", json={"correos": ["jefe@cliente.com", "bodega@cliente.com"]}, headers=david)

    # Sin lista explícita: van las copias del ticket en un aviso aparte
    r = client.post(f"{url}/comentarios", json={"texto": "Ya transmitimos la DAI."}, headers=david)
    assert r.status_code == 201, r.text
    ultimo = r.json()["comentarios"][-1]
    assert ultimo["copia_a"] == ["jefe@cliente.com", "bodega@cliente.com"]
    aviso = correos("RESPUESTA_COPIA")[-1]
    assert aviso.para == "jefe@cliente.com, bodega@cliente.com" and "Ya transmitimos la DAI." in aviso.cuerpo_html

    # Lista editada para este envío: quita una y agrega otra solo para esta respuesta
    r = client.post(f"{url}/comentarios", json={"texto": "Adjuntamos la liquidación.", "copia_a": ["bodega@cliente.com", "gerente@cliente.com"]},
                    headers=david)
    assert r.json()["comentarios"][-1]["copia_a"] == ["bodega@cliente.com", "gerente@cliente.com"]
    assert correos("RESPUESTA_COPIA")[-1].para == "bodega@cliente.com, gerente@cliente.com"
    assert [c["correo"] for c in r.json()["copias"]] == ["jefe@cliente.com", "bodega@cliente.com"]   # la lista del ticket no cambia

    # Lista vacía: nadie en copia; nota interna: nunca se copia
    total = len(correos("RESPUESTA_COPIA"))
    r = client.post(f"{url}/comentarios", json={"texto": "Solo al solicitante.", "copia_a": []}, headers=david)
    assert r.json()["comentarios"][-1]["copia_a"] == []
    r = client.post(f"{url}/comentarios", json={"texto": "Interna", "es_interno": True, "copia_a": ["jefe@cliente.com"]}, headers=david)
    assert r.json()["comentarios"][-1]["copia_a"] == []
    assert len(correos("RESPUESTA_COPIA")) == total
    assert client.post(f"{url}/comentarios", json={"texto": "x", "copia_a": ["malo"]}, headers=david).status_code == 422

    # El solicitante no ve a quién se copió
    assert all(c["copia_a"] == [] for c in client.get(url, headers=como("maria.andrade")).json()["comentarios"])

    # El cierre también llega a las copias (en CC del correo al solicitante)
    client.post(f"{url}/estado", json={"estado": "RESUELTO", "comentario": "Motivo de prueba"}, headers=david)
    client.post(f"{url}/cerrar", json={"comentario": "Cierre de prueba"}, headers=david)
    cierre = correos("TICKET_CERRADO")[-1]
    assert cierre.para == "maria.andrade@aducorp.com.ec" and cierre.cc == "jefe@cliente.com, bodega@cliente.com"


def test_formulario_web_copias_en_cc(client, como):
    t = crear_ticket(client, como("maria.andrade"), canal="WEB")
    url = f"{API}/tickets/{t['id']}"
    david = como("david.medina")
    client.put(f"{url}/copias", json={"correos": ["jefe@cliente.com"]}, headers=david)
    client.post(f"{url}/comentarios", json={"texto": "Respuesta web"}, headers=david)
    resp = correos("RESPUESTA_WEB")[-1]
    assert resp.para == "maria.andrade@aducorp.com.ec" and resp.cc == "jefe@cliente.com"
    assert not correos("RESPUESTA_COPIA")


def test_copia_automatica_por_categoria_y_cliente(client, como):
    admin = como("admin")
    cats = client.get(f"{API}/admin/categorias", headers=admin).json()
    cat = next(c for c in cats if c["codigo"] == "CLASIF_ARANCEL")
    assert cat["correos_copia"] == []
    body = {k: cat[k] for k in ("codigo", "nombre", "descripcion", "palabras_clave", "color", "orden", "modo_asignacion", "activo")}
    body.update(supervisor_id=cat["supervisor"]["id"] if cat["supervisor"] else None,
                responsables=[{"usuario_id": r["usuario_id"], "es_principal": r["es_principal"]} for r in cat["responsables"]],
                correos_copia=["Jefe.Clasificacion@aducorp.com.ec"])
    r = client.put(f"{API}/admin/categorias/{cat['id']}", json=body, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["correos_copia"] == ["jefe.clasificacion@aducorp.com.ec"]
    assert client.put(f"{API}/admin/categorias/{cat['id']}", json={**body, "correos_copia": ["malo"]}, headers=admin).status_code == 422

    cliente = client.get(f"{API}/admin/clientes", headers=admin).json()[0]
    r = client.put(f"{API}/admin/clientes/{cliente['id']}", headers=admin,
                   json={"ruc": cliente["ruc"], "razon_social": cliente["razon_social"], "correos_copia": ["compras@importadora.com"]})
    assert r.status_code == 200, r.text
    assert r.json()["correos_copia"] == ["compras@importadora.com"]
    # El catálogo general no expone los correos en copia
    assert "correos_copia" not in catalogo(client, como("maria.andrade"))["clientes"][0]

    t = crear_ticket(client, como("supervisor.tecnico"), cliente_id=cliente["id"])
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("supervisor.tecnico")).json()
    assert [(c["correo"], c["origen"]) for c in d["copias"]] == [("jefe.clasificacion@aducorp.com.ec", "CATEGORIA"),
                                                                ("compras@importadora.com", "CLIENTE")]


def test_buzon_agrega_cc_del_correo_y_respuesta_de_copia_es_nota_interna(db, m365):  # noqa: F811
    cc = [{"emailAddress": {"address": "Jefe@Importadora.com"}}, {"emailAddress": {"address": settings.BUZON_CORREO}},
          {"emailAddress": {"address": "no valido"}}]
    graph = GraphFalso([mensaje("c1", "compras@importadora.com", "Garantía aduanera", "Ayúdenos con la garantía aduanera.", ccRecipients=cc)])
    with SessionLocal() as s:
        assert BuzonService(s, graph).procesar()["creados"] == 1
        t = s.scalar(select(m.Ticket).where(m.Ticket.canal == "CORREO"))
        assert [(c.correo, c.origen) for c in s.scalars(select(m.TicketCopia).where(m.TicketCopia.ticket_id == t.id))] == [("jefe@importadora.com", "CORREO")]
        numero = t.numero

    graph2 = GraphFalso([mensaje("c2", "jefe@importadora.com", f"RE: [{numero}] Respuesta", "Confirmo la garantía.")])
    with SessionLocal() as s:
        assert BuzonService(s, graph2).procesar()["actualizados"] == 1
        t = s.scalar(select(m.Ticket).where(m.Ticket.numero == numero))
        nota = s.scalars(select(m.TicketComentario).where(m.TicketComentario.ticket_id == t.id).order_by(m.TicketComentario.id.desc())).first()
        assert nota.es_interno and "en copia del ticket" in nota.texto
