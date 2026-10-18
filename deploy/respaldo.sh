#!/bin/bash
# Respaldo de la base de datos y de los adjuntos. Programe con cron en el servidor, por ejemplo:
#   0 23 * * *  cd /opt/aducorp-mesa && ./deploy/respaldo.sh completo
#   */15 7-19 * * 1-5  cd /opt/aducorp-mesa && ./deploy/respaldo.sh log
set -euo pipefail
cd "$(dirname "$0")/.."
# Lee solo las variables necesarias (el .env no es un script de bash)
leer() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]\+#.*$//' -e 's/^"//' -e 's/"$//'; }
SA_PASSWORD=$(leer SA_PASSWORD)
BASE=$(leer DB_NAME); BASE=${BASE:-AducorpMesaServicios}
TIPO=${1:-completo}
FECHA=$(date +%Y%m%d_%H%M)
mkdir -p backups && chmod 777 backups   # SQL Server escribe como el usuario mssql (uid 10001)
sql() { docker compose exec -T -e SQLCMDPASSWORD="$SA_PASSWORD" sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -Q "$1"; }

if [ "$TIPO" = "log" ]; then
  sql "BACKUP LOG [$BASE] TO DISK = N'/var/opt/mssql/backups/${BASE}_log_${FECHA}.trn' WITH COMPRESSION, CHECKSUM"
else
  sql "BACKUP DATABASE [$BASE] TO DISK = N'/var/opt/mssql/backups/${BASE}_${FECHA}.bak' WITH COMPRESSION, CHECKSUM, INIT"
  # Adjuntos (volumen Docker) comprimidos junto a los respaldos
  if docker volume inspect aducorp-mesa_adjuntos >/dev/null 2>&1; then
    docker run --rm -v aducorp-mesa_adjuntos:/datos:ro -v "$PWD/backups:/destino" alpine:3.20 \
      tar czf "/destino/adjuntos_${FECHA}.tar.gz" -C /datos .
  fi
  # Retención: 30 días
  find backups -type f -mtime +30 -delete
fi
echo "Respaldo $TIPO terminado: $FECHA"
