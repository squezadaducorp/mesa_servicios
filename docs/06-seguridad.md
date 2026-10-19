# Fase 6 – Seguridad

Mesa de Servicios ADUCORP · versión 1.0

Este documento describe los controles de seguridad de la plataforma, cómo configurarlos en
producción y la lista de verificación previa a la puesta en marcha. Las pruebas automáticas
de estos controles están en `backend/tests/test_seguridad.py` (10 casos) y `backend/tests/test_api.py`.

---

## 1. Modelo de amenazas resumido

| Activo | Amenaza principal | Control |
|---|---|---|
| Datos de clientes y trámites aduaneros | Acceso de usuarios a tickets ajenos | RBAC + alcance de datos por rol validado en el servidor en cada consulta |
| Credenciales | Fuerza bruta, robo de token | Bloqueo por intentos, límite por IP, JWT de 15 min, refresh rotativo con detección de reutilización |
| Adjuntos (DAI, facturas, poderes) | Malware, XSS por archivo, path traversal | Lista blanca de extensiones, verificación de firma, nombres aleatorios en disco, descarga forzada |
| Indicadores de SLA | Manipulación de tiempos o borrado de evidencia | Auditoría inmutable (trigger), historial por ticket, borrado solo lógico |
| Exportaciones | Inyección de fórmulas en Excel/CSV | Celdas que empiezan con `= + - @` se neutralizan |
| Infraestructura | Exposición de la base de datos, secretos en el código | SQL Server sin puerto público, login de aplicación con mínimo privilegio, secretos por variables de entorno |

## 2. Controles según OWASP Top 10 (2021)

| OWASP | Riesgo | Implementación |
|---|---|---|
| A01 Control de acceso | Acceso a datos o acciones no autorizadas | Dependencia `requiere()` por endpoint; `TicketService.acciones()` decide qué puede hacer cada usuario sobre cada ticket; `filtro_visibilidad` limita las consultas por rol. El frontend solo oculta botones: la API vuelve a validar todo. |
| A02 Fallas criptográficas | Contraseñas o tokens expuestos | bcrypt (factor 12) para contraseñas; refresh tokens guardados como SHA-256; TLS 1.2/1.3 con HSTS en Nginx. |
| A03 Inyección | SQL, fórmulas | SQLAlchemy con parámetros; procedimientos con parámetros tipados; neutralización de fórmulas en exportaciones. |
| A04 Diseño inseguro | Reglas de negocio eludibles | Transiciones de estado validadas en el dominio (`app/domain/reglas.py`); control de concurrencia optimista (`version`, HTTP 409). |
| A05 Configuración | Valores por defecto inseguros | La API no arranca en `APP_ENV=production` con el `JWT_SECRET` de ejemplo o con SQLite; cabeceras de seguridad en API y Nginx; Swagger desactivable (`DOCS_ENABLED=false`). |
| A06 Componentes vulnerables | Dependencias con CVE | Versiones fijadas en `requirements.txt` y `package-lock.json`; `pip-audit` y `npm audit` en CI (Fase 7). |
| A07 Autenticación | Fuerza bruta, sesiones eternas | Bloqueo 15 min tras 5 intentos fallidos; 10 intentos por IP y minuto (API) y `limit_req` en Nginx; política de contraseñas; cambio obligatorio en el primer ingreso; revocación de sesiones al cambiar contraseña. |
| A08 Integridad | Tokens alterados, archivos falsos | JWT firmado HS256 (se rechaza `alg: none`); hash SHA-256 de cada adjunto guardado en la BD. |
| A09 Registro y monitoreo | Falta de trazabilidad | Auditoría de login, logout, fallos, cambios, exportaciones, SLA y roles con usuario, fecha, hora, IP y equipo; `X-Request-ID` en cada respuesta y en el log. |
| A10 SSRF | Llamadas a servidores internos | La API no descarga URLs proporcionadas por usuarios; las únicas salidas son SMTP, LDAP y (opcional) la API de Anthropic, configuradas por el administrador. |

## 3. Autenticación y sesiones

| Parámetro | Valor | Variable |
|---|---|---|
| Access token (JWT HS256) | 15 minutos | `ACCESS_TOKEN_MINUTES` |
| Refresh token (opaco, rotativo) | 7 días | `REFRESH_TOKEN_DAYS` |
| Intentos fallidos antes de bloquear | 5 | *Configuración* › `seguridad.max_intentos` (respaldo: `MAX_LOGIN_INTENTOS`) |
| Duración del bloqueo | 15 minutos | *Configuración* › `seguridad.bloqueo_min` (respaldo: `BLOQUEO_MINUTOS`) |
| Intentos de login por IP y minuto | 10 (API) + 10/min con ráfaga 5 (Nginx) | `LOGIN_MAX_POR_MINUTO` |
| Longitud mínima de contraseña | 10, con mayúscula, minúscula, número y símbolo | `CLAVE_MIN_LONGITUD` |

* **Rotación con detección de reutilización:** cada uso del refresh token emite uno nuevo y
  revoca el anterior. Si alguien presenta un token ya usado (posible robo), se revoca toda la
  familia de sesiones de ese dispositivo y se registra en la auditoría.
* **Desactivación inmediata:** en cada solicitud se verifica que el usuario siga activo y no
  bloqueado, y los permisos se leen de la base de datos; un cambio de rol aplica al instante.
* **Cambio de contraseña:** revoca todas las demás sesiones del usuario.
* **Almacenamiento en el navegador:** el access token vive solo en memoria; el refresh token se
  guarda en `localStorage` para mantener la sesión al recargar. La CSP estricta (`script-src 'self'`)
  reduce el riesgo de XSS. Si la política interna lo exige, el refresh puede moverse a una cookie
  `HttpOnly; Secure; SameSite=Strict` sin cambiar el resto del diseño.

## 4. Integración con Active Directory

> Para Microsoft Entra ID (SSO con MFA y roles por grupos) vea [10-microsoft-365.md](10-microsoft-365.md). Allí el flujo es OIDC con PKCE, el `id_token` se valida contra las claves del tenant y no se guardan contraseñas en la Mesa.

La autenticación contra AD se activa con variables de entorno, sin cambiar código:

```env
AUTH_PROVIDER=ldap
LDAP_URL=ldaps://dc01.aducorp.local:636
LDAP_DOMINIO=ADUCORP
LDAP_BASE_DN=DC=aducorp,DC=local
LDAP_USUARIO_SERVICIO=svc_mesa
LDAP_CLAVE_SERVICIO=********
LDAP_CREAR_USUARIOS=true
LDAP_GRUPO_ROLES={"CN=Mesa-Administradores,OU=Grupos,DC=aducorp,DC=local":"ADMIN_MESA","CN=Mesa-Supervisores,OU=Grupos,DC=aducorp,DC=local":"SUPERVISOR","CN=Mesa-Analistas,OU=Grupos,DC=aducorp,DC=local":"ANALISTA","CN=Gerencia,OU=Grupos,DC=aducorp,DC=local":"GERENCIA"}
```

Pasos:

1. Crear en AD la cuenta de servicio `svc_mesa` (solo lectura del directorio, sin inicio de sesión interactivo).
2. Crear los grupos de seguridad de la mesa y asignar usuarios.
3. Usar **LDAPS (636)** e importar la CA interna en la imagen de la API si el certificado no es público.
4. Los usuarios inician sesión con `ADUCORP\usuario`, `usuario` o su correo. La contraseña se valida
   contra AD y nunca se guarda en la mesa.
5. En el primer ingreso se crea el usuario con rol **Cliente Interno**, salvo que pertenezca a un
   grupo mapeado en `LDAP_GRUPO_ROLES`. En cada ingreso se sincronizan nombre, cargo y rol (si pertenece a un grupo mapeado).
6. Los usuarios locales (por ejemplo `admin@`) siguen funcionando como cuenta de emergencia si el
   controlador de dominio no responde.
7. Desactivar a un usuario en AD impide su ingreso; para cortar una sesión abierta al instante,
   desactívelo también en **Administración → Usuarios**.

## 5. Control de acceso (RBAC)

### Matriz de permisos inicial

| Permiso | Super Admin | Admin Mesa | Supervisor | Analista | Cliente Interno | Gerencia |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| sistema.administrar | ✔ | | | | | |
| usuario.administrar | ✔ | | | | | |
| rol.administrar | ✔ | | | | | |
| categoria.administrar | ✔ | | | | | |
| sla.modificar | ✔ | ✔ | | | | |
| ticket.ver_todos | ✔ | ✔ | | | | ✔ |
| ticket.ver_area | ✔ | ✔ | ✔ | | | |
| ticket.ver_asignados | ✔ | ✔ | ✔ | ✔ | | |
| ticket.ver_propios | ✔ | ✔ | ✔ | ✔ | ✔ | |
| ticket.crear | ✔ | ✔ | ✔ | ✔ | ✔ | |
| ticket.editar | ✔ | ✔ | ✔ | ✔ | | |
| ticket.asignar | ✔ | ✔ | ✔ | | | |
| ticket.escalar | ✔ | ✔ | ✔ | ✔ | | |
| ticket.cambiar_estado | ✔ | ✔ | ✔ | ✔ | | |
| ticket.cerrar | ✔ | ✔ | ✔ | ✔ | | |
| ticket.reabrir | ✔ | ✔ | ✔ | | ✔ | |
| ticket.comentar | ✔ | ✔ | ✔ | ✔ | ✔ | |
| ticket.adjuntar | ✔ | ✔ | ✔ | ✔ | ✔ | |
| registro.eliminar | ✔ | | | | | |
| reporte.ver | ✔ | ✔ | ✔ | | | ✔ |
| dashboard.ver | ✔ | ✔ | ✔ | | | ✔ |
| datos.exportar | ✔ | ✔ | | | | ✔ |
| auditoria.ver | ✔ | | | | | |
| ia.usar | ✔ | ✔ | ✔ | ✔ | | |

La matriz se edita en **Administración → Roles y permisos**. El Super Administrador no puede
perder permisos, y cada cambio queda auditado con el antes y el después.

### Alcance de los datos

| Permiso de lectura | Qué tickets ve |
|---|---|
| `ticket.ver_todos` | Todos |
| `ticket.ver_area` | Los de las categorías donde es supervisor |
| `ticket.ver_asignados` | Los que tiene asignados |
| `ticket.ver_propios` | Los que creó |

Los permisos se suman. Por ejemplo, un supervisor ve su área, lo que tiene asignado y lo que creó.
Indicadores, dashboard y exportaciones aplican el mismo alcance.

Las notas internas nunca se muestran al solicitante, y un cliente interno no puede ver, comentar ni
adjuntar en tickets de otra persona.

## 6. Auditoría

* **Eventos registrados:** login, login fallido, logout, refresh reutilizado, creación y edición de
  tickets, cambios de estado, asignación, escalamiento, cierre, reapertura, comentarios, subida y
  descarga de adjuntos, exportaciones, cambios de SLA, horario o calendario, cambios de rol o
  permisos, usuarios, catálogo y configuración.
* **Datos de cada registro:** usuario, fecha y hora (UTC; se muestran en hora de Ecuador), acción,
  entidad, detalle en JSON, IP, equipo (User-Agent o cabecera `X-Equipo`) y resultado (OK o ERROR).
* **Inmutabilidad:** el trigger `tr_auditoria_inmutable` bloquea `UPDATE` y `DELETE` sobre
  `dbo.auditoria`, incluso para el login de la aplicación. Además, `tr_tickets_sin_borrado_fisico`
  impide borrar tickets físicamente.
* **IP real:** la API solo acepta `X-Real-IP` y `X-Forwarded-For` cuando la conexión viene de un
  proxy confiable (`TRUSTED_PROXIES`, por defecto las redes privadas de Docker). Nginx sobrescribe
  esas cabeceras con la IP del cliente, así que no se pueden falsificar desde el navegador.
* **Retención:** `sp_Mantenimiento` depura notificaciones leídas y la cola de correos enviados.
  La auditoría no se depura: archívela por año si crece demasiado. Recomendación: 5 años, en línea
  con la conservación de documentos aduaneros.

## 7. Adjuntos

1. **Lista blanca de extensiones**, configurable en `adjuntos.extensiones`.
2. **Tamaño máximo:** `adjuntos.max_mb` (20 MB), más `client_max_body_size 25m` en Nginx.
3. **Verificación de firma (magic bytes):** un `.pdf` debe empezar con `%PDF`, una imagen con su
   cabecera y un `.docx` o `.xlsx` con la de ZIP. Los ejecutables (`MZ`, `ELF`, Mach-O) y los scripts
   (`#!`) se rechazan aunque se les cambie la extensión. Cada rechazo queda auditado.
4. **En disco:** nombre aleatorio (UUID) en carpetas por año y mes, fuera de la raíz web, con
   comprobación contra path traversal. Se guarda además el hash SHA-256 en la base de datos.
5. **Descarga:** siempre como `attachment`. El tipo MIME se limita a una lista segura (lo demás se
   sirve como `application/octet-stream`) y se envía `nosniff`. Así un HTML subido como `.txt` no se
   ejecuta en el navegador.
6. **Antivirus (recomendado):** monte el volumen de adjuntos en un servidor con antivirus de
   escaneo en acceso, o agregue un contenedor ClamAV. El punto de integración es `AlmacenamientoLocal.guardar`.

## 8. Transporte y cabeceras

* **Nginx en modo HTTPS** (`frontend/nginx/https.conf`): TLS 1.2 y 1.3, HTTP/2, HSTS de un año y
  redirección de 80 a 443.
* **Certificados:** monte `mesa.crt` (con la cadena) y `mesa.key` en `/etc/nginx/certs`. Use la CA
  interna de ADUCORP o un certificado público si el sitio se publica a internet.
* **Cabeceras del frontend:** CSP `default-src 'self'` sin scripts en línea, `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy` y `Permissions-Policy`.
* **Cabeceras de la API:** CSP `default-src 'none'`, `Cache-Control: no-store`, HSTS en producción
  y `X-Request-ID`.
* **CORS:** solo los orígenes de `CORS_ORIGINS`. Con el despliegue estándar (mismo dominio vía
  `/api`) CORS no se usa.

## 9. Base de datos

* **SQL Server sin publicar:** en Docker Compose de producción solo está en la red interna, sin
  puerto 1433 expuesto.
* **Login de aplicación `mesa_app`:** solo `db_datareader`, `db_datawriter` y `EXECUTE`. No puede
  crear, alterar ni borrar objetos, y los triggers protegen la auditoría. El usuario `sa` solo se
  usa para instalar y actualizar.
* **Cifrado (recomendado):** active TDE en SQL Server 2022 Standard o Enterprise, o cifre el
  volumen donde viven los datos.
* **Respaldos:** copia completa diaria y de log cada 15 minutos (modelo FULL). Pruebe la
  restauración cada mes y guarde una copia fuera del servidor. El procedimiento está en el manual
  del administrador (Fase 7).
* **Aislamiento de lecturas:** `READ_COMMITTED_SNAPSHOT` evita que los reportes bloqueen la
  operación diaria.

## 10. Secretos

* Ningún secreto está en el código. Todo se configura en `.env`, que no se versiona; las
  plantillas son `.env.example`.
* **Generar `JWT_SECRET`:** `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
  Cambiarlo invalida todas las sesiones.
* **Rotación sugerida:** `JWT_SECRET` y la contraseña de `mesa_app` cada 6 meses, y la de `svc_mesa`
  según la política de AD.
* **CI/CD:** los secretos de GitHub Actions se guardan en *Settings → Secrets*, nunca en el workflow.

## 11. Inteligencia artificial y privacidad

* **`AI_PROVIDER=local` (por defecto):** la clasificación, la prioridad, las respuestas, los
  resúmenes y el riesgo se calculan dentro del servidor. Ningún dato sale de la red.
* **`AI_PROVIDER=llm`:** el asunto, la descripción, los nombres del solicitante y del cliente y hasta los 10 últimos comentarios del ticket se envían a
  la API de Anthropic (Claude) por HTTPS. Antes de activarlo:
  * evalúe la cláusula de confidencialidad con los clientes
  * use una API key de la organización
  * limite la salida a internet del contenedor `api` a `api.anthropic.com`
* **Si la IA falla:** el sistema vuelve automáticamente al motor local. Cada sugerencia queda
  guardada en `ia_sugerencias` con el proveedor que la generó.

## 12. Lista de verificación previa a producción

| # | Verificación | Responsable |
|---|---|---|
| 1 | `APP_ENV=production` y `JWT_SECRET` aleatorio de 64 caracteres | TI |
| 2 | Contraseñas fuertes para `sa` y `mesa_app`, distintas entre sí | TI / DBA |
| 3 | Certificado TLS instalado y Nginx en modo `https.conf` | TI |
| 4 | Puerto 1433 no expuesto fuera del servidor | TI |
| 5 | `CORS_ORIGINS` y `APP_URL` con el dominio real | TI |
| 6 | SMTP con cuenta dedicada y `EMAIL_ENABLED=true` | TI |
| 7 | Cambiar la contraseña de `admin@aducorp.com.ec` en el primer ingreso (se exige automáticamente) | Administrador |
| 8 | Desactivar los usuarios demo que no correspondan a personas reales | Administrador |
| 9 | No ejecutar `06_datos_demo.sql` en producción | DBA |
| 10 | Revisar la matriz de roles con Gerencia | Administrador |
| 11 | Confirmar los feriados del año en **SLA y calendario** | Mesa de Servicios |
| 12 | Respaldos programados y prueba de restauración | DBA |
| 13 | `DOCS_ENABLED=false` si Swagger no debe estar disponible para todos | TI |
| 14 | Decidir `AI_PROVIDER` (local o llm) con el área legal | Gerencia |
| 15 | Escaneo de dependencias del CI en verde (`pip-audit`, `npm audit`) | TI |

## 13. Respuesta a incidentes (básico)

1. **Cuenta comprometida:** desactive al usuario (Administración → Usuarios). Sus sesiones dejan de
   funcionar en la siguiente solicitud. Genere una contraseña temporal y revise la auditoría
   filtrando por usuario.
2. **Sospecha de robo de tokens masivo:** cambie `JWT_SECRET` y reinicie la API. Todas las sesiones
   se cierran.
3. **Evidencia:** exporte la auditoría del período a Excel desde Administración → Auditoría. Los
   registros no pueden alterarse desde la aplicación.
