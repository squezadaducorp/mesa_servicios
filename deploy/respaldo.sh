#!/bin/bash
# Respaldo de la base de datos y de los adjuntos. Programe con cron en el servidor, por ejemplo:
#   0 23 * * *  cd /opt/aducorp-mesa && ./deploy/respaldo.sh completo
#   */15 7-19 * * 1-5  cd /opt/aducorp-mesa && ./deploy/respaldo.sh log
# Opcional (.env, ver docs/14-monitoreo-y-respaldos.md):
#   RESPALDO_S3_BUCKET=mi-bucket    copia cada respaldo a Amazon S3 (fuera del servidor) con la AWS CLI del servidor
#   RESPALDO_DIAS_LOCAL=30          días que se guardan en el disco del servidor
#   ALERTA_CORREOS=a@x.com,b@x.com  avisa por correo si el respaldo falla (y con RESPALDO_AVISO=siempre, también si sale bien)
set -euo pipefail
cd "$(dirname "$0")/.."
# Lee solo las variables necesarias (el .env no es un script de bash)
leer() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]\+#.*$//' -e 's/^"//' -e 's/"$//'; }
SA_PASSWORD=$(leer SA_PASSWORD)
BASE=$(leer DB_NAME); BASE=${BASE:-AducorpMesaServicios}
TIPO=${1:-completo}
FECHA=$(date +%Y%m%d_%H%M)
BUCKET=$(leer RESPALDO_S3_BUCKET)
DIAS_LOCAL=$(leer RESPALDO_DIAS_LOCAL); DIAS_LOCAL=${DIAS_LOCAL:-30}
PARA=$(leer ALERTA_CORREOS)
AVISO=$(leer RESPALDO_AVISO); AVISO=${AVISO:-error}
ARCHIVOS=()

alerta() {  # nivel asunto mensaje
  [ -n "$PARA" ] || return 0
  docker compose run --rm --no-deps -T api python -m app.alerta --para "$PARA" --nivel "$1" --asunto "$2" --mensaje "$3" </dev/null || true
}
fallo() {
  local linea=$1
  echo "ERROR en el respaldo $TIPO (línea $linea)"
  alerta error "Falló el respaldo $TIPO de la base" "El respaldo $TIPO del $FECHA terminó con error (deploy/respaldo.sh, línea $linea).
Revise /var/log/mesa-respaldo.log en el servidor $(hostname).
Disco usado: $(df -P / | awk 'NR==2 {print $5}')"
}
trap 'fallo $LINENO' ERR
mkdir -p backups && chmod 777 backups   # SQL Server escribe como el usuario mssql (uid 10001)
sql() { docker compose exec -T -e SQLCMDPASSWORD="$SA_PASSWORD" sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -Q "$1" "${@:2}"; }
# SQL Server Express (EngineEdition 4) no admite respaldos comprimidos
COMPRIMIR="COMPRESSION, "
[ "$(sql "SET NOCOUNT ON; SELECT SERVERPROPERTY('EngineEdition')" -h -1 | tr -d '[:space:]')" = 4 ] && COMPRIMIR=""

if [ "$TIPO" = "log" ]; then
  sql "BACKUP LOG [$BASE] TO DISK = N'/var/opt/mssql/backups/${BASE}_log_${FECHA}.trn' WITH ${COMPRIMIR}CHECKSUM"
  ARCHIVOS+=("backups/${BASE}_log_${FECHA}.trn")
else
  sql "BACKUP DATABASE [$BASE] TO DISK = N'/var/opt/mssql/backups/${BASE}_${FECHA}.bak' WITH ${COMPRIMIR}CHECKSUM, INIT"
  ARCHIVOS+=("backups/${BASE}_${FECHA}.bak")
  # Adjuntos (volumen Docker) comprimidos junto a los respaldos
  if docker volume inspect aducorp-mesa_adjuntos >/dev/null 2>&1; then
    docker run --rm -v aducorp-mesa_adjuntos:/datos:ro -v "$PWD/backups:/destino" alpine:3.20 \
      tar czf "/destino/adjuntos_${FECHA}.tar.gz" -C /datos .
    ARCHIVOS+=("backups/adjuntos_${FECHA}.tar.gz")
  fi
  # Retención en el servidor (en S3 la define la regla de ciclo de vida del bucket)
  find backups -maxdepth 1 -type f -mtime +"$DIAS_LOCAL" -delete
fi

# Copia fuera del servidor: Amazon S3 (rol IAM de la instancia; sin claves en el .env)
if [ -n "$BUCKET" ]; then
  command -v aws >/dev/null || { echo "Falta la AWS CLI (snap install aws-cli --classic)"; false; }
  for f in "${ARCHIVOS[@]}"; do
    aws s3 cp "$f" "s3://$BUCKET/$(hostname)/$TIPO/$(basename "$f")" --only-show-errors
  done
fi

echo "Respaldo $TIPO terminado: $FECHA ${BUCKET:+(copiado a s3://$BUCKET)}"
if [ "$TIPO" != "log" ] && [ "$AVISO" = "siempre" ]; then
  tam=$(du -ch "${ARCHIVOS[@]}" 2>/dev/null | tail -1 | cut -f1)
  alerta ok "Respaldo diario correcto" "Respaldo completo del $FECHA: ${#ARCHIVOS[@]} archivo(s), $tam.
Copia en S3: ${BUCKET:-no configurada}
Se guardan $DIAS_LOCAL días en el servidor."
fi
