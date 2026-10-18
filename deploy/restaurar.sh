#!/bin/bash
# Restaura un respaldo completo (y opcionalmente los adjuntos) generado por respaldo.sh.
#   ./deploy/restaurar.sh backups/AducorpMesaServicios_20261018_2300.bak [backups/adjuntos_20261018_2300.tar.gz]
# Detiene la API y el worker durante la restauración y los vuelve a levantar al final.
set -euo pipefail
cd "$(dirname "$0")/.."
BAK=${1:?Indique el archivo .bak dentro de backups/}
ADJ=${2:-}
leer() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]\+#.*$//' -e 's/^"//' -e 's/"$//'; }
SA_PASSWORD=$(leer SA_PASSWORD)
APP_USER=$(leer DB_APP_USER); APP_USER=${APP_USER:-mesa_app}
BASE=$(leer DB_NAME); BASE=${BASE:-AducorpMesaServicios}
sql() { docker compose exec -T -e SQLCMDPASSWORD="$SA_PASSWORD" sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -Q "$1"; }

read -r -p "Se reemplazará la base $BASE con $(basename "$BAK"). ¿Continuar? (si/no) " r
[ "$r" = "si" ] || { echo "Cancelado."; exit 1; }

docker compose stop api worker web
sql "ALTER DATABASE [$BASE] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
     RESTORE DATABASE [$BASE] FROM DISK = N'/var/opt/mssql/backups/$(basename "$BAK")' WITH REPLACE, CHECKSUM;
     ALTER DATABASE [$BASE] SET MULTI_USER;"
# El usuario de la base queda huérfano si el login se recreó: lo vuelve a enlazar
sql "USE [$BASE]; ALTER USER [$APP_USER] WITH LOGIN = [$APP_USER];"

if [ -n "$ADJ" ]; then
  docker run --rm -v aducorp-mesa_adjuntos:/datos -v "$PWD/backups:/origen:ro" alpine:3.20 \
    sh -c "rm -rf /datos/* && tar xzf /origen/$(basename "$ADJ") -C /datos"
fi
docker compose up -d api worker web
echo "Restauración terminada."
