#!/bin/bash
# Claves de producción en AWS Secrets Manager (ISO 27001, mejora 40). Guía: docs/15-endurecer-servidor.md
#
# Las claves (SA_PASSWORD, DB_APP_PASSWORD, JWT_SECRET, M365_CLIENT_SECRET…) dejan de estar en el disco:
#   .env.base           configuración SIN claves (es el archivo que se edita a partir de ahora)
#   secreto mesa/produccion en Secrets Manager (JSON {"CLAVE": "valor"})
#   .env  ->  /run/mesa-servicios/.env   (memoria; se arma en cada arranque con el servicio mesa-secretos)
# Los scripts de siempre (respaldo.sh, vigilante.sh, docker compose…) siguen leyendo .env sin cambios.
#
#   ./deploy/nube/secretos.sh exportar   muestra el JSON de claves del .env actual, para pegarlo en Secrets Manager
#   ./deploy/nube/secretos.sh probar     comprueba que el servidor puede leer el secreto (no cambia nada)
#   ./deploy/nube/secretos.sh separar    guarda el .env original en /root, crea .env.base y pasa a usar el secreto
#   ./deploy/nube/secretos.sh cargar     vuelve a armar .env desde .env.base + secreto (tras editar .env.base o el secreto)
#   ./deploy/nube/secretos.sh revertir   vuelve al .env original guardado por «separar»
# Variables opcionales: MESA_SECRETO (por defecto mesa/produccion), AWS_REGION (por defecto us-east-2).
set -euo pipefail
cd "$(dirname "$0")/../.."
DIR=$PWD
SECRETO=${MESA_SECRETO:-mesa/produccion}
REGION=${AWS_REGION:-us-east-2}
CLAVES="SA_PASSWORD DB_APP_PASSWORD JWT_SECRET M365_CLIENT_SECRET SMTP_PASSWORD ANTHROPIC_API_KEY LDAP_CLAVE_SERVICIO CLOUDFLARE_TUNNEL_TOKEN"
RUN=/run/mesa-servicios
AWS=$(command -v aws || echo /snap/bin/aws)
umask 077

leer_secreto() {
  [ -x "$AWS" ] || { echo "Falta la AWS CLI: snap install aws-cli --classic" >&2; exit 1; }
  "$AWS" secretsmanager get-secret-value --region "$REGION" --secret-id "$SECRETO" --query SecretString --output text
}

# Une un archivo de configuración con un JSON de claves: KEY=valor tal cual (sin comillas añadidas)
unir() {  # base json_en_stdin
  python3 -c '
import json, sys
claves = json.load(sys.stdin)
base = open(sys.argv[1], encoding="utf-8").read().splitlines()
nombres = {l.split("=", 1)[0].strip() for l in base if "=" in l and not l.lstrip().startswith("#")}
dup = nombres & set(claves)
if dup: sys.exit("Estas claves están en .env.base y en el secreto a la vez: " + ", ".join(sorted(dup)))
print("\n".join(base))
print("# --- claves desde AWS Secrets Manager (no se guardan en disco) ---")
for k, v in claves.items():
    if "\n" in str(v): sys.exit("El valor de %s tiene saltos de línea" % k)
    print("%s=%s" % (k, v))
' "$1"
}

case "${1:-}" in
  exportar)
    [ -f .env ] || { echo "No hay .env"; exit 1; }
    python3 -c '
import json, sys
claves = sys.argv[1].split()
out = {}
for l in open(".env", encoding="utf-8"):
    l = l.rstrip("\n")
    if "=" in l and not l.lstrip().startswith("#"):
        k, v = l.split("=", 1)
        if k.strip() in claves and v.strip():
            out[k.strip()] = v          # valor exacto, igual que en el .env
print(json.dumps(out, ensure_ascii=False))
' "$CLAVES"
    ;;
  probar)
    leer_secreto | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Secreto leído correctamente. Claves:", ", ".join(sorted(d)))'
    ;;
  separar)
    [ -L .env ] && { echo "Ya está separado (.env es un enlace). Use «cargar»."; exit 0; }
    [ -f .env ] || { echo "No hay .env"; exit 1; }
    leer_secreto > /dev/null   # no tocar nada si el servidor no puede leer el secreto
    COPIA=/root/env-original-$(date +%Y%m%d_%H%M)
    cp -p .env "$COPIA"; chmod 600 "$COPIA"
    python3 -c '
import sys
claves = sys.argv[1].split()
with open(".env.base", "w", encoding="utf-8") as f:
    for l in open(".env", encoding="utf-8"):
        k = l.split("=", 1)[0].strip() if "=" in l and not l.lstrip().startswith("#") else None
        if k not in claves or not l.split("=", 1)[1].strip():   # las claves vacías se quedan en .env.base
            f.write(l)
' "$CLAVES"
    chmod 600 .env.base
    rm -f .env
    "$0" cargar || { echo "No se pudo armar .env; se revierte."; "$0" revertir; exit 1; }
    # El armado nuevo debe ser idéntico al .env original (mismas variables, mismos valores)
    if ! diff <(grep -vE '^\s*(#|$)' "$COPIA" | sort) <(grep -vE '^\s*(#|$)' .env | sort) >/dev/null; then
      echo "ATENCIÓN: el .env armado no coincide con el original. Revise el secreto. Se revierte."; "$0" revertir; exit 1
    fi
    echo "Listo: claves en Secrets Manager, .env.base sin claves, copia del original en $COPIA"
    echo "Cuando confirme que todo funciona (incluido un reinicio), borre la copia: shred -u $COPIA"
    ;;
  cargar)
    [ -f .env.base ] || { echo "No hay .env.base (ejecute primero «separar»)"; exit 1; }
    mkdir -p "$RUN"; chmod 700 "$RUN"
    leer_secreto | unir .env.base > "$RUN/.env.nuevo"
    mv "$RUN/.env.nuevo" "$RUN/.env"
    [ -f .env ] && [ ! -L .env ] && { echo "Hay un .env normal; use «separar»."; exit 1; }
    ln -sfn "$RUN/.env" .env
    echo "Configuración armada en $RUN/.env (memoria)."
    ;;
  revertir)
    COPIA=$(ls -1t /root/env-original-* 2>/dev/null | head -1 || true)
    [ -n "$COPIA" ] || { echo "No hay copia del .env original en /root"; exit 1; }
    rm -f .env; cp -p "$COPIA" .env; chmod 600 .env
    systemctl disable --now mesa-secretos.service 2>/dev/null || true
    echo "Restaurado el .env original desde $COPIA (.env.base queda, pero ya no se usa)."
    ;;
  instalar)
    cat > /etc/systemd/system/mesa-secretos.service <<UNIT
[Unit]
Description=Mesa de Servicios: arma .env con las claves de AWS Secrets Manager
Wants=network-online.target
After=network-online.target snapd.service
Before=cron.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$DIR/deploy/nube/secretos.sh cargar
Restart=on-failure
RestartSec=20

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable mesa-secretos.service
    echo "Servicio mesa-secretos instalado: arma .env en cada arranque."
    ;;
  *)
    sed -n '2,16p' "$0"; exit 1 ;;
esac
