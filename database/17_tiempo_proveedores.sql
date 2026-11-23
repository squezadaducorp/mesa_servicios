/* =====================================================================
   Cuarta ronda, parte 2b. Idempotente (se ejecuta en cada arranque vía db-init). No borra datos.
   31. Control de tiempo: tiempo_registros (cronómetro y registros a mano por ticket, problema o cambio),
       tickets.tiempo_estimado_min y tickets.facturable.
   33. Proveedores y contratos: proveedores (con su contrato) y proveedor_casos (tickets escalados a un proveedor).
   Permisos nuevos: tiempo.reporte y proveedores.gestionar (Administrador Mesa y Supervisor).
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 31. Control de tiempo ---------------- */
IF COL_LENGTH(N'dbo.tickets', N'tiempo_estimado_min') IS NULL
    ALTER TABLE dbo.tickets ADD tiempo_estimado_min INT NULL;
GO
IF COL_LENGTH(N'dbo.tickets', N'facturable') IS NULL
    ALTER TABLE dbo.tickets ADD facturable BIT NOT NULL CONSTRAINT df_tickets_facturable DEFAULT (0);
GO
IF OBJECT_ID(N'dbo.tiempo_registros', N'U') IS NULL
CREATE TABLE dbo.tiempo_registros (
    id                   BIGINT IDENTITY(1,1) CONSTRAINT pk_tiempo_registros PRIMARY KEY,
    usuario_id           INT NOT NULL CONSTRAINT fk_tiempo_usuario REFERENCES dbo.usuarios(id),
    ticket_id            BIGINT NULL CONSTRAINT fk_tiempo_ticket REFERENCES dbo.tickets(id),
    problema_id          INT NULL CONSTRAINT fk_tiempo_problema REFERENCES dbo.problemas(id),
    cambio_id            INT NULL CONSTRAINT fk_tiempo_cambio REFERENCES dbo.cambios(id),
    actividad            NVARCHAR(200) NOT NULL,
    estado               VARCHAR(10) NOT NULL CONSTRAINT df_tiempo_estado DEFAULT ('CORRIENDO')
                         CONSTRAINT ck_tiempo_estado CHECK (estado IN ('CORRIENDO','PAUSADO','GUARDADO')),
    segundos             INT NOT NULL CONSTRAINT df_tiempo_segundos DEFAULT (0),
    corriendo_desde      DATETIME2(0) NULL,
    manual               BIT NOT NULL CONSTRAINT df_tiempo_manual DEFAULT (0),
    fecha                DATETIME2(0) NOT NULL CONSTRAINT df_tiempo_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion  DATETIME2(0) NULL,
    CONSTRAINT ck_tiempo_objeto CHECK ((CASE WHEN ticket_id IS NULL THEN 0 ELSE 1 END)
                                     + (CASE WHEN problema_id IS NULL THEN 0 ELSE 1 END)
                                     + (CASE WHEN cambio_id IS NULL THEN 0 ELSE 1 END) = 1)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tiempo_fecha')
    CREATE INDEX ix_tiempo_fecha ON dbo.tiempo_registros(fecha);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tiempo_ticket')
    CREATE INDEX ix_tiempo_ticket ON dbo.tiempo_registros(ticket_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tiempo_usuario_estado')
    CREATE INDEX ix_tiempo_usuario_estado ON dbo.tiempo_registros(usuario_id, estado);
GO

/* ---------------- 33. Proveedores y contratos ---------------- */
IF OBJECT_ID(N'dbo.proveedores', N'U') IS NULL
CREATE TABLE dbo.proveedores (
    id                 INT IDENTITY(1,1) CONSTRAINT pk_proveedores PRIMARY KEY,
    nombre             NVARCHAR(120) NOT NULL,
    servicio           NVARCHAR(150) NOT NULL,
    telefono           NVARCHAR(60) NULL,
    correo             NVARCHAR(150) NULL,
    correos_copia      NVARCHAR(500) NULL,
    portal             NVARCHAR(200) NULL,
    contacto           NVARCHAR(150) NULL,
    contrato_numero    NVARCHAR(60) NULL,
    contrato_vence     DATE NULL,
    contrato_detalle   NVARCHAR(300) NULL,
    atencion_24x7      BIT NOT NULL CONSTRAINT df_proveedores_24x7 DEFAULT (0),
    plazo_horas        INT NOT NULL CONSTRAINT df_proveedores_plazo DEFAULT (8),
    valor_mensual      DECIMAL(12,2) NULL,
    multa_pct_hora     DECIMAL(6,2) NULL,
    subcategorias      VARCHAR(300) NULL,
    notas              NVARCHAR(1000) NULL,
    aviso_vencimiento  DATE NULL,
    activo             BIT NOT NULL CONSTRAINT df_proveedores_activo DEFAULT (1),
    eliminado          BIT NOT NULL CONSTRAINT df_proveedores_eliminado DEFAULT (0),
    fecha_creacion     DATETIME2(0) NOT NULL CONSTRAINT df_proveedores_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'dbo.proveedor_casos', N'U') IS NULL
CREATE TABLE dbo.proveedor_casos (
    id                BIGINT IDENTITY(1,1) CONSTRAINT pk_proveedor_casos PRIMARY KEY,
    proveedor_id      INT NOT NULL CONSTRAINT fk_provcaso_proveedor REFERENCES dbo.proveedores(id),
    ticket_id         BIGINT NOT NULL CONSTRAINT fk_provcaso_ticket REFERENCES dbo.tickets(id),
    numero_caso       NVARCHAR(60) NULL,
    reporte           NVARCHAR(2000) NOT NULL,
    medio             NVARCHAR(100) NULL,
    contacto          NVARCHAR(150) NULL,
    estado            VARCHAR(10) NOT NULL CONSTRAINT df_provcaso_estado DEFAULT ('ABIERTO')
                      CONSTRAINT ck_provcaso_estado CHECK (estado IN ('ABIERTO','RESUELTO')),
    fecha_reporte     DATETIME2(0) NOT NULL CONSTRAINT df_provcaso_fecha DEFAULT (SYSUTCDATETIME()),
    vence             DATETIME2(0) NOT NULL,
    fecha_solucion    DATETIME2(0) NULL,
    minutos_solucion  INT NULL,
    cumplido          BIT NULL,
    solucion          NVARCHAR(1000) NULL,
    aviso_enviado     BIT NOT NULL CONSTRAINT df_provcaso_aviso DEFAULT (0),
    correo_enviado    BIT NOT NULL CONSTRAINT df_provcaso_correo DEFAULT (0),
    creado_por        INT NULL CONSTRAINT fk_provcaso_usuario REFERENCES dbo.usuarios(id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_provcaso_proveedor')
    CREATE INDEX ix_provcaso_proveedor ON dbo.proveedor_casos(proveedor_id, fecha_reporte);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_provcaso_ticket')
    CREATE INDEX ix_provcaso_ticket ON dbo.proveedor_casos(ticket_id, estado);
GO

/* ---------------- Permisos nuevos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('tiempo.reporte',        N'Control de tiempo', N'Ver el reporte semanal de horas del equipo y corregir registros de otros'),
    ('proveedores.gestionar', N'Proveedores',       N'Registrar proveedores y contratos, y ver su cumplimiento')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);
GO
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', 'tiempo.reporte' UNION ALL SELECT 'SUPER_ADMIN', 'proveedores.gestionar'
    UNION ALL SELECT 'ADMIN_MESA', 'tiempo.reporte' UNION ALL SELECT 'ADMIN_MESA', 'proveedores.gestionar'
    UNION ALL SELECT 'SUPERVISOR', 'tiempo.reporte' UNION ALL SELECT 'SUPERVISOR', 'proveedores.gestionar'
)
INSERT INTO dbo.rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM m
JOIN dbo.roles r ON r.codigo = m.rol
JOIN dbo.permisos p ON p.codigo = m.permiso
WHERE NOT EXISTS (SELECT 1 FROM dbo.rol_permisos rp WHERE rp.rol_id = r.id AND rp.permiso_id = p.id);
GO

/* ---------------- Plantillas de correo ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('PROVEEDOR_CASO', N'[{numero}] Reporte de falla · {proveedor}',
        N'<p>Estimados {destinatario}:</p><p>Reportamos la siguiente falla del servicio contratado por ADUCORP (contrato {contrato}):</p><p><b>{reporte}</b></p><ul><li>Caso del proveedor: <b>{caso}</b></li><li>Plazo de solución pactado: <b>{plazo}</b> · vence el {vence} (hora de Ecuador)</li><li>Reporta: {reporta}, Mesa de Servicios ADUCORP</li></ul><p>Por favor respondan a este correo con las novedades; su respuesta queda registrada en nuestro ticket {numero}.</p>'),
    ('PROVEEDOR_PLAZO', N'[{numero}] Plazo de {proveedor}',
        N'<p>Hola {destinatario},</p><p>El caso <b>{caso}</b> con <b>{proveedor}</b> del ticket <b>{numero}</b> «{asunto}» vence el {vence} (hora de Ecuador) y sigue abierto.</p><p>Llame al proveedor y, si ya dio solución, regístrela en el ticket para que nuestro SLA vuelva a correr.</p><p><a href="{url}">Ver el ticket</a></p>')
) AS s (codigo, asunto, cuerpo)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (s.codigo, s.asunto, s.cuerpo);
GO

/* ---------------- Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('tiempo.horas_semana',      N'40', N'Horas disponibles por analista a la semana (ocupación del equipo en Control de tiempo)'),
    ('proveedores.aviso_correo', N'squezada@aducorp.com.ec', N'Correos que reciben el aviso de contratos de proveedores que vencen en 30 días, separados por coma')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO
PRINT N'17_tiempo_proveedores.sql aplicado';
GO
