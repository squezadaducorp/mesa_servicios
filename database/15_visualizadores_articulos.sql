/* =====================================================================
   Quinta ronda (34 y 35). Idempotente (se ejecuta en cada arranque vía db-init). No borra datos.
   34. Visualizadores del ticket: ticket_visualizadores y categorias.visualizadores (los que siguen cada ticket nuevo).
   35. Artículos internos/externos: kb_articulos.visibilidad pasa de TODOS|MESA a EXTERNO|INTERNO,
       kb_articulos.articulo_relacionado_id y la marca usuarios.equipo_ti.
       La primera vez se marca como Equipo de TI a SUPER_ADMIN, ADMIN_MESA, SUPERVISOR y a quien es responsable
       o supervisor de alguna categoría. Después se ajusta en Administración › Usuarios (la migración no la vuelve a tocar).
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 34. Visualizadores ---------------- */
IF OBJECT_ID(N'dbo.ticket_visualizadores', N'U') IS NULL
CREATE TABLE dbo.ticket_visualizadores (
    id             BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_visualizadores PRIMARY KEY,
    ticket_id      BIGINT NOT NULL CONSTRAINT fk_ticketvis_ticket REFERENCES dbo.tickets(id),
    usuario_id     INT NOT NULL CONSTRAINT fk_ticketvis_usuario REFERENCES dbo.usuarios(id),
    avisos_correo  VARCHAR(10) NOT NULL CONSTRAINT df_ticketvis_avisos DEFAULT ('ESTADO')
                   CONSTRAINT ck_ticketvis_avisos CHECK (avisos_correo IN ('TODO','ESTADO','NINGUNO')),
    origen         VARCHAR(10) NOT NULL CONSTRAINT df_ticketvis_origen DEFAULT ('MANUAL')
                   CONSTRAINT ck_ticketvis_origen CHECK (origen IN ('MANUAL','SEGUIR','CATEGORIA')),
    agregado_por   INT NULL CONSTRAINT fk_ticketvis_agregado REFERENCES dbo.usuarios(id),
    fecha          DATETIME2(0) NOT NULL CONSTRAINT df_ticketvis_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT uq_ticket_visualizadores UNIQUE (ticket_id, usuario_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_ticketvis_usuario')
    CREATE INDEX ix_ticketvis_usuario ON dbo.ticket_visualizadores(usuario_id);
GO
IF COL_LENGTH(N'dbo.categorias', N'visualizadores') IS NULL
    ALTER TABLE dbo.categorias ADD visualizadores VARCHAR(300) NULL;
GO

/* ---------------- 35. Equipo de TI ---------------- */
IF COL_LENGTH(N'dbo.usuarios', N'equipo_ti') IS NULL
BEGIN
    ALTER TABLE dbo.usuarios ADD equipo_ti BIT NOT NULL CONSTRAINT df_usuarios_equipo_ti DEFAULT (0);
    -- Solo la primera vez: roles de gestión de la mesa y responsables o supervisores de alguna categoría
    EXEC (N'UPDATE u SET equipo_ti = 1
            FROM dbo.usuarios u
            JOIN dbo.roles r ON r.id = u.rol_id
            WHERE r.codigo IN (''SUPER_ADMIN'', ''ADMIN_MESA'', ''SUPERVISOR'')
               OR u.id IN (SELECT usuario_id FROM dbo.categoria_responsables)
               OR u.id IN (SELECT supervisor_id FROM dbo.categorias WHERE supervisor_id IS NOT NULL);');
END
GO

/* ---------------- 35. Artículos internos / externos ---------------- */
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'ck_kb_visibilidad'
           AND definition LIKE N'%MESA%')
    ALTER TABLE dbo.kb_articulos DROP CONSTRAINT ck_kb_visibilidad;
GO
UPDATE dbo.kb_articulos SET visibilidad = 'EXTERNO' WHERE visibilidad = 'TODOS';
UPDATE dbo.kb_articulos SET visibilidad = 'INTERNO' WHERE visibilidad = 'MESA';
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'ck_kb_visibilidad')
    ALTER TABLE dbo.kb_articulos ADD CONSTRAINT ck_kb_visibilidad CHECK (visibilidad IN ('EXTERNO','INTERNO'));
GO
IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = N'df_kb_visibilidad' AND definition LIKE N'%TODOS%')
    ALTER TABLE dbo.kb_articulos DROP CONSTRAINT df_kb_visibilidad;
GO
IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = N'df_kb_visibilidad')
    ALTER TABLE dbo.kb_articulos ADD CONSTRAINT df_kb_visibilidad DEFAULT ('EXTERNO') FOR visibilidad;
GO
IF COL_LENGTH(N'dbo.kb_articulos', N'articulo_relacionado_id') IS NULL
    ALTER TABLE dbo.kb_articulos ADD articulo_relacionado_id INT NULL
        CONSTRAINT fk_kb_relacionado REFERENCES dbo.kb_articulos(id);
GO

/* ---------------- Plantilla de correo ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('TICKET_VISUALIZADOR', N'[{numero}] Novedad en un ticket que sigue',
        N'<p>Hola {destinatario},</p><p>Hay una novedad en <b>{numero}</b> «{asunto}», que usted sigue como visualizador:</p><p>{novedad}</p><p>Estado actual: <b>{estado}</b> · lo atiende {responsable}.</p><p><a href="{url}">Ver el ticket</a></p><p style="font-size:12px;color:#5A6577">Puede cambiar qué avisos recibe por correo, o dejar de seguir el ticket, desde el propio ticket.</p>')
) AS s (codigo, asunto, cuerpo)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (s.codigo, s.asunto, s.cuerpo);
GO
PRINT N'15_visualizadores_articulos.sql aplicado';
GO
