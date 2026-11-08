#!/bin/bash
# Instala la Mesa de Servicios en un servidor Linux nuevo (Ubuntu 24.04, x86, 4 GB de RAM o más)
# con HTTPS automático. Guía: docs/12-publicar-en-la-nube.md
#   curl -fsSL https://raw.githubusercontent.com/squezadaducorp/mesa_servicios/main/deploy/nube/instalar.sh | sudo bash -s -- mesa-aducorp.duckdns.org
# Volver a ejecutarlo actualiza el código y conserva la base, el .env y los adjuntos.
set -euo pipefail

DOMINIO=${1:?Uso: instalar.sh <dominio>   por ejemplo: instalar.sh mesa-aducorp.duckdns.org}
REPO=${REPO:-https://github.com/squezadaducorp/mesa_servicios.git}
RAMA=${RAMA:-main}
DIR=/opt/mesa-servicios
CLAVE_INICIAL='$2b$12$sSwVHCSigHQMEw1oActf9.uA2NlGP17XMuRMVjduvaPgndWJQIHRS'   # Aducorp2026!, publicada en el README

[ "$(id -u)" = 0 ] || { echo "Ejecute con sudo"; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "SQL Server necesita un servidor x86_64 (Intel o AMD), no ARM."; exit 1; }

echo "== 1/6 Memoria de intercambio (swap) de 2 GB"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 2/6 Docker y herramientas"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git openssl cron curl ca-certificates >/dev/null
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh >/dev/null   # Docker oficial con Compose v2
systemctl enable --now docker cron >/dev/null

echo "== 3/6 Código ($RAMA)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$RAMA" && git -C "$DIR" checkout -q "$RAMA" && git -C "$DIR" pull -q --ff-only
else
  git clone -q -b "$RAMA" "$REPO" "$DIR"
fi
cd "$DIR"

echo "== 4/6 Configuración"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i \
    -e "s#^SA_PASSWORD=.*#SA_PASSWORD=Sa-$(openssl rand -hex 16)-X9#" \
    -e "s#^DB_APP_PASSWORD=.*#DB_APP_PASSWORD=App-$(openssl rand -hex 16)-Y8#" \
    -e "s#^JWT_SECRET=.*#JWT_SECRET=$(openssl rand -hex 48)#" \
    -e "s#^MSSQL_PID=.*#MSSQL_PID=Express              # gratuita para producción (bases de hasta 10 GB)#" \
    .env
  echo "Se creó .env con claves aleatorias."
fi
# El dominio puede cambiar entre ejecuciones (p. ej. de duckdns.org al dominio propio)
sed -i -e '/^DOMINIO=/d' -e "s#^APP_URL=.*#APP_URL=https://$DOMINIO#" \
  -e "s#^CORS_ORIGINS=.*#CORS_ORIGINS=[\"https://$DOMINIO\"]#" .env
echo "DOMINIO=$DOMINIO" >> .env
chmod 600 .env
leer() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]\+#.*$//' -e 's/^"//' -e 's/"$//'; }
SA_PASSWORD=$(leer SA_PASSWORD)
BASE=$(leer DB_NAME); BASE=${BASE:-AducorpMesaServicios}

C=(docker compose -f docker-compose.yml -f docker-compose.nube.yml)
sql() { "${C[@]}" exec -T -e SQLCMDPASSWORD="$SA_PASSWORD" sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -I -b -W -d "$BASE" "$@"; }

echo "== 5/6 Construir y levantar (la primera vez tarda 10 a 15 minutos)"
"${C[@]}" up -d --build      # sin el perfil nube: todavía no se publica en internet
for i in $(seq 1 90); do
  curl -sf http://127.0.0.1:8080/api/v1/health >/dev/null && break
  [ "$i" = 90 ] && { echo "La aplicación no respondió. Revise: ${C[*]} logs api"; exit 1; }
  sleep 5
done

echo "== 6/6 Cerrar las contraseñas conocidas y publicar"
CLAVE_ADMIN=""
if [ "$(sql -h -1 -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM dbo.usuarios WHERE correo = N'admin@aducorp.com.ec' AND clave_hash = '$CLAVE_INICIAL'" | tr -d '[:space:]')" != 0 ]; then
  CLAVE_ADMIN="Mesa9-$(openssl rand -hex 6)-$(openssl rand -hex 3 | tr a-f A-F)!"
  HASH=$("${C[@]}" exec -T api python -c "import sys; from app.core.security import hash_clave; print(hash_clave(sys.argv[1]))" "$CLAVE_ADMIN")
  sql -Q "UPDATE dbo.usuarios SET clave_hash = '$HASH', debe_cambiar_clave = 1, intentos_fallidos = 0, bloqueado_hasta = NULL WHERE correo = N'admin@aducorp.com.ec'" >/dev/null
  umask 077; echo "admin@aducorp.com.ec  $CLAVE_ADMIN" > /root/mesa-clave-admin.txt
fi
sql < deploy/cloudflare/antes-de-publicar.sql
"${C[@]}" --profile nube up -d

# Respaldos diarios de la base y los adjuntos, y del registro de transacciones en horario laboral (hora UTC del servidor)
cat > /etc/cron.d/mesa-servicios <<CRON
0 4 * * *  root  cd $DIR && ./deploy/respaldo.sh completo >> /var/log/mesa-respaldo.log 2>&1
*/15 13-23 * * 1-5  root  cd $DIR && ./deploy/respaldo.sh log >> /var/log/mesa-respaldo.log 2>&1
CRON

echo
echo "Listo. La Mesa queda en https://$DOMINIO (el certificado HTTPS tarda uno o dos minutos la primera vez)."
if [ -n "$CLAVE_ADMIN" ]; then
  echo "Usuario: admin@aducorp.com.ec"
  echo "Contraseña temporal: $CLAVE_ADMIN   (la Mesa pide cambiarla al ingresar; copia en /root/mesa-clave-admin.txt)"
fi
