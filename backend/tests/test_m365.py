"""Integración con Microsoft 365: SSO con Entra ID, buzón de Exchange Online y bot de Teams (Graph y Teams simulados)."""
import base64
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.application.services import entra_service
from app.application.services.buzon_service import BuzonService
from app.application.services.teams_service import TeamsService, tarjeta
from app.core.config import settings
from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.m365 import entra
from tests.conftest import API, CLAVE

TENANT, CLIENTE = "11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CLAVE_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PDF = b"%PDF-1.4\n%prueba\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


class JwksFalso:
    class _Clave:
        key = CLAVE_RSA.public_key()

    def get_signing_key_from_jwt(self, _token):
        return self._Clave()


@pytest.fixture
def m365(monkeypatch):
    for k, v in {"M365_TENANT_ID": TENANT, "M365_CLIENT_ID": CLIENTE, "M365_CLIENT_SECRET": "secreto", "APP_URL": "https://mesa.aducorp.com.ec",
                 "ENTRA_GRUPO_ROLES": {"grupo-mesa-admin": "ADMIN_MESA", "grupo-analistas": "ANALISTA"},
                 "ENTRA_ROL_DEFECTO": "CLIENTE", "BUZON_ENABLED": True, "TEAMS_ENABLED": True}.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(entra, "_jwks", lambda: JwksFalso())
    return settings


def id_token(nonce_flujo, **claims):
    ahora = utcnow()
    datos = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENTE, "sub": "x", "tid": TENANT,
             "iat": ahora, "exp": ahora + timedelta(hours=1), "nonce": nonce_flujo, "oid": "oid-nuevo-1",
             "name": "Andrea Ruiz", "preferred_username": "andrea.ruiz@aducorp.com.ec", "amr": ["pwd", "mfa"], **claims}
    return jwt.encode(datos, CLAVE_RSA, algorithm="RS256")


def iniciar_sso(client):
    r = client.get(f"{API}/auth/entra/login", params={"destino": "/tickets"}, follow_redirects=False)
    assert r.status_code == 302, r.text
    url = urlparse(r.headers["location"])
    assert url.netloc == "login.microsoftonline.com" and TENANT in url.path
    q = parse_qs(url.query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == [CLIENTE]
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    return q["state"][0], q["nonce"][0], cookie.split(";")[0]


def completar_sso(client, monkeypatch, **claims):
    state, nonce, cookie = iniciar_sso(client)
    monkeypatch.setattr(entra, "canjear_codigo", lambda codigo, verificador, http=None: {"id_token": id_token(nonce, **claims)})
    r = client.get(f"{API}/auth/entra/callback", params={"code": "codigo-ms", "state": state}, headers={"Cookie": cookie}, follow_redirects=False)
    assert r.status_code == 302
    return r.headers["location"]


# ================================================================ Entra ID
def test_sso_entra_crea_usuario_con_rol_por_grupo(client, m365, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "entra")
    assert client.get(f"{API}/auth/entra/config").json() == {"activo": True, "permitir_local": False}

    destino = completar_sso(client, monkeypatch, groups=["grupo-analistas", "grupo-mesa-admin"])
    assert destino.startswith("https://mesa.aducorp.com.ec/auth/entra#codigo=")
    frag = parse_qs(urlparse(destino).fragment)
    assert frag["destino"] == ["/tickets"]

    r = client.post(f"{API}/auth/entra/intercambio", json={"codigo": frag["codigo"][0]})
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["rol"] == "ADMIN_MESA"   # gana el rol de mayor alcance
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["correo"] == "andrea.ruiz@aducorp.com.ec"
    # el código es de un solo uso
    assert client.post(f"{API}/auth/entra/intercambio", json={"codigo": frag["codigo"][0]}).status_code == 401
    with SessionLocal() as s:
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == "andrea.ruiz@aducorp.com.ec"))
        assert u.origen_autenticacion == "ENTRA" and u.entra_oid == "oid-nuevo-1" and u.clave_hash is None


def test_sso_vincula_usuario_existente_y_bloquea_contrasena(client, m365, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "entra")
    completar_sso(client, monkeypatch, oid="oid-maria", preferred_username="maria.andrade@aducorp.com.ec", name="María Andrade", groups=[])
    with SessionLocal() as s:
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == "maria.andrade@aducorp.com.ec"))
        assert u.entra_oid == "oid-maria" and u.rol.codigo == "CLIENTE" and u.clave_hash is None
    r = client.post(f"{API}/auth/login", json={"correo": "admin@aducorp.com.ec", "clave": CLAVE})
    assert r.status_code == 401 and "Microsoft" in r.json()["detail"]
    monkeypatch.setattr(settings, "ENTRA_CUENTAS_EMERGENCIA", ["admin@aducorp.com.ec"])
    assert client.post(f"{API}/auth/login", json={"correo": "admin@aducorp.com.ec", "clave": CLAVE}).status_code == 200
    assert client.get(f"{API}/auth/entra/config").json()["permitir_local"] is True


def test_sso_rechaza_nonce_otro_inquilino_y_sin_mfa(client, m365, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "entra")
    assert "error_sso=" in completar_sso(client, monkeypatch, nonce="otro")
    assert "error_sso=" in completar_sso(client, monkeypatch, tid="99999999-0000-0000-0000-000000000000")
    monkeypatch.setattr(settings, "ENTRA_EXIGIR_MFA", True)
    assert "error_sso=" in completar_sso(client, monkeypatch, amr=["pwd"])
    monkeypatch.setattr(settings, "ENTRA_ROL_DEFECTO", "")
    assert "error_sso=" in completar_sso(client, monkeypatch, groups=["grupo-desconocido"])
    # state alterado o sin cookie
    state, _, cookie = iniciar_sso(client)
    r = client.get(f"{API}/auth/entra/callback", params={"code": "x", "state": state}, follow_redirects=False)
    assert "error_sso=" in r.headers["location"]
    r = client.get(f"{API}/auth/entra/callback", params={"code": "x", "state": "otro"}, headers={"Cookie": cookie}, follow_redirects=False)
    assert "error_sso=" in r.headers["location"]


def test_rol_para_precedencia_y_app_roles(m365):
    assert entra_service.rol_para(["grupo-analistas"], []) == "ANALISTA"
    assert entra_service.rol_para(["grupo-analistas"], ["Gerencia"]) == "GERENCIA"
    assert entra_service.rol_para([], []) == "CLIENTE"
    assert entra_service.destino_seguro("//evil.com") == "/" and entra_service.destino_seguro("/tickets/5") == "/tickets/5"


def test_sincronizacion_de_grupos(db, m365):
    class GraphGrupos:
        def paginar(self, ruta, params=None, headers=None):
            if "grupo-analistas" in ruta:
                yield {"id": "oid-a1", "displayName": "Nuevo Analista", "mail": "nuevo.analista@aducorp.com.ec", "accountEnabled": True, "jobTitle": "Analista"}
                yield {"id": "oid-a2", "displayName": "Ex Analista", "mail": "maria.andrade@aducorp.com.ec", "accountEnabled": False}
    with SessionLocal() as s:
        r = entra_service.EntraService(s, graph=GraphGrupos()).sincronizar_grupos()
        assert r["creados"] == 1 and r["desactivados"] == 1
        nuevo = s.scalar(select(m.Usuario).where(m.Usuario.correo == "nuevo.analista@aducorp.com.ec"))
        assert nuevo.rol.codigo == "ANALISTA" and nuevo.cargo == "Analista"
        assert s.scalar(select(m.Usuario).where(m.Usuario.correo == "maria.andrade@aducorp.com.ec")).activo is False


# =========================================================== Exchange Online
class GraphFalso:
    def __init__(self, mensajes, adjuntos=None):
        self.mensajes, self.adjuntos, self.marcados, self.enviados = mensajes, adjuntos or {}, [], []

    def get(self, ruta, params=None, headers=None):
        assert "isRead eq false" in params["$filter"]
        return {"value": self.mensajes}

    def paginar(self, ruta, params=None, headers=None):
        yield from self.adjuntos.get(ruta.split("/messages/")[1].split("/")[0], [])

    def patch(self, ruta, json):
        self.marcados.append((ruta.rsplit("/", 1)[-1], json))


def mensaje(id_, remitente, asunto, texto, adjuntos=False, **extra):
    return {"id": id_, "internetMessageId": f"<{id_}@mail>", "subject": asunto, "receivedDateTime": "2026-10-19T15:00:00Z",
            "from": {"emailAddress": {"address": remitente, "name": remitente.split("@")[0].title()}},
            "uniqueBody": {"content": texto}, "hasAttachments": adjuntos, **extra}


def adjunto(nombre, contenido, inline=False):
    return {"@odata.type": "#microsoft.graph.fileAttachment", "name": nombre, "contentType": "application/pdf",
            "contentBytes": base64.b64encode(contenido).decode(), "isInline": inline}


def test_buzon_crea_ticket_acuse_y_respuesta(db, m365):
    graph = GraphFalso([mensaje("m1", "maria.andrade@aducorp.com.ec", "Consulta Clasificación Arancelaria",
                                "Necesito la partida arancelaria de repuestos de maquinaria agrícola.", adjuntos=True)],
                       {"m1": [adjunto("factura.pdf", PDF), adjunto("virus.exe", b"MZ\x90\x00"), adjunto("logo.png", b"x", inline=True)]})
    with SessionLocal() as s:
        r = BuzonService(s, graph).procesar()
        assert r["creados"] == 1
        t = s.scalar(select(m.Ticket).where(m.Ticket.canal == "CORREO"))
        assert t.categoria.codigo == "CLASIF_ARANCEL" and t.responsable_id is not None and t.estado == "ASIGNADO"
        assert t.solicitante.correo == "maria.andrade@aducorp.com.ec"
        assert [a.nombre_original for a in s.scalars(select(m.TicketAdjunto).where(m.TicketAdjunto.ticket_id == t.id))] == ["factura.pdf"]
        notas = s.scalars(select(m.TicketComentario).where(m.TicketComentario.ticket_id == t.id)).all()
        assert any("virus.exe" in n.texto and n.es_interno for n in notas)
        acuse = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACUSE_CORREO"))
        assert acuse.para == "maria.andrade@aducorp.com.ec" and t.numero in acuse.asunto
        assert not s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "TICKET_CREADO"))   # sin correo duplicado
        assert graph.marcados[0] == ("m1", {"isRead": True, "categories": [f"Mesa {t.numero}"]})
        numero = t.numero

    # Respuesta al hilo del correo: se agrega al ticket; el mismo mensaje no se procesa dos veces
    graph2 = GraphFalso([mensaje("m2", "maria.andrade@aducorp.com.ec", f"RE: [{numero}] Recibimos su solicitud",
                                 "Adjunto la ficha técnica que faltaba."), mensaje("m1", "x@y.com", "repetido", "repetido")])
    with SessionLocal() as s:
        r = BuzonService(s, graph2).procesar()
        assert r == {"leidos": 2, "creados": 0, "actualizados": 1, "ignorados": 1, "errores": 0}
        t = s.scalar(select(m.Ticket).where(m.Ticket.numero == numero))
        assert any(c.texto == "Adjunto la ficha técnica que faltaba." and not c.es_interno
                   for c in s.scalars(select(m.TicketComentario).where(m.TicketComentario.ticket_id == t.id)))


def test_buzon_remitente_externo_recibe_respuestas_por_correo(client, como, m365):
    graph = GraphFalso([mensaje("e1", "compras@importadora.com", "Trámite de garantía aduanera SENAE",
                                "Por favor ayúdenos con la garantía aduanera del trámite en ECUAPASS."),
                        mensaje("e2", "noreply@importadora.com", "Respuesta automática: fuera de la oficina", "Estoy de vacaciones",
                                internetMessageHeaders=[{"name": "Auto-Submitted", "value": "auto-replied"}])])
    with SessionLocal() as s:
        r = BuzonService(s, graph).procesar()
        assert r["creados"] == 1 and r["ignorados"] == 1
        t = s.scalar(select(m.Ticket).where(m.Ticket.canal == "CORREO"))
        assert t.solicitante.correo == settings.BUZON_CORREO and t.correo == "compras@importadora.com"
        assert "compras@importadora.com" in t.descripcion
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "ACUSE_CORREO")).para == "compras@importadora.com"
        tid, responsable = t.id, t.responsable.correo.split("@")[0]

    r = client.post(f"{API}/tickets/{tid}/comentarios", json={"texto": "Necesitamos la póliza vigente."}, headers=como(responsable))
    assert r.status_code == 201, r.text
    with SessionLocal() as s:
        resp = s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "RESPUESTA_TICKET"))
        assert resp.para == "compras@importadora.com" and "póliza vigente" in resp.cuerpo_html
        assert not s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.para == settings.BUZON_CORREO))


# ================================================================== Teams
class ConectorFalso:
    def __init__(self):
        self.enviados = []

    def enviar(self, service_url, conversacion, actividad):
        self.enviados.append((conversacion, actividad))
        return {"id": "act-1"}


def actividad_mensaje(texto, oid, canal="19:canal-clasif@thread.tacv2", nombre="Clasificación Arancelaria"):
    return {"type": "message", "id": "msg-1", "text": f"<at>Mesa</at> {texto}", "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "from": {"aadObjectId": oid}, "conversation": {"id": f"{canal};messageid=1"},
            "channelData": {"channel": {"id": canal, "name": nombre}, "team": {"id": "19:equipo@thread.tacv2"}}}


def invoke(verbo, ticket_id, oid, **datos):
    return {"type": "invoke", "name": "adaptiveCard/action", "from": {"aadObjectId": oid},
            "value": {"action": {"type": "Action.Execute", "verb": verbo, "data": {"ticket_id": ticket_id, **datos}}}}


def vincular_oid(correo, oid):
    with SessionLocal() as s:
        s.scalar(select(m.Usuario).where(m.Usuario.correo == correo)).entra_oid = oid
        s.commit()


def test_teams_canales_avisos_y_acciones(client, como, m365):
    vincular_oid("admin@aducorp.com.ec", "oid-admin")
    conector = ConectorFalso()
    with SessionLocal() as s:
        svc = TeamsService(s, conector)
        svc.procesar(actividad_mensaje("vincular clasificacion arancelaria", "oid-admin"))
        svc.procesar(actividad_mensaje("vincular general", "oid-admin", canal="19:general@thread.tacv2", nombre=None))
        svc.procesar(actividad_mensaje("vincular general", "oid-desconocido", canal="19:otro@thread.tacv2"))
        assert "Clasificación Arancelaria" in conector.enviados[0][1]["text"]
        assert "todos los tickets" in conector.enviados[1][1]["text"]
        assert "Solo un administrador" in conector.enviados[2][1]["text"]
        assert s.scalar(select(m.TeamsCanal).where(m.TeamsCanal.conversation_id == "19:general@thread.tacv2")).categoria_id is None

    from tests.test_api import crear_ticket
    t = crear_ticket(client, como("maria.andrade"))
    with SessionLocal() as s:
        cola = s.scalars(select(m.ColaTeams).where(m.ColaTeams.ticket_id == t["id"])).all()
        assert [c.evento for c in cola] == ["TICKET_CREADO"]   # la asignación automática no duplica el aviso
        conector = ConectorFalso()
        assert TeamsService(s, conector).procesar_cola() == {"enviados": 1, "errores": 0}
        assert {c for c, _ in conector.enviados} == {"19:canal-clasif@thread.tacv2", "19:general@thread.tacv2"}
        card = conector.enviados[0][1]["attachments"][0]["content"]
        hechos = {f["title"]: f["value"] for f in card["body"][1]["facts"]}
        assert {"Prioridad", "Cliente", "Responsable", "Estado", "SLA restante"} <= hechos.keys()
        assert [a["title"] for a in card["actions"]] == ["Aceptar", "Escalar", "Cambiar estado", "Abrir en la Mesa"]
        responsable = s.get(m.Ticket, t["id"]).responsable.correo

    vincular_oid(responsable, "oid-analista")
    vincular_oid("luis.paredes@aducorp.com.ec", "oid-cliente")
    with SessionLocal() as s:
        svc = TeamsService(s, ConectorFalso())
        r = svc.procesar(invoke("aceptar", t["id"], "oid-cliente"))
        assert r["value"]["body"][0]["style"] == "attention"           # un cliente no puede aceptar
        r = svc.procesar(invoke("aceptar", t["id"], "oid-analista"))
        assert r["statusCode"] == 200 and r["value"]["body"][0]["style"] == "good"
        assert s.get(m.Ticket, t["id"]).estado == "EN_PROCESO"
        r = svc.procesar(invoke("escalar", t["id"], "oid-analista", motivo="Requiere criterio del supervisor técnico"))
        assert s.get(m.Ticket, t["id"]).estado == "ESCALADO"
        r = svc.procesar(invoke("estado", t["id"], "oid-analista", estado="RESUELTO", comentario="Partida 8433.90.00 confirmada"))
        assert r["value"]["body"][0]["style"] == "good" and s.get(m.Ticket, t["id"]).estado == "RESUELTO"
        assert s.scalar(select(m.ColaTeams).where(m.ColaTeams.evento == "TICKET_ESCALADO"))
        r = svc.procesar(invoke("aceptar", t["id"], "oid-nadie"))
        assert "no está vinculada" in r["value"]["body"][0]["items"][0]["text"]


def test_endpoint_teams_valida_token(client, m365, monkeypatch):
    assert client.post(f"{API}/teams/mensajes", json={"type": "message"}).status_code == 401
    from app.api.v1.routers import teams as router_teams
    monkeypatch.setattr(router_teams, "validar_llamada_bot", lambda *a, **k: {})
    monkeypatch.setattr(router_teams.TeamsService, "procesar", lambda self, act: {"statusCode": 200})
    assert client.post(f"{API}/teams/mensajes", json={"type": "invoke"}).json() == {"statusCode": 200}
    monkeypatch.setattr(settings, "TEAMS_ENABLED", False)
    assert client.post(f"{API}/teams/mensajes", json={"type": "message"}).status_code == 404


def test_tarjeta_ticket_cerrado_sin_acciones(client, como, m365):
    from tests.test_api import crear_ticket
    t = crear_ticket(client, como("maria.andrade"))
    with SessionLocal() as s:
        ticket = s.get(m.Ticket, t["id"])
        assert "laborables" in next(f["value"] for f in tarjeta(ticket, "TICKET_CREADO")["body"][1]["facts"] if f["title"] == "SLA restante")
        ticket.estado = "CERRADO"
        assert [a["type"] for a in tarjeta(ticket, "TICKET_CERRADO")["actions"]] == ["Action.OpenUrl"]


def test_estado_integraciones(client, como, m365):
    r = client.get(f"{API}/admin/integraciones", headers=como("admin"))
    assert r.status_code == 200 and r.json()["teams"]["activo"] is True
    assert client.get(f"{API}/admin/integraciones", headers=como("maria.andrade")).status_code == 403
