# Publicar la Mesa de Servicios en internet (gratis)

Esta guía deja la Mesa disponible fuera de la oficina, con HTTPS y sin pagar hosting. La Mesa sigue corriendo donde ya funciona (el PC o servidor con Docker) y **Cloudflare Tunnel** la publica: el equipo abre una conexión de salida hacia Cloudflare, así que no hay que abrir puertos en el router ni tener IP fija.

## 1. Por qué esta opción y no un hosting gratuito en la nube

| Opción | ¿Gratis? | Problema |
|---|---|---|
| **Cloudflare Tunnel desde el equipo actual** (recomendada) | Sí, sin límite de tiempo | El equipo debe quedar encendido con Docker abierto |
| Azure SQL Database gratis + Azure Container Apps | Solo en parte | La base gratuita trae 100 000 segundos de vCore al mes. El motor de SLA consulta la base cada minuto, así que la base nunca se pausa y el cupo se agota en unos 2 o 3 días; después se apaga hasta el mes siguiente o empieza a cobrar. Además pide adaptar los scripts de la base (logins, modo de recuperación) |
| Render, Railway, Fly.io, Koyeb y similares | Planes gratuitos pequeños | No ofrecen SQL Server. Habría que reescribir la base (procedimientos, vistas, triggers) para PostgreSQL, y los planes gratuitos se duermen y no guardan los adjuntos |

Cuando la Mesa ya se use a diario y se quiera independizar del PC, lo natural es un servidor pequeño en la nube (o un servidor de la oficina) con el mismo Docker Compose de siempre; ese paso sí tiene costo mensual.

## 2. Antes de empezar

1. **Equipo siempre encendido.** En Windows: Configuración > Sistema > Energía > «Suspender» en *Nunca*. En Docker Desktop: Settings > General > *Start Docker Desktop when you sign in*.
2. **Código al día.** En la carpeta del proyecto: `git pull` (necesita la rama `main` con estos archivos).
3. **Contraseña del administrador.** La contraseña inicial `Aducorp2026!` está escrita en el README y la comparten todos los usuarios de demostración. Ingrese a la Mesa con `admin@aducorp.com.ec` y cámbiela por una larga y propia. El script de publicación se niega a publicar mientras un Super Admin la siga usando, y **desactiva** las demás cuentas que la usen. Para volver a habilitar a alguien: Administración > Usuarios > activar y «Generar contraseña temporal».

Licencia: Docker Desktop es gratuito para empresas con menos de 250 empleados y menos de 10 millones de dólares de facturación anual.

## 3. Prueba rápida (5 minutos, sin cuenta)

Sirve para mostrar la Mesa hoy desde cualquier celular. En PowerShell, dentro de la carpeta del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\publicar.ps1 -Modo prueba
```

El script revisa las contraseñas, levanta el túnel y muestra una dirección como `https://palabras-al-azar.trycloudflare.com`. Límites de esta modalidad: la dirección **cambia cada vez** que se reinicia el túnel o el PC, Cloudflare no garantiza disponibilidad y admite hasta 200 solicitudes simultáneas. Es para pruebas, no para el uso diario.

Para dejar de publicar (la Mesa sigue en la red local):

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\publicar.ps1 -Modo detener
```

## 4. Dirección fija: `https://mesa.aducorp.com.ec`

Cloudflare publica gratis una dirección fija si el dominio usa los servidores DNS de Cloudflare.

### 4.1 Pasar el dominio a Cloudflare (una sola vez)

> Esto lo hace quien administra el dominio `aducorp.com.ec`. Un error aquí puede cortar el correo de Microsoft 365, así que conviene hacerlo con calma y fuera del horario laboral.

1. Cree una cuenta en <https://dash.cloudflare.com/sign-up> (plan **Free**).
2. *Add a domain* > `aducorp.com.ec` > plan Free. Cloudflare copia los registros DNS actuales.
3. Compare la lista con la del proveedor actual. Deben estar **todos**, en especial los de correo: `MX`, `autodiscover`, el `TXT` de SPF (`v=spf1 include:spf.protection.outlook.com …`), DKIM (`selector1._domainkey`, `selector2._domainkey`) y DMARC. Los registros de correo deben quedar con la nube **gris** (*DNS only*).
4. Cloudflare indica dos servidores de nombres. Cámbielos en el registrador del dominio (donde se compró `aducorp.com.ec`). El cambio tarda de minutos a 24 horas; Cloudflare envía un correo cuando el dominio está activo.

Si no se quiere mover el dominio de la empresa, otra opción es comprar un dominio aparte solo para la Mesa (unos 10 dólares al año) y agregarlo a Cloudflare con los mismos pasos.

### 4.2 Crear el túnel

1. En Cloudflare: **Zero Trust** (menú izquierdo; la primera vez pide un nombre de equipo y elegir el plan Free, que puede pedir una tarjeta pero no cobra).
2. *Networks* > *Tunnels* > *Create a tunnel* > **Cloudflared** > nombre `mesa-aducorp`.
3. En «Install and run a connector» elija **Docker**. Copie solo el texto largo que va después de `--token` (empieza con `eyJ`). No hace falta ejecutar ese comando.
4. *Next* > *Public hostname*: Subdomain `mesa`, Domain `aducorp.com.ec`, Service **HTTP**, URL `web:8080`. Guarde.

### 4.3 Configurar y publicar

Edite el archivo `.env` de la carpeta del proyecto:

```ini
CLOUDFLARE_TUNNEL_TOKEN=eyJ...el token copiado...
APP_URL=https://mesa.aducorp.com.ec
CORS_ORIGINS=["https://mesa.aducorp.com.ec"]
```

Y publique:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\publicar.ps1 -Modo publico
```

En Cloudflare, *Tunnels* debe mostrar `mesa-aducorp` como **Healthy**. Abra `https://mesa.aducorp.com.ec` desde el celular con datos móviles para confirmar. El túnel se reinicia solo con Docker, así que después de un reinicio del PC vuelve sin hacer nada.

Recomendado en Cloudflare (dominio > *SSL/TLS* > *Edge Certificates*): activar **Always Use HTTPS**.

## 5. Seguridad

- La Mesa ya trae bloqueo por intentos fallidos, límite de 10 intentos de login por minuto por IP, contraseñas cifradas con bcrypt y auditoría. Con el túnel, `deploy/cloudflare/ip-real.conf` hace que Nginx vea la IP real de cada usuario (cabecera `CF-Connecting-IP`); sin eso todos compartirían el límite de intentos y la auditoría registraría la IP del túnel.
- Si la Mesa tiene los 650 tickets de demostración, quedan visibles para quien tenga una cuenta. Antes del uso real conviene dejarla limpia.
- Capa extra opcional y gratuita (hasta 50 usuarios): **Cloudflare Access** (*Zero Trust* > *Access* > *Applications* > *Self-hosted*, dominio `mesa.aducorp.com.ec`, política «Emails ending in `@aducorp.com.ec`»). Cloudflare pide un código enviado al correo antes de mostrar la Mesa, así que nadie de fuera de la empresa llega siquiera a la pantalla de login.
- Swagger (`/api/v1/docs`) queda público con la Mesa. Si no se usa, ponga `DOCS_ENABLED=false` en `.env`.
- Los respaldos siguen igual que antes (`deploy/respaldo.sh` o el procedimiento del manual técnico).

## 6. Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| El script dice que un Super Admin usa la contraseña inicial | Cámbiela en la Mesa (menú de usuario > Cambiar contraseña) y repita |
| «No se puede cargar el archivo … la ejecución de scripts está deshabilitada» | Use el comando completo con `powershell -ExecutionPolicy Bypass -File …` |
| Cloudflare muestra error 502 o 1033 | Docker Desktop cerrado o el PC suspendido. `docker compose ps` debe mostrar `web` y `tunel` en ejecución |
| El túnel aparece *Inactive* | Token mal copiado en `.env` (debe ir completo, sin comillas ni espacios). Revise `docker compose -f docker-compose.yml -f docker-compose.publico.yml logs tunel` |
| Los enlaces de los correos apuntan a `localhost` | Falta `APP_URL=https://mesa.aducorp.com.ec` en `.env`; luego repita `-Modo publico` |
