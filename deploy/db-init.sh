#!/bin/bash
# Crea o actualiza la base de datos de la Mesa de Servicios (scripts idempotentes).
#   CARGAR_DEMO=true  ejecuta además 06_datos_demo.sql (solo si no hay tickets)
#   SOLO_DEMO=true    ejecuta únicamente 06_datos_demo.sql
set -euo pipefail

SQLCMD=/opt/mssql-tools18/bin/sqlcmd
SERVIDOR=${DB_HOST:-sqlserver}
BASE=${DB_NAME:-AducorpMesaServicios}
ejecutar() {   # $1 = base de datos, $2 = script
  echo ">> $(basename "$2")"
  "$SQLCMD" -S "$SERVIDOR" -U sa -P "$SA_PASSWORD" -C -b -I -d "$1" -i "$2" \
    -v DB_NAME="$BASE" APP_LOGIN="${DB_APP_USER:-mesa_app}" APP_PASSWORD="$DB_APP_PASSWORD"
}

for i in $(seq 1 60); do
  "$SQLCMD" -S "$SERVIDOR" -U sa -P "$SA_PASSWORD" -C -Q "SELECT 1" -b -o /dev/null && break
  echo "Esperando a SQL Server ($i)..."; sleep 2
done

if [ "${SOLO_DEMO:-false}" != "true" ]; then
  ejecutar master /database/00_crear_base.sql
  for s in 01_tablas 02_vistas 03_procedimientos 04_triggers 05_datos_iniciales; do
    ejecutar "$BASE" "/database/$s.sql"
  done
fi
if [ "${CARGAR_DEMO:-false}" = "true" ]; then
  ejecutar "$BASE" /database/06_datos_demo.sql
fi
echo "Base de datos $BASE lista."
