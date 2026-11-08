# Publicar la Mesa en la nube (sin depender de un PC encendido)

Esta guía instala la Mesa completa (SQL Server, API, worker y web) en un servidor en la nube, con un enlace público HTTPS que funciona las 24 horas aunque los equipos de la oficina estén apagados. Todo se instala con un solo comando.

## 0. Lo que conviene saber antes

- **No existe una opción gratis para siempre con SQL Server.** SQL Server necesita un servidor Intel/AMD con al menos 2 GB de RAM libres, y los servidores «gratis para siempre» de las nubes traen 1 GB o son ARM, que no sirve.
- **Lo más cercano a gratis es la cuenta nueva de AWS (Amazon):** trae 100 dólares de crédito al crear la cuenta y hasta 100 más por completar actividades sencillas, válidos por 6 meses. El servidor recomendado consume unos 60 a 70 dólares de crédito al mes, así que alcanza para **unos 3 meses sin pagar nada**. AWS pide una tarjeta para verificar la identidad, pero en el plan gratuito no cobra: cuando se acaba el crédito, la cuenta se pausa hasta que uno decida pasar a pago.
- **Después de esos meses** hay dos caminos: pasar a pago en AWS, o mover la Mesa a un servidor más barato de cualquier proveedor (Hetzner, Contabo, DigitalOcean, etc.) que tenga Ubuntu 24.04, procesador x86 y 4 GB de RAM. El mismo comando de instalación funciona en cualquiera de ellos, y los respaldos de la base permiten llevarse los datos.
- La base usa **SQL Server Express**, la edición gratuita para producción. Su límite es 10 GB por base, mucho más de lo que ocupa la Mesa.

Tiempo total: unos 45 minutos, la mayor parte esperando.

## 1. Crear la cuenta de AWS

1. Entre a <https://aws.amazon.com/free> y elija **Crear una cuenta gratuita**.
2. Use un correo de la empresa (por ejemplo `ti@aducorp.com.ec`) y elija el plan **Gratuito** (*Free plan*) cuando lo pregunte.
3. Complete la verificación con tarjeta y teléfono.
4. Ya dentro, arriba a la derecha elija la región **EE. UU. Este (Norte de Virginia) `us-east-1`**: es la más barata y la latencia a Ecuador es buena.
5. Recomendado y además suma 20 dólares de crédito: busque **Budgets** > *Create budget* > plantilla *Zero spend budget* con su correo. AWS avisará si algo llegara a generar costo.

## 2. Crear el servidor

1. Busque **EC2** > **Launch instance** (Lanzar instancia).
2. **Name:** `mesa-servicios`.
3. **Imagen (AMI):** *Ubuntu Server 24.04 LTS*, arquitectura **64-bit (x86)**.
4. **Tipo de instancia:** `c7i-flex.large` (2 vCPU, 4 GB). Aparece marcada como *Free tier eligible*.
5. **Key pair:** *Proceed without a key pair*. Se entrará desde el navegador, sin llaves.
6. **Network settings:** marque **Allow SSH traffic from Anywhere**, **Allow HTTPS traffic from the internet** y **Allow HTTP traffic from the internet**. El puerto 80 es necesario para obtener el certificado HTTPS.
7. **Configure storage:** cambie 8 GiB a **30 GiB** (gp3).
8. **Launch instance**.

### IP fija

Para que la dirección del servidor no cambie si se reinicia:

1. En EC2, menú izquierdo **Elastic IPs** > **Allocate Elastic IP address** > *Allocate*.
2. Selecciónela > **Actions** > **Associate Elastic IP address** > elija la instancia `mesa-servicios` > *Associate*.
3. Anote esa IP (por ejemplo `3.215.40.12`).

## 3. Crear el nombre del enlace (gratis)

Se usa **DuckDNS**, un servicio gratuito que da un nombre fijo como `mesa-aducorp.duckdns.org`.

1. Entre a <https://www.duckdns.org> e ingrese con su cuenta de Google o GitHub.
2. En *sub domain* escriba `mesa-aducorp` (u otro nombre libre) > **add domain**.
3. En la fila del dominio, en *current ip*, escriba la **IP fija** del paso anterior > **update ip**.

Más adelante se puede usar `mesa.aducorp.com.ec` (sección 7).

## 4. Instalar la Mesa

1. En EC2 > *Instances*, seleccione `mesa-servicios` > **Connect** > pestaña **EC2 Instance Connect** > **Connect**. Se abre una terminal negra en el navegador.
2. Pegue este comando, con su nombre de DuckDNS, y presione Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/squezadaducorp/mesa_servicios/main/deploy/nube/instalar.sh | sudo bash -s -- mesa-aducorp.duckdns.org
   ```

3. Espere de 10 a 15 minutos. El script instala Docker, descarga el código, crea claves aleatorias, construye la aplicación, crea la base y activa HTTPS.
4. Al final muestra algo así. **Copie la contraseña temporal**:

   ```
   Listo. La Mesa queda en https://mesa-aducorp.duckdns.org
   Usuario: admin@aducorp.com.ec
   Contraseña temporal: Mesa9-1a2b3c4d5e6f-A1B2C3!
   ```

## 5. Primer ingreso

1. Abra el enlace desde cualquier equipo o celular. Si el navegador avisa de un certificado no válido, espere un par de minutos y recargue.
2. Ingrese con `admin@aducorp.com.ec` y la contraseña temporal. La Mesa pedirá cambiarla por una propia.
3. La base empieza **limpia** (sin los tickets de demostración). Por seguridad, el script **desactivó** a los demás usuarios iniciales, que traían la contraseña pública `Aducorp2026!`. Para habilitarlos o crear los usuarios reales: Administración > Usuarios > activar y **Generar contraseña temporal**.
4. Revise en Administración la configuración de la empresa, categorías, SLA y feriados.

## 6. Operación diaria

| Tarea | Cómo |
|---|---|
| Respaldos | Automáticos: base y adjuntos todas las noches a las 23:00, y el registro de transacciones cada 15 minutos en horario laboral. Quedan en `/opt/mesa-servicios/backups` (se guardan 30 días) |
| Copia fuera del servidor | Recomendado una vez al mes: EC2 > *Volumes* > el volumen de la instancia > *Create snapshot* |
| Actualizar a la última versión | Conectarse como en el paso 4.1 y volver a pegar el mismo comando. Conserva la base, la configuración y los adjuntos |
| Ver si todo está en marcha | `cd /opt/mesa-servicios && sudo docker compose ps` |
| Ver errores | `cd /opt/mesa-servicios && sudo docker compose logs --tail 100 api` |
| Correo soporte@ y Microsoft 365 | Editar `/opt/mesa-servicios/.env` (`sudo nano .env`) como indica [10-microsoft-365.md](10-microsoft-365.md) y volver a pegar el comando de instalación |

Antes de que se acabe el crédito, AWS envía avisos al correo (cuando queda 50 %, 25 % y 10 %, y 15, 7 y 2 días antes del fin del plan). En ese momento se decide si pasar a pago o mudarse a otro proveedor. Para mudarse: crear el servidor nuevo, ejecutar el mismo comando y restaurar el último respaldo con `deploy/restaurar.sh`.

## 7. Usar `mesa.aducorp.com.ec` (opcional)

No hace falta mover el dominio a otro proveedor:

1. Quien administra el DNS de `aducorp.com.ec` agrega un registro **A**: nombre `mesa`, valor la **IP fija** del servidor.
2. Cuando responda (`nslookup mesa.aducorp.com.ec` muestra la IP), vuelva a pegar el comando de instalación con el nuevo nombre:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/squezadaducorp/mesa_servicios/main/deploy/nube/instalar.sh | sudo bash -s -- mesa.aducorp.com.ec
   ```

## 8. Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| `c7i-flex.large` no aparece como *Free tier eligible* | Revise que la región sea `us-east-1`. Si no está, use `m7i-flex.large` (8 GB, consume crédito algo más rápido) |
| El navegador no abre el enlace | En DuckDNS, la IP debe ser la Elastic IP. En EC2, el grupo de seguridad debe permitir los puertos 80 y 443 |
| Error de certificado que no se corrige solo | Ver `sudo docker compose -f docker-compose.yml -f docker-compose.nube.yml logs caddy`. Suele ser el puerto 80 cerrado o la IP mal puesta en DuckDNS |
| «SQL Server necesita un servidor x86_64» | Se eligió una imagen ARM. Cree la instancia de nuevo con *64-bit (x86)* |
| Se perdió la contraseña temporal | `sudo cat /root/mesa-clave-admin.txt` (solo existe si el script la generó) |
