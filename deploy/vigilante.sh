#!/bin/bash
# Vigilante del servidor: revisa cada 5 minutos que la Mesa responda y avisa por correo si algo falla.
# Lo programa deploy/nube/instalar.sh (o a mano, ver docs/14-monitoreo-y-respaldos.md):
#   */5 * * * *  root  cd /opt/mesa-servicios && ./deploy/vigilante.sh >> /var/log/mesa-vigilante.log 2>&1
#
# Revisa: la página responde con la base conectada, los contenedores están en marcha, espacio en disco,
# vencimiento del certificado HTTPS y que exista un respaldo de las últimas 26 horas.
# - Si la Mesa no responde o un contenedor está detenido, intenta levantarla sola (docker compose up -d).
# - Avisa por correo a ALERTA_CORREOS después de VIGILANTE_FALLOS revisiones seguidas con problemas
#   (3 = 15 minutos), repite el aviso cada 2 horas si sigue igual y envía otro cuando se normaliza.
# - Prueba manual: ./deploy/vigilante.sh --probar   (envía un correo de prueba)
set -uo pipefail
cd "$(dirname "$0")/.."
leer() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]\+#.*$//' -e 's/^"//' -e 's/"$//'; }

PARA=$(leer ALERTA_CORREOS)
DOMINIO=$(leer DOMINIO)
FALLOS_MIN=$(leer VIGILANTE_FALLOS); FALLOS_MIN=${FALLOS_MIN:-3}
DISCO_MAX=$(leer VIGILANTE_DISCO_PCT); DISCO_MAX=${DISCO_MAX:-85}
REPETIR_MIN=120
ESTADO_DIR=/var/lib/mesa-vigilante
[ -w /var/lib ] || ESTADO_DIR="$PWD/backups/.vigilante"
mkdir -p "$ESTADO_DIR"
ESTADO="$ESTADO_DIR/estado"

if [ -f docker-compose.nube.yml ] && [ -n "$DOMINIO" ]; then
  C=(docker compose -f docker-compose.yml -f docker-compose.nube.yml --profile nube)
  SERVICIOS="sqlserver api worker web caddy"
  PUERTO=8080
else
  C=(docker compose)
  SERVICIOS="sqlserver api worker web"
  PUERTO=$(leer WEB_PUERTO); PUERTO=${PUERTO:-8080}
fi

ahora() { date '+%Y-%m-%d %H:%M:%S'; }
avisar() {  # nivel asunto mensaje
  if [ -z "$PARA" ]; then echo "$(ahora) sin ALERTA_CORREOS: no se envía «$2»"; return 0; fi
  "${C[@]}" run --rm --no-deps -T api python -m app.alerta --para "$PARA" --nivel "$1" --asunto "$2" --mensaje "$3" </dev/null \
    || echo "$(ahora) ERROR: no se pudo enviar la alerta «$2»"
}

if [ "${1:-}" = "--probar" ]; then
  avisar info "Prueba del vigilante" "Si recibe este correo, las alertas del servidor están bien configuradas.
Servidor: $(hostname)
Disco usado: $(df -P / | awk 'NR==2 {print $5}')"
  exit 0
fi

# ------------------------------------------------------------------ revisiones
problemas=()
caida=0

salud=$(curl -s -m 15 "http://127.0.0.1:$PUERTO/api/v1/health" 2>/dev/null || true)
if ! grep -q '"estado":"ok"' <<<"$salud"; then
  caida=1
  if grep -q '"base_datos"' <<<"$salud"; then problemas+=("La Mesa responde pero la base de datos no: $salud")
  else problemas+=("La Mesa no responde en el servidor (http://127.0.0.1:$PUERTO)"); fi
elif [ -n "$DOMINIO" ] && ! curl -sf -m 15 -o /dev/null "https://$DOMINIO/api/v1/health"; then
  problemas+=("La Mesa funciona en el servidor pero no desde internet (https://$DOMINIO): revise Caddy, el DNS o el grupo de seguridad de AWS")
fi

en_marcha=$("${C[@]}" ps --status running --services 2>/dev/null || true)
for s in $SERVICIOS; do
  if ! grep -qx "$s" <<<"$en_marcha"; then problemas+=("El contenedor «$s» está detenido"); caida=1; fi
done

disco=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
[ "${disco:-0}" -ge "$DISCO_MAX" ] && problemas+=("Disco al ${disco} % (límite ${DISCO_MAX} %). Libere espacio: docker system prune -f y respaldos antiguos")

if [ -n "$DOMINIO" ]; then
  fin=$(echo | timeout 15 openssl s_client -servername "$DOMINIO" -connect "$DOMINIO:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  if [ -n "$fin" ]; then
    dias=$(( ( $(date -d "$fin" +%s) - $(date +%s) ) / 86400 ))
    [ "$dias" -lt 15 ] && problemas+=("El certificado HTTPS vence en $dias días ($fin). Caddy debería renovarlo solo: revise «${C[*]} logs caddy»")
  fi
fi

if [ -d backups ] && ls backups/*.bak >/dev/null 2>&1; then
  ultimo=$(ls -t backups/*.bak | head -1)
  horas=$(( ( $(date +%s) - $(stat -c %Y "$ultimo") ) / 3600 ))
  [ "$horas" -ge 26 ] && problemas+=("El último respaldo de la base tiene $horas horas ($(basename "$ultimo")). Revise /var/log/mesa-respaldo.log")
fi

# ------------------------------------------------------------------ estado y avisos
fallos=0; alertado=0; ultimo_aviso=0; firma_ant=""
[ -f "$ESTADO" ] && . "$ESTADO"
firma=$(printf '%s\n' "${problemas[@]:-}" | sed 's/[0-9]\+/#/g' | md5sum | cut -c1-12)

if [ ${#problemas[@]} -eq 0 ]; then
  if [ "$alertado" = 1 ]; then
    avisar ok "La Mesa volvió a la normalidad" "Todas las revisiones están bien desde $(ahora).
Disco usado: ${disco} %"
  fi
  [ "$fallos" -gt 0 ] && echo "$(ahora) normal otra vez"
  fallos=0; alertado=0; ultimo_aviso=0; firma=""
else
  fallos=$((fallos + 1))
  echo "$(ahora) revisión $fallos con problemas: ${problemas[*]}"
  reparado=""
  if [ "$caida" = 1 ]; then
    echo "$(ahora) intentando levantar la Mesa"
    "${C[@]}" up -d >/dev/null 2>&1 && reparado="Se intentó levantar los servicios automáticamente (docker compose up -d)."
  fi
  minutos=$(( ( $(date +%s) - ultimo_aviso ) / 60 ))
  if [ "$fallos" -ge "$FALLOS_MIN" ] && { [ "$alertado" = 0 ] || [ "$firma" != "$firma_ant" ] || [ "$minutos" -ge "$REPETIR_MIN" ]; }; then
    mensaje=$(printf '%s\n' "${problemas[@]}")
    mensaje+=$'\n'"Revisiones seguidas con problemas: $fallos (cada 5 minutos)"
    [ -n "$reparado" ] && mensaje+=$'\n'"$reparado"
    mensaje+=$'\n'"Servidor: $(hostname) · disco ${disco} %"
    asunto="${problemas[0]}"; [ ${#problemas[@]} -gt 1 ] && asunto="${#problemas[@]} problemas en el servidor"
    avisar error "${asunto:0:120}" "$mensaje"
    alertado=1; ultimo_aviso=$(date +%s)
  fi
fi

cat > "$ESTADO" <<EOF
fallos=$fallos
alertado=$alertado
ultimo_aviso=$ultimo_aviso
firma_ant=$firma
EOF
