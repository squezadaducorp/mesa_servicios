/* =====================================================================
   Personas en copia (CC) de los tickets. Idempotente.
   - ticket_copias: lista editable por ticket
   - ticket_comentarios.copia_a: a quién se copió cada respuesta (trazabilidad)
   - categorias / clientes .correos_copia: copia automática al crear tickets
   - plantilla RESPUESTA_COPIA: aviso a las copias cuando el solicitante no recibe correo
   ===================================================================== */
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.ticket_copias', N'U') IS NULL
CREATE TABLE dbo.ticket_copias (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_copias PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_copias_ticket REFERENCES dbo.tickets(id),
    correo          NVARCHAR(150) NOT NULL,
    origen          VARCHAR(12) NOT NULL CONSTRAINT df_copias_origen DEFAULT ('MANUAL'),   -- MANUAL | CATEGORIA | CLIENTE | CORREO
    agregado_por    INT NULL CONSTRAINT fk_copias_usuario REFERENCES dbo.usuarios(id),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_copias_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT ux_ticket_copias UNIQUE (ticket_id, correo)
);
GO

IF COL_LENGTH(N'dbo.ticket_comentarios', N'copia_a') IS NULL
    ALTER TABLE dbo.ticket_comentarios ADD copia_a NVARCHAR(500) NULL;
GO
IF COL_LENGTH(N'dbo.categorias', N'correos_copia') IS NULL
    ALTER TABLE dbo.categorias ADD correos_copia NVARCHAR(500) NULL;
GO
IF COL_LENGTH(N'dbo.clientes', N'correos_copia') IS NULL
    ALTER TABLE dbo.clientes ADD correos_copia NVARCHAR(500) NULL;
GO

MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('RESPUESTA_COPIA', N'[{numero}] Respuesta: {asunto}',
        N'<p>Hola,</p><p><b>{autor}</b> respondió al ticket <b>{numero}</b> «{asunto}» de {solicitante}:</p><div style="white-space:pre-line;border-left:3px solid #70A9CE;padding:8px 12px;background:#F4F6FA">{comentario}</div><p>Estado actual: <b>{estado}</b></p><p>Recibe este correo porque está en copia del ticket.</p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

PRINT N'09_copias_correo aplicado';
GO
