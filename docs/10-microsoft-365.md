# Integración con Microsoft 365

La Mesa de Servicios se integra con el Microsoft 365 de ADUCORP en tres frentes. Cada uno se enciende por separado en el archivo `.env` del servidor.

| Módulo | Qué hace | Variable |
|---|---|---|
| **Entra ID** | Inicio de sesión único con la cuenta corporativa, MFA, sin contraseñas locales y roles tomados de los grupos de Entra ID | `AUTH_PROVIDER=entra` |
| **Exchange Online** | El buzón compartido `soporte@aducorp.com.ec` crea tickets, recibe respuestas y adjuntos, y envía los avisos | `BUZON_ENABLED=true`, `EMAIL_TRANSPORTE=graph` |
| **Microsoft Teams** | Avisos con tarjetas adaptables en los canales por categoría y botones Aceptar, Escalar y Cambiar estado | `TEAMS_ENABLED=true` |

Los tres usan **una sola aplicación** registrada en Entra ID. Ninguna clave se guarda en el repositorio: van solo en el `.env` del servidor.

## Configuración mínima: solo el correo

Si por ahora solo quiere que los correos a `soporte@` creen tickets y avisen al responsable, el login y Teams quedan como están. Para el correo no hace falta HTTPS ni un dominio público, porque es la Mesa la que consulta el buzón.

1. Cree el buzón compartido `soporte@aducorp.com.ec`, si no existe.
2. Registre la aplicación (sección 2, pasos 1, 2, 4 y 5). Omita la URI de redirección, la notificación de grupos y los permisos de Graph: para el correo no se necesitan.
3. Dé acceso a la aplicación solo a ese buzón con los comandos de la sección 3.
4. Agregue al `.env` del servidor (el secreto lo escribe usted, nunca por chat ni en el repositorio):

```env
M365_TENANT_ID=<Id. de directorio (inquilino)>
M365_CLIENT_ID=<Id. de aplicación (cliente)>
M365_CLIENT_SECRET=<valor del secreto>
BUZON_ENABLED=true
EMAIL_TRANSPORTE=graph
EMAIL_ENABLED=true
```

5. Reinicie con `docker compose up -d`. En **Administración › Configuración** verá el estado del buzón y los últimos correos procesados.
6. Pruebe enviando a `soporte@` un correo con el asunto *Consulta Clasificación Arancelaria*. En un minuto debe aparecer el ticket asignado y llegar el acuse.

## 1. Requisitos

* Un administrador global (o de aplicaciones y de Exchange) de Microsoft 365 para los pasos 2 a 6.
* La Mesa publicada con **HTTPS** en un dominio propio, por ejemplo `https://mesa.aducorp.com.ec` (ver la sección 5 del [manual técnico](07-manual-tecnico.md#5-https)).
* Salida a Internet desde el servidor hacia `login.microsoftonline.com`, `graph.microsoft.com`, `login.botframework.com`, `api.botframework.com` y `smba.trafficmanager.net`.
* Solo para Teams: la ruta `https://mesa.aducorp.com.ec/api/v1/teams/mensajes` debe ser accesible desde Internet, porque Microsoft entrega ahí los clics de los botones. El resto de la Mesa puede quedar solo en la red interna.

## 2. Registrar la aplicación en Entra ID

En el [Centro de administración de Microsoft Entra](https://entra.microsoft.com) › **Identidad › Aplicaciones › Registros de aplicaciones › Nuevo registro**:

1. **Nombre:** `Mesa de Servicios ADUCORP`.
2. **Tipos de cuenta admitidos:** *Solo las cuentas de este directorio organizativo* (un solo inquilino).
3. **URI de redirección:** plataforma *Web*, `https://mesa.aducorp.com.ec/api/v1/auth/entra/callback`.
4. Anote el **Id. de aplicación (cliente)** y el **Id. de directorio (inquilino)**.
5. **Certificados y secretos › Nuevo secreto de cliente**, con vigencia de 12 o 24 meses. Copie el **valor** de inmediato y anote en el calendario de TI la fecha en que vence.
6. **Configuración de token › Agregar notificación de grupos:** marque *Grupos de seguridad* y, en el token de identificador, *Id. de grupo*.
7. **Permisos de API › Agregar un permiso › Microsoft Graph**:

   | Tipo | Permiso | Para qué |
   |---|---|---|
   | Delegado | `openid`, `profile`, `email`, `offline_access`, `User.Read` | Inicio de sesión |
   | Aplicación | `User.Read.All` | Sincronizar nombre, cargo y estado de las cuentas |
   | Aplicación | `GroupMember.Read.All` | Leer los grupos que definen los roles |

   Pulse **Conceder consentimiento de administrador**.

> No agregue aquí `Mail.ReadWrite` ni `Mail.Send`. Un permiso de aplicación concedido en Entra ID vale para **todos** los buzones de la empresa. El acceso al correo se da en el paso 3 y queda limitado al buzón de soporte.

## 3. Buzón compartido soporte@ (Exchange Online)

1. Cree el buzón compartido `soporte@aducorp.com.ec` si aún no existe.
2. En **PowerShell de Exchange Online**, conceda a la aplicación acceso **solo a ese buzón** con RBAC para aplicaciones. El `ObjectId` es el de la *aplicación empresarial* (Entra › Aplicaciones empresariales › Mesa de Servicios ADUCORP), no el del registro:

```powershell
Connect-ExchangeOnline
$app = "<Id. de aplicación (cliente)>"
New-ServicePrincipal -AppId $app -ObjectId "<Id. de objeto de la aplicación empresarial>" -DisplayName "Mesa de Servicios ADUCORP"
New-ManagementScope -Name "Mesa - buzón soporte" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'soporte@aducorp.com.ec'"
New-ManagementRoleAssignment -App $app -Role "Application Mail.ReadWrite" -CustomResourceScope "Mesa - buzón soporte"
New-ManagementRoleAssignment -App $app -Role "Application Mail.Send"      -CustomResourceScope "Mesa - buzón soporte"
# Comprobación: debe decir InScope = True para soporte@ y False para cualquier otro buzón
Test-ServicePrincipalAuthorization -Identity $app -Resource soporte@aducorp.com.ec
```

**Cómo funciona el buzón:**

* Cada minuto, el worker lee los correos **no leídos** de la bandeja de entrada.
* Un correo **sin número de ticket** en el asunto crea un ticket con canal *Correo*:
  * **Categoría:** si el asunto nombra una categoría del catálogo (por ejemplo *Consulta Clasificación Arancelaria* o *Legal Aduanero - multa*), se usa esa. Si no nombra ninguna, la IA la elige por el asunto y el texto, con las palabras clave de cada subcategoría.
  * Se asigna el responsable de esa categoría, que recibe el aviso en la Mesa y el correo `[ADU-2026-000123] Ticket asignado a usted`.
  * Quien escribió recibe el acuse `[ADU-2026-000123] Recibimos su solicitud: …`.
  * Los adjuntos pasan por las mismas validaciones que en la web: extensión, tamaño y contenido.
* Una **respuesta** cuyo asunto conserva el número se agrega al ticket con sus adjuntos. Si el ticket estaba *Pendiente cliente*, el SLA se reanuda.
  * Si el ticket ya estaba cerrado, se abre uno nuevo que cita al anterior.
  * Si quien responde no participa en el ticket, su mensaje queda como nota interna.
* Remitentes:
  * Si el remitente es de `aducorp.com.ec` y aún no existe en la Mesa, se crea como *Cliente interno*.
  * Los remitentes externos quedan bajo la cuenta de sistema *Buzón de soporte*, y su dirección se guarda en el ticket.
* Cuando el equipo comenta un ticket que llegó por correo, el solicitante recibe la respuesta por correo en el mismo hilo.
* No se procesan:
  * las respuestas automáticas (fuera de oficina);
  * los rebotes;
  * los mensajes enviados por el propio buzón.
* Cada mensaje se procesa una sola vez y queda marcado como leído, con la categoría `Mesa ADU-…` en Outlook.
* Con `EMAIL_TRANSPORTE=graph` todos los avisos de la Mesa salen desde `soporte@`, así que las respuestas vuelven al buzón.

## 4. Grupos y roles

Cree en Entra ID un **grupo de seguridad** por rol y anote su **Id. de objeto**:

| Grupo sugerido | Rol en la Mesa |
|---|---|
| `Mesa - Super Administradores` | `SUPER_ADMIN` |
| `Mesa - Administradores` | `ADMIN_MESA` |
| `Mesa - Supervisores` | `SUPERVISOR` |
| `Mesa - Analistas` | `ANALISTA` |
| `Mesa - Gerencia` | `GERENCIA` |

```dotenv
ENTRA_GRUPO_ROLES={"<id grupo super admins>":"SUPER_ADMIN","<id grupo administradores>":"ADMIN_MESA","<id grupo supervisores>":"SUPERVISOR","<id grupo analistas>":"ANALISTA","<id grupo gerencia>":"GERENCIA"}
ENTRA_ROL_DEFECTO=CLIENTE
```

* Si una persona está en varios grupos, recibe el rol de mayor alcance.
* Con `ENTRA_ROL_DEFECTO=CLIENTE`, todo empleado del inquilino puede entrar como *Cliente interno*. Déjelo vacío para que solo entren los miembros de los grupos.
* El rol se actualiza en cada inicio de sesión. Además, el worker sincroniza los grupos cada `ENTRA_SYNC_MINUTOS`:
  * crea las cuentas nuevas;
  * cambia los roles;
  * desactiva en la Mesa a quien fue deshabilitado en Microsoft 365.
* Como alternativa a los grupos, puede definir **Roles de aplicación** en el registro, con los valores `ADMIN_MESA`, `ANALISTA`, etc. Si existen, se usan.
* Los supervisores de cada categoría y los responsables siguen configurándose en **Administración › Categorías**.

## 5. MFA y acceso condicional

* El MFA lo exige **Microsoft Entra**, no la Mesa.
* En **Protección › Acceso condicional**, cree una directiva para la aplicación *Mesa de Servicios ADUCORP* con *Conceder: requerir autenticación multifactor*.
* Con `ENTRA_EXIGIR_MFA=true`, la Mesa además rechaza los tokens que no indiquen MFA en el claim `amr`.

**Sin usuarios locales:**

* Con `AUTH_PROVIDER=entra`, el formulario de contraseña desaparece y el inicio de sesión local queda bloqueado en la API.
* La única excepción son las cuentas de `ENTRA_CUENTAS_EMERGENCIA` (recomendado: una, `admin@aducorp.com.ec`, con una contraseña larga guardada en sobre cerrado). Sirven si Microsoft 365 no está disponible.
* La primera vez que alguien entra con Microsoft, su usuario existente en la Mesa se vincula por correo. A partir de ahí su contraseña local se elimina.

## 6. Microsoft Teams

**Bot de Azure:**

1. En el [portal de Azure](https://portal.azure.com) cree un recurso **Azure Bot**:
   * tipo *Inquilino único*;
   * *Usar registro de aplicación existente*, con el Id. de aplicación y el secreto del paso 2.
2. En **Configuración › Punto de conexión de mensajería** escriba `https://mesa.aducorp.com.ec/api/v1/teams/mensajes`.
3. En **Canales**, agregue **Microsoft Teams**.

**Paquete de la app** (en el equipo de TI, con Python):

```bash
python teams/empaquetar.py --bot-id <Id. de aplicación> --app-url https://mesa.aducorp.com.ec
```

* Genera `teams/mesa-servicios-teams.zip`.
* Súbalo en el [Centro de administración de Teams](https://admin.teams.microsoft.com) › **Aplicaciones de Teams › Administrar aplicaciones › Cargar nueva aplicación**.

**Canales:**

1. Cree el equipo **Mesa de Servicios** con los canales *Mesa de Servicios* (o use *General*), *Clasificación Arancelaria*, *Legal Aduanero*, *FedEx*, *Regímenes Especiales* y *Trámites Aduaneros*.
2. Agregue la app **Mesa ADUCORP** al equipo.
3. En cada canal, un administrador de la Mesa escribe:

| Canal | Mensaje |
|---|---|
| Mesa de Servicios | `@Mesa ADUCORP vincular general` |
| Clasificación Arancelaria | `@Mesa ADUCORP vincular Clasificación Arancelaria` |
| Legal Aduanero | `@Mesa ADUCORP vincular Legal Aduanero` |
| FedEx | `@Mesa ADUCORP vincular Consultas FedEx` |
| Regímenes Especiales | `@Mesa ADUCORP vincular Regímenes Especiales` |
| Trámites Aduaneros | `@Mesa ADUCORP vincular Trámites Aduaneros` |

El nombre después de «vincular» es el de la categoría en la Mesa. `desvincular` detiene los avisos del canal. El estado de los canales se ve en **Administración › Configuración › Microsoft 365**.

**Avisos:**

* Se publican en el canal general y en el de la categoría.
* Eventos: nuevo ticket, asignado, escalado, SLA 75 %, SLA 90 %, SLA vencido y cerrado. Se pueden limitar con `TEAMS_EVENTOS`.
* La tarjeta muestra el ticket, la prioridad, el cliente, el responsable, el estado y el SLA restante en horas laborables.

**Acciones desde Teams:**

* **Aceptar:** el analista toma un ticket sin responsable de su categoría, o uno que ya tiene, y lo pasa a *En proceso*. El supervisor y el coordinador pueden aceptar cualquiera.
* **Escalar:** pide el motivo y avisa al supervisor.
* **Cambiar estado:** permite elegir *En proceso*, *Pendiente cliente* (pausa el SLA), *Resuelto* o *Cerrado*, con un comentario para el solicitante.

Cada acción se ejecuta con los permisos del usuario de la Mesa vinculado a la cuenta de Teams y queda en el historial y la auditoría. La cuenta se vincula sola la primera vez que la persona entra a la Mesa con Microsoft. La tarjeta se actualiza en el momento con el resultado o con el motivo del rechazo.

## 7. Variables del .env

```dotenv
# Aplicación registrada en Entra ID
M365_TENANT_ID=<Id. de directorio>
M365_CLIENT_ID=<Id. de aplicación>
M365_CLIENT_SECRET=<valor del secreto>

# Entra ID
AUTH_PROVIDER=entra
ENTRA_GRUPO_ROLES={"<id grupo>":"ADMIN_MESA","<id grupo>":"ANALISTA"}
ENTRA_ROL_DEFECTO=CLIENTE
ENTRA_EXIGIR_MFA=false
ENTRA_CUENTAS_EMERGENCIA=["admin@aducorp.com.ec"]
ENTRA_SYNC_MINUTOS=60

# Exchange Online
BUZON_ENABLED=true
BUZON_CORREO=soporte@aducorp.com.ec
BUZON_DOMINIOS_INTERNOS=["aducorp.com.ec"]
EMAIL_ENABLED=true
EMAIL_TRANSPORTE=graph

# Teams
TEAMS_ENABLED=true
```

Aplique con `docker compose up -d`. El script de base de datos `07_microsoft365.sql` se ejecuta solo al arrancar.

Recomendación de puesta en marcha:

1. Active primero Teams y el buzón, y pruebe con un correo a `soporte@`.
2. Luego active Entra ID con `ENTRA_CUENTAS_EMERGENCIA` definido.
3. Cuando todos hayan ingresado al menos una vez con Microsoft, retire las contraseñas locales que ya no se usen.

## 8. Solución de problemas

| Síntoma | Causa probable |
|---|---|
| «Microsoft no completó el inicio de sesión» | La URI de redirección del registro no coincide exactamente con `APP_URL` + `/api/v1/auth/entra/callback` |
| «Su cuenta no pertenece a ningún grupo autorizado» | `ENTRA_ROL_DEFECTO` vacío y la persona no está en ningún grupo de `ENTRA_GRUPO_ROLES` |
| El rol no cambia | Falta la notificación de grupos en el token (paso 2.6) o el Id. del grupo está mal copiado |
| El worker registra `Graph GET … 403` en el ciclo `buzon` | Falta el paso 3 o aún no se propagó; verifique con `Test-ServicePrincipalAuthorization` |
| Los correos no crean tickets | `BUZON_ENABLED=false`, o el correo ya estaba leído cuando llegó el worker |
| No llegan avisos a Teams | El canal no está vinculado; revise **Configuración › Microsoft 365** y el ciclo `teams` del worker |
| Los botones de Teams dan error | El punto de conexión `/api/v1/teams/mensajes` no es accesible desde Internet o el Id. del bot no coincide con `M365_CLIENT_ID` |
| «Su cuenta de Teams no está vinculada» | La persona aún no entró a la Mesa con «Iniciar sesión con Microsoft» |
