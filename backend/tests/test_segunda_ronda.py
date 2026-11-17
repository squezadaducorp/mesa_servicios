"""Segunda ronda: base de conocimiento, respuestas rápidas, recurrentes, reporte por correo, inventario y tickets en nombre de otra persona."""
import io
from datetime import date, datetime, time, timedelta

from openpyxl import load_workbook
from sqlalchemy import select

from app.application.services.recurrentes_service import RecurrentesService
from app.application.services.reportes_programados_service import ReportesProgramadosService, periodo_para
from app.domain import recurrencia as rc
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API
from tests.test_api import catalogo, crear_ticket, ids


def usuario_id(correo_local: str) -> int:
    with SessionLocal() as s:
        return s.scalar(select(m.Usuario.id).where(m.Usuario.correo == f"{correo_local}@aducorp.com.ec"))


def area_id(nombre: str) -> int:
    with SessionLocal() as s:
        return s.scalar(select(m.Area.id).where(m.Area.nombre == nombre))


def correos(codigo_asunto: str) -> list[m.ColaCorreo]:
    with SessionLocal() as s:
        return [c for c in s.scalars(select(m.ColaCorreo)) if codigo_asunto in c.asunto]


# =============================================================== recurrencia (dominio)
def test_recurrencia_primer_lunes_y_feriados():
    regla = rc.Regla(frecuencia="MENSUAL", desde=date(2026, 11, 1), semana_mes=1, dia_semana=1)
    fechas = [o.efectiva for _, o in zip(range(3), rc.ocurrencias(regla, lambda d: d.weekday() < 5))]
    assert fechas == [date(2026, 11, 2), date(2026, 12, 7), date(2027, 1, 4)]
    # Si el 2 de noviembre es feriado se mueve al siguiente día laborable
    o = next(rc.ocurrencias(regla, lambda d: d.weekday() < 5 and d != date(2026, 11, 2)))
    assert o.efectiva == date(2026, 11, 3) and o.movida
    assert rc.describir(regla) == "Mensual · primer lunes · 08:30"


def test_recurrencia_ultimo_dia_trimestral_y_diaria():
    regla = rc.Regla(frecuencia="TRIMESTRAL", desde=date(2026, 1, 1), dia_mes=-1)
    fechas = [o.nominal for _, o in zip(range(3), rc.ocurrencias(regla, lambda d: True))]
    assert fechas == [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31)]
    diaria = rc.Regla(frecuencia="DIARIA", desde=date(2026, 11, 13))   # viernes
    fechas = [o.efectiva for _, o in zip(range(2), rc.ocurrencias(diaria, lambda d: d.weekday() < 5))]
    assert fechas == [date(2026, 11, 13), date(2026, 11, 16)]   # se salta el fin de semana
    assert rc.validar(rc.Regla(frecuencia="SEMANAL", desde=date(2026, 1, 1))) is not None
    assert rc.rellenar_fecha("Mantenimiento {mes} {año}", date(2026, 12, 1)) == "Mantenimiento diciembre 2026"


def test_periodo_semanal_es_lunes_a_domingo_anterior():
    p = periodo_para("SEMANAL", date(2026, 11, 16))   # lunes
    assert (p.desde, p.hasta) == (date(2026, 11, 9), date(2026, 11, 15))
    assert periodo_para("MENSUAL", date(2026, 11, 1)).desde == date(2026, 10, 1)


# =============================================================== base de conocimiento
def articulo(client, h, **extra) -> dict:
    cats = catalogo(client, h)["categorias"]
    body = {"titulo": "No puedo ingresar a Ecuapass con el token", "sintoma": "Ecuapass dice que el token no es válido",
            "solucion": "Desconecte el token, cierre el navegador y vuelva a conectarlo antes de abrir Ecuapass.",
            "palabras_clave": "token, firma electrónica, ecuapass", "categoria_id": cats[0]["id"], "estado": "PUBLICADO", **extra}
    r = client.post(f"{API}/conocimiento", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_kb_sugerencias_y_ticket_evitado(client, como):
    a = articulo(client, como("david.medina"))
    borrador = articulo(client, como("david.medina"), titulo="Borrador interno sobre token", estado="BORRADOR")

    h = como("maria.andrade")
    sug = client.post(f"{API}/conocimiento/sugerir", json={"texto": "el token de ecuapass no funciona"}, headers=h).json()
    assert [x["id"] for x in sug] == [a["id"]]
    assert client.get(f"{API}/conocimiento/{borrador['id']}", headers=h).status_code == 404   # el cliente no ve borradores
    assert client.post(f"{API}/conocimiento", json={"titulo": "x" * 10, "solucion": "y" * 20}, headers=h).status_code == 403

    assert client.get(f"{API}/conocimiento/{a['id']}", headers=h).json()["vistas"] == 1
    assert client.post(f"{API}/conocimiento/{a['id']}/evitar-ticket", headers=h).status_code == 200
    detalle = client.get(f"{API}/conocimiento/{a['id']}", headers=como("david.medina")).json()
    assert detalle["tickets_evitados"] == 1 and detalle["util_pct"] == 100

    # Si igual crea el ticket, el analista ve qué artículos leyó
    t = crear_ticket(client, h, kb_vistos=[a["id"]])
    d = client.get(f"{API}/tickets/{t['id']}", headers=como("admin")).json()
    assert d["kb_vistos"] == [{"id": a["id"], "nombre": a["titulo"]}]


def test_kb_borrador_desde_ticket_resuelto(client, como):
    t = crear_ticket(client, como("maria.andrade"))
    h = como("admin")
    assert client.post(f"{API}/conocimiento/desde-ticket", json={"ticket_id": t["id"]}, headers=h).status_code == 422
    client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": "Se reinició el servicio y quedó transmitida."}, headers=h)
    r = client.post(f"{API}/tickets/{t['id']}/estado", json={"estado": "RESUELTO", "comentario": "Listo"}, headers=h)
    assert r.status_code == 200, r.text
    b = client.post(f"{API}/conocimiento/desde-ticket", json={"ticket_id": t["id"]}, headers=h).json()
    assert b["ticket_origen_numero"] == t["numero"] and b["solucion"]


# =============================================================== respuestas rápidas
def test_respuestas_rapidas(client, como):
    h = como("david.medina")
    r = client.post(f"{API}/respuestas", json={"atajo": "saludo", "titulo": "Saludo", "texto": "Hola {solicitante}, revisamos {ticket}.",
                                               "alcance": "PERSONAL"}, headers=h)
    assert r.status_code == 201, r.text
    resp = r.json()
    assert resp["atajo"] == "/saludo" and resp["puede_editar"]
    # Una compartida exige permiso de gestión (el analista no lo tiene)
    assert client.post(f"{API}/respuestas", json={"atajo": "/todos", "titulo": "Para todos", "texto": "abc", "alcance": "TODOS"},
                       headers=h).status_code == 403
    assert client.post(f"{API}/respuestas", json={"atajo": "/saludo", "titulo": "Otra", "texto": "abc", "alcance": "PERSONAL"},
                       headers=h).status_code == 409
    assert client.post(f"{API}/respuestas", json={"atajo": "/x1", "titulo": "Cliente", "texto": "abc", "alcance": "PERSONAL"},
                       headers=como("maria.andrade")).status_code == 403

    t = crear_ticket(client, como("maria.andrade"))
    para = client.get(f"{API}/respuestas/ticket/{t['id']}", headers=h).json()
    assert para[0]["texto"] == f"Hola María, revisamos {t['numero']}."
    r = client.post(f"{API}/tickets/{t['id']}/comentarios", json={"texto": para[0]["texto"], "respuesta_rapida_id": resp["id"]}, headers=h)
    assert r.status_code == 201, r.text
    assert client.get(f"{API}/respuestas", headers=h).json()[0]["usos"] == 1
    # La respuesta personal no la ve otro analista
    assert client.get(f"{API}/respuestas", headers=como("juan.villamar")).json() == []


# =============================================================== tickets recurrentes
def programacion(client, h, **extra) -> dict:
    cid, sid = ids(client, h, "CLASIF_ARANCEL", "Presentación DAI")
    prioridades = catalogo(client, h)["prioridades"]
    body = {"nombre": "Mantenimiento preventivo", "asunto": "Mantenimiento de {mes} {año}",
            "descripcion": "Revisión mensual de equipos de la planta baja.", "tareas": "Limpiar\nActualizar antivirus",
            "categoria_id": cid, "subcategoria_id": sid, "prioridad_id": prioridades[-1]["id"], "frecuencia": "MENSUAL",
            "semana_mes": 1, "dia_semana": 1, "hora": "08:30:00", "desde": "2026-11-01", **extra}
    r = client.post(f"{API}/recurrentes", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_recurrentes_crea_y_omite_si_sigue_abierto(client, como):
    h = como("admin")
    assert client.get(f"{API}/recurrentes", headers=como("david.medina")).status_code == 403
    prev = client.post(f"{API}/recurrentes/vista-previa", json={
        "nombre": "abc", "asunto": "Mantenimiento", "descripcion": "Revisión mensual", "categoria_id": 1, "subcategoria_id": 1,
        "prioridad_id": 1, "frecuencia": "MENSUAL", "dia_mes": 15, "desde": "2026-11-01"}, headers=h).json()
    assert len(prev["fechas"]) == 6
    p = programacion(client, h)
    assert p["descripcion_frecuencia"] == "Mensual · primer lunes · 08:30" and p["proxima_ejecucion"]

    with SessionLocal() as s:   # simulamos que llegó la fecha
        r = s.get(m.TicketRecurrente, p["id"])
        r.proxima_ejecucion = datetime(2026, 12, 7, 13, 30)
        s.commit()
        res = RecurrentesService(s).procesar(datetime(2026, 12, 7, 13, 31))
        s.commit()
        assert res == {"creados": 1, "omitidos": 0, "errores": 0}
        t = s.get(m.Ticket, r.ultimo_ticket_id)
        assert t.asunto == "Mantenimiento de diciembre 2026" and t.canal == "PROGRAMADO" and t.recurrente_id == r.id
        assert "☐ Limpiar" in t.descripcion
        assert r.proxima_ejecucion > datetime(2026, 12, 7, 14, 0)

        r.proxima_ejecucion = datetime(2027, 1, 4, 13, 30)
        s.commit()
        res = RecurrentesService(s).procesar(datetime(2027, 1, 4, 13, 31))
        s.commit()
        assert res["omitidos"] == 1 and "sigue abierto" in r.ultimo_resultado

    t = client.post(f"{API}/recurrentes/{p['id']}/ejecutar", headers=h)
    assert t.status_code == 201, t.text


# =============================================================== reporte por correo
def test_reporte_programado_prueba_y_envio(client, como):
    crear_ticket(client, como("maria.andrade"))
    h = como("admin")
    assert client.get(f"{API}/reportes-programados", headers=como("gerencia")).status_code == 403
    r = client.post(f"{API}/reportes-programados", json={
        "nombre": "Reporte semanal a gerencia", "destinatarios": ["gerencia@aducorp.com.ec", "GERENCIA@aducorp.com.ec"],
        "frecuencia": "SEMANAL", "dia_semana": 1, "hora": "08:00:00", "secciones": ["totales", "sla_area", "vencidos", "comparacion"]},
        headers=h)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["destinatarios"] == ["gerencia@aducorp.com.ec"] and rep["proximo_envio"]
    assert "Tickets nuevos" in client.get(f"{API}/reportes-programados/{rep['id']}/vista-previa", headers=h).json()["html"]

    assert client.post(f"{API}/reportes-programados/{rep['id']}/prueba", headers=h).status_code == 200
    with SessionLocal() as s:
        c = s.scalars(select(m.ColaCorreo).order_by(m.ColaCorreo.id.desc())).first()
        assert c.para == "admin@aducorp.com.ec" and c.adjunto_nombre.endswith(".xlsx")
        libro = load_workbook(io.BytesIO(c.adjunto))
        assert "Por área" in libro.sheetnames

        reporte = s.get(m.ReporteProgramado, rep["id"])
        momento = reporte.proximo_envio
        assert ReportesProgramadosService(s).procesar(momento + timedelta(minutes=1)) == {"enviados": 1}
        s.commit()
        assert reporte.ultimo_envio and reporte.proximo_envio > momento
    envios = client.get(f"{API}/reportes-programados/{rep['id']}/envios", headers=h).json()
    assert len(envios) == 2 and envios[0]["es_prueba"] is False


# =============================================================== inventario
def test_inventario_equipo_en_ticket_y_aviso(client, como):
    h = como("admin")
    maria = usuario_id("maria.andrade")
    r = client.post(f"{API}/inventario", json={"codigo": "adu-pc-014", "tipo": "PORTATIL", "marca_modelo": "Lenovo ThinkPad E14",
                                               "usuario_id": maria}, headers=h)
    assert r.status_code == 201, r.text
    eq = r.json()
    assert eq["codigo"] == "ADU-PC-014"
    otro = client.post(f"{API}/inventario", json={"codigo": "ADU-PC-099", "tipo": "ESCRITORIO", "marca_modelo": "Dell", "usuario_id":
                                                  usuario_id("david.medina"), "area_id": area_id("Tecnología")}, headers=h).json()
    assert client.get(f"{API}/inventario", headers=como("maria.andrade")).status_code == 403

    hm = como("maria.andrade")
    opciones = client.get(f"{API}/inventario/opciones", headers=hm).json()
    assert [o["codigo"] for o in opciones] == ["ADU-PC-014"] and opciones[0]["propio"]
    # No puede elegir un equipo ajeno
    cid, sid = ids(client, hm, "CLASIF_ARANCEL", "Presentación DAI")
    body = {"asunto": "Laptop no enciende", "descripcion": "La laptop no enciende desde esta mañana.", "categoria_id": cid, "subcategoria_id": sid}
    assert client.post(f"{API}/tickets", json={**body, "equipo_id": otro["id"]}, headers=hm).status_code in (403, 422)
    for _ in range(3):
        t = client.post(f"{API}/tickets", json={**body, "equipo_id": eq["id"]}, headers=hm).json()
    d = client.get(f"{API}/tickets/{t['id']}", headers=h).json()
    assert d["equipo"]["codigo"] == "ADU-PC-014" and "3.ª falla" in d["equipo"]["aviso"]
    ficha = client.get(f"{API}/inventario/{eq['id']}", headers=h).json()
    assert len(ficha["historial"]) == 3 and ficha["fallas_12m"] == 3


def test_inventario_importar_excel(client, como):
    h = como("admin")
    plantilla = client.get(f"{API}/inventario/plantilla", headers=h)
    assert plantilla.status_code == 200
    libro = load_workbook(io.BytesIO(plantilla.content))
    hoja = libro.active
    hoja["E2"] = "maria.andrade@aducorp.com.ec"
    hoja.append(["ADU-X-1", "Monitor", "LG 24", "", "nadie@aducorp.com.ec"])
    buf = io.BytesIO()
    libro.save(buf)
    r = client.post(f"{API}/inventario/importar", files={"archivo": ("equipos.xlsx", buf.getvalue())}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["creados"] == 2 and len(r.json()["errores"]) == 1
    r = client.post(f"{API}/inventario/importar", files={"archivo": ("equipos.xlsx", buf.getvalue())}, headers=h)
    assert r.json()["actualizados"] == 2


# =============================================================== en nombre de otra persona
def test_en_nombre_requiere_permiso_y_queda_registrado(client, como):
    hm, ha = como("maria.andrade"), como("admin")
    maria, luis = usuario_id("maria.andrade"), usuario_id("luis.paredes")
    cid, sid = ids(client, hm, "CLASIF_ARANCEL", "Presentación DAI")
    body = {"asunto": "Revisión de DAI de Luis", "descripcion": "Luis está en puerto sin acceso al sistema.", "categoria_id": cid,
            "subcategoria_id": sid, "solicitante_id": luis, "en_nombre_motivo": "Está en puerto sin computadora"}

    assert client.get(f"{API}/tickets/en-nombre/personas", headers=hm).json() == []
    assert client.post(f"{API}/tickets", json=body, headers=hm).status_code == 403

    # El administrador lo activa solo para el área Comercial y hasta una fecha
    hasta = (date.today() + timedelta(days=30)).isoformat()
    r = client.put(f"{API}/admin/usuarios/{maria}/en-nombre", json={"activa": True, "areas": [area_id("Legal")], "hasta": hasta}, headers=ha)
    assert r.status_code == 200 and r.json()["activa"]
    assert client.post(f"{API}/tickets", json=body, headers=hm).status_code == 403   # Luis es de Comercial, no de Legal
    client.put(f"{API}/admin/usuarios/{maria}/en-nombre", json={"activa": True, "areas": [area_id("Comercial")], "hasta": hasta}, headers=ha)
    assert [p["nombre"] for p in client.get(f"{API}/tickets/en-nombre/personas", headers=hm).json()] == ["Luis Alberto Paredes"]
    assert client.post(f"{API}/tickets", json={**body, "en_nombre_motivo": ""}, headers=hm).status_code == 422

    r = client.post(f"{API}/tickets", json=body, headers=hm)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["solicitante"]["id"] == luis and t["creado_por"]["id"] == maria
    assert t["solo_lectura_creador"] and "comentar" not in t["acciones"]
    assert any("registró un ticket en su nombre" in c.asunto and c.para == "luis.paredes@aducorp.com.ec" for c in correos("[ADU-"))
    with SessionLocal() as s:
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "TICKET_CREADO_EN_NOMBRE")) is not None
    # El creador lo ve en «Tickets en los que participé»
    lista = client.get(f"{API}/tickets", params={"participe": True}, headers=hm).json()["items"]
    assert t["id"] in [x["id"] for x in lista]
    # Luis lo ve como propio y puede responder
    assert "comentar" in client.get(f"{API}/tickets/{t['id']}", headers=como("luis.paredes")).json()["acciones"]

    # Las categorías sensibles no se pueden pedir en nombre de otro
    with SessionLocal() as s:
        s.get(m.Categoria, cid).restringida_en_nombre = True
        s.commit()
    assert client.post(f"{API}/tickets", json=body, headers=hm).status_code == 422

    # Vencida la autorización deja de funcionar
    with SessionLocal() as s:
        s.get(m.UsuarioDelegacion, maria).hasta = date.today() - timedelta(days=1)
        s.commit()
    assert client.get(f"{API}/tickets/en-nombre/personas", headers=hm).json() == []
    assert client.put(f"{API}/admin/usuarios/{maria}/en-nombre", json={"activa": False}, headers=ha).json()["activa"] is False


def test_categoria_flags_en_catalogo(client, como):
    h = como("admin")
    cat = client.get(f"{API}/admin/categorias", headers=h).json()[0]
    body = {k: cat[k] for k in ("codigo", "nombre", "descripcion", "palabras_clave", "color", "orden", "modo_asignacion", "activo")}
    body.update(supervisor_id=cat["supervisor"]["id"] if cat["supervisor"] else None, pide_equipo=True, restringida_en_nombre=True,
                responsables=[{"usuario_id": r["usuario_id"], "es_principal": r["es_principal"]} for r in cat["responsables"]])
    r = client.put(f"{API}/admin/categorias/{cat['id']}", json=body, headers=h)
    assert r.status_code == 200, r.text
    c = next(x for x in catalogo(client, h)["categorias"] if x["id"] == cat["id"])
    assert c["pide_equipo"] and c["restringida_en_nombre"]


def test_enviador_smtp_adjunta_archivo(monkeypatch):
    from app.infrastructure.email import smtp

    enviados = []

    class FalsoSmtp:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): enviados.append(msg)

    monkeypatch.setattr(smtp.settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(smtp.smtplib, "SMTP", FalsoSmtp)
    smtp.EnviadorSmtp().enviar("a@b.com", "Reporte", "<p>hola</p>", adjunto=("reporte.xlsx", b"PK123"))
    adjuntos = list(enviados[0].iter_attachments())
    assert adjuntos[0].get_filename() == "reporte.xlsx" and adjuntos[0].get_content() == b"PK123"
