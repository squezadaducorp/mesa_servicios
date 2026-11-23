/* =====================================================================
   Cuarta ronda, parte 2a. Idempotente (se ejecuta en cada arranque vía db-init). No borra datos.
   30. Gestión de problemas: problemas (PRB-AAAA-NNN), problema_tickets (incidentes agrupados),
       problema_descartes («No es esto» en un ticket e «Ignorar» un patrón detectado).
   32. Panel gerencial: panel_envios (cada PDF mensual enviado por correo). La configuración del envío
       vive en dbo.configuracion (panel.envio_*) y queda APAGADA hasta que se active en la pantalla.
   Permisos nuevos: problemas.gestionar (Administrador Mesa, Supervisor) y panel.ver (Administrador Mesa, Gerencia).
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 30. Problemas ---------------- */
IF OBJECT_ID(N'dbo.problemas', N'U') IS NULL
CREATE TABLE dbo.problemas (
    id                   INT IDENTITY(1,1) CONSTRAINT pk_problemas PRIMARY KEY,
    numero               VARCHAR(20) NOT NULL CONSTRAINT uq_problemas_numero UNIQUE,
    anio                 INT NOT NULL,
    secuencia            INT NOT NULL,
    titulo               NVARCHAR(200) NOT NULL,
    descripcion          NVARCHAR(MAX) NULL,
    estado               VARCHAR(20) NOT NULL CONSTRAINT df_problemas_estado DEFAULT ('DETECTADO')
                         CONSTRAINT ck_problemas_estado CHECK (estado IN ('DETECTADO','EN_ANALISIS','ERROR_CONOCIDO','SOLUCION_EN_CAMBIO','CERRADO')),
    origen               VARCHAR(10) NOT NULL CONSTRAINT df_problemas_origen DEFAULT ('MANUAL')
                         CONSTRAINT ck_problemas_origen CHECK (origen IN ('MANUAL','PATRON')),
    categoria_id         INT NULL CONSTRAINT fk_problemas_categoria REFERENCES dbo.categorias(id),
    subcategoria_id      INT NULL CONSTRAINT fk_problemas_subcategoria REFERENCES dbo.subcategorias(id),
    responsable_id       INT NULL CONSTRAINT fk_problemas_responsable REFERENCES dbo.usuarios(id),
    porques              NVARCHAR(MAX) NULL,      -- JSON [{pregunta, respuesta}]
    causa_raiz           NVARCHAR(1000) NULL,
    solucion_definitiva  NVARCHAR(1000) NULL,
    solucion_temporal    NVARCHAR(2000) NULL,
    palabras_clave       NVARCHAR(500) NULL,
    articulo_id          INT NULL CONSTRAINT fk_problemas_articulo REFERENCES dbo.kb_articulos(id),
    cambio_id            INT NULL CONSTRAINT fk_problemas_cambio REFERENCES dbo.cambios(id),
    nota_cierre          NVARCHAR(1000) NULL,
    creado_por           INT NULL CONSTRAINT fk_problemas_creado REFERENCES dbo.usuarios(id),
    fecha_creacion       DATETIME2(0) NOT NULL CONSTRAINT df_problemas_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_causa          DATETIME2(0) NULL,
    fecha_cierre         DATETIME2(0) NULL,
    fecha_actualizacion  DATETIME2(0) NULL,
    CONSTRAINT uq_problemas_secuencia UNIQUE (anio, secuencia)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_problemas_estado')
    CREATE INDEX ix_problemas_estado ON dbo.problemas(estado);
GO
IF OBJECT_ID(N'dbo.problema_tickets', N'U') IS NULL
CREATE TABLE dbo.problema_tickets (
    id             BIGINT IDENTITY(1,1) CONSTRAINT pk_problema_tickets PRIMARY KEY,
    problema_id    INT NOT NULL CONSTRAINT fk_probtick_problema REFERENCES dbo.problemas(id),
    ticket_id      BIGINT NOT NULL CONSTRAINT fk_probtick_ticket REFERENCES dbo.tickets(id),
    con_solucion   BIT NOT NULL CONSTRAINT df_probtick_solucion DEFAULT (0),
    vinculado_por  INT NULL CONSTRAINT fk_probtick_usuario REFERENCES dbo.usuarios(id),
    fecha          DATETIME2(0) NOT NULL CONSTRAINT df_probtick_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT uq_probtick UNIQUE (problema_id, ticket_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_probtick_ticket')
    CREATE INDEX ix_probtick_ticket ON dbo.problema_tickets(ticket_id);
GO
IF OBJECT_ID(N'dbo.problema_descartes', N'U') IS NULL
CREATE TABLE dbo.problema_descartes (
    id           BIGINT IDENTITY(1,1) CONSTRAINT pk_problema_descartes PRIMARY KEY,
    problema_id  INT NULL CONSTRAINT fk_probdesc_problema REFERENCES dbo.problemas(id),
    ticket_id    BIGINT NULL CONSTRAINT fk_probdesc_ticket REFERENCES dbo.tickets(id),
    firma        VARCHAR(64) NULL,
    usuario_id   INT NULL CONSTRAINT fk_probdesc_usuario REFERENCES dbo.usuarios(id),
    fecha        DATETIME2(0) NOT NULL CONSTRAINT df_probdesc_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_probdesc_ticket')
    CREATE INDEX ix_probdesc_ticket ON dbo.problema_descartes(ticket_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_probdesc_firma')
    CREATE INDEX ix_probdesc_firma ON dbo.problema_descartes(firma);
GO

/* ---------------- 32. Envíos del panel gerencial ---------------- */
IF OBJECT_ID(N'dbo.panel_envios', N'U') IS NULL
CREATE TABLE dbo.panel_envios (
    id             BIGINT IDENTITY(1,1) CONSTRAINT pk_panel_envios PRIMARY KEY,
    periodo        CHAR(7) NOT NULL,             -- AAAA-MM del mes informado
    archivo        NVARCHAR(150) NOT NULL,
    fecha          DATETIME2(0) NOT NULL CONSTRAINT df_panelenv_fecha DEFAULT (SYSUTCDATETIME()),
    destinatarios  NVARCHAR(1000) NOT NULL,
    es_prueba      BIT NOT NULL CONSTRAINT df_panelenv_prueba DEFAULT (0),
    correo_id      BIGINT NULL,
    enviado_por    INT NULL CONSTRAINT fk_panelenv_usuario REFERENCES dbo.usuarios(id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_panelenv_periodo')
    CREATE INDEX ix_panelenv_periodo ON dbo.panel_envios(periodo, es_prueba);
GO

/* ---------------- Permisos nuevos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('problemas.gestionar', N'Gestión de problemas', N'Registrar problemas, analizar la causa raíz, publicar errores conocidos y cerrarlos'),
    ('panel.ver',           N'Panel gerencial',      N'Ver el panel gerencial y descargar su PDF mensual')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);
GO
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', 'problemas.gestionar' UNION ALL SELECT 'SUPER_ADMIN', 'panel.ver'
    UNION ALL SELECT 'ADMIN_MESA', 'problemas.gestionar' UNION ALL SELECT 'ADMIN_MESA', 'panel.ver'
    UNION ALL SELECT 'SUPERVISOR', 'problemas.gestionar' UNION ALL SELECT 'GERENCIA', 'panel.ver'
)
INSERT INTO dbo.rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM m
JOIN dbo.roles r ON r.codigo = m.rol
JOIN dbo.permisos p ON p.codigo = m.permiso
WHERE NOT EXISTS (SELECT 1 FROM dbo.rol_permisos rp WHERE rp.rol_id = r.id AND rp.permiso_id = p.id);
GO

/* ---------------- Plantilla de correo ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('PROBLEMA_RESUELTO', N'[{numero}] Se corrigió la causa de su incidente',
        N'<p>Hola {destinatario},</p><p>Hace un tiempo reportó <b>{numero}</b> «{asunto}». Era parte de un problema de fondo que TI estaba analizando (<b>{problema}</b> · {titulo_problema}).</p><p>Ya se aplicó la solución definitiva:</p><p><b>{solucion}</b></p><p>Si vuelve a pasar, responda este correo o abra un ticket nuevo.</p><p><a href="{url}">Ver el ticket</a></p>')
) AS s (codigo, asunto, cuerpo)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (s.codigo, s.asunto, s.cuerpo);
GO

/* ---------------- Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('problemas.patron_minimo', N'5',  N'Tickets parecidos (misma subcategoría y asunto) que forman un «patrón detectado» en Problemas'),
    ('problemas.patron_dias',   N'7',  N'Días hacia atrás en que se buscan los tickets parecidos del patrón'),
    ('panel.envio_activo',      N'no', N'Enviar por correo el PDF del panel gerencial cada mes (si/no). Se configura en Panel gerencial'),
    ('panel.envio_para',        N'',   N'Destinatarios del PDF mensual, separados por coma'),
    ('panel.envio_cuando',      N'PRIMER_HABIL', N'PRIMER_HABIL (primer día hábil del mes) o DIA_1'),
    ('panel.envio_hora',        N'08:00', N'Hora de Ecuador en que sale el PDF mensual'),
    ('panel.envio_secciones',   N'indicadores,tendencia,sla_area,satisfaccion,problemas,cambios,proveedores,horas', N'Secciones del PDF mensual'),
    ('panel.comentario',        N'',   N'Comentario de TI que sale en la portada del próximo PDF (se borra tras el envío automático)')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO
PRINT N'16_problemas_panel.sql aplicado';
GO
