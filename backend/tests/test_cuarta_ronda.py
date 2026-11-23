"""Cuarta ronda (parte 1): catálogo de servicios (26), gestión de cambios (27) y verificación en dos pasos (28)."""
from datetime import datetime, timedelta, timezone

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.api.v1.routers.auth import limitador_login
from app.application.services import dos_pasos_service as dp
from app.application.services.cambio_service import CambioService, riesgo
from app.core.config import settings
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API, CLAVE
from tests.test_segunda_ronda import area_id, usuario_id


@pytest.fixture(autouse=True)
def sin_limite():
    limitador_login.reiniciar()
    yield


def servicio(client, h, nombre: str) -> dict:
    lista = client.get(f"{API}/servicios", headers=h).json()["servicios"]
    s = next(x for x in lista if x["nombre"] == nombre)
    return client.get(f"{API}/servicios/{s['id']}", headers=h).json()


# ============================================================ 26 catálogo
def test_catalogo_alta_de_usuario_pide_aprobacion_y_reparte_tareas(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    cat = client.get(f"{API}/servicios", headers=hm).json()
    assert len(cat["servicios"]) == 8 and {"Accesos", "Equipos", "Personal", "Aduanas"} <= set(cat["grupos"])
    alta = servicio(client, hm, "Alta de usuario nuevo")
    assert alta["requiere_aprobacion"] and alta["plazo"] == "2 días hábiles" and alta["lo_pide"] == "Talento Humano"
    assert [c["clave"] for c in alta["campos"]][:3] == ["nombres", "cedula", "fecha_ingreso"]

    # Tareas con responsables distintos: la de ECUAPASS a Carlos Torres
    opciones = [{**o, "responsable_id": usuario_id("carlos.torres") if o["clave"] == "ecuapass" else o["responsable_id"]} for o in alta["opciones"]]
    edit = {k: alta[k] for k in ("nombre", "descripcion", "icono", "grupo", "categoria_id", "subcategoria_id", "plazo_horas", "plazo_texto",
                                 "requiere_aprobacion", "lo_pide", "titulo_campos", "titulo_opciones", "aviso", "campos", "orden", "activo")}
    assert client.put(f"{API}/servicios/admin/{alta['id']}", json={**edit, "opciones": opciones}, headers=hm).status_code == 403
    r = client.put(f"{API}/servicios/admin/{alta['id']}", json={**edit, "opciones": opciones}, headers=ha)
    assert r.status_code == 200, r.text

    body = {"respuestas": {"nombres": "Andrés Sebastián Villacís Haro", "cedula": "1716458823", "fecha_ingreso": "2026-12-01",
                           "area": area_id("Operaciones Aduaneras"), "cargo": "Asistente de liquidación",
                           "jefe": usuario_id("gerencia"), "sucursal": "Guayaquil · Puerto Marítimo"},
            "opciones": ["correo", "portatil", "ecuapass"], "observaciones": "Reemplaza a Daniela Cedeño."}
    falta = client.post(f"{API}/servicios/{alta['id']}/solicitar", json={**body, "respuestas": {**body["respuestas"], "cedula": "123"}}, headers=hm)
    assert falta.status_code == 422 and "Cédula" in falta.json()["detail"]
    r = client.post(f"{API}/servicios/{alta['id']}/solicitar", json=body, headers=hm)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    t = client.get(f"{API}/tickets/{tid}", headers=hm).json()
    # Aprueba el jefe elegido en el formulario (reutiliza las aprobaciones de la mejora 21)
    assert t["estado"] == "POR_APROBAR" and t["asunto"].startswith("Alta de usuario nuevo · Andrés")
    assert "Fecha de ingreso: 01/12/2026" in t["descripcion"] and "• Portátil" in t["descripcion"]
    assert [x["titulo"] for x in t["servicio"]["tareas"]] == ["Crear correo y licencia M365", "Preparar portátil e imagen",
                                                              "Alta en ECUAPASS · perfil liquidador"]
    assert t["sla_resolucion_min"] == 16 * 60
    mis = client.get(f"{API}/servicios", headers=hm).json()["mis_solicitudes"]
    assert mis[0]["avance"] == "Por aprobar · Gerencia General"

    hc = como("carlos.torres")
    assert client.get(f"{API}/tickets/{tid}", headers=hc).status_code == 200   # tiene una tarea: lo ve
    tarea = t["servicio"]["tareas"][2]
    assert client.post(f"{API}/servicios/tickets/{tid}/tareas/{tarea['id']}", json={"lista": True}, headers=hc).status_code == 422

    hg = como("gerencia")
    pend = client.get(f"{API}/aprobaciones", headers=hg).json()["pendientes"]
    assert client.post(f"{API}/aprobaciones/{pend[0]['id']}/responder", json={"aprobar": True}, headers=hg).status_code == 200
    with SessionLocal() as s:
        avisos = [n.titulo for n in s.scalars(select(m.Notificacion).where(m.Notificacion.usuario_id == usuario_id("carlos.torres")))]
    assert any("tarea" in a for a in avisos)

    d = client.get(f"{API}/tickets/{tid}", headers=hc).json()
    assert d["estado"] == "ASIGNADO" and "comentar" in d["acciones"] and "nota_interna" in d["acciones"]
    mia = next(x for x in d["servicio"]["tareas"] if x["id"] == tarea["id"])
    otra = next(x for x in d["servicio"]["tareas"] if x["id"] != tarea["id"])
    assert mia["puede_marcar"] and not otra["puede_marcar"]
    assert client.post(f"{API}/servicios/tickets/{tid}/tareas/{otra['id']}", json={"lista": True}, headers=hc).status_code == 403
    assert client.post(f"{API}/servicios/tickets/{tid}/tareas/{tarea['id']}", json={"lista": True}, headers=hc).json()["estado"] == "LISTA"
    assert "1 de 3 tareas listas" in client.get(f"{API}/servicios", headers=hm).json()["mis_solicitudes"][0]["avance"]
    # Las tareas sin responsable propio quedaron con el responsable del ticket
    assert all(x["responsable"] for x in d["servicio"]["tareas"])


def test_catalogo_sin_aprobacion_se_asigna_directo(client, como):
    hm = como("maria.andrade")
    buzon = servicio(client, hm, "Buzón compartido o lista")
    r = client.post(f"{API}/servicios/{buzon['id']}/solicitar",
                    json={"respuestas": {"buzon": "facturacion@", "accion": "Acceso a un buzón existente"}}, headers=hm)
    assert r.status_code == 201, r.text
    t = client.get(f"{API}/tickets/{r.json()['id']}", headers=hm).json()
    assert t["estado"] == "ASIGNADO" and t["canal"] == "CATALOGO" and len(t["servicio"]["tareas"]) == 1
    mal = client.post(f"{API}/servicios/{buzon['id']}/solicitar", json={"respuestas": {"buzon": "x", "accion": "Otra cosa"}}, headers=hm)
    assert mal.status_code == 422


# ============================================================ 27 cambios
def proximo_sabado(hora: int = 8) -> datetime:
    """Un sábado futuro que no es el último día hábil del mes (no cae en el congelamiento de cierre)."""
    hoy = datetime.now(timezone.utc)
    d = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
    return d.replace(hour=hora + 5, minute=0, second=0, microsecond=0)   # 08:00 Ecuador = 13:00 UTC


SOLICITUD = {"formato": "GENERAL", "titulo": "Actualizar el sistema contable a la versión 2027", "tipo_solicitud": "MEJORA",
             "aplicacion": "Sistema contable", "pantalla": "Facturación electrónica SRI",
             "situacion_actual": "La versión 2025 deja de recibir actualizaciones del SRI el 31/12.",
             "situacion_deseada": "Actualizar a la versión 2027 antes del cierre de año.", "beneficiados": "TODA_EMPRESA",
             "prioridad_sugerida": "ALTA"}


def evaluacion(**extra) -> dict:
    ini = proximo_sabado()
    return {"clasificacion": "MEJORA", "tipo_cambio": "NORMAL", "impacto": "ALTO", "probabilidad": "MEDIA", "esfuerzo": "1_3",
            "prioridad_ti": "ALTA", "plan_implementacion": "1. Respaldo\n2. Instalar v2027", "plan_reversion": "Restaurar respaldo (40 min)",
            "ventana_inicio": ini.isoformat(), "ventana_fin": (ini + timedelta(hours=4)).isoformat(), "comentario": "Ventana fuera de horario",
            **extra}


def test_cambio_normal_riesgo_medio_pasa_por_gerencia(client, como):
    hm, ha, hg = como("maria.andrade"), como("admin"), como("gerencia")
    assert riesgo("ALTO", "MEDIA") == "MEDIO" and riesgo("BAJO", "MEDIA") == "BAJO" and riesgo("MEDIO", "ALTA") == "ALTO"
    r = client.post(f"{API}/cambios", json={**SOLICITUD, "aplicacion": None}, headers=hm)
    assert r.status_code == 422   # TI-FOR-002 exige la aplicación
    c = client.post(f"{API}/cambios", json=SOLICITUD, headers=hm).json()
    assert c["numero"].startswith("CAM-") and c["numero"].endswith("-001") and c["estado"] == "SOLICITADO"
    assert "evaluar" not in c["acciones"] and "editar" in c["acciones"]
    assert client.post(f"{API}/cambios/{c['id']}/evaluar", json=evaluacion(), headers=hm).status_code == 403
    assert client.post(f"{API}/cambios/{c['id']}/evaluar", json=evaluacion(plan_reversion=""), headers=ha).status_code == 422

    # Evalúa el Jefe de TI (admin): su evaluación es la aprobación; riesgo medio → Gerencia
    e = client.post(f"{API}/cambios/{c['id']}/evaluar", json=evaluacion(), headers=ha)
    assert e.status_code == 200, e.text
    e = e.json()
    assert e["riesgo"] == "MEDIO" and e["estado"] == "EN_APROBACION"
    assert [(a["rol"], a["estado"]) for a in e["aprobaciones"]] == [("JEFE_TI", "APROBADO"), ("GERENCIA", "PENDIENTE")]
    g = client.get(f"{API}/cambios/{c['id']}", headers=hg).json()
    assert "aprobar" in g["acciones"]
    assert client.post(f"{API}/cambios/{c['id']}/responder", json={"aprobar": False}, headers=hg).status_code == 422
    p = client.post(f"{API}/cambios/{c['id']}/responder", json={"aprobar": True}, headers=hg).json()
    assert p["estado"] == "PROGRAMADO"

    cal = client.get(f"{API}/cambios/calendario", params={"desde": proximo_sabado().date().isoformat()}, headers=ha).json()
    assert any(x["numero"] == c["numero"] for d in cal["dias"] for x in d["cambios"])
    lista = client.get(f"{API}/cambios", headers=ha).json()
    assert lista["resumen"]["programados"] == 1
    assert client.get(f"{API}/cambios", headers=como("carlos.torres")).json()["cambios"] == []   # no es suyo

    i = client.post(f"{API}/cambios/{c['id']}/implementar", json={"version_ref": "PR #36"}, headers=ha).json()
    assert i["estado"] == "EN_REVISION"
    f = client.post(f"{API}/cambios/{c['id']}/revision", json={"resultado": "EXITOSO", "probado_solicitante": True}, headers=ha).json()
    assert f["estado"] == "IMPLEMENTADO" and f["resultado"] == "EXITOSO"
    assert client.get(f"{API}/cambios", headers=ha).json()["resumen"]["exitosos_pct"] == 100

    x = client.get(f"{API}/cambios/exportar", headers=ha)
    assert x.status_code == 200
    import io

    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws["A5"].value == c["numero"] and ws["S5"].value == "Implementado"


def test_cambio_estandar_congelamiento_y_rechazo(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    c = client.post(f"{API}/cambios", json={**SOLICITUD, "formato": "MESA", "tipo_solicitud": "CATALOGO", "partes": ["Crear ticket"]},
                    headers=hm).json()
    assert c["aplicacion"] == "Mesa de Servicios"
    # Periodo congelado: no se puede programar ahí salvo emergencia
    ini = proximo_sabado()
    r = client.post(f"{API}/cambios/congelamientos", json={"titulo": "Auditoría externa", "inicio": (ini - timedelta(hours=2)).isoformat(),
                                                             "fin": (ini + timedelta(days=1)).isoformat()}, headers=ha)
    assert r.status_code == 201
    bloqueado = client.post(f"{API}/cambios/{c['id']}/evaluar", json=evaluacion(tipo_cambio="ESTANDAR", impacto="BAJO", probabilidad="BAJA"),
                            headers=ha)
    assert bloqueado.status_code == 422 and "congelado" in bloqueado.json()["detail"]
    ok = client.post(f"{API}/cambios/{c['id']}/evaluar", json=evaluacion(tipo_cambio="EMERGENCIA", impacto="BAJO", probabilidad="BAJA"),
                     headers=ha).json()
    assert ok["estado"] == "PROGRAMADO" and ok["congelado"]
    # Estándar en otra fecha: sin aprobaciones
    c2 = client.post(f"{API}/cambios", json=SOLICITUD, headers=hm).json()
    ini2 = ini + timedelta(days=3)
    e = client.post(f"{API}/cambios/{c2['id']}/evaluar", json=evaluacion(tipo_cambio="ESTANDAR", impacto="BAJO", probabilidad="BAJA",
                                                                       ventana_inicio=ini2.isoformat(),
                                                                       ventana_fin=(ini2 + timedelta(hours=1)).isoformat()), headers=ha).json()
    assert e["estado"] == "PROGRAMADO" and e["aprobaciones"] == []
    # Rechazo con motivo
    c3 = client.post(f"{API}/cambios", json=SOLICITUD, headers=hm).json()
    assert client.post(f"{API}/cambios/{c3['id']}/evaluar", json=evaluacion(decision="RECHAZAR", comentario=""), headers=ha).status_code == 422
    rz = client.post(f"{API}/cambios/{c3['id']}/evaluar", json=evaluacion(decision="RECHAZAR", comentario="No aplica"), headers=ha).json()
    assert rz["estado"] == "RECHAZADO" and rz["motivo"] == "No aplica"
    # Cierre de mes automático
    with SessionLocal() as s:
        svc = CambioService(s)
        fin_mes = [f for f in svc.congelamientos(datetime(2026, 11, 27), datetime(2026, 12, 1)) if f["automatico"]]
        assert fin_mes and fin_mes[0]["inicio"] == datetime(2026, 11, 30, 5, 0)   # lunes 30/11 00:00 Ecuador (el 28 es sábado)


# ============================================================ 28 dos pasos
def politica(client, ha, **cambios) -> dict:
    base = {"obligatoria_admin": False, "obligatoria_analistas": False, "opcional_otros": True, "permitir_correo": True,
            "solo_fuera_oficina": False, "redes_oficina": "", "dias_confianza": 30, "exentos": ["admin@aducorp.com.ec"]}
    r = client.put(f"{API}/seguridad/politica", json={**base, **cambios}, headers=ha)
    assert r.status_code == 200, r.text
    return r.json()


def entrar(client, usuario: str, **extra):
    return client.post(f"{API}/auth/login", json={"correo": f"{usuario}@aducorp.com.ec", "clave": CLAVE, **extra})


def test_dos_pasos_con_authenticator(client, como, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    hd = como("david.medina")
    est = client.get(f"{API}/seguridad/mi-cuenta", headers=hd).json()
    assert est["metodo"] is None and not est["exigida"] and est["puede_correo"] is False   # sin correo no se ofrece
    assert client.post(f"{API}/seguridad/mi-cuenta/iniciar", json={"metodo": "CORREO"}, headers=hd).status_code == 422
    ini = client.post(f"{API}/seguridad/mi-cuenta/iniciar", json={"metodo": "APP"}, headers=hd).json()
    assert ini["qr"].startswith("data:image/svg+xml") and ini["uri"].startswith("otpauth://totp/")
    clave = ini["clave"].replace(" ", "")
    assert client.post(f"{API}/seguridad/mi-cuenta/confirmar", json={"codigo": "000000"}, headers=hd).status_code == 422
    codigos = client.post(f"{API}/seguridad/mi-cuenta/confirmar", json={"codigo": dp.codigo_totp(clave, dp.paso_actual())}, headers=hd).json()["codigos"]
    assert len(codigos) == 8 and len(codigos[0]) == 9

    # Ahora el inicio de sesión pide el segundo paso
    r = entrar(client, "david.medina").json()
    assert "access_token" not in r and r["segundo_paso"]["modo"] == "VERIFICAR" and r["segundo_paso"]["metodo"] == "APP"
    assert r["segundo_paso"]["correo_mascara"] == "d•••••@aducorp.com.ec" and not r["segundo_paso"]["puede_correo"]
    desafio = r["segundo_paso"]["desafio"]
    assert client.post(f"{API}/auth/2fa/enviar-codigo", json={"desafio": desafio}).status_code == 422
    malo = client.post(f"{API}/auth/2fa/verificar", json={"desafio": desafio, "codigo": "123456"})
    assert malo.status_code == 401 and "quedan 4" in malo.json()["detail"]
    # El código ya usado al activar no sirve otra vez; el del siguiente periodo sí
    siguiente = dp.codigo_totp(clave, dp.paso_actual() + 1)
    ok = client.post(f"{API}/auth/2fa/verificar", json={"desafio": desafio, "codigo": siguiente, "confiar": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"] and ok.json()["equipo_token"]
    assert client.post(f"{API}/auth/2fa/verificar", json={"desafio": desafio, "codigo": siguiente}).status_code == 401   # desafío usado

    # Equipo de confianza: no vuelve a pedir el código
    assert "access_token" in entrar(client, "david.medina", equipo_token=ok.json()["equipo_token"]).json()
    # Código de respaldo (una sola vez)
    d2 = entrar(client, "david.medina").json()["segundo_paso"]["desafio"]
    assert client.post(f"{API}/auth/2fa/verificar", json={"desafio": d2, "codigo": codigos[0].lower()}).status_code == 200
    d3 = entrar(client, "david.medina").json()["segundo_paso"]["desafio"]
    assert client.post(f"{API}/auth/2fa/verificar", json={"desafio": d3, "codigo": codigos[0]}).status_code == 401
    with SessionLocal() as s:
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "DOSF_FALLIDA")) is not None

    # El administrador la restablece (cambió de celular)
    ha = como("admin")
    est = client.get(f"{API}/seguridad/politica", headers=ha).json()
    fila = next(u for u in est["usuarios"] if u["correo"] == "david.medina@aducorp.com.ec")
    assert fila["metodo"] == "APP" and fila["codigos_restantes"] == 7
    assert client.post(f"{API}/seguridad/usuarios/{fila['id']}/restablecer", headers=como("maria.andrade")).status_code == 403
    assert client.post(f"{API}/seguridad/usuarios/{fila['id']}/restablecer", headers=ha).status_code == 200
    assert "access_token" in entrar(client, "david.medina", equipo_token=ok.json()["equipo_token"]).json()
    with SessionLocal() as s:
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "DOSF_RESTABLECIDA")) is not None


def test_politica_obliga_a_activar_al_entrar(client, como, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    ha = como("admin")
    pol = politica(client, ha, obligatoria_analistas=True, obligatoria_admin=True)
    assert pol["politica"]["obligatoria_analistas"]
    pend = next(u for u in pol["usuarios"] if u["correo"] == "jorge.caicedo@aducorp.com.ec")
    assert pend["exigida"] and pend["pendiente_dias"] == 0
    # La cuenta de emergencia queda fuera
    assert "access_token" in entrar(client, "admin").json()
    assert next(u for u in pol["usuarios"] if u["correo"] == "admin@aducorp.com.ec")["exento"]
    # Clientes internos: opcional
    assert "access_token" in entrar(client, "maria.andrade").json()

    r = entrar(client, "jorge.caicedo").json()["segundo_paso"]
    assert r["modo"] == "ACTIVAR" and r["metodo"] is None
    assert client.post(f"{API}/auth/2fa/activar/iniciar", json={"desafio": r["desafio"], "metodo": "CORREO"}).status_code == 422
    ini = client.post(f"{API}/auth/2fa/activar/iniciar", json={"desafio": r["desafio"], "metodo": "APP"}).json()
    clave = ini["clave"].replace(" ", "")
    t = client.post(f"{API}/auth/2fa/activar/confirmar",
                    json={"desafio": r["desafio"], "codigo": dp.codigo_totp(clave, dp.paso_actual()), "metodo": "APP"})
    assert t.status_code == 200, t.text
    assert t.json()["access_token"] and len(t.json()["codigos_respaldo"]) == 8
    # No puede desactivarla: su rol la tiene obligatoria
    hj = {"Authorization": f"Bearer {t.json()['access_token']}"}
    assert client.post(f"{API}/seguridad/mi-cuenta/desactivar", json={"clave": CLAVE}, headers=hj).status_code == 422
    # Las redes de la oficina deben ser IP o rangos válidos
    assert client.put(f"{API}/seguridad/politica", json={"obligatoria_admin": False, "obligatoria_analistas": True, "opcional_otros": True,
                                                        "permitir_correo": True, "solo_fuera_oficina": True, "redes_oficina": "no-es-ip",
                                                        "dias_confianza": 30, "exentos": []}, headers=ha).status_code == 422


def test_codigo_por_correo_cuando_el_correo_esta_activo(client, como, monkeypatch):
    enviados = []

    class Falso:
        def enviar(self, para, asunto, cuerpo, cc=None, adjunto=None):
            enviados.append((para, asunto))

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr("app.infrastructure.email.smtp.enviador", lambda: Falso())
    hl = como("luis.paredes")
    assert client.get(f"{API}/seguridad/mi-cuenta", headers=hl).json()["puede_correo"]
    assert client.post(f"{API}/seguridad/mi-cuenta/iniciar", json={"metodo": "CORREO"}, headers=hl).json()["enviado_a"].startswith("l•")
    codigo = enviados[-1][1][:6]
    r = client.post(f"{API}/seguridad/mi-cuenta/confirmar", json={"metodo": "CORREO", "codigo": codigo}, headers=hl)
    assert r.status_code == 200, r.text
    paso = entrar(client, "luis.paredes").json()["segundo_paso"]
    assert paso["metodo"] == "CORREO" and paso["codigo_enviado"]
    codigo = enviados[-1][1][:6]
    ok = client.post(f"{API}/auth/2fa/verificar", json={"desafio": paso["desafio"], "codigo": codigo})
    assert ok.status_code == 200, ok.text
    assert enviados[-1][0] == "luis.paredes@aducorp.com.ec"
