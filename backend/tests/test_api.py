from datetime import timedelta

from sqlalchemy import select

from app.core.security import utcnow
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API, CLAVE


def catalogo(client, h):
    return client.get(f"{API}/catalogos", headers=h).json()


def ids(client, h, cat_codigo, sub_nombre):
    cats = catalogo(client, h)["categorias"]
    c = next(x for x in cats if x["codigo"] == cat_codigo)
    s = next(x for x in c["subcategorias"] if x["nombre"] == sub_nombre)
    return c["id"], s["id"]


def crear_ticket(client, h, cat="CLASIF_ARANCEL", sub="Presentación DAI", **extra):
    cid, sid = ids(client, h, cat, sub)
    body = {"asunto": "Transmisión de DAI urgente", "descripcion": "Contenedor en puerto, se necesita transmitir la DAI hoy.",
            "categoria_id": cid, "subcategoria_id": sid, **extra}
    r = client.post(f"{API}/tickets", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- seguridad
def test_login_y_me(client, como):
    r = client.get(f"{API}/auth/me", headers=como("admin"))
    assert r.status_code == 200
    assert r.json()["rol"] == "SUPER_ADMIN"
    assert "auditoria.ver" in r.json()["permisos"]


def test_login_fallido_y_bloqueo(client):
    for _ in range(5):
        r = client.post(f"{API}/auth/login", json={"correo": "gerencia@aducorp.com.ec", "clave": "mala"})
        assert r.status_code == 401
    r = client.post(f"{API}/auth/login", json={"correo": "gerencia@aducorp.com.ec", "clave": CLAVE})
    assert r.status_code == 401 and "bloqueada" in r.json()["detail"]


def test_refresh_rota_y_detecta_reutilizacion(client):
    r = client.post(f"{API}/auth/login", json={"correo": "admin@aducorp.com.ec", "clave": CLAVE}).json()
    r2 = client.post(f"{API}/auth/refresh", json={"refresh_token": r["refresh_token"]})
    assert r2.status_code == 200
    # Reutilizar el token viejo revoca toda la familia, incluido el nuevo
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": r["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": r2.json()["refresh_token"]}).status_code == 401


def test_sin_token(client, db):
    assert client.get(f"{API}/tickets").status_code == 401


# ------------------------------------------------------------------ tickets
def test_crear_ticket_asigna_y_notifica(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    assert t["numero"].startswith("ADU-") and t["numero"].endswith("000001")
    assert t["estado"] == "ASIGNADO"
    assert t["responsable"]["nombre"] == "David Medina"
    assert t["prioridad"]["codigo"] == "URGENTE"   # sugerida por IA: «urgente», «hoy», «contenedor en puerto»
    assert t["sla_resolucion_min"] == 240
    with SessionLocal() as s:
        assert s.scalar(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "TICKET_ASIGNADO")) is not None
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "TICKET_CREADO")) is not None


def test_balanceo_tramites(client, como):
    h = como("maria.andrade")
    responsables = {crear_ticket(client, h, "TRAMITES_ADUANA", "Garantías")["responsable"]["nombre"] for _ in range(3)}
    assert responsables == {"Jorge Caicedo", "Debbie Díaz", "Carlos Torres"}


def test_visibilidad_por_rol(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("david.medina")).status_code == 200
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("denisse.quinga")).status_code == 404   # otro analista
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("luis.paredes")).status_code == 404     # otro cliente
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("supervisor.tecnico")).status_code == 200
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("supervisor.operativo")).status_code == 404
    assert client.get(f"{API}/tickets/{t['id']}", headers=como("gerencia")).status_code == 200
    assert client.get(f"{API}/tickets", headers=como("luis.paredes")).json()["total"] == 0


def test_ciclo_completo_con_pausa(client, como):
    cliente, analista = como("maria.andrade"), como("david.medina")
    t = crear_ticket(client, cliente)
    url = f"{API}/tickets/{t['id']}"
    r = client.post(f"{url}/estado", json={"estado": "EN_PROCESO", "comentario": "Motivo de prueba"}, headers=analista)
    assert r.json()["estado"] == "EN_PROCESO" and r.json()["fecha_primera_respuesta"]
    r = client.post(f"{url}/estado", json={"estado": "PENDIENTE_CLIENTE"}, headers=analista)
    assert r.status_code == 422   # exige comentario
    r = client.post(f"{url}/estado", json={"estado": "PENDIENTE_CLIENTE", "comentario": "Envíe la factura"}, headers=analista)
    assert r.json()["sla_pausado"] is True
    # El cliente responde: el SLA se reanuda automáticamente
    r = client.post(f"{url}/comentarios", json={"texto": "Adjunto la factura"}, headers=cliente)
    assert r.json()["estado"] == "EN_PROCESO" and r.json()["sla_pausado"] is False
    r = client.post(f"{url}/comentarios", json={"texto": "Revisar valor", "es_interno": True}, headers=analista)
    assert r.status_code == 201
    vista_cliente = client.get(url, headers=cliente).json()
    assert all(not c["es_interno"] for c in vista_cliente["comentarios"])
    assert "nota_interna" not in vista_cliente["acciones"]
    r = client.post(f"{url}/estado", json={"estado": "RESUELTO", "comentario": "Motivo de prueba"}, headers=analista)
    assert r.json()["estado"] == "RESUELTO" and r.json()["sla_resolucion_cumplido"] is not None
    # El solicitante confirma el cierre y luego reabre
    r = client.post(f"{url}/cerrar", json={"comentario": "Cierre de prueba"}, headers=cliente)
    assert r.json()["estado"] == "CERRADO"
    r = client.post(f"{url}/reabrir", json={"motivo": "El problema persiste"}, headers=cliente)
    assert r.json()["estado"] == "EN_PROCESO" and r.json()["reaperturas"] == 1
    acciones = [h["accion"] for h in client.get(url, headers=analista).json()["historial"]]
    assert {"CREACION", "ASIGNACION", "CIERRE", "REAPERTURA"} <= set(acciones)


def test_cada_cambio_de_estado_exige_motivo_y_queda_en_historial(client, como):
    cliente, analista = como("maria.andrade"), como("david.medina")
    t = crear_ticket(client, cliente)
    url = f"{API}/tickets/{t['id']}"
    r = client.post(f"{url}/estado", json={"estado": "EN_PROCESO"}, headers=analista)
    assert r.status_code == 422 and "motivo" in r.json()["detail"]
    assert client.post(f"{url}/estado", json={"estado": "EN_PROCESO", "comentario": "ok"}, headers=analista).status_code == 422
    r = client.post(f"{url}/estado", json={"estado": "EN_PROCESO", "comentario": "Reviso el equipo"}, headers=analista)
    assert r.status_code == 200
    # En proceso: el motivo queda como nota interna (el solicitante no la ve)
    assert not any("Reviso el equipo" in c["texto"] for c in client.get(url, headers=cliente).json()["comentarios"])
    r = client.post(f"{url}/estado", json={"estado": "RESUELTO", "comentario": "Se reinstaló el controlador"}, headers=analista)
    assert any(c["texto"] == "Se reinstaló el controlador" for c in client.get(url, headers=cliente).json()["comentarios"])
    assert client.post(f"{url}/cerrar", json={}, headers=cliente).status_code == 422
    # Respuesta rápida: el motivo va solo al historial
    client.post(f"{url}/reabrir", json={"motivo": "Volvió a fallar"}, headers=cliente)
    r = client.post(f"{url}/estado", json={"estado": "PENDIENTE_CLIENTE", "comentario": "Respuesta rápida «Pedir captura»",
                                           "solo_historial": True}, headers=analista)
    assert r.status_code == 200
    historial = client.get(url, headers=analista).json()["historial"]
    cambios = [h for h in historial if h["accion"] in ("CAMBIO_ESTADO", "REAPERTURA")]
    assert all(h["detalle"] for h in cambios)
    detalles = {h["detalle"] for h in cambios}
    assert {"Reviso el equipo", "Se reinstaló el controlador", "Volvió a fallar", "Respuesta rápida «Pedir captura»"} <= detalles
    assert not any("Pedir captura" in c["texto"] for c in client.get(url, headers=cliente).json()["comentarios"])


def test_transicion_invalida(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    r = client.post(f"{API}/tickets/{t['id']}/estado", json={"estado": "CERRADO", "comentario": "Motivo de prueba"}, headers=como("david.medina"))
    assert r.status_code == 422


def test_asignar_y_escalar(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    url = f"{API}/tickets/{t['id']}"
    juan = next(u for u in catalogo(client, como("admin"))["responsables"] if u["nombre"] == "Juan Manuel Villamar")
    # Un analista que no es el responsable del ticket no puede reasignarlo (el responsable sí: test_segunda_ronda)
    assert t["responsable"]["nombre"] != "Denisse Quinga"
    assert client.post(f"{url}/asignar", json={"responsable_id": juan["id"]}, headers=como("denisse.quinga")).status_code in (403, 404)
    r = client.post(f"{url}/asignar", json={"responsable_id": juan["id"], "motivo": "Tema legal"}, headers=como("supervisor.tecnico"))
    assert r.status_code == 200 and r.json()["responsable"]["nombre"] == "Juan Manuel Villamar"
    r = client.post(f"{url}/escalar", json={"motivo": "Requiere criterio del supervisor"}, headers=como("juan.villamar"))
    assert r.json()["estado"] == "ESCALADO" and r.json()["escalamientos"][0]["tipo"] == "MANUAL"


def test_editar_cambia_sla_y_controla_version(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    prioridades = {p["codigo"]: p["id"] for p in catalogo(client, como("admin"))["prioridades"]}
    h = como("david.medina")
    r = client.patch(f"{API}/tickets/{t['id']}", json={"prioridad_id": prioridades["BAJA"], "version": t["version"]}, headers=h)
    assert r.status_code == 200 and r.json()["sla_resolucion_min"] == 2880
    r = client.patch(f"{API}/tickets/{t['id']}", json={"asunto": "Otro asunto", "version": t["version"]}, headers=h)
    assert r.status_code == 409


def test_gerencia_solo_lectura(client, como):
    h = como("gerencia")
    cid, sid = ids(client, h, "CLASIF_ARANCEL", "Presentación DAI")
    r = client.post(f"{API}/tickets", json={"asunto": "Prueba", "descripcion": "No debería poder crear", "categoria_id": cid, "subcategoria_id": sid}, headers=h)
    assert r.status_code == 403
    assert client.get(f"{API}/reportes/dashboard", headers=h).status_code == 200
    assert client.get(f"{API}/auditoria", headers=h).status_code == 403


def test_adjuntos(client, como):
    h = como("maria.andrade")
    t = crear_ticket(client, h)
    url = f"{API}/tickets/{t['id']}/adjuntos"
    r = client.post(url, files={"archivo": ("factura.pdf", b"%PDF-1.4 demo", "application/pdf")}, headers=h)
    assert r.status_code == 201
    adj = r.json()["adjuntos"][0]
    r = client.get(f"{url}/{adj['id']}", headers=como("david.medina"))
    assert r.status_code == 200 and r.content == b"%PDF-1.4 demo"
    r = client.post(url, files={"archivo": ("virus.exe", b"MZ", "application/octet-stream")}, headers=h)
    assert r.status_code == 422



def test_eliminar_adjunto(client, como):
    """Quien subió el archivo (o la mesa / supervisor) lo quita; queda en el Historial y la auditoría; con el ticket cerrado no."""
    sol, analista, admin = como("maria.andrade"), como("david.medina"), como("admin")
    t = crear_ticket(client, sol)
    url = f"{API}/tickets/{t['id']}/adjuntos"
    d = client.post(url, files={"archivo": ("equivocado.pdf", b"%PDF-1.4 a", "application/pdf")}, headers=sol).json()
    d = client.post(url, files={"archivo": ("correcto.pdf", b"%PDF-1.4 b", "application/pdf")}, headers=sol).json()
    equivocado, correcto = (next(a for a in d["adjuntos"] if a["nombre_original"] == n) for n in ("equivocado.pdf", "correcto.pdf"))
    assert equivocado["puede_eliminar"] and correcto["puede_eliminar"]

    # Un analista que no lo subió no puede quitarlo
    vista = client.get(f"{API}/tickets/{t['id']}", headers=analista)
    if vista.status_code == 200:
        assert not any(a["puede_eliminar"] for a in vista.json()["adjuntos"])
    assert client.delete(f"{url}/{equivocado['id']}", headers=analista).status_code in (403, 404)

    r = client.delete(f"{url}/{equivocado['id']}", headers=sol)
    assert r.status_code == 200, r.text
    assert [a["nombre_original"] for a in r.json()["adjuntos"]] == ["correcto.pdf"]
    assert client.get(f"{url}/{equivocado['id']}", headers=sol).status_code == 404
    assert client.delete(f"{url}/{equivocado['id']}", headers=sol).status_code == 404
    with SessionLocal() as s:
        a = s.get(m.TicketAdjunto, equivocado["id"])
        assert a.eliminado   # borrado lógico: el registro y el archivo se conservan
        h = s.scalars(select(m.TicketHistorial).where(m.TicketHistorial.ticket_id == t["id"],
                                                      m.TicketHistorial.accion == "ADJUNTO_ELIMINADO")).all()
        assert len(h) == 1 and h[0].detalle == "equivocado.pdf"
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "ADJUNTO_ELIMINADO")) is not None

    # La mesa de servicio puede quitar el archivo de otra persona; con el ticket cerrado nadie puede
    d = client.post(url, files={"archivo": ("otro.pdf", b"%PDF-1.4 c", "application/pdf")}, headers=sol).json()
    otro = next(a for a in d["adjuntos"] if a["nombre_original"] == "otro.pdf")
    with SessionLocal() as s:
        s.get(m.Ticket, t["id"]).estado = "CERRADO"
        s.commit()
    d = client.get(f"{API}/tickets/{t['id']}", headers=admin).json()
    assert not any(a["puede_eliminar"] for a in d["adjuntos"])
    assert client.delete(f"{url}/{otro['id']}", headers=admin).status_code == 422
    with SessionLocal() as s:
        s.get(m.Ticket, t["id"]).estado = "EN_PROCESO"
        s.commit()
    r = client.delete(f"{url}/{otro['id']}", headers=admin)
    assert r.status_code == 200 and [a["nombre_original"] for a in r.json()["adjuntos"]] == ["correcto.pdf"]
    hist = [h for h in r.json()["historial"] if h["accion"] == "ADJUNTO_ELIMINADO"]
    assert hist[-1]["detalle"] == "otro.pdf (subido por María Fernanda Andrade)"


def test_comentario_con_capturas(client, como):
    """Capturas de pantalla dentro del comentario; las de notas internas no las ve el solicitante."""
    import json

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    sol, analista = como("maria.andrade"), como("david.medina")
    t = crear_ticket(client, sol)
    url = f"{API}/tickets/{t['id']}/comentarios/con-archivos"
    r = client.post(url, data={"datos": json.dumps({"texto": ""})}, files=[("archivos", ("captura.png", png, "image/png"))], headers=sol)
    assert r.status_code == 201, r.text
    c = r.json()["comentarios"][-1]
    assert c["texto"] == "Adjuntó 1 archivo" and [a["nombre_original"] for a in c["adjuntos"]] == ["captura.png"]
    assert r.json()["adjuntos"][0]["comentario_id"] == c["id"]
    img = c["adjuntos"][0]["id"]
    r = client.get(f"{API}/tickets/{t['id']}/adjuntos/{img}?vista=true", headers=analista)
    assert r.status_code == 200 and r.content == png

    r = client.post(url, data={"datos": json.dumps({"texto": "Error en la consola", "es_interno": True})},
                    files=[("archivos", ("consola.png", png, "image/png")), ("archivos", ("log.txt", b"traza", "text/plain"))], headers=analista)
    assert r.status_code == 201, r.text
    nota = r.json()["comentarios"][-1]
    assert nota["es_interno"] and len(nota["adjuntos"]) == 2
    d = client.get(f"{API}/tickets/{t['id']}", headers=sol).json()
    assert [a["nombre_original"] for a in d["adjuntos"]] == ["captura.png"]
    assert client.get(f"{API}/tickets/{t['id']}/adjuntos/{nota['adjuntos'][0]['id']}", headers=sol).status_code == 404

    # Un archivo no permitido rechaza todo el comentario, sin guardar nada
    antes = len(d["comentarios"])
    r = client.post(url, data={"datos": json.dumps({"texto": "va"})},
                    files=[("archivos", ("ok.png", png, "image/png")), ("archivos", ("virus.exe", b"MZ", "application/octet-stream"))], headers=sol)
    assert r.status_code == 422
    assert len(client.get(f"{API}/tickets/{t['id']}", headers=sol).json()["comentarios"]) == antes


# --------------------------------------------------------------------- SLA
def test_worker_escalamiento_automatico(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    with SessionLocal() as s:
        ticket = s.get(m.Ticket, t["id"])
        ticket.fecha_creacion = utcnow() - timedelta(days=10)   # muy vencido
        s.commit()
    from app.worker import ciclo_sla

    stats = ciclo_sla()
    assert stats["vencidos"] == 1 and stats["aviso_75"] == 1 and stats["aviso_90"] == 1
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()
    assert d["estado"] == "ESCALADO" and d["sla_incumplido"] is True and d["cumplimiento_sla"] == "INCUMPLIDO"
    assert [e["nivel"] for e in d["escalamientos"]] == [75, 90, 100]
    with SessionLocal() as s:
        assert s.scalar(select(m.SlaIncumplimiento).where(m.SlaIncumplimiento.tipo == "RESOLUCION")) is not None
    notifs = client.get(f"{API}/notificaciones", headers=como("supervisor.tecnico")).json()
    assert any(n["tipo"] == "SLA_VENCIDO" for n in notifs)
    # Segundo ciclo: no repite alertas
    assert ciclo_sla()["vencidos"] == 0


def test_excepcion_sla(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    r = client.post(f"{API}/tickets/{t['id']}/excepcion-sla", json={"tipo": "EXTENSION", "minutos": 120, "motivo": "Espera de SENAE"},
                    headers=como("mesa.servicios"))
    assert r.status_code == 200 and r.json()["sla_minutos_extension"] == 120
    r = client.post(f"{API}/tickets/{t['id']}/excepcion-sla", json={"tipo": "EXCLUSION", "motivo": "Caso fuera de alcance"},
                    headers=como("david.medina"))
    assert r.status_code == 403


# ---------------------------------------------------------------- reportes
def test_reportes_y_exportaciones(client, como):
    h = como("maria.andrade")
    for _ in range(3):
        crear_ticket(client, h)
    g = como("gerencia")
    d = client.get(f"{API}/reportes/dashboard", headers=g).json()
    assert d["widgets"]["tickets_totales"] == 3 and d["widgets"]["tickets_abiertos"] == 3
    cats = client.get(f"{API}/reportes/categorias", headers=g).json()
    assert next(c for c in cats if c["categoria"] == "Clasificación Arancelaria")["tickets_recibidos"] == 3
    assert client.get(f"{API}/reportes/responsables", headers=g).json()[0]["ranking"] == 1
    for formato, firma in (("xlsx", b"PK"), ("pdf", b"%PDF"), ("csv", "﻿".encode())):
        r = client.get(f"{API}/tickets/exportar?formato={formato}", headers=g)
        assert r.status_code == 200 and r.content.startswith(firma), formato
        r = client.get(f"{API}/reportes/exportar?formato={formato}", headers=g)
        assert r.status_code == 200 and r.content.startswith(firma), formato
    assert client.get(f"{API}/tickets/exportar", headers=como("david.medina")).status_code == 403
    aud = client.get(f"{API}/auditoria?accion=EXPORTACION", headers=como("admin")).json()
    assert aud["total"] == 6


def test_supervisor_ve_metricas_de_su_area(client, como):
    crear_ticket(client, como("maria.andrade"))                                   # Clasificación (técnico)
    crear_ticket(client, como("maria.andrade"), "CONSULTAS_FEDEX", "Tracking")    # FedEx (operativo)
    d = client.get(f"{API}/reportes/dashboard", headers=como("supervisor.operativo")).json()
    assert d["widgets"]["tickets_totales"] == 1


# ---------------------------------------------------------------------- IA
def test_ia_clasifica_y_sugiere(client, como):
    r = client.post(f"{API}/ia/sugerir", json={"asunto": "Paquete FedEx retenido", "descripcion": "La guía está retenida, necesitamos la desaduanización"},
                    headers=como("maria.andrade"))
    d = r.json()
    assert d["clasificaciones"][0]["categoria"] == "Consultas FedEx"
    assert d["clasificaciones"][0]["subcategoria"] == "Desaduanización"
    assert d["responsable"]["nombre"] == "Denisse Quinga"
    t = crear_ticket(client, como("maria.andrade"))
    h = como("david.medina")
    assert "David Medina" in client.post(f"{API}/tickets/{t['id']}/ia/respuesta", headers=h).json()["texto"]
    assert client.post(f"{API}/tickets/{t['id']}/ia/resumen", headers=h).json()["texto"]
    assert client.get(f"{API}/tickets/{t['id']}/ia/riesgo", headers=h).json()["nivel"] in {"BAJO", "MEDIO", "ALTO"}


# ------------------------------------------------------------ administración
def test_admin_usuarios_y_cambio_rol_auditado(client, como):
    h = como("admin")
    roles = {r["codigo"]: r["id"] for r in client.get(f"{API}/admin/roles", headers=h).json()}
    r = client.post(f"{API}/admin/usuarios", json={"nombre": "Nuevo Analista", "correo": "nuevo@aducorp.com.ec", "rol_id": roles["CLIENTE"]}, headers=h)
    assert r.status_code == 201 and r.json()["clave_temporal"]
    uid = r.json()["usuario"]["id"]
    assert client.patch(f"{API}/admin/usuarios/{uid}", json={"rol_id": roles["ANALISTA"]}, headers=h).json()["rol"] == "ANALISTA"
    assert client.get(f"{API}/auditoria?accion=CAMBIO_ROL", headers=h).json()["total"] == 1
    assert client.get(f"{API}/admin/usuarios", headers=como("mesa.servicios")).status_code == 403


def test_admin_sla(client, como):
    h = como("mesa.servicios")
    p = next(x for x in catalogo(client, h)["prioridades"] if x["codigo"] == "MEDIA")
    r = client.put(f"{API}/admin/sla/prioridades/{p['id']}", json={"sla_respuesta_min": 180, "sla_resolucion_min": 960}, headers=h)
    assert r.status_code == 200 and r.json()["sla_resolucion_min"] == 960
    r = client.post(f"{API}/admin/sla/calendario", json={"fecha": "2026-12-24", "tipo": "HORARIO_ESPECIAL", "hora_inicio": "08:30:00",
                                                         "hora_fin": "13:00:00", "descripcion": "Nochebuena"}, headers=h)
    assert r.status_code == 201
    assert client.get(f"{API}/auditoria?accion=CAMBIO_SLA", headers=como("admin")).json()["total"] == 2


def test_cambiar_clave(client):
    r = client.post(f"{API}/auth/login", json={"correo": "luis.paredes@aducorp.com.ec", "clave": CLAVE}).json()
    h = {"Authorization": f"Bearer {r['access_token']}"}
    assert client.post(f"{API}/auth/cambiar-clave", json={"clave_actual": CLAVE, "clave_nueva": "corta"}, headers=h).status_code == 422
    r2 = client.post(f"{API}/auth/cambiar-clave", json={"clave_actual": CLAVE, "clave_nueva": "Nueva#Llave2026"}, headers=h)
    assert r2.status_code == 200 and r2.json()["usuario"]["debe_cambiar_clave"] is False
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": r["refresh_token"]}).status_code == 401


def test_swagger(client):
    r = client.get(f"{API}/openapi.json")
    assert r.status_code == 200 and len(r.json()["paths"]) > 40


def test_tickets_en_los_que_participe_solo_lectura(client, como):
    """Si el ticket pasa a otro responsable (p. ej. a LEGAL), quien lo atendió antes lo sigue viendo, sin poder operarlo."""
    t = crear_ticket(client, como("maria.andrade"))   # asignado automáticamente a David Medina
    url = f"{API}/tickets/{t['id']}"
    david, juan, denisse = como("david.medina"), como("juan.villamar"), como("denisse.quinga")
    client.post(f"{url}/comentarios", json={"texto": "Revisé la partida", "es_interno": True}, headers=david)
    juan_id = next(u for u in catalogo(client, como("admin"))["responsables"] if u["nombre"] == "Juan Manuel Villamar")["id"]
    r = client.post(f"{url}/asignar", json={"responsable_id": juan_id, "motivo": "Pasa a LEGAL"}, headers=como("supervisor.tecnico"))
    assert r.status_code == 200

    # La lista normal de David ya no lo incluye; el filtro «participé» sí
    numeros = lambda h, **q: [x["numero"] for x in client.get(f"{API}/tickets", params=q, headers=h).json()["items"]]  # noqa: E731
    assert t["numero"] not in numeros(david)
    assert t["numero"] in numeros(david, participe="true")
    assert t["numero"] in numeros(juan, participe="true")        # el responsable actual también lo ve con el filtro
    assert numeros(denisse, participe="true") == []               # nunca participó

    # Detalle en solo lectura, con historial completo y notas internas
    d = client.get(url, headers=david)
    assert d.status_code == 200
    d = d.json()
    assert d["solo_lectura_participante"] is True
    assert not {"editar", "asignar", "cambiar_estado", "escalar", "cerrar", "comentar", "nota_interna", "adjuntar", "ia"} & set(d["acciones"])
    assert "ASIGNACION" in [h["accion"] for h in d["historial"]]
    assert any(c["es_interno"] for c in d["comentarios"])
    assert client.get(url, headers=juan).json()["solo_lectura_participante"] is False

    # Y el backend rechaza las acciones aunque se intenten directamente
    assert client.post(f"{url}/estado", json={"estado": "EN_PROCESO", "comentario": "Motivo de prueba"}, headers=david).status_code == 403
    assert client.post(f"{url}/comentarios", json={"texto": "hola"}, headers=david).status_code == 403
    assert client.get(url, headers=denisse).status_code == 404


def test_responsable_recibe_comentarios_de_otros_del_equipo(client, como):
    """Si comenta un supervisor o la mesa (público o nota interna), el responsable recibe aviso; si comenta él, no."""
    t = crear_ticket(client, como("maria.andrade"))
    url = f"{API}/tickets/{t['id']}"
    analista = como("david.medina")
    assert client.get(url, headers=analista).json()["responsable"]

    def avisos():
        return [n for n in client.get(f"{API}/notificaciones", headers=analista).json() if n["tipo"] == "COMENTARIO"]

    antes = len(avisos())
    assert client.post(f"{url}/comentarios", json={"texto": "Revisa la partida", "es_interno": True},
                       headers=como("supervisor.tecnico")).status_code == 201
    assert client.post(f"{url}/comentarios", json={"texto": "Ya lo vemos"}, headers=como("mesa.servicios")).status_code == 201
    nuevos = avisos()[: len(avisos()) - antes]
    assert len(nuevos) == 2
    assert any("nota interna" in n["titulo"] for n in nuevos) and any("comentario de" in n["titulo"] for n in nuevos)
    # Su propio comentario no le genera aviso
    assert client.post(f"{url}/comentarios", json={"texto": "Atendiendo"}, headers=analista).status_code == 201
    assert len(avisos()) == antes + 2
