/* =====================================================================
   Acuse de creación con enlace de seguimiento para todos los solicitantes.
   Idempotente (se ejecuta en cada arranque vía db-init). No borra datos.
   Cambia el asunto y el texto de la plantilla TICKET_CREADO a «Recibimos su solicitud»
   solo si sigue igual a la original (si un administrador ya la editó, se respeta).
   El botón «Ver el estado de mi solicitud» lo agrega la aplicación al enviar.
   ===================================================================== */
SET NOCOUNT ON;
GO

UPDATE dbo.plantillas_correo
   SET asunto = N'[{numero}] Recibimos su solicitud: {asunto}',
       cuerpo_html = N'<p>Hola {destinatario},</p><p>Recibimos su solicitud y la registramos con el número <b>{numero}</b> «{asunto}» en la categoría <b>{categoria}</b>, prioridad <b>{prioridad}</b>.</p><p>Primera respuesta comprometida: {sla_respuesta_vence}<br>Resolución comprometida: {sla_resolucion_vence}</p><p>Con el botón de abajo puede ver en qué va su solicitud, quién la atiende, responder y adjuntar documentos sin usuario ni contraseña. También puede <a href="{url}">abrirla en la Mesa de Servicios</a>.</p>'
 WHERE codigo = 'TICKET_CREADO'
   AND asunto = N'[{numero}] Ticket creado: {asunto}'
   AND CAST(cuerpo_html AS NVARCHAR(MAX)) = N'<p>Hola {destinatario},</p><p>Se registró el ticket <b>{numero}</b> «{asunto}» en la categoría <b>{categoria}</b> con prioridad <b>{prioridad}</b>.</p><p>Primera respuesta comprometida: {sla_respuesta_vence}<br>Resolución comprometida: {sla_resolucion_vence}</p><p><a href="{url}">Ver ticket</a></p>';
GO
