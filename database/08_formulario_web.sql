/* =====================================================================
   Formulario público de solicitudes (/solicitud): plantillas de correo
   para personas sin cuenta en la Mesa. Idempotente.
   ===================================================================== */
SET NOCOUNT ON;
GO

MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('ACUSE_WEB', N'[{numero}] Recibimos su solicitud: {asunto}',
        N'<p>Hola {destinatario},</p><p>Recibimos su solicitud y registramos el ticket <b>{numero}</b> «{asunto}».</p><p>Categoría: <b>{categoria}</b><br>Prioridad: <b>{prioridad}</b><br>Responsable: <b>{responsable}</b></p><p>Resolución comprometida: {sla_resolucion_vence}</p><p>Le escribiremos a este correo con las novedades. Si necesita agregar información, registre una nueva solicitud en <a href="{url}">{url}</a> indicando el número <b>{numero}</b>.</p>'),
    ('RESPUESTA_WEB', N'[{numero}] Respuesta: {asunto}',
        N'<p>Hola {destinatario},</p><p><b>{autor}</b> respondió a su solicitud <b>{numero}</b> «{asunto}»:</p><div style="white-space:pre-line;border-left:3px solid #70A9CE;padding:8px 12px;background:#F4F6FA">{comentario}</div><p>Estado actual: <b>{estado}</b></p><p>Si necesita agregar información, registre una nueva solicitud en <a href="{url}">{url}</a> indicando el número <b>{numero}</b>.</p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

PRINT N'08_formulario_web aplicado';
GO
