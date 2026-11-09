#!/bin/bash
# Carga el personal real desde un CSV (ver backend/scripts/importar_usuarios.py) y retira los usuarios de ejemplo.
#   sudo /opt/mesa-servicios/deploy/nube/cargar-usuarios.sh /opt/mesa-servicios/usuarios.csv
# Las contraseñas temporales quedan en /root/mesa-usuarios-claves.txt. El CSV se borra al terminar
# porque tiene datos del personal; el listado no se guarda en GitHub.
set -euo pipefail
CSV=${1:?Uso: cargar-usuarios.sh <archivo.csv>}
[ "$(id -u)" = 0 ] || { echo "Ejecute con sudo"; exit 1; }
cd "$(dirname "$0")/../.."
SALIDA=$(docker compose -f docker-compose.yml -f docker-compose.nube.yml exec -T api python -m scripts.importar_usuarios < "$CSV")
umask 077
{ date '+%Y-%m-%d %H:%M'; echo "$SALIDA"; echo; } >> /root/mesa-usuarios-claves.txt
echo "$SALIDA"
rm -f "$CSV"
echo
echo "Copia guardada en /root/mesa-usuarios-claves.txt (sudo cat /root/mesa-usuarios-claves.txt)."
