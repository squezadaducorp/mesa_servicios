/* =====================================================================
   ISO 27001: revisión de accesos (38) y clasificación y retención (42). Idempotente (db-init lo ejecuta en cada arranque).
   - 38: campañas trimestrales de revisión por jefe directo, acta en PDF a squezada@aducorp.com.ec,
         bajas por inactividad a los 90 días con aviso 7 días antes.
   - 42: clasificación Pública/Interna/Confidencial en tickets y categorías; retención de 5 años desde el cierre
         con depuración aprobada por TI y retención legal por ticket. No borra nada por sí sola.
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 38. Aviso de baja por inactividad ---------------- */
IF COL_LENGTH('dbo.usuarios', 'aviso_inactividad') IS NULL
    ALTER TABLE dbo.usuarios ADD aviso_inactividad DATETIME2(0) NULL;
GO

/* ---------------- 38. Campañas de revisión de accesos ---------------- */
IF OBJECT_ID(N'dbo.revisiones_acceso', N'U') IS NULL
CREATE TABLE dbo.revisiones_acceso (
    id                INT IDENTITY(1,1) CONSTRAINT pk_revisiones_acceso PRIMARY KEY,
    periodo           VARCHAR(10) NOT NULL CONSTRAINT ux_revisiones_acceso_periodo UNIQUE,
    estado            VARCHAR(12) NOT NULL CONSTRAINT df_revisiones_acceso_estado DEFAULT ('ABIERTA'),
    fecha_creacion    DATETIME2(0) NOT NULL CONSTRAINT df_revisiones_acceso_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_limite      DATETIME2(0) NOT NULL,
    creada_por        INT NULL CONSTRAINT fk_revisiones_acceso_creada REFERENCES dbo.usuarios(id),
    recordatorio      BIT NOT NULL CONSTRAINT df_revisiones_acceso_recordatorio DEFAULT (0),
    aprobada_por      INT NULL CONSTRAINT fk_revisiones_acceso_aprobada REFERENCES dbo.usuarios(id),
    fecha_aprobacion  DATETIME2(0) NULL,
    observacion       NVARCHAR(1000) NULL,
    CONSTRAINT ck_revisiones_acceso_estado CHECK (estado IN ('ABIERTA','APROBADA'))
);
GO
IF OBJECT_ID(N'dbo.revision_acceso_items', N'U') IS NULL
CREATE TABLE dbo.revision_acceso_items (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_revision_acceso_items PRIMARY KEY,
    revision_id     INT NOT NULL CONSTRAINT fk_revision_items_revision REFERENCES dbo.revisiones_acceso(id),
    usuario_id      INT NOT NULL CONSTRAINT fk_revision_items_usuario REFERENCES dbo.usuarios(id),
    jefe_id         INT NULL CONSTRAINT fk_revision_items_jefe REFERENCES dbo.usuarios(id),
    rol             NVARCHAR(100) NOT NULL,
    ultimo_login    DATETIME2(0) NULL,
    alertas         VARCHAR(300) NULL,
    decision        VARCHAR(10) NULL,
    comentario      NVARCHAR(500) NULL,
    decidido_por    INT NULL CONSTRAINT fk_revision_items_decidido REFERENCES dbo.usuarios(id),
    fecha_decision  DATETIME2(0) NULL,
    aplicado        BIT NOT NULL CONSTRAINT df_revision_items_aplicado DEFAULT (0),
    CONSTRAINT ux_revision_acceso_items UNIQUE (revision_id, usuario_id),
    CONSTRAINT ck_revision_items_decision CHECK (decision IS NULL OR decision IN ('MANTENER','AJUSTAR','BAJA'))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_revision_items_jefe')
    CREATE INDEX ix_revision_items_jefe ON dbo.revision_acceso_items(jefe_id, revision_id);
GO

/* ---------------- 42. Clasificación y retención ---------------- */
IF COL_LENGTH('dbo.tickets', 'clasificacion') IS NULL
    ALTER TABLE dbo.tickets ADD clasificacion VARCHAR(12) NOT NULL CONSTRAINT df_tickets_clasificacion DEFAULT ('INTERNA')
        CONSTRAINT ck_tickets_clasificacion CHECK (clasificacion IN ('PUBLICA','INTERNA','CONFIDENCIAL'));
GO
IF COL_LENGTH('dbo.tickets', 'retencion_legal') IS NULL
    ALTER TABLE dbo.tickets ADD retencion_legal BIT NOT NULL CONSTRAINT df_tickets_retencion_legal DEFAULT (0);
GO
IF COL_LENGTH('dbo.tickets', 'fecha_depuracion') IS NULL
    ALTER TABLE dbo.tickets ADD fecha_depuracion DATETIME2(0) NULL;
GO
IF COL_LENGTH('dbo.categorias', 'clasificacion') IS NULL
    ALTER TABLE dbo.categorias ADD clasificacion VARCHAR(12) NULL
        CONSTRAINT ck_categorias_clasificacion CHECK (clasificacion IS NULL OR clasificacion IN ('PUBLICA','INTERNA','CONFIDENCIAL'));
GO

/* ---------------- Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('accesos.informe_correo',    N'squezada@aducorp.com.ec', N'Correo que recibe el acta de la revisión de accesos y el aviso de bajas por inactividad'),
    ('accesos.meses_revision',    N'3,6,9,12', N'Meses en que se abre la revisión trimestral de accesos (día 1), separados por coma'),
    ('accesos.dias_plazo',        N'15', N'Días que tienen los jefes para revisar los accesos de su gente'),
    ('accesos.dias_alerta',       N'60', N'Días sin ingresar a partir de los cuales la revisión marca la cuenta'),
    ('accesos.bajas_automaticas', N'si', N'Desactivar las cuentas que no ingresan en los días configurados (si/no)'),
    ('accesos.dias_inactividad',  N'90', N'Días sin ingresar tras los que se desactiva la cuenta'),
    ('accesos.dias_aviso_baja',   N'7',  N'Días de anticipación del aviso de baja por inactividad'),
    ('accesos.excluidos',         N'',   N'Correos que nunca se desactivan por inactividad (cuentas de servicio), separados por coma'),
    ('retencion.tickets_anios',   N'5',  N'Años que se conservan los tickets desde su cierre antes de poder depurarlos'),
    ('retencion.aviso_mensual',   N'si', N'Avisar el primer día de cada mes si hay tickets listos para depurar (si/no)')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO

PRINT N'19_cumplimiento_iso.sql aplicado';
GO
