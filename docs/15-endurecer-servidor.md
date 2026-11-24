# Endurecer el servidor EC2 (ISO 27001 · mejora 40)

Guía paso a paso para dejar el servidor de producción como en las maquetas 40a y 40b:

- se entra **sin SSH abierto a internet** (Session Manager);
- las claves salen del `.env` y quedan en **AWS Secrets Manager**;
- el **disco va cifrado**;
- los **parches de seguridad** se instalan solos;
- los **metadatos** quedan protegidos (IMDSv2);
- la cuenta de AWS tiene **MFA y CloudTrail**.

Para los usuarios no cambia nada: la Mesa sigue en https://mesa.aducorp.com.ec.

**Servidor:** instancia `mesa-servicios` en **EE. UU. Este (Ohio) · `us-east-2`**, Ubuntu 24.04, `/opt/mesa-servicios`, IP elástica `3.140.8.228`.
**Cómo usar la guía:** en la consola de AWS siga los menús tal cual. En la terminal del servidor pegue los comandos **de a uno** y espere a que termine cada uno.

## Resumen: qué se hace y cuándo

| # | Paso | ¿Corta el servicio? | Cuándo |
|---|---|---|---|
| 1 | Rol del servidor y Session Manager | No | Esta semana |
| 2 | IMDSv2 obligatorio | No | Esta semana |
| 3 | Cifrado por defecto de discos nuevos | No | Esta semana |
| 4 | Parches de seguridad automáticos | No | Esta semana |
| 5 | MFA en la cuenta raíz y CloudTrail | No | Esta semana |
| 6 | DBeaver por Session Manager | No (en su PC) | Esta semana |
| 7 | Preparar Secrets Manager | No | Esta semana |
| 8 | **Cifrar el disco** | **Sí, ~30 min** | **Domingo 29-nov, 02:00 a 04:00** |
| 9 | **Pasar las claves a Secrets Manager** y probar un reinicio | **Sí, ~3 min** | **Domingo 29-nov, en la misma ventana** |
| 10 | Cerrar el puerto 22 y reinicio dominical por parches | No | Lunes 30-nov o después |
| 11 | Borrar copias sin cifrar | No | Domingo 6-dic |

Lo que queda para el código (va en otro PR, no en esta guía): el contenedor `web` sin root, el script diario `deploy/verificar-servidor.sh` y la pestaña «Servidor» de la maqueta 40a. El WAF es opcional y no se instala (con 32 usuarios no es prioritario).

---

## 1. Rol del servidor y Session Manager (sin corte)

Session Manager permite abrir una terminal del servidor desde la consola de AWS **sin el puerto 22**. Ubuntu en EC2 ya trae el agente instalado; solo le falta permiso.

### 1.1 ¿El servidor ya tiene un rol?
**EC2 › Instances** › `mesa-servicios` › pestaña *Security* › **IAM Role**.
- Si dice un nombre (por ejemplo `mesa-servicios-respaldos`), use **ese rol** en 1.2: vaya a *IAM › Roles*, ábralo y salte directo al punto 3 («Add permissions»).
- Si está vacío, cree uno como en 1.2.

### 1.2 Crear el rol
1. **IAM › Roles › Create role**.
2. *Trusted entity type:* **AWS service** · *Use case:* **EC2** › *Next*.
3. *Add permissions:* busque y marque **AmazonSSMManagedInstanceCore** › *Next*.
4. *Role name:* `mesa-servicios-ec2` › **Create role**.
5. Asígnelo: **EC2 › Instances** › `mesa-servicios` › *Actions* › *Security* › **Modify IAM role** › elija `mesa-servicios-ec2` › **Update IAM role**.

### 1.3 Despertar al agente
Entre por **EC2 Instance Connect** como siempre y pegue, de a uno:
```bash
sudo -i
```
```bash
snap restart amazon-ssm-agent
```
```bash
snap services amazon-ssm-agent
```
Debe decir `enabled  active`.

### 1.4 Probar
Espere 2 a 5 minutos. **EC2 › Instances** › `mesa-servicios` › **Connect** › pestaña **Session Manager** › **Connect**. Se abre una terminal en el navegador. Pruebe:
```bash
sudo -i
```
```bash
cd /opt/mesa-servicios && docker compose -f docker-compose.yml -f docker-compose.nube.yml ps
```
Si la pestaña Session Manager dice que la instancia no está conectada, espere unos minutos más y revise **Systems Manager › Fleet Manager**: la instancia debe aparecer como *Online*.

> Desde ahora tiene dos formas de entrar. **No cierre el puerto 22 todavía**: eso se hace en el paso 10, después del domingo.

---

## 2. IMDSv2 obligatorio (sin corte)

Evita que alguien que llegara a entrar en un contenedor robe las credenciales del rol del servidor.

1. **EC2 › Instances** › `mesa-servicios` › *Actions* › *Instance settings* › **Modify instance metadata options**.
2. *Instance metadata service:* **Enable** · *IMDSv2:* **Required** · *Metadata response hop limit:* **1** › **Save**.

Comprobación en la terminal del servidor:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://169.254.169.254/latest/meta-data/
```
Debe decir `401` (sin token ya no responde). La AWS CLI y el agente de Session Manager usan IMDSv2 y siguen funcionando.

---

## 3. Cifrado por defecto de discos nuevos (sin corte)

**EC2 › Dashboard** › a la derecha *Account attributes* › **Data protection and security** › *EBS encryption* › **Manage** › marque **Enable** · clave `alias/aws/ebs` › **Update EBS encryption**.
Desde ahí todo disco o instantánea nueva en Ohio nace cifrado. No cambia el disco actual: eso es el paso 8.

---

## 4. Parches de seguridad automáticos (sin corte)

Ubuntu trae `unattended-upgrades`; aquí se confirma que está activo y que solo instala parches de seguridad. En la terminal, de a uno:
```bash
sudo -i
```
```bash
apt-get update && apt-get install -y unattended-upgrades
```
```bash
dpkg-reconfigure -f noninteractive unattended-upgrades
```
```bash
cat /etc/apt/apt.conf.d/20auto-upgrades
```
Deben aparecer las dos líneas con `"1"` (`Update-Package-Lists` y `Unattended-Upgrade`).
```bash
unattended-upgrade --dry-run 2>&1 | tail -3
```
Sin errores. Docker no se actualiza solo (viene de otro repositorio), así que nunca se reinicia la Mesa por sorpresa.

El reinicio automático cuando un parche lo pide (por ejemplo, un kernel nuevo) se programa en el paso 10, **después** del domingo, para que no caiga dentro de la ventana.

---

## 5. MFA en la cuenta raíz y CloudTrail (sin corte)

### 5.1 Cuenta raíz
1. Ingrese con el **correo de la cuenta raíz** › arriba a la derecha, el nombre de la cuenta › **Security credentials**.
2. *Multi-factor authentication (MFA)* › **Assign MFA device** › *Authenticator app* (Microsoft Authenticator o Google Authenticator) › escanee el código › ingrese dos códigos seguidos.
3. En la misma página, *Access keys*: si hay alguna, **elimínela**. La raíz no debe tener claves.
4. Para el trabajo diario conviene un usuario IAM propio con MFA (IAM › Users › Create user, política `AdministratorAccess`) y dejar la raíz guardada.

### 5.2 CloudTrail
1. **CloudTrail › Trails › Create trail**.
2. *Trail name:* `mesa-auditoria` · *Storage location:* **Create new S3 bucket** (nombre sugerido).
3. *Log file SSE-KMS encryption:* **desmarque** para usar el cifrado de S3, que es gratuito (con KMS cuesta USD 1 al mes).
4. *Log file validation:* **Enabled** › *Next*.
5. *Events:* solo **Management events** (Read y Write) › *Next* › **Create trail**.

Costo: el primer registro de eventos de administración es gratuito. El bucket cuesta centavos al mes.

---

## 6. DBeaver por Session Manager (sin corte, en su PC con Windows)

Hoy DBeaver entra por SSH con la llave `mesa_aducorp.pem`. Con Session Manager se abre el mismo túnel sin el puerto 22.

### 6.1 Usuario de AWS solo para el túnel
1. **IAM › Users › Create user** › nombre `dbeaver-santiago` › *Next* › *Attach policies directly* › no marque nada › *Next* › **Create user**.
2. Abra el usuario › *Add permissions* › **Create inline policy** › pestaña **JSON** y pegue (cambie `CUENTA` por su número de cuenta de 12 dígitos e `INSTANCIA` por el `i-…` del servidor):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "ssm:StartSession",
         "Resource": [
           "arn:aws:ec2:us-east-2:CUENTA:instance/INSTANCIA",
           "arn:aws:ssm:us-east-2::document/AWS-StartPortForwardingSessionToRemoteHost"
         ]
       },
       {
         "Effect": "Allow",
         "Action": ["ssm:TerminateSession", "ssm:ResumeSession"],
         "Resource": "arn:aws:ssm:*:*:session/${aws:username}-*"
       }
     ]
   }
   ```
   Nombre: `tunel-sql-mesa` › **Create policy**.
3. En el usuario › *Security credentials* › **Create access key** › *Command Line Interface (CLI)* › confirme › **guarde** el *Access key* y el *Secret access key* (solo se muestran una vez).

### 6.2 Instalar en su PC
1. AWS CLI: https://awscli.amazonaws.com/AWSCLIV2.msi
2. Session Manager plugin: https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe
3. Abra **PowerShell** nuevo y configure el perfil (pegue las claves del paso 6.1, región `us-east-2`, formato `json`):
   ```powershell
   aws configure --profile mesa
   ```

### 6.3 Abrir el túnel
La IP interna del contenedor de SQL Server la ve en el servidor con:
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' aducorp-mesa-sqlserver-1
```
(normalmente `172.18.0.2`; puede cambiar tras un reinicio).

En PowerShell (cambie `INSTANCIA` y la IP si hace falta):
```powershell
aws ssm start-session --profile mesa --region us-east-2 --target INSTANCIA --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host=172.18.0.2,portNumber=1433,localPortNumber=14330
```
Debe decir `Waiting for connections...`. Deje esa ventana abierta mientras use DBeaver (también puede usar el archivo `abrir-tunel-dbeaver.bat` que acompaña esta guía).

### 6.4 Cambiar la conexión en DBeaver
Clic derecho en la conexión › *Edit Connection*:
- **Host:** `localhost` · **Port:** `14330` (usuario y clave de SQL, los mismos de siempre).
- Pestaña **SSH**: **desmarque** *Use SSH Tunnel*.
- *Test Connection* › OK.

Cuando esto funcione, la llave `.pem` ya no hace falta. Guárdela en un lugar seguro hasta el paso 10.

---

## 7. Preparar Secrets Manager (sin corte)

Antes del domingo, **actualice producción a `main`** como siempre (respaldo, `git pull --ff-only`, `up -d --build`). Así llega el script `deploy/nube/secretos.sh`. El script por sí solo no cambia nada.

### 7.1 Instalar la AWS CLI en el servidor
```bash
sudo -i
```
```bash
snap install aws-cli --classic
```
```bash
aws --version
```

### 7.2 Sacar las claves actuales
```bash
cd /opt/mesa-servicios
```
```bash
./deploy/nube/secretos.sh exportar
```
Muestra una línea JSON, por ejemplo `{"SA_PASSWORD": "…", "DB_APP_PASSWORD": "…", "JWT_SECRET": "…", "M365_CLIENT_SECRET": "…"}`. **Cópiela completa.** No la guarde en ningún archivo ni la envíe por correo.

### 7.3 Crear el secreto
1. **Secrets Manager** (región **Ohio**) › **Store a new secret**.
2. *Secret type:* **Other type of secret** › pestaña **Plaintext** › borre lo que haya y **pegue el JSON** › *Encryption key:* `aws/secretsmanager` › *Next*.
3. *Secret name:* `mesa/produccion` · *Description:* `Claves de la Mesa de Servicios (SQL, JWT, Graph)`.
   *Tags:* `vence-graph` = `2028-11-22` (el secreto de Graph vence ese mes) › *Next*.
4. *Rotation:* no › *Next* › **Store**.
5. Abra el secreto y copie su **Secret ARN** (empieza con `arn:aws:secretsmanager:us-east-2:`).

Costo: USD 0,40 al mes.

### 7.4 Dar permiso al servidor para leerlo
**IAM › Roles** › el rol del paso 1 › *Add permissions* › **Create inline policy** › **JSON**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-2:CUENTA:secret:mesa/produccion-*"
    }
  ]
}
```
Nombre: `leer-secreto-mesa` › **Create policy**.

### 7.5 Probar (no cambia nada)
```bash
./deploy/nube/secretos.sh probar
```
Debe decir `Secreto leído correctamente. Claves: …` con los mismos nombres del paso 7.2.

---

## 8. Cifrar el disco (domingo 29, en la ventana)

Siga el runbook **`Runbook-Cifrado-Disco-EC2-29-nov.md`** (carpeta `ventana-mantenimiento` del proyecto). Ahí está el respaldo previo, la instantánea, el disco cifrado, el cambio de disco, la verificación y el plan de reversa.

Puede usar Session Manager o EC2 Instance Connect: las dos sirven el domingo.

---

## 9. Pasar las claves a Secrets Manager (domingo 29, en la misma ventana)

Hágalo **solo si el paso 8 terminó bien** y queda al menos media hora de ventana. Si no, puede hacerlo otro día a última hora, con un corte de unos 3 minutos.

En la terminal del servidor, de a uno:
```bash
sudo -i
```
```bash
cd /opt/mesa-servicios
```
```bash
./deploy/nube/secretos.sh separar
```
Esto hace lo siguiente:
- guarda una copia del `.env` original en `/root/env-original-…`;
- crea `.env.base`, que es la misma configuración pero sin claves;
- cambia `.env` por un enlace a `/run/mesa-servicios/.env`, que vive solo en memoria;
- comprueba que el resultado sea idéntico al original. Si no lo es, vuelve todo atrás solo.
```bash
./deploy/nube/secretos.sh instalar
```
(servicio `mesa-secretos`: arma `.env` en cada arranque del servidor)
```bash
ls -l .env
```
Debe verse `.env -> /run/mesa-servicios/.env`.
```bash
grep -E "^(SA_PASSWORD|DB_APP_PASSWORD|JWT_SECRET|M365_CLIENT_SECRET)=" .env.base
```
No debe mostrar nada: el archivo en disco ya no tiene claves.
```bash
docker compose -f docker-compose.yml -f docker-compose.nube.yml --profile nube up -d
```
Debe decir *Running* o *up-to-date* para todo, sin recrear nada.

**Prueba de reinicio** (comprueba que todo vuelve solo):
```bash
reboot
```
Espere 2 minutos, vuelva a entrar y compruebe:
```bash
sudo -i
```
```bash
systemctl status mesa-secretos --no-pager | head -5
```
Debe decir `active (exited)`.
```bash
cd /opt/mesa-servicios && docker compose -f docker-compose.yml -f docker-compose.nube.yml ps
```
```bash
curl -s http://127.0.0.1:8080/api/v1/health; echo
```
Debe decir `"estado":"ok"`. Entre a la Mesa desde el navegador.

**Si algo falla:**
```bash
./deploy/nube/secretos.sh revertir
```
Vuelve al `.env` original. Después ejecute el `docker compose … up -d` de siempre.

### Desde ahora, para cambiar la configuración
- Un valor normal (por ejemplo `BUZON_ENABLED`): edite **`.env.base`** (ya no `.env`), luego `./deploy/nube/secretos.sh cargar` y el `docker compose … up -d` de siempre.
- Una clave (por ejemplo, cuando renueve el secreto de Graph): **Secrets Manager** › `mesa/produccion` › *Retrieve secret value* › **Edit**. Luego, en el servidor, `./deploy/nube/secretos.sh cargar` y `docker compose … up -d`.
- Las guías anteriores que dicen «edite el .env» se aplican ahora a `.env.base`.
- `respaldo.sh`, `vigilante.sh` e `instalar.sh` funcionan igual que antes.

---

## 10. Cerrar el puerto 22 y programar el reinicio por parches (lunes 30 o después)

Antes de cerrar, confirme que **Session Manager funciona** (paso 1.4) y que **DBeaver conecta por el túnel nuevo** (paso 6).

### 10.1 Cerrar el puerto 22
1. **EC2 › Instances** › `mesa-servicios` › pestaña *Security* › clic en el **Security group**.
2. *Inbound rules* › **Edit inbound rules** › en la fila **SSH · 22** › **Delete** › **Save rules**.
3. Deben quedar solo **80** y **443**.

Desde ahora se entra con **Connect › Session Manager**. EC2 Instance Connect deja de funcionar porque usa el puerto 22. Si alguna vez lo necesita, se vuelve a abrir el 22 solo para su IP y se cierra al terminar.

### 10.2 Reinicio automático los domingos a las 03:00 si un parche lo pide
```bash
sudo -i
```
```bash
echo '0 8 * * 0  root  [ -f /var/run/reboot-required ] && /sbin/shutdown -r +2 "Reinicio por parches de seguridad"' > /etc/cron.d/mesa-reinicio
```
El servidor está en UTC, así que 08:00 UTC son las 03:00 en Ecuador. Solo reinicia si hace falta. La Mesa vuelve sola en unos 2 minutos: los contenedores se reinician y el servicio `mesa-secretos` arma el `.env`.

### 10.3 Borrar la copia del .env original
Cuando ya haya pasado al menos un reinicio sin problemas:
```bash
shred -u /root/env-original-*
```

---

## 11. Borrar copias sin cifrar (domingo 6-dic)

Las copias viejas del disco todavía tienen el `.env` con claves y los datos sin cifrar. Bórrelas:
- **EC2 › Volumes** › `mesa-raiz-VIEJO-sin-cifrar` › **Delete volume**.
- **EC2 › Snapshots** › `mesa-raiz-antes-de-cifrar` y `mesa-raiz-previa-sabado` › **Delete snapshot**.
- La llave `mesa_aducorp.pem` ya no hace falta: bórrela de su PC y elimine el par de llaves en **EC2 › Key pairs**.

Opcional, como higiene: las claves viejas estuvieron en un disco sin cifrar. Se pueden renovar con calma:
- `JWT_SECRET`: obliga a todos a volver a ingresar;
- el secreto de Graph: se crea uno nuevo en Entra;
- las claves de SQL: necesitan un cambio en la base.

Se puede hacer en otra ventana.

## 12. Verificación diaria: pestaña «Servidor» (sin corte)

La Mesa corre dentro de un contenedor y no puede revisar el servidor por sí misma. El script
`deploy/nube/verificar-servidor.sh` lo revisa en modo **solo lectura** y deja `estado/servidor.json`.
La API lo lee y lo muestra en **Seguridad y cumplimiento › Servidor**.

Revisa: puerto 22 abierto a internet, disco cifrado, parches pendientes y reinicio, claves fuera del disco, IMDSv2,
contenedores sin root, CloudTrail y MFA de la cuenta raíz.

### 12.1 Permisos de solo lectura para el rol del servidor
**IAM › Roles** › el rol del paso 1 › *Add permissions* › **Create inline policy** › **JSON**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances", "ec2:DescribeSecurityGroups", "ec2:DescribeVolumes", "ec2:GetEbsEncryptionByDefault",
        "cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus", "iam:GetAccountSummary"
      ],
      "Resource": "*"
    }
  ]
}
```
Nombre: `verificar-servidor-mesa` › **Create policy**. Sin estos permisos, los controles de AWS salen como «Sin dato».

### 12.2 Programarlo
```bash
cd /opt/mesa-servicios
sudo ./deploy/nube/verificar-servidor.sh instalar      # revisa ahora y lo programa todos los días a las 06:00
docker compose -f docker-compose.yml -f docker-compose.nube.yml --profile nube up -d api   # monta estado/ en la API
```
Para revisar en cualquier momento: `sudo ./deploy/nube/verificar-servidor.sh`.

## Evidencia para ISO 27001

Guarde capturas de pantalla de cada punto:

| Evidencia | Control |
|---|---|
| Volumen con *Encrypted* | A.8.24 |
| Grupo de seguridad solo con 80 y 443 | A.8.20 |
| Opciones de metadatos con IMDSv2 *Required* | A.8.9 |
| Secreto `mesa/produccion` | A.8.24 |
| `20auto-upgrades` | A.8.8 |
| Trail activo | A.8.15 |
| MFA en la raíz | A.8.5 |

La pestaña **Servidor** de la Mesa resume estos puntos cada día; una captura mensual sirve de evidencia.

Registre los pasos 8 y 9 como **cambio normal** en el registro de cambios de la Mesa.
