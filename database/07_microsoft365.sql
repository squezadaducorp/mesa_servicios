/* =====================================================================
   Mesa de Servicios ADUCORP
   07 · Integración con Microsoft 365 (Entra ID, Exchange Online, Teams)
   Idempotente: se ejecuta en instalaciones nuevas y existentes.
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
GO

/* ---------------------------------------------------------------------
   Usuarios: identidad de Entra ID
   --------------------------------------------------------------------- */
IF COL_LENGTH(N'dbo.usuarios', N'entra_oid') IS NULL
    ALTER TABLE dbo.usuarios ADD entra_oid VARCHAR(36) NULL;   -- objectId del usuario en Entra ID
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ux_usuarios_entra_oid')
    CREATE UNIQUE INDEX ux_usuarios_entra_oid ON dbo.usuarios(entra_oid) WHERE entra_oid IS NOT NULL;
GO
-- Origen de autenticación: se agrega ENTRA
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'ck_usuarios_origen'
           AND definition NOT LIKE N'%ENTRA%')
    ALTER TABLE dbo.usuarios DROP CONSTRAINT ck_usuarios_origen;
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'ck_usuarios_origen')
    ALTER TABLE dbo.usuarios ADD CONSTRAINT ck_usuarios_origen CHECK (origen_autenticacion IN ('LOCAL','AD','ENTRA'));
GO

/* ---------------------------------------------------------------------
   Exchange Online: mensajes del buzón compartido ya procesados
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.correos_entrantes', N'U') IS NULL
CREATE TABLE dbo.correos_entrantes (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_correos_entrantes PRIMARY KEY,
    message_id       VARCHAR(300)   NOT NULL CONSTRAINT uq_correos_entrantes_msg UNIQUE,   -- internetMessageId
    graph_id         VARCHAR(300)   NULL,
    remitente        NVARCHAR(150)  NOT NULL,
    asunto           NVARCHAR(250)  NOT NULL,
    ticket_id        BIGINT NULL CONSTRAINT fk_correos_entrantes_ticket REFERENCES dbo.tickets(id),
    resultado        VARCHAR(20)    NOT NULL
                     CONSTRAINT ck_correos_entrantes_resultado CHECK (resultado IN ('CREADO','ACTUALIZADO','IGNORADO','ERROR')),
    detalle          NVARCHAR(1000) NULL,
    fecha_recepcion  DATETIME2(0)   NULL,
    fecha_proceso    DATETIME2(0)   NOT NULL CONSTRAINT df_correos_entrantes_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_correos_entrantes_ticket')
    CREATE INDEX ix_correos_entrantes_ticket ON dbo.correos_entrantes(ticket_id);
GO

/* ---------------------------------------------------------------------
   Microsoft Teams: canales vinculados y cola de avisos
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.teams_canales', N'U') IS NULL
CREATE TABLE dbo.teams_canales (
    id               INT IDENTITY(1,1) CONSTRAINT pk_teams_canales PRIMARY KEY,
    nombre           NVARCHAR(150) NOT NULL,
    conversation_id  VARCHAR(300)  NOT NULL CONSTRAINT uq_teams_canales_conv UNIQUE,
    service_url      VARCHAR(300)  NOT NULL,
    team_id          VARCHAR(300)  NULL,
    categoria_id     INT NULL CONSTRAINT fk_teams_canales_categoria REFERENCES dbo.categorias(id),   -- NULL = canal general
    activo           BIT NOT NULL CONSTRAINT df_teams_canales_activo DEFAULT (1),
    vinculado_por    INT NULL CONSTRAINT fk_teams_canales_usuario REFERENCES dbo.usuarios(id),
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_teams_canales_fecha DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'dbo.cola_teams', N'U') IS NULL
CREATE TABLE dbo.cola_teams (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_cola_teams PRIMARY KEY,
    ticket_id        BIGINT NOT NULL CONSTRAINT fk_cola_teams_ticket REFERENCES dbo.tickets(id),
    evento           VARCHAR(30)    NOT NULL,
    detalle          NVARCHAR(500)  NULL,
    estado           VARCHAR(12)    NOT NULL CONSTRAINT df_cola_teams_estado DEFAULT ('PENDIENTE')
                     CONSTRAINT ck_cola_teams_estado CHECK (estado IN ('PENDIENTE','ENVIADO','ERROR','DESCARTADO')),
    intentos         INT NOT NULL CONSTRAINT df_cola_teams_intentos DEFAULT (0),
    ultimo_error     NVARCHAR(1000) NULL,
    proximo_intento  DATETIME2(0) NOT NULL CONSTRAINT df_cola_teams_proximo DEFAULT (SYSUTCDATETIME()),
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_cola_teams_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_envio      DATETIME2(0) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_cola_teams_pendientes')
    CREATE INDEX ix_cola_teams_pendientes ON dbo.cola_teams(estado, proximo_intento);
GO

/* ---------------------------------------------------------------------
   Plantilla del acuse de recepción para tickets creados por correo
   --------------------------------------------------------------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('ACUSE_CORREO', N'[{numero}] Recibimos su solicitud: {asunto}',
        N'<p>Hola {destinatario},</p><p>Recibimos su correo y registramos el ticket <b>{numero}</b> «{asunto}».</p><p>Categoría: <b>{categoria}</b><br>Prioridad: <b>{prioridad}</b><br>Responsable: <b>{responsable}</b></p><p>Resolución comprometida: {sla_resolucion_vence}</p><p>Para agregar información o documentos, responda a este correo sin cambiar el asunto.</p>'),
    ('RESPUESTA_TICKET', N'[{numero}] Respuesta: {asunto}',
        N'<p>Hola {destinatario},</p><p><b>{autor}</b> respondió a su ticket <b>{numero}</b> «{asunto}»:</p><div style="white-space:pre-line;border-left:3px solid #70A9CE;padding:8px 12px;background:#F4F6FA">{comentario}</div><p>Estado actual: <b>{estado}</b></p><p>Para responder, conteste este correo sin cambiar el asunto.</p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

PRINT N'07_microsoft365 aplicado';
GO
