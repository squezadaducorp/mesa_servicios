# Formulario público y enlace desde el sitio web

## Enlaces

| Para quién | Enlace | Qué pasa |
|---|---|---|
| Personal de ADUCORP (tiene cuenta) | `https://mesa.aducorp.com.ec/tickets/nuevo` | Si no ha iniciado sesión, pasa por el login (y por el cambio de contraseña obligatorio, si toca) y luego abre directo «Nuevo ticket». |
| Clientes y personas externas (sin cuenta) | `https://mesa.aducorp.com.ec/solicitud` | Formulario público: nombre, correo, empresa, teléfono, asunto y descripción. El tipo de solicitud es opcional; si lo dejan en blanco, la Mesa lo clasifica con la IA. |

La pantalla de login muestra además «¿No tiene cuenta? Registre su solicitud aquí», y el formulario público tiene «¿Trabaja en ADUCORP? Ingrese con su cuenta».

## Cómo queda el ticket

* Canal **WEB**. El solicitante es la cuenta técnica `formulario-web@aducorp.com.ec` (sin contraseña, no puede ingresar); el nombre real de la persona queda en el ticket y su correo, empresa y teléfono, en la descripción.
* Se asigna el responsable de la categoría como cualquier ticket (le llega el aviso «Ticket asignado» si el correo está activo).
* Correos a la persona externa (requieren `EMAIL_ENABLED=true`): acuse con el número (`ACUSE_WEB`), cada respuesta no interna del equipo (`RESPUESTA_WEB`) y el cierre. Los enlaces de esos correos llevan al formulario, no al ticket, porque la persona no tiene cuenta. Las notas internas nunca se envían.
* No admite adjuntos; si hacen falta, el responsable los pide por correo.

## Protección contra abuso

* Ficha firmada que entrega `GET /api/v1/publico/formulario`: se rechaza si el formulario se envía en menos de 4 segundos (robots) o después de 2 horas.
* Campo trampa oculto.
* Máximo `FORMULARIO_WEB_MAX_POR_HORA` solicitudes (5 por defecto) por IP y por correo en una hora, más el límite de Nginx de 10 por minuto por IP.
* Para apagarlo: `FORMULARIO_WEB_ENABLED=false` en `.env` y `docker compose up -d api`.

## Botón del sitio web (cPanel)

Cambie el enlace del botón «MESA DE SERVICIOS» por uno de los dos enlaces de arriba. En WordPress: Páginas → editar la página → seleccionar el botón → campo Enlace/URL. En el Administrador de archivos de cPanel (sitio en HTML): editar el archivo de la página y reemplazar el `href` del botón.
