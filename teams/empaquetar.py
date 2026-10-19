"""Genera el paquete de la app de Teams (mesa-servicios-teams.zip) para cargarlo en el Centro de administración de Teams.

Uso:  python teams/empaquetar.py --bot-id <Id. de aplicación> --app-url https://mesa.aducorp.com.ec
"""
import argparse
import json
import zipfile
from pathlib import Path
from urllib.parse import urlparse

AQUI = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot-id", required=True, help="Id. de aplicación (cliente) registrado en Entra ID / Azure Bot")
    ap.add_argument("--app-url", required=True, help="URL pública de la Mesa, por ejemplo https://mesa.aducorp.com.ec")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--salida", default=str(AQUI / "mesa-servicios-teams.zip"))
    a = ap.parse_args()

    url = a.app_url.rstrip("/")
    texto = (AQUI / "manifest.json").read_text(encoding="utf-8")
    texto = texto.replace("{{BOT_ID}}", a.bot_id).replace("{{APP_URL}}", url).replace("{{DOMINIO}}", urlparse(url).netloc)
    manifiesto = json.loads(texto)
    manifiesto["version"] = a.version
    with zipfile.ZipFile(a.salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))
        z.write(AQUI / "color.png", "color.png")
        z.write(AQUI / "outline.png", "outline.png")
    print(f"Paquete listo: {a.salida}")


if __name__ == "__main__":
    main()
