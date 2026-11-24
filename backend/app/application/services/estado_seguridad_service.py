"""Seguridad y cumplimiento: política de acceso (37), servidor (40) y vulnerabilidades (41).

- Política de acceso: resume la verificación en dos pasos de las cuentas con privilegios, permite ajustar la política
  de contraseñas y bloqueo, y envía un recordatorio a quien aún no activa la verificación obligatoria.
- Servidor: lee el informe JSON que ``deploy/nube/verificar-servidor.sh`` deja cada día en el servidor
  (``settings.SERVIDOR_ESTADO``). La API corre en un contenedor y no puede revisar el servidor por sí misma.
- Vulnerabilidades: lee de GitHub (con un token de solo lectura) el último escaneo del flujo «Seguridad», las alertas
  abiertas de Dependabot y sus PR. Sin token, muestra solo la política de plazos.
"""
from __future__ import annotations

import html
import io
import json
import logging
import time
import zipfile
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.application.errores import Contexto, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.dos_pasos_service import ROLES_ADMIN, DosPasosService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

log = logging.getLogger(__name__)

# clave: (valor por defecto, mínimo, máximo, descripción)
CLAVES = {
    "seguridad.claves_previas": (5, 0, 24, "Contraseñas anteriores que no se pueden repetir"),
    "seguridad.max_intentos": (5, 3, 20, "Intentos fallidos antes de bloquear la cuenta"),
    "seguridad.bloqueo_min": (15, 5, 1440, "Minutos que la cuenta queda bloqueada"),
    "seguridad.inactividad_min": (30, 0, 480, "Minutos sin actividad antes de cerrar la sesión (0 = desactivado)"),
}
PLAZOS = {"CRITICAL": 7, "HIGH": 30, "MEDIUM": 90}
SEVERIDAD = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "moderate": "MEDIUM", "low": "LOW"}
CACHE_SEG = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def _si(v: str | None) -> bool:
    return (v or "").strip().lower() in ("si", "sí", "true", "1", "s")


def _fecha_gh(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class EstadoSeguridadService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # ============================================================ 37 política de acceso
    def _claves(self) -> dict:
        cfg = CatalogoRepository(self.session).configuracion()
        out: dict = {"min_longitud": settings.CLAVE_MIN_LONGITUD, "aviso_bloqueo": _si(cfg.get("seguridad.aviso_bloqueo", "si"))}
        for k, (defecto, minimo, maximo, _) in CLAVES.items():
            try:
                out[k.split(".", 1)[1]] = max(minimo, min(int(cfg.get(k, defecto)), maximo))
            except (TypeError, ValueError):
                out[k.split(".", 1)[1]] = defecto
        return out

    def _privilegiados(self) -> list[dict]:
        dp = DosPasosService(self.session)
        pol = dp.politica()
        filas = []
        for u in dp._usuarios():
            exento = u.correo.lower() in pol["exentos"]
            exigida = dp.exigida(u, pol)
            if not (u.rol.codigo in ROLES_ADMIN or exigida or exento):
                continue
            restante = dp.dias_restantes(u, pol)
            if u.dosf_metodo:
                estado = "ACTIVA"
            elif exento:
                estado = "EXENTA"
            elif not exigida:
                estado = "OPCIONAL"
            elif restante:
                estado = "PENDIENTE"
            else:
                estado = "VENCIDA"
            filas.append({"id": u.id, "nombre": u.nombre, "correo": u.correo, "rol": u.rol.nombre, "estado": estado,
                          "metodo": u.dosf_metodo, "dias_restantes": restante, "ultimo_login": _iso(u.ultimo_login)})
        orden = {"VENCIDA": 0, "PENDIENTE": 1, "OPCIONAL": 2, "ACTIVA": 3, "EXENTA": 4}
        return sorted(filas, key=lambda f: (orden[f["estado"]], f["nombre"]))

    def acceso(self) -> dict:
        pol = DosPasosService(self.session).politica()
        privilegiados = self._privilegiados()
        cuenta = lambda *e: sum(1 for f in privilegiados if f["estado"] in e)  # noqa: E731
        cfg = CatalogoRepository(self.session).configuracion()
        return {
            "dos_pasos": pol,
            "claves": self._claves(),
            "privilegiados": privilegiados,
            "resumen": {"total": len(privilegiados) - cuenta("EXENTA"), "con_verificacion": cuenta("ACTIVA"),
                        "pendientes": cuenta("PENDIENTE"), "vencidos": cuenta("VENCIDA"), "exentos": cuenta("EXENTA")},
            "correos_alerta": cfg.get("seguridad.correos_alerta", "") or "",
        }

    def guardar_claves(self, datos: dict, ctx: Contexto) -> dict:
        valores: dict[str, str] = {"seguridad.aviso_bloqueo": "si" if datos.get("aviso_bloqueo") else "no"}
        for k, (_, minimo, maximo, nombre) in CLAVES.items():
            corto = k.split(".", 1)[1]
            v = datos.get(corto)
            if v is None:
                continue
            if not minimo <= int(v) <= maximo:
                raise ReglaNegocio(f"{nombre}: use un valor entre {minimo} y {maximo}")
            valores[k] = str(int(v))
        ahora, quien = utcnow(), ctx.usuario
        cambios = {}
        for k, v in valores.items():
            fila = self.session.get(m.Configuracion, k)
            descripcion = CLAVES[k][3] if k in CLAVES else "Avisar por correo a la persona cuando su cuenta se bloquea (si/no)"
            if fila is None:
                self.session.add(m.Configuracion(clave=k, valor=v, descripcion=descripcion, fecha_actualizacion=ahora,
                                                 actualizado_por=quien.id if quien else None))
                cambios[k] = v
            elif fila.valor != v:
                cambios[k] = {"de": fila.valor, "a": v}
                fila.valor, fila.fecha_actualizacion, fila.actualizado_por = v, ahora, quien.id if quien else None
        self.session.flush()
        if cambios:
            self.auditoria.registrar(ctx, AccionAuditoria.POLITICA_CLAVES, "configuracion", None, cambios)
        return self._claves()

    def recordar(self, ctx: Contexto) -> dict:
        """Correo a quien tiene la verificación obligatoria y aún no la activa."""
        from app.application.services.notificacion_service import cuentas_sistema
        from app.infrastructure.email.smtp import plantilla_base

        enlace = f"{settings.APP_URL.rstrip('/')}/seguridad"
        enviados = []
        for f in self._privilegiados():
            if f["estado"] not in ("PENDIENTE", "VENCIDA") or f["correo"].lower() in cuentas_sistema():
                continue
            plazo = (f"Le quedan <b>{f['dias_restantes']} días</b> para activarla; después se le pedirá al entrar."
                     if f["estado"] == "PENDIENTE" else "El plazo ya venció: la Mesa le pedirá activarla en su próximo ingreso.")
            cuerpo = (f"<p>Hola {html.escape(f['nombre'])}:</p>"
                      "<p>Por la política de seguridad de ADUCORP (ISO 27001), su cuenta de la Mesa de Servicios necesita la "
                      f"<b>verificación en dos pasos</b>. {plazo}</p>"
                      "<p>Toma dos minutos: instale Microsoft Authenticator o Google Authenticator en su celular y siga los pasos en "
                      f"<a href=\"{enlace}\">Seguridad de la cuenta</a>.</p>"
                      "<p>Si tiene dudas, responda este correo o escriba a TI.</p>")
            self.session.add(m.ColaCorreo(para=f["correo"][:500], asunto="Active la verificación en dos pasos en la Mesa de Servicios",
                                          cuerpo_html=plantilla_base(cuerpo), plantilla="RECORDATORIO_2FA", estado="PENDIENTE",
                                          proximo_intento=utcnow(), fecha_creacion=utcnow()))
            enviados.append(f["correo"])
        if enviados:
            self.auditoria.registrar(ctx, AccionAuditoria.RECORDATORIO_2FA, "usuario", None, {"para": enviados})
        return {"enviados": len(enviados)}

    # ============================================================ 40 servidor
    def servidor(self) -> dict:
        ruta = settings.SERVIDOR_ESTADO
        base = {"disponible": False, "archivo": ruta, "script": "deploy/nube/verificar-servidor.sh"}
        try:
            with open(ruta, encoding="utf-8") as fh:
                datos = json.load(fh)
        except FileNotFoundError:
            return base
        except (OSError, ValueError) as exc:
            log.warning("No se pudo leer el estado del servidor %s: %s", ruta, exc)
            return {**base, "error": "El informe del servidor no se pudo leer. Vuelva a ejecutar el script de verificación."}
        controles = [c for c in datos.get("controles") or [] if isinstance(c, dict) and c.get("nombre")]
        for c in controles:
            if c.get("estado") not in ("ok", "alerta", "sin_dato", "opcional"):
                c["estado"] = "sin_dato"
        generado = _fecha_gh(datos.get("generado"))
        horas = round((utcnow() - generado).total_seconds() / 3600, 1) if generado else None
        obligatorios = [c for c in controles if c["estado"] != "opcional"]
        return {
            **base, "disponible": True, "generado": _iso(generado), "antiguedad_horas": horas,
            "desactualizado": horas is None or horas > 36,
            "servidor": datos.get("servidor") or {}, "parches": datos.get("parches") or {},
            "controles": controles, "cumplidos": sum(1 for c in obligatorios if c["estado"] == "ok"), "total": len(obligatorios),
        }

    # ============================================================ 41 vulnerabilidades
    def vulnerabilidades(self, refrescar: bool = False) -> dict:
        repo = settings.GITHUB_REPO
        base = {"configurado": bool(settings.GITHUB_TOKEN_SEGURIDAD), "repo": repo, "enlace": f"https://github.com/{repo}",
                "plazos": PLAZOS}
        if not settings.GITHUB_TOKEN_SEGURIDAD:
            return base
        guardado = _cache.get(repo)
        if guardado and not refrescar and time.time() - guardado[0] < CACHE_SEG:
            return guardado[1]
        try:
            datos = {**base, **self._leer_github(repo), "actualizado": _iso(utcnow())}
        except Exception as exc:   # GitHub caído, token vencido o sin permisos: se muestra el aviso, no un error 500
            log.warning("No se pudo leer GitHub para Vulnerabilidades: %s", exc)
            datos = {**base, "error": f"No se pudo leer GitHub: {exc}"[:300], "actualizado": _iso(utcnow())}
        _cache[repo] = (time.time(), datos)
        return datos

    def _leer_github(self, repo: str) -> dict:
        import httpx

        api = f"https://api.github.com/repos/{repo}"
        cabeceras = {"Authorization": f"Bearer {settings.GITHUB_TOKEN_SEGURIDAD}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "mesa-servicios"}
        with httpx.Client(headers=cabeceras, timeout=20, follow_redirects=True) as c:
            def leer(url: str, **params) -> dict | list:
                r = c.get(url, params=params or None)
                if r.status_code in (401, 403):
                    raise RuntimeError("el token no tiene permiso o venció (revise GITHUB_TOKEN_SEGURIDAD)")
                if r.status_code == 404:
                    raise RuntimeError(f"no se encontró {url.replace(api, repo)} (revise GITHUB_REPO y los permisos del token)")
                r.raise_for_status()
                return r.json()

            # Último escaneo «Seguridad» sobre main
            escaneo: dict = {}
            componentes: list[dict] = []
            runs = leer(f"{api}/actions/workflows/seguridad.yml/runs", branch="main", per_page=5).get("workflow_runs") or []
            corrida = next((x for x in runs if x.get("status") == "completed"), runs[0] if runs else None)
            if corrida:
                jobs = leer(f"{api}/actions/runs/{corrida['id']}/jobs", per_page=30).get("jobs") or []
                escaneo = {"fecha": _iso(_fecha_gh(corrida.get("run_started_at") or corrida.get("created_at"))),
                           "estado": corrida.get("status"), "conclusion": corrida.get("conclusion"), "url": corrida.get("html_url"),
                           "evento": corrida.get("event"),
                           "jobs": [{"nombre": j.get("name"), "conclusion": j.get("conclusion")} for j in jobs]}
                artefactos = leer(f"{api}/actions/runs/{corrida['id']}/artifacts", per_page=50).get("artifacts") or []
                for a in artefactos:
                    if not str(a.get("name", "")).startswith("resumen-") or a.get("expired"):
                        continue
                    try:
                        r = c.get(a["archive_download_url"])
                        r.raise_for_status()
                        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                            for nombre in z.namelist():
                                if nombre.endswith(".json"):
                                    componentes.append(self._componente(json.loads(z.read(nombre))))
                    except Exception as exc:  # un artefacto dañado no tumba la pestaña
                        log.warning("Artefacto %s ilegible: %s", a.get("name"), exc)
            componentes.sort(key=lambda x: {"mesa-api": 0, "mesa-web": 1}.get(x["imagen"], 2))

            # Revisión de librerías del CI (pip-audit y npm audit)
            ci = leer(f"{api}/actions/workflows/ci.yml/runs", branch="main", per_page=5).get("workflow_runs") or []
            ci_ultima = next((x for x in ci if x.get("status") == "completed"), None)

            # Alertas de Dependabot y sus PR
            alertas = []
            for a in leer(f"{api}/dependabot/alerts", state="open", per_page=100):
                adv, vul = a.get("security_advisory") or {}, a.get("security_vulnerability") or {}
                sev = SEVERIDAD.get(str(vul.get("severity") or adv.get("severity") or "").lower(), "LOW")
                creada = _fecha_gh(a.get("created_at"))
                plazo = PLAZOS.get(sev)
                alertas.append({
                    "numero": a.get("number"), "severidad": sev, "paquete": (vul.get("package") or {}).get("name"),
                    "ecosistema": (vul.get("package") or {}).get("ecosystem"), "resumen": adv.get("summary"),
                    "manifiesto": (a.get("dependency") or {}).get("manifest_path"), "corregida": (vul.get("first_patched_version") or {}).get("identifier"),
                    "creada": _iso(creada), "vence": _iso(creada + timedelta(days=plazo)) if creada and plazo else None, "url": a.get("html_url"),
                })
            orden = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            alertas.sort(key=lambda x: (orden[x["severidad"]], x["vence"] or ""))
            prs = [p for p in leer(f"{api}/pulls", state="open", per_page=100) if (p.get("user") or {}).get("login") == "dependabot[bot]"]

        hallazgos = [h for comp in componentes for h in comp["hallazgos"]]
        return {
            "escaneo": escaneo,
            "ci": {"conclusion": ci_ultima.get("conclusion"), "fecha": _iso(_fecha_gh(ci_ultima.get("run_started_at"))),
                   "url": ci_ultima.get("html_url")} if ci_ultima else None,
            "componentes": componentes,
            "dependabot": {"alertas": alertas, "prs_abiertos": len(prs),
                           "por_severidad": {s: sum(1 for a in alertas if a["severidad"] == s) for s in orden}},
            "totales": {
                "CRITICAL": sum(x["critica"] for x in componentes) + sum(1 for a in alertas if a["severidad"] == "CRITICAL"),
                "HIGH": sum(x["alta"] for x in componentes) + sum(1 for a in alertas if a["severidad"] == "HIGH"),
            },
            "hallazgos": hallazgos[:50],
        }

    @staticmethod
    def _componente(d: dict) -> dict:
        nombres = {"mesa-api": "Imagen api", "mesa-web": "Imagen web", "sqlserver": "Imagen SQL Server"}
        imagen = str(d.get("imagen") or "?")
        hallazgos = []
        for h in (d.get("hallazgos") or [])[:30]:
            hallazgos.append({"imagen": nombres.get(imagen, imagen), "id": h.get("id"), "severidad": h.get("severidad"),
                              "paquete": h.get("paquete"), "instalada": h.get("instalada"), "corregida": h.get("corregida"),
                              "titulo": h.get("titulo")})
        return {"imagen": imagen, "nombre": nombres.get(imagen, imagen), "critica": int(d.get("critica") or 0),
                "alta": int(d.get("alta") or 0), "media": int(d.get("media") or 0), "hallazgos": hallazgos}

