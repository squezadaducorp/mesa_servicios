# Monitoreo y respaldos del servidor

La Mesa tiene dos niveles de protección. Cada uno cubre lo que el otro no ve:

| Qué falla | Quién lo detecta | Qué hace |
|---|---|---|
| La página no responde, la base no conecta, un contenedor se detuvo | **Vigilante** (`deploy/vigilante.sh`, cada 5 min) | Intenta levantar la Mesa sola; si sigue mal 15 min, envía un correo. Avisa también cuando se normaliza |
| Disco casi lleno, certificado HTTPS por vencer, falta el respaldo de anoche | Vigilante | Correo |
| El respaldo nocturno falla | `deploy/respaldo.sh` | Correo inmediato |
| El servidor entero se apaga o se cuelga (el vigilante tampoco corre) | **AWS CloudWatch** | Reinicia o recupera la instancia y envía un correo (SNS) |
| Se pierde el servidor o el disco | **Copia en S3** + instantáneas del disco | Se restaura en un servidor nuevo |

Los correos del vigilante y del respaldo salen por el mismo canal que los demás correos de la Mesa (`EMAIL_TRANSPORTE`: Graph desde el buzón `mesaservicios@` o SMTP). No necesitan la base de datos, así que llegan aunque la Mesa esté caída. Si `EMAIL_ENABLED=false`, solo quedan en el registro.

## 1. Vigilante y avisos de respaldo

En el `.env` del servidor:

```bash
ALERTA_CORREOS=ti@aducorp.com.ec,santiago@aducorp.com.ec   # quién recibe las alertas
VIGILANTE_FALLOS=3          # revisiones seguidas con problemas antes de avisar (3 × 5 min = 15 min)
VIGILANTE_DISCO_PCT=85      # % de disco usado que dispara aviso
RESPALDO_DIAS_LOCAL=7       # días de respaldos en el disco del servidor (con S3 basta una semana)
RESPALDO_AVISO=error        # error = correo solo si falla · siempre = también un correo diario de "respaldo correcto"
```

`deploy/nube/instalar.sh` ya programa el vigilante. En un servidor instalado antes, agregue la línea a cron:

```bash
sudo tee -a /etc/cron.d/mesa-servicios <<'CRON'
*/5 * * * *  root  cd /opt/mesa-servicios && ./deploy/vigilante.sh >> /var/log/mesa-vigilante.log 2>&1
CRON
```

Pruebe que el correo llega:

```bash
cd /opt/mesa-servicios && sudo ./deploy/vigilante.sh --probar
tail -n 20 /var/log/mesa-vigilante.log
```

Qué revisa en cada pasada:

1. `http://127.0.0.1:8080/api/v1/health` responde `"estado":"ok"` con la base conectada.
2. La Mesa responde también desde internet (`https://DOMINIO`). Si solo falla esto, el problema está en Caddy, el DNS o el grupo de seguridad.
3. Los contenedores `sqlserver`, `api`, `worker`, `web` y `caddy` están en marcha.
4. Disco por debajo de `VIGILANTE_DISCO_PCT`.
5. El certificado HTTPS vence en más de 15 días.
6. El respaldo `.bak` más reciente tiene menos de 26 horas.

Si la Mesa no responde o hay un contenedor detenido, ejecuta `docker compose ... up -d` en cada pasada. El correo se envía a la tercera pasada seguida con problemas, se repite cada 2 horas si sigue igual (o antes si cambia el problema) y llega un correo de "volvió a la normalidad" al resolverse. El estado se guarda en `/var/lib/mesa-vigilante/estado`.

## 2. Copia de los respaldos en Amazon S3

Los respaldos quedan en `/opt/mesa-servicios/backups`. Si se pierde el servidor, se pierden con él. Para tener una copia fuera:

1. **Crear el bucket** (consola de AWS › S3 › Crear bucket), en la misma región del servidor (Ohio, `us-east-2`). Nombre, por ejemplo, `aducorp-mesa-respaldos`. Deje **Bloquear todo el acceso público** activado y active el **cifrado** (SSE-S3, viene por defecto).
2. **Regla de ciclo de vida** (bucket › Administración › Crear regla): "Vencer versiones actuales de objetos" a los **35 días**. Así S3 borra solo los respaldos viejos.
3. **Rol para el servidor** (IAM › Roles › Crear rol › Servicio de AWS › EC2). Agregue una política en línea con solo este permiso (cambie el nombre del bucket):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
       "Resource": ["arn:aws:s3:::aducorp-mesa-respaldos", "arn:aws:s3:::aducorp-mesa-respaldos/*"]
     }]
   }
   ```

   Nombre del rol: `mesa-servicios-respaldos`. Luego, en EC2 › la instancia › Acciones › Seguridad › **Modificar rol de IAM**, elija ese rol. No hace falta guardar claves de AWS en el servidor.
4. **Instalar la AWS CLI en el servidor** y agregar el bucket al `.env`:

   ```bash
   sudo snap install aws-cli --classic
   aws s3 ls s3://aducorp-mesa-respaldos      # debe responder sin error (vacío)
   echo "RESPALDO_S3_BUCKET=aducorp-mesa-respaldos" | sudo tee -a /opt/mesa-servicios/.env
   ```

5. Pruebe un respaldo completo y confirme que llegó:

   ```bash
   cd /opt/mesa-servicios && sudo ./deploy/respaldo.sh completo
   aws s3 ls s3://aducorp-mesa-respaldos --recursive | tail
   ```

Desde ese momento cada respaldo (el completo de las 23:00 y el del registro cada 15 minutos) se copia a `s3://BUCKET/<servidor>/completo|log/`. Costo estimado: menos de USD 1 al mes.

**Restaurar desde S3** en un servidor nuevo: instale la Mesa con `deploy/nube/instalar.sh`, descargue el último respaldo con `aws s3 cp s3://BUCKET/<servidor>/completo/<archivo>.bak backups/` (y `adjuntos_*.tar.gz`) y siga `deploy/restaurar.sh`.

## 3. Alarmas de AWS (si el servidor entero falla)

El vigilante corre dentro del servidor, así que no puede avisar si la máquina se apaga. Para eso están las alarmas de CloudWatch (gratis hasta 10 alarmas):

1. **Tema de avisos**: SNS › Temas › Crear tema (Estándar) `mesa-alertas` › Crear suscripción › Protocolo **Correo electrónico** › el mismo correo de `ALERTA_CORREOS`. Confirme el correo que llega de AWS.
2. **Recuperación automática**: EC2 › la instancia › pestaña **Estado y alarmas** › Administrar alarmas de CloudWatch › Crear:
   - Métrica **Error en la comprobación de estado del sistema** (`StatusCheckFailed_System`), 2 periodos de 1 minuto. Acción: **Recuperar** la instancia. Notificación: `mesa-alertas`.
   - Métrica **Error en la comprobación de estado de la instancia** (`StatusCheckFailed_Instance`), 3 periodos de 1 minuto. Acción: **Reiniciar**. Notificación: `mesa-alertas`.
   - (Opcional) **Uso de CPU** promedio ≥ 90 % durante 15 minutos. Solo notificación.
3. **Instantánea semanal del disco**: EC2 › Elastic Block Store › **Administrador del ciclo de vida** › Crear política (instantáneas de EBS) › destino: la instancia (por etiqueta `Name`), cada semana, conservar 4. Permite volver el servidor completo a un punto anterior.

## Revisar el estado a mano

```bash
cd /opt/mesa-servicios
tail -n 30 /var/log/mesa-vigilante.log     # últimas revisiones (solo escribe cuando hay problemas)
tail -n 30 /var/log/mesa-respaldo.log      # respaldos
ls -lh backups | tail                      # respaldos locales
cat /var/lib/mesa-vigilante/estado         # fallos seguidos y si ya se avisó
```
