#!/bin/bash
# Verificación diaria del endurecimiento del servidor (ISO 27001, mejora 40). Guía: docs/15-endurecer-servidor.md
#
# Revisa el servidor y la cuenta de AWS (solo lectura) y deja el resultado en estado/servidor.json, que la Mesa muestra
# en Seguridad y cumplimiento › Servidor. No cambia nada del servidor.
#
#   sudo ./deploy/nube/verificar-servidor.sh            revisa ahora y actualiza el informe
#   sudo ./deploy/nube/verificar-servidor.sh instalar   además lo programa todos los días a las 06:00 de Ecuador
#
# Los controles de AWS necesitan estos permisos de solo lectura en el rol del servidor (si faltan, salen «Sin dato»):
#   ec2:DescribeInstances, ec2:DescribeSecurityGroups, ec2:DescribeVolumes, ec2:GetEbsEncryptionByDefault,
#   cloudtrail:DescribeTrails, cloudtrail:GetTrailStatus, iam:GetAccountSummary
set -uo pipefail
cd "$(dirname "$0")/../.."
DIR=$PWD
SALIDA_DIR=$DIR/estado
SALIDA=$SALIDA_DIR/servidor.json
AWS=$(command -v aws || echo /snap/bin/aws)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [ "${1:-}" = "instalar" ]; then
  [ "$(id -u)" = 0 ] || { echo "Ejecute con sudo"; exit 1; }
  echo "0 11 * * * root $DIR/deploy/nube/verificar-servidor.sh >/var/log/mesa-verificar-servidor.log 2>&1" > /etc/cron.d/mesa-verificar-servidor
  chmod 644 /etc/cron.d/mesa-verificar-servidor
  echo "Programado todos los días a las 06:00 de Ecuador (/etc/cron.d/mesa-verificar-servidor)."
fi

# ---------------------------------------------------------------- metadatos de la instancia (IMDSv2)
TOKEN=$(curl -sf -m 3 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 120" 2>/dev/null || true)
meta() { [ -n "$TOKEN" ] && curl -sf -m 3 -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/$1" 2>/dev/null || true; }
INSTANCIA=$(meta instance-id)
REGION=$(meta placement/region)
REGION=${REGION:-${AWS_REGION:-us-east-2}}
meta instance-type > "$TMP/tipo"
meta placement/availability-zone > "$TMP/zona"
echo "$INSTANCIA" > "$TMP/instancia"
echo "$REGION" > "$TMP/region"
curl -s -o /dev/null -w '%{http_code}' -m 3 http://169.254.169.254/latest/meta-data/ > "$TMP/imdsv1" 2>/dev/null || echo "000" > "$TMP/imdsv1"

# ---------------------------------------------------------------- AWS (solo lectura; un fallo deja el control «Sin dato»)
aws_json() { [ -x "$AWS" ] && [ -n "$INSTANCIA" ] && "$AWS" --region "$REGION" --output json "$@" 2>"$TMP/aws.err"; }
aws_json ec2 describe-instances --instance-ids "$INSTANCIA" > "$TMP/instancia.json" || true
SGS=$(python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1])); print(" ".join(g["GroupId"] for g in d["Reservations"][0]["Instances"][0]["SecurityGroups"]))
except Exception: pass' "$TMP/instancia.json")
[ -n "$SGS" ] && aws_json ec2 describe-security-groups --group-ids $SGS > "$TMP/sg.json" || true
aws_json ec2 describe-volumes --filters "Name=attachment.instance-id,Values=$INSTANCIA" > "$TMP/volumenes.json" || true
aws_json ec2 get-ebs-encryption-by-default > "$TMP/cifrado-defecto.json" || true
aws_json cloudtrail describe-trails > "$TMP/trails.json" || true
python3 -c 'import json,sys
try: print("\n".join(t["TrailARN"] for t in json.load(open(sys.argv[1]))["trailList"]))
except Exception: pass' "$TMP/trails.json" | while read -r arn; do
  aws_json cloudtrail get-trail-status --name "$arn" >> "$TMP/trail-estado.jsonl" && echo >> "$TMP/trail-estado.jsonl"
done
aws_json iam get-account-summary > "$TMP/cuenta.json" || true

# ---------------------------------------------------------------- servidor
. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-Linux}" > "$TMP/so"
uname -r > "$TMP/kernel"
hostname > "$TMP/nombre"
{ dpkg -s unattended-upgrades >/dev/null 2>&1 && grep -qs 'Unattended-Upgrade "1"' /etc/apt/apt.conf.d/20auto-upgrades && echo si || echo no; } > "$TMP/unattended"
stat -c %Y /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null > "$TMP/unattended-fecha" || true
[ -f /var/run/reboot-required ] && echo si > "$TMP/reinicio" || echo no > "$TMP/reinicio"
apt-get -s dist-upgrade 2>/dev/null | grep -c '^Inst .*-security' > "$TMP/parches" || true
systemctl is-active mesa-secretos 2>/dev/null > "$TMP/secretos-servicio" || true
[ -L "$DIR/.env" ] && readlink "$DIR/.env" > "$TMP/env-enlace" || true
awk 'f && /=/ {n++} /claves desde AWS Secrets Manager/ {f=1} END {print n+0}' "$DIR/.env" 2>/dev/null > "$TMP/claves-secreto" || echo 0 > "$TMP/claves-secreto"
CLAVES="SA_PASSWORD DB_APP_PASSWORD JWT_SECRET M365_CLIENT_SECRET SMTP_PASSWORD ANTHROPIC_API_KEY LDAP_CLAVE_SERVICIO CLOUDFLARE_TUNNEL_TOKEN GITHUB_TOKEN_SEGURIDAD"
EN_DISCO=""
for k in $CLAVES; do
  for f in "$DIR/.env.base" "$DIR/.env"; do
    [ -f "$f" ] && [ ! -L "$f" ] && grep -Eq "^$k=.+" "$f" && EN_DISCO="$EN_DISCO $k"
  done
done
echo "$EN_DISCO" | xargs -n1 2>/dev/null | sort -u | xargs > "$TMP/claves-disco"
: > "$TMP/contenedores"
for c in $(docker ps --format '{{.Names}}' 2>/dev/null | grep -E -- '-(api|worker|web)-[0-9]+$'); do
  echo "$c $(docker inspect -f '{{.Config.User}}' "$c" 2>/dev/null)" >> "$TMP/contenedores"
done

# ---------------------------------------------------------------- informe
mkdir -p "$SALIDA_DIR"
python3 - "$TMP" "$SALIDA.tmp" <<'PY'
import json, os, sys
from datetime import datetime, timezone

t, salida = sys.argv[1], sys.argv[2]
def leer(n, defecto=""):
    try: return open(os.path.join(t, n), encoding="utf-8").read().strip()
    except OSError: return defecto
def js(n):
    try: return json.load(open(os.path.join(t, n), encoding="utf-8"))
    except Exception: return None

controles = []
def control(clave, nombre, detalle, estado, etiqueta, iso):
    controles.append({"clave": clave, "nombre": nombre, "detalle": detalle, "estado": estado, "etiqueta": etiqueta, "iso": iso})

sin_permiso = "Sin permiso de lectura en AWS (vea la guía)"

# 1. Puerto 22
sg = js("sg.json")
if sg:
    abiertos = set()
    for g in sg.get("SecurityGroups", []):
        for p in g.get("IpPermissions", []):
            publico = any(r.get("CidrIp") == "0.0.0.0/0" for r in p.get("IpRanges", [])) or \
                      any(r.get("CidrIpv6") == "::/0" for r in p.get("Ipv6Ranges", []))
            if not publico: continue
            if p.get("IpProtocol") == "-1": abiertos.add("todos")
            else: abiertos.update(str(x) for x in range(p.get("FromPort", 0), min(p.get("ToPort", 0), p.get("FromPort", 0) + 50) + 1))
    ssh = "todos" in abiertos or "22" in abiertos
    lista = ", ".join(sorted(abiertos, key=lambda x: (x == "todos", int(x) if x.isdigit() else 0))) or "ninguno"
    control("ssh", "Puerto 22 (SSH) cerrado a internet", f"Puertos abiertos a internet: {lista}. Se entra con Session Manager.",
            "alerta" if ssh else "ok", "Abierto" if ssh else "Cerrado", "A.8.20")
else:
    control("ssh", "Puerto 22 (SSH) cerrado a internet", sin_permiso, "sin_dato", "Sin dato", "A.8.20")

# 2. Disco cifrado
vol = js("volumenes.json")
defecto = (js("cifrado-defecto.json") or {}).get("EbsEncryptionByDefault")
if vol and vol.get("Volumes"):
    cif = [v.get("Encrypted") for v in vol["Volumes"]]
    extra = " · cifrado por defecto activo en la región" if defecto else (" · falta activar el cifrado por defecto en la región" if defecto is False else "")
    control("disco", "Disco cifrado", f"{sum(1 for c in cif if c)} de {len(cif)} volúmenes EBS cifrados{extra}",
            "ok" if all(cif) else "alerta", "Cifrado" if all(cif) else "Sin cifrar", "A.8.24")
else:
    control("disco", "Disco cifrado", sin_permiso, "sin_dato", "Sin dato", "A.8.24")

# 3. Parches
activo = leer("unattended") == "si"
reinicio = leer("reinicio") == "si"
pendientes = int(leer("parches", "0") or 0)
fecha_u = leer("unattended-fecha")
ultimo = datetime.fromtimestamp(int(fecha_u), timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if fecha_u.isdigit() else "sin registro"
if not activo:
    estado, etiqueta = "alerta", "Desactivado"
elif reinicio:
    estado, etiqueta = "alerta", "Reinicio pendiente"
elif pendientes:
    estado, etiqueta = "alerta", f"{pendientes} pendientes"
else:
    estado, etiqueta = "ok", "Al día"
control("parches", "Parches de seguridad automáticos", f"unattended-upgrades · última ejecución {ultimo}", estado, etiqueta, "A.8.8")

# 4. Secretos
servicio = leer("secretos-servicio") == "active"
en_disco = leer("claves-disco")
n_claves = int(leer("claves-secreto", "0") or 0)
if en_disco:
    control("secretos", "Secretos fuera del .env", f"Claves aún escritas en disco: {en_disco}", "alerta", "En disco", "A.8.24")
elif servicio and leer("env-enlace").startswith("/run/"):
    control("secretos", "Secretos fuera del .env", f"{n_claves} claves en AWS Secrets Manager; el .env vive solo en memoria", "ok",
            f"{n_claves} en Secrets Manager", "A.8.24")
else:
    control("secretos", "Secretos fuera del .env", "El servicio mesa-secretos no está activo", "alerta", "Sin migrar", "A.8.24")

# 5. IMDSv2
v1 = leer("imdsv1")
if v1 == "401":
    control("imds", "Metadatos protegidos (IMDSv2)", "Evita robo de credenciales del rol desde un contenedor", "ok", "Obligatorio", "A.8.9")
elif v1 == "200":
    control("imds", "Metadatos protegidos (IMDSv2)", "Aún se aceptan pedidos IMDSv1 sin token", "alerta", "Opcional", "A.8.9")
else:
    control("imds", "Metadatos protegidos (IMDSv2)", "No se pudo consultar el servicio de metadatos", "sin_dato", "Sin dato", "A.8.9")

# 6. Contenedores sin root
filas = [l.split(" ", 1) + [""] for l in leer("contenedores").splitlines() if l.strip()]
if filas:
    root = [n.rsplit("-", 2)[-2] for n, u, *_ in filas if u.strip() in ("", "0", "root") or u.strip().startswith("0:")]
    control("contenedores", "Contenedores sin root", "api, worker y web corren con un usuario sin privilegios",
            "alerta" if root else "ok", (", ".join(sorted(set(root))) + " como root") if root else "Sin root", "A.8.9")
else:
    control("contenedores", "Contenedores sin root", "No se encontraron los contenedores de la Mesa", "sin_dato", "Sin dato", "A.8.9")

# 7. CloudTrail
trails = js("trails.json")
estados = []
for l in leer("trail-estado.jsonl").splitlines():
    try: estados.append(json.loads(l).get("IsLogging"))
    except Exception: pass
if trails is None:
    control("cloudtrail", "CloudTrail activo", sin_permiso, "sin_dato", "Sin dato", "A.8.15")
else:
    ok = any(estados)
    control("cloudtrail", "CloudTrail activo", "Quién cambió qué en la cuenta de AWS", "ok" if ok else "alerta", "Activo" if ok else "Inactivo", "A.8.15")

# 8. Cuenta raíz
cuenta = (js("cuenta.json") or {}).get("SummaryMap")
if cuenta:
    mfa, claves = cuenta.get("AccountMFAEnabled") == 1, cuenta.get("AccountAccessKeysPresent", 0) == 0
    detalle = "Con MFA" if mfa else "Sin MFA"
    detalle += " y sin claves de acceso" if claves else " y CON claves de acceso (bórrelas)"
    control("raiz", "Cuenta raíz de AWS con MFA", detalle, "ok" if mfa and claves else "alerta", "Correcto" if mfa and claves else "Revisar", "A.8.2")
else:
    control("raiz", "Cuenta raíz de AWS con MFA", sin_permiso, "sin_dato", "Sin dato", "A.8.2")

# 9. WAF (opcional)
control("waf", "Firewall de aplicaciones (opcional)", "AWS WAF o Cloudflare delante de Caddy", "opcional", "No instalado", "A.8.20")

informe = {
    "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "servidor": {"nombre": leer("nombre"), "instancia": leer("instancia"), "tipo": leer("tipo"), "region": leer("region"),
                 "zona": leer("zona"), "so": leer("so"), "kernel": leer("kernel")},
    "parches": {"pendientes": pendientes, "reinicio": reinicio},
    "controles": controles,
}
json.dump(informe, open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
chmod 644 "$SALIDA.tmp" && mv "$SALIDA.tmp" "$SALIDA"
python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
for c in d["controles"]: print(("OK " if c["estado"]=="ok" else "!! " if c["estado"]=="alerta" else "-- ")+c["nombre"]+": "+c["etiqueta"])' "$SALIDA"
echo "Informe: $SALIDA"
