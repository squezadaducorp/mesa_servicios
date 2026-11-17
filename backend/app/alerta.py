"""Correo de alerta del servidor (vigilante y respaldos). No usa la base de datos: funciona aunque la Mesa esté caída.

Uso (desde el servidor, lo llaman deploy/vigilante.sh y deploy/respaldo.sh):
    docker compose run --rm --no-deps api python -m app.alerta --para "a@x.com,b@x.com" --nivel error \
        --asunto "La Mesa no responde" --mensaje "Detalle…"
Respeta EMAIL_ENABLED y EMAIL_TRANSPORTE (smtp o graph) del .env, igual que los demás correos.
"""
from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.infrastructure.email.smtp import enviador, plantilla_base

NIVELES = {
    "error": ("#C62828", "Alerta"),
    "aviso": ("#E65100", "Aviso"),
    "ok": ("#2E7D32", "Resuelto"),
    "info": ("#1367AC", "Información"),
}


def cuerpo(nivel: str, asunto: str, mensaje: str) -> str:
    color, etiqueta = NIVELES.get(nivel, NIVELES["info"])
    ahora = datetime.now(ZoneInfo(settings.ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
    lineas = "".join(f"<li style='margin:2px 0'>{html.escape(x.lstrip('-• ').strip())}</li>"
                     for x in mensaje.splitlines() if x.strip())
    url = settings.APP_URL.rstrip("/")
    return (
        f'<div style="border-left:5px solid {color};padding:4px 14px;margin-bottom:14px">'
        f'<div style="font-size:12px;font-weight:700;color:{color};text-transform:uppercase">{etiqueta} · servidor de la Mesa</div>'
        f'<div style="font-size:18px;font-weight:700;margin-top:2px">{html.escape(asunto)}</div>'
        f'<div style="font-size:12px;color:#5A6577">{ahora} (hora de Ecuador) · {html.escape(url)}</div></div>'
        f'<ul style="padding-left:18px;margin:0 0 14px">{lineas}</ul>'
        '<p style="font-size:12px;color:#5A6577">Lo envía el vigilante del servidor (deploy/vigilante.sh). '
        "Guía: docs/14-monitoreo-y-respaldos.md</p>"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--para", required=True, help="Correos separados por coma")
    p.add_argument("--asunto", required=True)
    p.add_argument("--mensaje", default="", help="Una línea por dato")
    p.add_argument("--nivel", choices=list(NIVELES), default="error")
    a = p.parse_args(argv)
    para = ",".join(x.strip() for x in a.para.replace(";", ",").split(",") if x.strip())
    if not para:
        print("Sin destinatarios (ALERTA_CORREOS vacío)", file=sys.stderr)
        return 2
    prefijo = {"error": "🔴", "aviso": "🟠", "ok": "🟢"}.get(a.nivel, "")
    enviador().enviar(para, f"{prefijo} Mesa de Servicios: {a.asunto}".strip()[:250], plantilla_base(cuerpo(a.nivel, a.asunto, a.mensaje)))
    print(f"Alerta enviada a {para}" + ("" if settings.EMAIL_ENABLED else " (simulada: EMAIL_ENABLED=false)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
