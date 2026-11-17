/* =====================================================================
   Segunda ronda de mejoras. Idempotente (se ejecuta en cada arranque vía db-init).
   14. Base de conocimiento (kb_articulos, kb_ticket_vistos)
   15. Respuestas rápidas (respuestas_rapidas)
   16. Tickets recurrentes (tickets_recurrentes)
   17. Reportes programados por correo (reportes_programados, reporte_envios, adjunto en cola_correos)
   18. Inventario de equipos (equipos, tickets.equipo_id, categorias.pide_equipo)
   19. Tickets en nombre de otra persona (usuario_delegaciones, tickets.creado_por_id, categorias.restringida_en_nombre)
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 14. Base de conocimiento ---------------- */
IF OBJECT_ID(N'dbo.kb_articulos', N'U') IS NULL
CREATE TABLE dbo.kb_articulos (
    id                 INT IDENTITY(1,1) CONSTRAINT pk_kb_articulos PRIMARY KEY,
    titulo             NVARCHAR(200) NOT NULL,
    sintoma            NVARCHAR(1000) NULL,
    solucion           NVARCHAR(MAX) NOT NULL,
    nota               NVARCHAR(500) NULL,
    palabras_clave     NVARCHAR(500) NULL,
    categoria_id       INT NULL CONSTRAINT fk_kb_categoria REFERENCES dbo.categorias(id),
    subcategoria_id    INT NULL CONSTRAINT fk_kb_subcategoria REFERENCES dbo.subcategorias(id),
    estado             VARCHAR(10) NOT NULL CONSTRAINT df_kb_estado DEFAULT ('BORRADOR')
                       CONSTRAINT ck_kb_estado CHECK (estado IN ('BORRADOR','PUBLICADO','ARCHIVADO')),
    visibilidad        VARCHAR(10) NOT NULL CONSTRAINT df_kb_visibilidad DEFAULT ('TODOS')
                       CONSTRAINT ck_kb_visibilidad CHECK (visibilidad IN ('TODOS','MESA')),
    ticket_origen_id   BIGINT NULL CONSTRAINT fk_kb_ticket REFERENCES dbo.tickets(id),
    vistas             INT NOT NULL CONSTRAINT df_kb_vistas DEFAULT (0),
    util_si            INT NOT NULL CONSTRAINT df_kb_util_si DEFAULT (0),
    util_no            INT NOT NULL CONSTRAINT df_kb_util_no DEFAULT (0),
    tickets_evitados   INT NOT NULL CONSTRAINT df_kb_evitados DEFAULT (0),
    creado_por         INT NULL CONSTRAINT fk_kb_creado_por REFERENCES dbo.usuarios(id),
    actualizado_por    INT NULL CONSTRAINT fk_kb_actualizado_por REFERENCES dbo.usuarios(id),
    fecha_creacion     DATETIME2(0) NOT NULL CONSTRAINT df_kb_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion DATETIME2(0) NULL,
    eliminado          BIT NOT NULL CONSTRAINT df_kb_eliminado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_kb_estado')
    CREATE INDEX ix_kb_estado ON dbo.kb_articulos(estado, eliminado) INCLUDE (categoria_id, subcategoria_id);
GO
-- Artículos que la persona revisó antes de crear el ticket (el responsable los ve en el detalle)
IF OBJECT_ID(N'dbo.kb_ticket_vistos', N'U') IS NULL
CREATE TABLE dbo.kb_ticket_vistos (
    ticket_id   BIGINT NOT NULL CONSTRAINT fk_kb_vistos_ticket REFERENCES dbo.tickets(id),
    articulo_id INT NOT NULL CONSTRAINT fk_kb_vistos_articulo REFERENCES dbo.kb_articulos(id),
    CONSTRAINT pk_kb_ticket_vistos PRIMARY KEY (ticket_id, articulo_id)
);
GO

/* ---------------- 15. Respuestas rápidas ---------------- */
IF OBJECT_ID(N'dbo.respuestas_rapidas', N'U') IS NULL
CREATE TABLE dbo.respuestas_rapidas (
    id               INT IDENTITY(1,1) CONSTRAINT pk_respuestas_rapidas PRIMARY KEY,
    atajo            VARCHAR(30) NOT NULL,
    titulo           NVARCHAR(150) NOT NULL,
    texto            NVARCHAR(4000) NOT NULL,
    categoria_id     INT NULL CONSTRAINT fk_resp_categoria REFERENCES dbo.categorias(id),
    subcategoria_id  INT NULL CONSTRAINT fk_resp_subcategoria REFERENCES dbo.subcategorias(id),
    estado_destino   VARCHAR(20) NULL CONSTRAINT fk_resp_estado REFERENCES dbo.estados(codigo),
    alcance          VARCHAR(10) NOT NULL CONSTRAINT df_resp_alcance DEFAULT ('TODOS')
                     CONSTRAINT ck_resp_alcance CHECK (alcance IN ('TODOS','AREA','PERSONAL')),
    area_id          INT NULL CONSTRAINT fk_resp_area REFERENCES dbo.areas(id),
    propietario_id   INT NULL CONSTRAINT fk_resp_propietario REFERENCES dbo.usuarios(id),
    usos             INT NOT NULL CONSTRAINT df_resp_usos DEFAULT (0),
    ultimo_uso       DATETIME2(0) NULL,
    activo           BIT NOT NULL CONSTRAINT df_resp_activo DEFAULT (1),
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_resp_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT ck_resp_area CHECK (alcance <> 'AREA' OR area_id IS NOT NULL),
    CONSTRAINT ck_resp_personal CHECK (alcance <> 'PERSONAL' OR propietario_id IS NOT NULL)
);
GO
-- Las plantillas de respuesta que ya tenía cada subcategoría pasan, una sola vez, a ser respuestas rápidas compartidas
IF NOT EXISTS (SELECT 1 FROM dbo.configuracion WHERE clave = 'respuestas.plantillas_migradas')
BEGIN
    INSERT INTO dbo.respuestas_rapidas (atajo, titulo, texto, categoria_id, subcategoria_id, alcance)
    SELECT LEFT('/s' + CAST(s.id AS VARCHAR(10)), 30), LEFT(N'Plantilla: ' + s.nombre, 150), s.respuesta_plantilla, s.categoria_id, s.id, 'TODOS'
    FROM dbo.subcategorias s
    WHERE s.respuesta_plantilla IS NOT NULL AND LTRIM(RTRIM(s.respuesta_plantilla)) <> N'' AND s.eliminado = 0;
    INSERT INTO dbo.configuracion (clave, valor, descripcion)
    VALUES ('respuestas.plantillas_migradas', CONVERT(NVARCHAR(30), SYSUTCDATETIME(), 126), N'Uso interno: plantillas de subcategoría copiadas a respuestas rápidas');
END
GO

/* ---------------- 16. Tickets recurrentes ---------------- */
IF OBJECT_ID(N'dbo.tickets_recurrentes', N'U') IS NULL
CREATE TABLE dbo.tickets_recurrentes (
    id                 INT IDENTITY(1,1) CONSTRAINT pk_tickets_recurrentes PRIMARY KEY,
    nombre             NVARCHAR(150) NOT NULL,
    asunto             NVARCHAR(200) NOT NULL,
    descripcion        NVARCHAR(4000) NOT NULL,
    tareas             NVARCHAR(4000) NULL,                     -- una tarea por línea
    categoria_id       INT NOT NULL CONSTRAINT fk_rec_categoria REFERENCES dbo.categorias(id),
    subcategoria_id    INT NOT NULL CONSTRAINT fk_rec_subcategoria REFERENCES dbo.subcategorias(id),
    prioridad_id       INT NOT NULL CONSTRAINT fk_rec_prioridad REFERENCES dbo.prioridades(id),
    responsable_id     INT NULL CONSTRAINT fk_rec_responsable REFERENCES dbo.usuarios(id),   -- NULL = asignación automática
    solicitante_id     INT NOT NULL CONSTRAINT fk_rec_solicitante REFERENCES dbo.usuarios(id),
    frecuencia         VARCHAR(12) NOT NULL CONSTRAINT ck_rec_frecuencia
                       CHECK (frecuencia IN ('DIARIA','SEMANAL','MENSUAL','TRIMESTRAL','SEMESTRAL','ANUAL')),
    dia_semana         TINYINT NULL CONSTRAINT ck_rec_dia_semana CHECK (dia_semana BETWEEN 1 AND 7),
    dia_mes            SMALLINT NULL CONSTRAINT ck_rec_dia_mes CHECK (dia_mes = -1 OR dia_mes BETWEEN 1 AND 31),
    semana_mes         SMALLINT NULL CONSTRAINT ck_rec_semana CHECK (semana_mes = -1 OR semana_mes BETWEEN 1 AND 4),
    hora               TIME(0) NOT NULL CONSTRAINT df_rec_hora DEFAULT ('08:30'),
    desde              DATE NOT NULL,
    hasta              DATE NULL,
    omitir_si_abierto  BIT NOT NULL CONSTRAINT df_rec_omitir DEFAULT (1),
    activo             BIT NOT NULL CONSTRAINT df_rec_activo DEFAULT (1),
    proxima_ejecucion  DATETIME2(0) NULL,                       -- UTC; NULL = terminó
    ultima_ejecucion   DATETIME2(0) NULL,
    ultimo_ticket_id   BIGINT NULL,
    ultimo_resultado   NVARCHAR(300) NULL,
    creado_por         INT NULL CONSTRAINT fk_rec_creado_por REFERENCES dbo.usuarios(id),
    fecha_creacion     DATETIME2(0) NOT NULL CONSTRAINT df_rec_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_rec_proxima')
    CREATE INDEX ix_rec_proxima ON dbo.tickets_recurrentes(activo, proxima_ejecucion);
GO
IF COL_LENGTH(N'dbo.tickets', N'recurrente_id') IS NULL
    ALTER TABLE dbo.tickets ADD recurrente_id INT NULL CONSTRAINT fk_tickets_recurrente REFERENCES dbo.tickets_recurrentes(id);
GO

/* ---------------- 17. Reportes programados ---------------- */
IF OBJECT_ID(N'dbo.reportes_programados', N'U') IS NULL
CREATE TABLE dbo.reportes_programados (
    id               INT IDENTITY(1,1) CONSTRAINT pk_reportes_programados PRIMARY KEY,
    nombre           NVARCHAR(150) NOT NULL,
    destinatarios    NVARCHAR(1000) NOT NULL,
    frecuencia       VARCHAR(10) NOT NULL CONSTRAINT ck_rep_frecuencia CHECK (frecuencia IN ('DIARIA','SEMANAL','MENSUAL')),
    dia_semana       TINYINT NULL CONSTRAINT ck_rep_dia_semana CHECK (dia_semana BETWEEN 1 AND 7),
    dia_mes          TINYINT NULL CONSTRAINT ck_rep_dia_mes CHECK (dia_mes BETWEEN 1 AND 28),
    hora             TIME(0) NOT NULL CONSTRAINT df_rep_hora DEFAULT ('08:00'),
    secciones        VARCHAR(300) NOT NULL,
    areas            VARCHAR(300) NULL,                         -- ids separados por coma; NULL = todas
    adjuntar_excel   BIT NOT NULL CONSTRAINT df_rep_excel DEFAULT (1),
    activo           BIT NOT NULL CONSTRAINT df_rep_activo DEFAULT (1),
    proximo_envio    DATETIME2(0) NULL,                         -- UTC
    ultimo_envio     DATETIME2(0) NULL,
    creado_por       INT NULL CONSTRAINT fk_rep_creado_por REFERENCES dbo.usuarios(id),
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_rep_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'dbo.reporte_envios', N'U') IS NULL
CREATE TABLE dbo.reporte_envios (
    id             BIGINT IDENTITY(1,1) CONSTRAINT pk_reporte_envios PRIMARY KEY,
    reporte_id     INT NOT NULL CONSTRAINT fk_envios_reporte REFERENCES dbo.reportes_programados(id) ON DELETE CASCADE,
    fecha          DATETIME2(0) NOT NULL CONSTRAINT df_envios_fecha DEFAULT (SYSUTCDATETIME()),
    periodo        NVARCHAR(100) NOT NULL,
    destinatarios  NVARCHAR(1000) NOT NULL,
    es_prueba      BIT NOT NULL CONSTRAINT df_envios_prueba DEFAULT (0),
    correo_id      BIGINT NULL CONSTRAINT fk_envios_correo REFERENCES dbo.cola_correos(id),
    enviado_por    INT NULL CONSTRAINT fk_envios_usuario REFERENCES dbo.usuarios(id)
);
GO
IF COL_LENGTH(N'dbo.cola_correos', N'adjunto_nombre') IS NULL
    ALTER TABLE dbo.cola_correos ADD adjunto_nombre NVARCHAR(150) NULL, adjunto VARBINARY(MAX) NULL;
GO

/* ---------------- 18. Inventario de equipos ---------------- */
IF OBJECT_ID(N'dbo.equipos', N'U') IS NULL
CREATE TABLE dbo.equipos (
    id               INT IDENTITY(1,1) CONSTRAINT pk_equipos PRIMARY KEY,
    codigo           VARCHAR(30) NOT NULL CONSTRAINT ux_equipos_codigo UNIQUE,
    tipo             VARCHAR(15) NOT NULL CONSTRAINT ck_equipos_tipo
                     CHECK (tipo IN ('ESCRITORIO','PORTATIL','IMPRESORA','RED','TOKEN','TELEFONO','MONITOR','SERVIDOR','OTRO')),
    marca_modelo     NVARCHAR(150) NOT NULL,
    serie            NVARCHAR(80) NULL,
    usuario_id       INT NULL CONSTRAINT fk_equipos_usuario REFERENCES dbo.usuarios(id),
    area_id          INT NULL CONSTRAINT fk_equipos_area REFERENCES dbo.areas(id),
    compartido       BIT NOT NULL CONSTRAINT df_equipos_compartido DEFAULT (0),
    ubicacion        NVARCHAR(150) NULL,
    estado           VARCHAR(12) NOT NULL CONSTRAINT df_equipos_estado DEFAULT ('EN_USO')
                     CONSTRAINT ck_equipos_estado CHECK (estado IN ('EN_USO','BODEGA','REPARACION','BAJA')),
    fecha_compra     DATE NULL,
    garantia_hasta   DATE NULL,
    sistema          NVARCHAR(150) NULL,
    notas            NVARCHAR(1000) NULL,
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_equipos_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion DATETIME2(0) NULL,
    eliminado        BIT NOT NULL CONSTRAINT df_equipos_eliminado DEFAULT (0)
);
GO
IF COL_LENGTH(N'dbo.tickets', N'equipo_id') IS NULL
    ALTER TABLE dbo.tickets ADD equipo_id INT NULL CONSTRAINT fk_tickets_equipo REFERENCES dbo.equipos(id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_equipo')
    CREATE INDEX ix_tickets_equipo ON dbo.tickets(equipo_id, fecha_creacion) WHERE equipo_id IS NOT NULL;
GO
IF COL_LENGTH(N'dbo.categorias', N'pide_equipo') IS NULL
    ALTER TABLE dbo.categorias ADD pide_equipo BIT NOT NULL CONSTRAINT df_categorias_pide_equipo DEFAULT (0);
GO

/* ---------------- 19. Tickets en nombre de otra persona ---------------- */
IF OBJECT_ID(N'dbo.usuario_delegaciones', N'U') IS NULL
CREATE TABLE dbo.usuario_delegaciones (
    usuario_id     INT NOT NULL CONSTRAINT pk_usuario_delegaciones PRIMARY KEY
                   CONSTRAINT fk_delegaciones_usuario REFERENCES dbo.usuarios(id),
    areas          VARCHAR(300) NULL,                           -- ids separados por coma; NULL = todas las áreas
    hasta          DATE NULL,                                   -- vence ese día (inclusive); NULL = sin vencimiento
    otorgado_por   INT NULL CONSTRAINT fk_delegaciones_otorgado REFERENCES dbo.usuarios(id),
    fecha          DATETIME2(0) NOT NULL CONSTRAINT df_delegaciones_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF COL_LENGTH(N'dbo.tickets', N'creado_por_id') IS NULL
    ALTER TABLE dbo.tickets ADD creado_por_id INT NULL CONSTRAINT fk_tickets_creado_por REFERENCES dbo.usuarios(id),
                                en_nombre_motivo NVARCHAR(300) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_creado_por')
    CREATE INDEX ix_tickets_creado_por ON dbo.tickets(creado_por_id) WHERE creado_por_id IS NOT NULL;
GO
IF COL_LENGTH(N'dbo.categorias', N'restringida_en_nombre') IS NULL
    ALTER TABLE dbo.categorias ADD restringida_en_nombre BIT NOT NULL CONSTRAINT df_categorias_restringida DEFAULT (0);
GO

/* ---------------- Permisos nuevos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('kb.gestionar',          N'Base de conocimiento', N'Crear, editar y publicar artículos de la base de conocimiento'),
    ('respuestas.gestionar',  N'Respuestas rápidas',   N'Administrar las respuestas rápidas compartidas'),
    ('recurrentes.gestionar', N'Tickets recurrentes',  N'Programar tickets que se crean solos'),
    ('reportes.programar',    N'Reportes',             N'Programar reportes que se envían por correo'),
    ('inventario.ver',        N'Inventario',           N'Ver el inventario de equipos y su historial de fallas'),
    ('inventario.gestionar',  N'Inventario',           N'Registrar, editar e importar equipos')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);
GO
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', codigo FROM dbo.permisos
    WHERE codigo IN ('kb.gestionar','respuestas.gestionar','recurrentes.gestionar','reportes.programar','inventario.ver','inventario.gestionar')
    UNION ALL SELECT 'ADMIN_MESA', 'kb.gestionar'          UNION ALL SELECT 'ADMIN_MESA', 'respuestas.gestionar'
    UNION ALL SELECT 'ADMIN_MESA', 'recurrentes.gestionar' UNION ALL SELECT 'ADMIN_MESA', 'reportes.programar'
    UNION ALL SELECT 'ADMIN_MESA', 'inventario.ver'        UNION ALL SELECT 'ADMIN_MESA', 'inventario.gestionar'
    UNION ALL SELECT 'SUPERVISOR', 'kb.gestionar'          UNION ALL SELECT 'SUPERVISOR', 'respuestas.gestionar'
    UNION ALL SELECT 'SUPERVISOR', 'inventario.ver'
    UNION ALL SELECT 'ANALISTA',   'kb.gestionar'          UNION ALL SELECT 'ANALISTA',   'inventario.ver'
    UNION ALL SELECT 'GERENCIA',   'inventario.ver'
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
    ('TICKET_EN_NOMBRE', N'[{numero}] {creado_por} registró un ticket en su nombre',
        N'<p>Hola {destinatario},</p><p><b>{creado_por}</b> registró el ticket <b>{numero}</b> «{asunto}» en su nombre.</p><p>Motivo indicado: <i>{motivo}</i></p><p>Las respuestas del equipo le llegarán a usted. Si usted no lo pidió, responda a este correo o avise a la Mesa de Servicios para revisarlo.</p><p><a href="{url}">Ver ticket</a></p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

/* ---------------- Analistas: reasignar los tickets que tienen a su cargo ----------------
   Se otorga una sola vez: si luego se quita el permiso en Roles, una nueva instalación no lo vuelve a poner. */
IF NOT EXISTS (SELECT 1 FROM dbo.configuracion WHERE clave = 'permisos.analista_reasigna')
BEGIN
    INSERT INTO dbo.rol_permisos (rol_id, permiso_id)
    SELECT r.id, p.id
    FROM dbo.roles r JOIN dbo.permisos p ON p.codigo = 'ticket.asignar'
    WHERE r.codigo = 'ANALISTA'
      AND NOT EXISTS (SELECT 1 FROM dbo.rol_permisos rp WHERE rp.rol_id = r.id AND rp.permiso_id = p.id);
    INSERT INTO dbo.configuracion (clave, valor, descripcion)
    VALUES ('permisos.analista_reasigna', CONVERT(NVARCHAR(30), SYSUTCDATETIME(), 126), N'Uso interno: permiso de reasignar otorgado a analistas');
END
GO

PRINT N'11_segunda_ronda aplicado';
GO
