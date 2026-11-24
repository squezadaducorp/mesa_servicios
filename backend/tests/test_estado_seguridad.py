"""Seguridad y cumplimiento: política de acceso (37), servidor (40) y vulnerabilidades (41)."""
import io
import json
import zipfile

from sqlalchemy import select

from app.application.services import estado_seguridad_service as ess
from app.core.config import settings
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.conftest import API

DOM = "@aducorp.com.ec"


# ================================================================== 37 política de acceso
def test_politica_de_acceso_muestra_privilegiados_y_recuerda(client, como):
    ha = como("admin")
    pol = client.get(f"{API}/seguridad/politica", headers=ha).json()["politica"]
    r = client.put(f"{API}/seguridad/politica", json={**pol, "obligatoria_admin": True, "dias_gracia": 7}, headers=ha)
    assert r.status_code == 200, r.text

    d = client.get(f"{API}/cumplimiento/acceso", headers=ha).json()
    por_correo = {f["correo"]: f for f in d["privilegiados"]}
    assert por_correo["admin" + DOM]["estado"] == "EXENTA"                       # cuenta de emergencia
    assert por_correo["supervisor.operativo" + DOM]["estado"] == "PENDIENTE"
    assert por_correo["supervisor.operativo" + DOM]["dias_restantes"] == 7
    assert "maria.andrade" + DOM not in por_correo                               # analista: no tiene privilegios
    assert d["resumen"]["exentos"] == 1 and d["resumen"]["pendientes"] >= 1
    assert d["claves"]["min_longitud"] == settings.CLAVE_MIN_LONGITUD

    r = client.post(f"{API}/cumplimiento/acceso/recordar", headers=ha)
    assert r.status_code == 200 and r.json()["enviados"] == d["resumen"]["pendientes"] + d["resumen"]["vencidos"]
    with SessionLocal() as s:
        correos = s.scalars(select(m.ColaCorreo).where(m.ColaCorreo.plantilla == "RECORDATORIO_2FA")).all()
        assert "supervisor.operativo" + DOM in {c.para for c in correos}
        assert "admin" + DOM not in {c.para for c in correos}
    # Un analista no ve ni toca la política
    assert client.get(f"{API}/cumplimiento/acceso", headers=como("maria.andrade")).status_code == 403


def test_politica_de_claves_valida_y_queda_en_auditoria(client, como):
    ha = como("admin")
    r = client.put(f"{API}/cumplimiento/acceso/claves",
                   json={"claves_previas": 8, "max_intentos": 4, "bloqueo_min": 30, "inactividad_min": 20, "aviso_bloqueo": False}, headers=ha)
    assert r.status_code == 200, r.text
    assert r.json() | {"min_longitud": 0} == {"min_longitud": 0, "claves_previas": 8, "max_intentos": 4, "bloqueo_min": 30,
                                               "inactividad_min": 20, "aviso_bloqueo": False}
    assert client.put(f"{API}/cumplimiento/acceso/claves", json={"max_intentos": 1}, headers=ha).status_code == 422
    with SessionLocal() as s:
        assert s.get(m.Configuracion, "seguridad.max_intentos").valor == "4"
        assert s.get(m.Configuracion, "seguridad.aviso_bloqueo").valor == "no"
        assert s.scalar(select(m.Auditoria).where(m.Auditoria.accion == "POLITICA_CLAVES")) is not None


# ================================================================== 40 servidor
def test_servidor_lee_el_informe_del_script(client, como, tmp_path, monkeypatch):
    ha = como("admin")
    monkeypatch.setattr(settings, "SERVIDOR_ESTADO", str(tmp_path / "servidor.json"))
    d = client.get(f"{API}/cumplimiento/servidor", headers=ha).json()
    assert d["disponible"] is False and d["script"].endswith("verificar-servidor.sh")

    (tmp_path / "servidor.json").write_text(json.dumps({
        "generado": "2020-01-01T06:00:00Z",
        "servidor": {"nombre": "mesa-prod", "tipo": "c7i-flex.large", "region": "us-east-2"},
        "parches": {"pendientes": 0, "reinicio": True},
        "controles": [
            {"clave": "ssh", "nombre": "Puerto 22", "estado": "ok", "etiqueta": "Cerrado", "iso": "A.8.20"},
            {"clave": "parches", "nombre": "Parches", "estado": "alerta", "etiqueta": "Reinicio pendiente", "iso": "A.8.8"},
            {"clave": "raiz", "nombre": "Raíz", "estado": "raro", "etiqueta": "?", "iso": "A.8.2"},
            {"clave": "waf", "nombre": "WAF", "estado": "opcional", "etiqueta": "No instalado", "iso": "A.8.20"},
        ],
    }), encoding="utf-8")
    d = client.get(f"{API}/cumplimiento/servidor", headers=ha).json()
    assert d["disponible"] and d["servidor"]["nombre"] == "mesa-prod"
    assert (d["cumplidos"], d["total"]) == (1, 3)              # el opcional no cuenta
    assert d["controles"][2]["estado"] == "sin_dato"           # estado desconocido
    assert d["desactualizado"] is True                         # informe viejo
    assert client.get(f"{API}/cumplimiento/servidor", headers=como("supervisor.operativo")).status_code == 403


# ================================================================== 41 vulnerabilidades
def test_vulnerabilidades_sin_token_muestra_solo_la_politica(client, como, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN_SEGURIDAD", "")
    d = client.get(f"{API}/cumplimiento/vulnerabilidades", headers=como("admin")).json()
    assert d["configurado"] is False and d["plazos"] == {"CRITICAL": 7, "HIGH": 30, "MEDIUM": 90}


class _Resp:
    def __init__(self, datos=None, contenido=b"", estado=200):
        self._datos, self.content, self.status_code = datos, contenido, estado

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Cliente:
    def __init__(self, rutas):
        self.rutas = rutas

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        for clave, resp in self.rutas.items():
            if url.endswith(clave):
                return resp
        return _Resp(estado=404)


def test_vulnerabilidades_lee_escaneo_y_dependabot(client, como, monkeypatch):
    import httpx

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("resumen-mesa-api.json", json.dumps({"imagen": "mesa-api", "critica": 0, "alta": 1, "media": 4, "hallazgos": [
            {"id": "CVE-2026-1", "severidad": "HIGH", "paquete": "urllib3", "instalada": "2.0", "corregida": "2.6", "titulo": "Fuga"}]}))
    rutas = {
        "/actions/workflows/seguridad.yml/runs": _Resp({"workflow_runs": [{"id": 9, "status": "completed", "conclusion": "success",
                                                                          "run_started_at": "2026-11-24T10:00:00Z", "html_url": "u", "event": "schedule"}]}),
        "/actions/runs/9/jobs": _Resp({"jobs": [{"name": "Secretos en el código (gitleaks)", "conclusion": "success"}]}),
        "/actions/runs/9/artifacts": _Resp({"artifacts": [{"name": "resumen-mesa-api", "archive_download_url": "https://x/zip", "expired": False},
                                                          {"name": "seguridad-mesa-api", "archive_download_url": "https://x/otro"}]}),
        "https://x/zip": _Resp(contenido=zbuf.getvalue()),
        "/actions/workflows/ci.yml/runs": _Resp({"workflow_runs": [{"status": "completed", "conclusion": "success", "html_url": "c"}]}),
        "/dependabot/alerts": _Resp([{"number": 41, "created_at": "2026-11-18T00:00:00Z", "html_url": "a",
                                       "security_advisory": {"summary": "Formularios"},
                                       "security_vulnerability": {"severity": "high", "package": {"name": "python-multipart", "ecosystem": "pip"},
                                                                  "first_patched_version": {"identifier": "0.0.20"}},
                                       "dependency": {"manifest_path": "backend/requirements.txt"}}]),
        "/pulls": _Resp([{"user": {"login": "dependabot[bot]"}}, {"user": {"login": "squezada1993"}}]),
    }
    monkeypatch.setattr(settings, "GITHUB_TOKEN_SEGURIDAD", "token-de-prueba")
    monkeypatch.setattr(httpx, "Client", lambda **kw: _Cliente(rutas))
    ess._cache.clear()
    d = client.get(f"{API}/cumplimiento/vulnerabilidades?refrescar=true", headers=como("admin")).json()
    assert d["configurado"] and "error" not in d, d
    assert d["escaneo"]["conclusion"] == "success" and d["escaneo"]["jobs"][0]["conclusion"] == "success"
    assert d["componentes"] == [{"imagen": "mesa-api", "nombre": "Imagen api", "critica": 0, "alta": 1, "media": 4,
                                 "hallazgos": d["hallazgos"]}]
    alerta = d["dependabot"]["alertas"][0]
    assert alerta["severidad"] == "HIGH" and alerta["vence"].startswith("2026-12-18") and d["dependabot"]["prs_abiertos"] == 1
    assert d["totales"] == {"CRITICAL": 0, "HIGH": 2}

    # Token vencido: aviso, no error 500
    monkeypatch.setattr(httpx, "Client", lambda **kw: _Cliente({"/actions/workflows/seguridad.yml/runs": _Resp(estado=401)}))
    d = client.get(f"{API}/cumplimiento/vulnerabilidades?refrescar=true", headers=como("admin")).json()
    assert "token" in d["error"]
    ess._cache.clear()
