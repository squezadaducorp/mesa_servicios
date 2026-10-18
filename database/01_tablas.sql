/* =====================================================================
   Mesa de Servicios ADUCORP
   01 · Tablas, claves e índices
   Convenciones:
     - Todas las fechas se guardan en UTC (DATETIME2(0)); la aplicación
       convierte a America/Guayaquil para mostrar y para el cálculo de SLA.
     - Nombres en español, snake_case.
     - Borrado lógico (eliminado = 1) en entidades de negocio.
   Idempotente: crea solo lo que no existe.
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* ---------------------------------------------------------------------
   SEGURIDAD
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.roles', N'U') IS NULL
CREATE TABLE dbo.roles (
    id              INT IDENTITY(1,1) CONSTRAINT pk_roles PRIMARY KEY,
    codigo          VARCHAR(40)    NOT NULL CONSTRAINT uq_roles_codigo UNIQUE,
    nombre          NVARCHAR(100)  NOT NULL,
    descripcion     NVARCHAR(300)  NULL,
    es_sistema      BIT            NOT NULL CONSTRAINT df_roles_es_sistema DEFAULT (1),
    fecha_creacion  DATETIME2(0)   NOT NULL CONSTRAINT df_roles_fecha DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'dbo.permisos', N'U') IS NULL
CREATE TABLE dbo.permisos (
    id              INT IDENTITY(1,1) CONSTRAINT pk_permisos PRIMARY KEY,
    codigo          VARCHAR(60)    NOT NULL CONSTRAINT uq_permisos_codigo UNIQUE,
    modulo          NVARCHAR(60)   NOT NULL,
    descripcion     NVARCHAR(300)  NOT NULL
);
GO

IF OBJECT_ID(N'dbo.rol_permisos', N'U') IS NULL
CREATE TABLE dbo.rol_permisos (
    rol_id      INT NOT NULL CONSTRAINT fk_rol_permisos_rol REFERENCES dbo.roles(id) ON DELETE CASCADE,
    permiso_id  INT NOT NULL CONSTRAINT fk_rol_permisos_permiso REFERENCES dbo.permisos(id) ON DELETE CASCADE,
    CONSTRAINT pk_rol_permisos PRIMARY KEY (rol_id, permiso_id)
);
GO

IF OBJECT_ID(N'dbo.areas', N'U') IS NULL
CREATE TABLE dbo.areas (
    id          INT IDENTITY(1,1) CONSTRAINT pk_areas PRIMARY KEY,
    nombre      NVARCHAR(100) NOT NULL CONSTRAINT uq_areas_nombre UNIQUE,
    activo      BIT NOT NULL CONSTRAINT df_areas_activo DEFAULT (1)
);
GO

IF OBJECT_ID(N'dbo.usuarios', N'U') IS NULL
CREATE TABLE dbo.usuarios (
    id                    INT IDENTITY(1,1) CONSTRAINT pk_usuarios PRIMARY KEY,
    nombre                NVARCHAR(150) NOT NULL,
    correo                NVARCHAR(150) NOT NULL CONSTRAINT uq_usuarios_correo UNIQUE,
    usuario_ad            NVARCHAR(100) NULL,             -- sAMAccountName (soporte AD)
    origen_autenticacion  VARCHAR(10)   NOT NULL CONSTRAINT df_usuarios_origen DEFAULT ('LOCAL')
                          CONSTRAINT ck_usuarios_origen CHECK (origen_autenticacion IN ('LOCAL','AD')),
    clave_hash            VARCHAR(100)  NULL,             -- bcrypt; NULL si autentica por AD
    debe_cambiar_clave    BIT NOT NULL CONSTRAINT df_usuarios_cambiar DEFAULT (0),
    cargo                 NVARCHAR(100) NULL,
    telefono              NVARCHAR(30)  NULL,
    area_id               INT NULL CONSTRAINT fk_usuarios_area REFERENCES dbo.areas(id),
    rol_id                INT NOT NULL CONSTRAINT fk_usuarios_rol REFERENCES dbo.roles(id),
    supervisor_id         INT NULL CONSTRAINT fk_usuarios_supervisor REFERENCES dbo.usuarios(id),
    activo                BIT NOT NULL CONSTRAINT df_usuarios_activo DEFAULT (1),
    intentos_fallidos     INT NOT NULL CONSTRAINT df_usuarios_intentos DEFAULT (0),
    bloqueado_hasta       DATETIME2(0) NULL,
    ultimo_login          DATETIME2(0) NULL,
    fecha_creacion        DATETIME2(0) NOT NULL CONSTRAINT df_usuarios_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion   DATETIME2(0) NULL,
    eliminado             BIT NOT NULL CONSTRAINT df_usuarios_eliminado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_usuarios_rol')
    CREATE INDEX ix_usuarios_rol ON dbo.usuarios(rol_id) INCLUDE (activo);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ux_usuarios_usuario_ad')
    CREATE UNIQUE INDEX ux_usuarios_usuario_ad ON dbo.usuarios(usuario_ad) WHERE usuario_ad IS NOT NULL;
GO

IF OBJECT_ID(N'dbo.refresh_tokens', N'U') IS NULL
CREATE TABLE dbo.refresh_tokens (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_refresh_tokens PRIMARY KEY,
    usuario_id       INT NOT NULL CONSTRAINT fk_refresh_usuario REFERENCES dbo.usuarios(id) ON DELETE CASCADE,
    token_hash       CHAR(64) NOT NULL CONSTRAINT uq_refresh_hash UNIQUE,   -- SHA-256 hex
    familia          CHAR(32) NOT NULL,                                     -- cadena de rotación
    fecha_creacion   DATETIME2(0) NOT NULL CONSTRAINT df_refresh_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_expiracion DATETIME2(0) NOT NULL,
    revocado         BIT NOT NULL CONSTRAINT df_refresh_revocado DEFAULT (0),
    fecha_revocacion DATETIME2(0) NULL,
    reemplazado_por  BIGINT NULL,
    ip               VARCHAR(45) NULL,
    equipo           NVARCHAR(300) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_refresh_usuario')
    CREATE INDEX ix_refresh_usuario ON dbo.refresh_tokens(usuario_id, revocado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_refresh_familia')
    CREATE INDEX ix_refresh_familia ON dbo.refresh_tokens(familia);
GO

/* ---------------------------------------------------------------------
   CATÁLOGO DE SERVICIOS
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.clientes', N'U') IS NULL
CREATE TABLE dbo.clientes (
    id              INT IDENTITY(1,1) CONSTRAINT pk_clientes PRIMARY KEY,
    ruc             VARCHAR(13)   NULL CONSTRAINT uq_clientes_ruc UNIQUE,
    razon_social    NVARCHAR(200) NOT NULL,
    nombre_comercial NVARCHAR(200) NULL,
    correo          NVARCHAR(150) NULL,
    telefono        NVARCHAR(30)  NULL,
    es_vip          BIT NOT NULL CONSTRAINT df_clientes_vip DEFAULT (0),
    activo          BIT NOT NULL CONSTRAINT df_clientes_activo DEFAULT (1),
    fecha_creacion  DATETIME2(0) NOT NULL CONSTRAINT df_clientes_fecha DEFAULT (SYSUTCDATETIME()),
    eliminado       BIT NOT NULL CONSTRAINT df_clientes_eliminado DEFAULT (0)
);
GO

IF OBJECT_ID(N'dbo.categorias', N'U') IS NULL
CREATE TABLE dbo.categorias (
    id              INT IDENTITY(1,1) CONSTRAINT pk_categorias PRIMARY KEY,
    codigo          VARCHAR(30)   NOT NULL CONSTRAINT uq_categorias_codigo UNIQUE,
    nombre          NVARCHAR(120) NOT NULL,
    descripcion     NVARCHAR(500) NULL,
    palabras_clave  NVARCHAR(1000) NULL,          -- usadas por la IA local
    supervisor_id   INT NULL CONSTRAINT fk_categorias_supervisor REFERENCES dbo.usuarios(id),
    modo_asignacion VARCHAR(15) NOT NULL CONSTRAINT df_categorias_modo DEFAULT ('PRINCIPAL')
                    CONSTRAINT ck_categorias_modo CHECK (modo_asignacion IN ('PRINCIPAL','BALANCEO','MANUAL')),
    color           CHAR(7) NULL,
    orden           INT NOT NULL CONSTRAINT df_categorias_orden DEFAULT (0),
    activo          BIT NOT NULL CONSTRAINT df_categorias_activo DEFAULT (1),
    fecha_creacion  DATETIME2(0) NOT NULL CONSTRAINT df_categorias_fecha DEFAULT (SYSUTCDATETIME()),
    eliminado       BIT NOT NULL CONSTRAINT df_categorias_eliminado DEFAULT (0)
);
GO

IF OBJECT_ID(N'dbo.subcategorias', N'U') IS NULL
CREATE TABLE dbo.subcategorias (
    id              INT IDENTITY(1,1) CONSTRAINT pk_subcategorias PRIMARY KEY,
    categoria_id    INT NOT NULL CONSTRAINT fk_subcategorias_categoria REFERENCES dbo.categorias(id),
    nombre          NVARCHAR(120) NOT NULL,
    palabras_clave  NVARCHAR(1000) NULL,
    respuesta_plantilla NVARCHAR(2000) NULL,      -- base para la respuesta sugerida
    activo          BIT NOT NULL CONSTRAINT df_subcategorias_activo DEFAULT (1),
    eliminado       BIT NOT NULL CONSTRAINT df_subcategorias_eliminado DEFAULT (0),
    CONSTRAINT uq_subcategorias UNIQUE (categoria_id, nombre)
);
GO

IF OBJECT_ID(N'dbo.categoria_responsables', N'U') IS NULL
CREATE TABLE dbo.categoria_responsables (
    categoria_id    INT NOT NULL CONSTRAINT fk_catresp_categoria REFERENCES dbo.categorias(id) ON DELETE CASCADE,
    usuario_id      INT NOT NULL CONSTRAINT fk_catresp_usuario REFERENCES dbo.usuarios(id),
    es_principal    BIT NOT NULL CONSTRAINT df_catresp_principal DEFAULT (0),
    CONSTRAINT pk_categoria_responsables PRIMARY KEY (categoria_id, usuario_id)
);
GO

/* ---------------------------------------------------------------------
   SLA Y CALENDARIO LABORAL
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.prioridades', N'U') IS NULL
CREATE TABLE dbo.prioridades (
    id                  INT IDENTITY(1,1) CONSTRAINT pk_prioridades PRIMARY KEY,
    codigo              VARCHAR(15)  NOT NULL CONSTRAINT uq_prioridades_codigo UNIQUE,
    nombre              NVARCHAR(50) NOT NULL,
    orden               INT NOT NULL,
    color               CHAR(7) NULL,
    sla_respuesta_min   INT NOT NULL CONSTRAINT ck_prioridades_resp CHECK (sla_respuesta_min > 0),
    sla_resolucion_min  INT NOT NULL CONSTRAINT ck_prioridades_res  CHECK (sla_resolucion_min > 0),
    activo              BIT NOT NULL CONSTRAINT df_prioridades_activo DEFAULT (1)
);
GO

/* Sobrescritura opcional del SLA por categoría (y prioridad). */
IF OBJECT_ID(N'dbo.sla_politicas', N'U') IS NULL
CREATE TABLE dbo.sla_politicas (
    id                  INT IDENTITY(1,1) CONSTRAINT pk_sla_politicas PRIMARY KEY,
    categoria_id        INT NOT NULL CONSTRAINT fk_slapol_categoria REFERENCES dbo.categorias(id),
    prioridad_id        INT NOT NULL CONSTRAINT fk_slapol_prioridad REFERENCES dbo.prioridades(id),
    sla_respuesta_min   INT NOT NULL,
    sla_resolucion_min  INT NOT NULL,
    activo              BIT NOT NULL CONSTRAINT df_slapol_activo DEFAULT (1),
    CONSTRAINT uq_sla_politicas UNIQUE (categoria_id, prioridad_id)
);
GO

IF OBJECT_ID(N'dbo.horarios_laborales', N'U') IS NULL
CREATE TABLE dbo.horarios_laborales (
    id                  INT IDENTITY(1,1) CONSTRAINT pk_horarios PRIMARY KEY,
    nombre              NVARCHAR(100) NOT NULL,
    zona_horaria        VARCHAR(50) NOT NULL CONSTRAINT df_horarios_tz DEFAULT ('America/Guayaquil'),
    es_predeterminado   BIT NOT NULL CONSTRAINT df_horarios_pred DEFAULT (0),
    activo              BIT NOT NULL CONSTRAINT df_horarios_activo DEFAULT (1)
);
GO

/* Varios tramos por día (p. ej. mañana y tarde con almuerzo en medio). dia_semana: 1 = lunes … 7 = domingo */
IF OBJECT_ID(N'dbo.horario_tramos', N'U') IS NULL
CREATE TABLE dbo.horario_tramos (
    id              INT IDENTITY(1,1) CONSTRAINT pk_horario_tramos PRIMARY KEY,
    horario_id      INT NOT NULL CONSTRAINT fk_tramos_horario REFERENCES dbo.horarios_laborales(id) ON DELETE CASCADE,
    dia_semana      TINYINT NOT NULL CONSTRAINT ck_tramos_dia CHECK (dia_semana BETWEEN 1 AND 7),
    hora_inicio     TIME(0) NOT NULL,
    hora_fin        TIME(0) NOT NULL,
    CONSTRAINT ck_tramos_rango CHECK (hora_fin > hora_inicio)
);
GO

/* Feriados (día no laborable) u horarios especiales (jornada reducida). */
IF OBJECT_ID(N'dbo.calendario_excepciones', N'U') IS NULL
CREATE TABLE dbo.calendario_excepciones (
    id              INT IDENTITY(1,1) CONSTRAINT pk_cal_excepciones PRIMARY KEY,
    horario_id      INT NULL CONSTRAINT fk_calexc_horario REFERENCES dbo.horarios_laborales(id),  -- NULL = aplica a todos
    fecha           DATE NOT NULL,
    tipo            VARCHAR(20) NOT NULL CONSTRAINT ck_calexc_tipo CHECK (tipo IN ('FERIADO','HORARIO_ESPECIAL')),
    hora_inicio     TIME(0) NULL,
    hora_fin        TIME(0) NULL,
    descripcion     NVARCHAR(200) NOT NULL,
    CONSTRAINT ck_calexc_horas CHECK (tipo = 'FERIADO' OR (hora_inicio IS NOT NULL AND hora_fin > hora_inicio))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_calexc_fecha')
    CREATE INDEX ix_calexc_fecha ON dbo.calendario_excepciones(fecha);
GO

/* ---------------------------------------------------------------------
   TICKETS
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.estados', N'U') IS NULL
CREATE TABLE dbo.estados (
    codigo          VARCHAR(20)  NOT NULL CONSTRAINT pk_estados PRIMARY KEY,
    nombre          NVARCHAR(50) NOT NULL,
    orden           INT NOT NULL,
    color           CHAR(7) NULL,
    pausa_sla       BIT NOT NULL,       -- el reloj del SLA se detiene en este estado
    es_final        BIT NOT NULL        -- ticket ya no está abierto
);
GO

IF OBJECT_ID(N'dbo.ticket_secuencias', N'U') IS NULL
CREATE TABLE dbo.ticket_secuencias (
    anio        INT NOT NULL CONSTRAINT pk_ticket_secuencias PRIMARY KEY,
    ultimo      INT NOT NULL
);
GO

IF OBJECT_ID(N'dbo.tickets', N'U') IS NULL
CREATE TABLE dbo.tickets (
    id                       BIGINT IDENTITY(1,1) CONSTRAINT pk_tickets PRIMARY KEY,
    numero                   VARCHAR(20)   NOT NULL CONSTRAINT uq_tickets_numero UNIQUE,   -- ADU-2026-000123
    asunto                   NVARCHAR(200) NOT NULL,
    descripcion              NVARCHAR(MAX) NOT NULL,
    -- Solicitante (se copia al crear para conservar el dato histórico)
    solicitante_id           INT NOT NULL CONSTRAINT fk_tickets_solicitante REFERENCES dbo.usuarios(id),
    solicitante_nombre       NVARCHAR(150) NOT NULL,
    solicitante_cargo        NVARCHAR(100) NULL,
    area_id                  INT NULL CONSTRAINT fk_tickets_area REFERENCES dbo.areas(id),
    cliente_id               INT NULL CONSTRAINT fk_tickets_cliente REFERENCES dbo.clientes(id),
    correo                   NVARCHAR(150) NOT NULL,
    telefono                 NVARCHAR(30)  NULL,
    -- Clasificación
    categoria_id             INT NOT NULL CONSTRAINT fk_tickets_categoria REFERENCES dbo.categorias(id),
    subcategoria_id          INT NOT NULL CONSTRAINT fk_tickets_subcategoria REFERENCES dbo.subcategorias(id),
    prioridad_id             INT NOT NULL CONSTRAINT fk_tickets_prioridad REFERENCES dbo.prioridades(id),
    responsable_id           INT NULL CONSTRAINT fk_tickets_responsable REFERENCES dbo.usuarios(id),
    estado                   VARCHAR(20) NOT NULL CONSTRAINT fk_tickets_estado REFERENCES dbo.estados(codigo),
    canal                    VARCHAR(20) NOT NULL CONSTRAINT df_tickets_canal DEFAULT ('PORTAL'),
    -- Fechas del ciclo de vida
    fecha_creacion           DATETIME2(0) NOT NULL CONSTRAINT df_tickets_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_asignacion         DATETIME2(0) NULL,
    fecha_primera_respuesta  DATETIME2(0) NULL,
    fecha_resolucion         DATETIME2(0) NULL,
    fecha_cierre             DATETIME2(0) NULL,
    fecha_actualizacion      DATETIME2(0) NULL,
    -- SLA (minutos laborables)
    sla_respuesta_min        INT NOT NULL,
    sla_resolucion_min       INT NOT NULL,
    sla_respuesta_vence      DATETIME2(0) NOT NULL,
    sla_resolucion_vence     DATETIME2(0) NOT NULL,
    sla_minutos_pausa        INT NOT NULL CONSTRAINT df_tickets_pausa DEFAULT (0),
    sla_minutos_extension    INT NOT NULL CONSTRAINT df_tickets_ext DEFAULT (0),
    sla_pausa_desde          DATETIME2(0) NULL,
    sla_minutos_consumidos   INT NOT NULL CONSTRAINT df_tickets_consumidos DEFAULT (0),
    sla_consumido_pct        DECIMAL(7,2) NOT NULL CONSTRAINT df_tickets_pct DEFAULT (0),
    sla_respuesta_cumplido   BIT NULL,
    sla_resolucion_cumplido  BIT NULL,
    sla_incumplido           BIT NOT NULL CONSTRAINT df_tickets_incumplido DEFAULT (0),
    sla_excluido             BIT NOT NULL CONSTRAINT df_tickets_excluido DEFAULT (0),
    sla_nivel_alerta         TINYINT NOT NULL CONSTRAINT df_tickets_alerta DEFAULT (0),     -- 0, 75, 90, 100
    minutos_respuesta        INT NULL,       -- minutos laborables hasta la primera respuesta (sin pausas)
    minutos_resolucion       INT NULL,       -- minutos laborables hasta la resolución (sin pausas)
    -- Otros
    reaperturas              INT NOT NULL CONSTRAINT df_tickets_reaperturas DEFAULT (0),
    resumen_ia               NVARCHAR(1000) NULL,
    riesgo_ia                DECIMAL(5,2) NULL,
    version                  INT NOT NULL CONSTRAINT df_tickets_version DEFAULT (1),       -- concurrencia optimista
    eliminado                BIT NOT NULL CONSTRAINT df_tickets_eliminado DEFAULT (0),
    eliminado_por            INT NULL,
    fecha_eliminacion        DATETIME2(0) NULL,
    -- Columna calculada: texto de cumplimiento para reportes
    cumplimiento_sla AS (CASE WHEN sla_excluido = 1 THEN 'EXCLUIDO'
                              WHEN sla_incumplido = 1 THEN 'INCUMPLIDO'
                              WHEN sla_resolucion_cumplido = 1 THEN 'CUMPLIDO'
                              ELSE 'EN_CURSO' END)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_estado')
    CREATE INDEX ix_tickets_estado ON dbo.tickets(estado, eliminado) INCLUDE (sla_consumido_pct, responsable_id, categoria_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_responsable')
    CREATE INDEX ix_tickets_responsable ON dbo.tickets(responsable_id, estado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_categoria')
    CREATE INDEX ix_tickets_categoria ON dbo.tickets(categoria_id, fecha_creacion);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_solicitante')
    CREATE INDEX ix_tickets_solicitante ON dbo.tickets(solicitante_id, fecha_creacion);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_cliente')
    CREATE INDEX ix_tickets_cliente ON dbo.tickets(cliente_id, fecha_creacion);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_fecha')
    CREATE INDEX ix_tickets_fecha ON dbo.tickets(fecha_creacion) INCLUDE (estado, sla_incumplido);
GO

IF OBJECT_ID(N'dbo.ticket_comentarios', N'U') IS NULL
CREATE TABLE dbo.ticket_comentarios (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_comentarios PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_comentarios_ticket REFERENCES dbo.tickets(id),
    usuario_id      INT NOT NULL CONSTRAINT fk_comentarios_usuario REFERENCES dbo.usuarios(id),
    texto           NVARCHAR(MAX) NOT NULL,
    es_interno      BIT NOT NULL CONSTRAINT df_comentarios_interno DEFAULT (0),   -- nota interna, no visible al cliente
    tipo            VARCHAR(20) NOT NULL CONSTRAINT df_comentarios_tipo DEFAULT ('COMENTARIO'),   -- COMENTARIO | ACTIVIDAD | SISTEMA
    minutos_invertidos INT NULL,
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_comentarios_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_comentarios_ticket')
    CREATE INDEX ix_comentarios_ticket ON dbo.ticket_comentarios(ticket_id, fecha);
GO

IF OBJECT_ID(N'dbo.ticket_adjuntos', N'U') IS NULL
CREATE TABLE dbo.ticket_adjuntos (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_adjuntos PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_adjuntos_ticket REFERENCES dbo.tickets(id),
    comentario_id   BIGINT NULL CONSTRAINT fk_adjuntos_comentario REFERENCES dbo.ticket_comentarios(id),
    nombre_original NVARCHAR(255) NOT NULL,
    ruta_almacenamiento NVARCHAR(400) NOT NULL,
    tipo_mime       VARCHAR(100) NOT NULL,
    tamano_bytes    BIGINT NOT NULL,
    hash_sha256     CHAR(64) NOT NULL,
    subido_por      INT NOT NULL CONSTRAINT fk_adjuntos_usuario REFERENCES dbo.usuarios(id),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_adjuntos_fecha DEFAULT (SYSUTCDATETIME()),
    eliminado       BIT NOT NULL CONSTRAINT df_adjuntos_eliminado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_adjuntos_ticket')
    CREATE INDEX ix_adjuntos_ticket ON dbo.ticket_adjuntos(ticket_id);
GO

/* Historial de cambios de campos (trazabilidad del ticket). */
IF OBJECT_ID(N'dbo.ticket_historial', N'U') IS NULL
CREATE TABLE dbo.ticket_historial (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_historial PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_historial_ticket REFERENCES dbo.tickets(id),
    usuario_id      INT NULL CONSTRAINT fk_historial_usuario REFERENCES dbo.usuarios(id),   -- NULL = sistema
    accion          VARCHAR(40) NOT NULL,      -- CREACION, EDICION, CAMBIO_ESTADO, ASIGNACION, ESCALAMIENTO, ...
    campo           VARCHAR(60) NULL,
    valor_anterior  NVARCHAR(500) NULL,
    valor_nuevo     NVARCHAR(500) NULL,
    detalle         NVARCHAR(1000) NULL,
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_historial_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_historial_ticket')
    CREATE INDEX ix_historial_ticket ON dbo.ticket_historial(ticket_id, fecha);
GO

IF OBJECT_ID(N'dbo.ticket_asignaciones', N'U') IS NULL
CREATE TABLE dbo.ticket_asignaciones (
    id                 BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_asignaciones PRIMARY KEY,
    ticket_id          BIGINT NOT NULL CONSTRAINT fk_asignaciones_ticket REFERENCES dbo.tickets(id),
    responsable_anterior_id INT NULL CONSTRAINT fk_asignaciones_anterior REFERENCES dbo.usuarios(id),
    responsable_nuevo_id    INT NOT NULL CONSTRAINT fk_asignaciones_nuevo REFERENCES dbo.usuarios(id),
    asignado_por       INT NULL CONSTRAINT fk_asignaciones_por REFERENCES dbo.usuarios(id),   -- NULL = automática
    tipo               VARCHAR(20) NOT NULL,     -- AUTOMATICA | MANUAL | REASIGNACION | ESCALAMIENTO
    motivo             NVARCHAR(500) NULL,
    fecha              DATETIME2(0) NOT NULL CONSTRAINT df_asignaciones_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_asignaciones_ticket')
    CREATE INDEX ix_asignaciones_ticket ON dbo.ticket_asignaciones(ticket_id);
GO

IF OBJECT_ID(N'dbo.ticket_escalamientos', N'U') IS NULL
CREATE TABLE dbo.ticket_escalamientos (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_escalamientos PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_escalamientos_ticket REFERENCES dbo.tickets(id),
    nivel           TINYINT NOT NULL,        -- 75, 90, 100 (automático) o 0 (manual)
    tipo            VARCHAR(10) NOT NULL CONSTRAINT ck_escalamientos_tipo CHECK (tipo IN ('AUTOMATICO','MANUAL')),
    escalado_por    INT NULL CONSTRAINT fk_escalamientos_por REFERENCES dbo.usuarios(id),
    escalado_a      INT NULL CONSTRAINT fk_escalamientos_a REFERENCES dbo.usuarios(id),
    motivo          NVARCHAR(500) NULL,
    sla_consumido_pct DECIMAL(7,2) NULL,
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_escalamientos_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_escalamientos_ticket')
    CREATE INDEX ix_escalamientos_ticket ON dbo.ticket_escalamientos(ticket_id);
GO

/* Intervalos en que el reloj estuvo detenido (Pendiente Cliente, Resuelto, …). */
IF OBJECT_ID(N'dbo.sla_pausas', N'U') IS NULL
CREATE TABLE dbo.sla_pausas (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_sla_pausas PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_pausas_ticket REFERENCES dbo.tickets(id),
    estado          VARCHAR(20) NOT NULL,
    inicio          DATETIME2(0) NOT NULL,
    fin             DATETIME2(0) NULL,
    minutos_laborables INT NULL,
    usuario_id      INT NULL CONSTRAINT fk_pausas_usuario REFERENCES dbo.usuarios(id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_pausas_ticket')
    CREATE INDEX ix_pausas_ticket ON dbo.sla_pausas(ticket_id, fin);
GO

/* Excepciones aprobadas a nivel de ticket. */
IF OBJECT_ID(N'dbo.sla_excepciones', N'U') IS NULL
CREATE TABLE dbo.sla_excepciones (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_sla_excepciones PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_slaexc_ticket REFERENCES dbo.tickets(id),
    tipo            VARCHAR(15) NOT NULL CONSTRAINT ck_slaexc_tipo CHECK (tipo IN ('EXTENSION','EXCLUSION')),
    minutos         INT NULL,
    motivo          NVARCHAR(500) NOT NULL,
    aprobado_por    INT NOT NULL CONSTRAINT fk_slaexc_usuario REFERENCES dbo.usuarios(id),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_slaexc_fecha DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'dbo.sla_incumplimientos', N'U') IS NULL
CREATE TABLE dbo.sla_incumplimientos (
    id                  BIGINT IDENTITY(1,1) CONSTRAINT pk_sla_incumplimientos PRIMARY KEY,
    ticket_id           BIGINT NOT NULL CONSTRAINT fk_incump_ticket REFERENCES dbo.tickets(id),
    tipo                VARCHAR(15) NOT NULL CONSTRAINT ck_incump_tipo CHECK (tipo IN ('RESPUESTA','RESOLUCION')),
    responsable_id      INT NULL CONSTRAINT fk_incump_responsable REFERENCES dbo.usuarios(id),
    categoria_id        INT NOT NULL CONSTRAINT fk_incump_categoria REFERENCES dbo.categorias(id),
    prioridad_id        INT NOT NULL CONSTRAINT fk_incump_prioridad REFERENCES dbo.prioridades(id),
    fecha_vencimiento   DATETIME2(0) NOT NULL,
    fecha_registro      DATETIME2(0) NOT NULL CONSTRAINT df_incump_fecha DEFAULT (SYSUTCDATETIME()),
    justificacion       NVARCHAR(1000) NULL,
    CONSTRAINT uq_sla_incumplimientos UNIQUE (ticket_id, tipo, fecha_vencimiento)
);
GO

/* ---------------------------------------------------------------------
   NOTIFICACIONES
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.notificaciones', N'U') IS NULL
CREATE TABLE dbo.notificaciones (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_notificaciones PRIMARY KEY,
    usuario_id      INT NOT NULL CONSTRAINT fk_notif_usuario REFERENCES dbo.usuarios(id),
    ticket_id       BIGINT NULL CONSTRAINT fk_notif_ticket REFERENCES dbo.tickets(id),
    tipo            VARCHAR(30) NOT NULL,     -- TICKET_CREADO, TICKET_ASIGNADO, SLA_75, SLA_90, SLA_VENCIDO, ...
    severidad       VARCHAR(10) NOT NULL CONSTRAINT df_notif_sev DEFAULT ('INFO'),   -- INFO | AVISO | CRITICO
    titulo          NVARCHAR(200) NOT NULL,
    mensaje         NVARCHAR(1000) NOT NULL,
    leida           BIT NOT NULL CONSTRAINT df_notif_leida DEFAULT (0),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_notif_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_lectura   DATETIME2(0) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_notif_usuario')
    CREATE INDEX ix_notif_usuario ON dbo.notificaciones(usuario_id, leida, fecha DESC);
GO

IF OBJECT_ID(N'dbo.plantillas_correo', N'U') IS NULL
CREATE TABLE dbo.plantillas_correo (
    codigo          VARCHAR(30) NOT NULL CONSTRAINT pk_plantillas_correo PRIMARY KEY,
    asunto          NVARCHAR(200) NOT NULL,
    cuerpo_html     NVARCHAR(MAX) NOT NULL,
    activo          BIT NOT NULL CONSTRAINT df_plantillas_activo DEFAULT (1)
);
GO

IF OBJECT_ID(N'dbo.cola_correos', N'U') IS NULL
CREATE TABLE dbo.cola_correos (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_cola_correos PRIMARY KEY,
    para            NVARCHAR(500) NOT NULL,
    cc              NVARCHAR(500) NULL,
    asunto          NVARCHAR(250) NOT NULL,
    cuerpo_html     NVARCHAR(MAX) NOT NULL,
    ticket_id       BIGINT NULL CONSTRAINT fk_cola_ticket REFERENCES dbo.tickets(id),
    plantilla       VARCHAR(30) NULL,
    estado          VARCHAR(12) NOT NULL CONSTRAINT df_cola_estado DEFAULT ('PENDIENTE')
                    CONSTRAINT ck_cola_estado CHECK (estado IN ('PENDIENTE','ENVIADO','ERROR','DESCARTADO')),
    intentos        INT NOT NULL CONSTRAINT df_cola_intentos DEFAULT (0),
    ultimo_error    NVARCHAR(1000) NULL,
    proximo_intento DATETIME2(0) NOT NULL CONSTRAINT df_cola_proximo DEFAULT (SYSUTCDATETIME()),
    fecha_creacion  DATETIME2(0) NOT NULL CONSTRAINT df_cola_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_envio     DATETIME2(0) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_cola_pendientes')
    CREATE INDEX ix_cola_pendientes ON dbo.cola_correos(estado, proximo_intento);
GO

/* ---------------------------------------------------------------------
   AUDITORÍA (inmutable: ver trigger en 05_triggers.sql)
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.auditoria', N'U') IS NULL
CREATE TABLE dbo.auditoria (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_auditoria PRIMARY KEY,
    usuario_id      INT NULL,
    usuario_correo  NVARCHAR(150) NULL,
    fecha_hora      DATETIME2(3) NOT NULL CONSTRAINT df_auditoria_fecha DEFAULT (SYSUTCDATETIME()),
    accion          VARCHAR(40) NOT NULL,     -- LOGIN, LOGOUT, LOGIN_FALLIDO, TICKET_CREADO, ...
    entidad         VARCHAR(40) NULL,
    entidad_id      VARCHAR(40) NULL,
    detalle         NVARCHAR(MAX) NULL,       -- JSON
    ip              VARCHAR(45) NULL,
    equipo          NVARCHAR(300) NULL,       -- user-agent / nombre de equipo
    resultado       VARCHAR(10) NOT NULL CONSTRAINT df_auditoria_resultado DEFAULT ('OK')
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_auditoria_fecha')
    CREATE INDEX ix_auditoria_fecha ON dbo.auditoria(fecha_hora DESC) INCLUDE (accion, usuario_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_auditoria_usuario')
    CREATE INDEX ix_auditoria_usuario ON dbo.auditoria(usuario_id, fecha_hora DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_auditoria_entidad')
    CREATE INDEX ix_auditoria_entidad ON dbo.auditoria(entidad, entidad_id);
GO

/* ---------------------------------------------------------------------
   INTELIGENCIA ARTIFICIAL Y CONFIGURACIÓN
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.ia_sugerencias', N'U') IS NULL
CREATE TABLE dbo.ia_sugerencias (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ia_sugerencias PRIMARY KEY,
    ticket_id       BIGINT NULL CONSTRAINT fk_ia_ticket REFERENCES dbo.tickets(id),
    tipo            VARCHAR(20) NOT NULL,     -- CLASIFICACION, PRIORIDAD, RESPONSABLE, RESPUESTA, RIESGO, RESUMEN
    valor           NVARCHAR(MAX) NOT NULL,   -- JSON
    confianza       DECIMAL(5,2) NULL,
    proveedor       VARCHAR(20) NOT NULL,     -- LOCAL | LLM
    aceptada        BIT NULL,
    usuario_id      INT NULL CONSTRAINT fk_ia_usuario REFERENCES dbo.usuarios(id),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_ia_fecha DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'dbo.configuracion', N'U') IS NULL
CREATE TABLE dbo.configuracion (
    clave           VARCHAR(60) NOT NULL CONSTRAINT pk_configuracion PRIMARY KEY,
    valor           NVARCHAR(1000) NOT NULL,
    descripcion     NVARCHAR(300) NULL,
    fecha_actualizacion DATETIME2(0) NOT NULL CONSTRAINT df_config_fecha DEFAULT (SYSUTCDATETIME()),
    actualizado_por INT NULL
);
GO

/* Bloqueo con expiración para que solo un worker procese el SLA a la vez. */
IF OBJECT_ID(N'dbo.bloqueos_proceso', N'U') IS NULL
CREATE TABLE dbo.bloqueos_proceso (
    nombre          VARCHAR(50) NOT NULL CONSTRAINT pk_bloqueos PRIMARY KEY,
    propietario     VARCHAR(100) NOT NULL,
    expira          DATETIME2(0) NOT NULL
);
GO

PRINT N'01_tablas.sql aplicado.';
GO
