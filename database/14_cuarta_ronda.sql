/* =====================================================================
   Cuarta ronda, parte 1. Idempotente (se ejecuta en cada arranque vía db-init).
   No borra ni cambia datos existentes: solo agrega columnas, tablas, permisos, una plantilla y parámetros.
   26. Catálogo de servicios con formularios (servicios_catalogo, ticket_solicitudes_servicio, ticket_tareas)
       + categoría «Servicios de TI» con los 8 servicios iniciales (solo si el catálogo está vacío)
   27. Gestión de cambios (cambios, cambio_aprobaciones, cambio_historial, cambio_adjuntos, cambio_congelamientos)
   28. Verificación en dos pasos (columnas usuarios.dosf_*, dosf_equipos, dosf_desafios). La política queda APAGADA:
       nadie tiene que hacer nada hasta que el administrador la active en Seguridad de la cuenta.
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 28. Columnas de verificación en dos pasos ---------------- */
IF COL_LENGTH('dbo.usuarios', 'dosf_metodo') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_metodo VARCHAR(10) NULL CONSTRAINT ck_usuarios_dosf CHECK (dosf_metodo IN ('APP','CORREO'));
IF COL_LENGTH('dbo.usuarios', 'dosf_secreto') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_secreto VARCHAR(300) NULL;
IF COL_LENGTH('dbo.usuarios', 'dosf_pendiente') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_pendiente VARCHAR(300) NULL;
IF COL_LENGTH('dbo.usuarios', 'dosf_codigos') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_codigos NVARCHAR(1500) NULL;
IF COL_LENGTH('dbo.usuarios', 'dosf_fecha') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_fecha DATETIME2(0) NULL;
IF COL_LENGTH('dbo.usuarios', 'dosf_ultimo_paso') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_ultimo_paso BIGINT NULL;
IF COL_LENGTH('dbo.usuarios', 'dosf_exigido_desde') IS NULL
    ALTER TABLE dbo.usuarios ADD dosf_exigido_desde DATETIME2(0) NULL;
GO

IF OBJECT_ID(N'dbo.dosf_equipos', N'U') IS NULL
CREATE TABLE dbo.dosf_equipos (
    id                BIGINT IDENTITY(1,1) CONSTRAINT pk_dosf_equipos PRIMARY KEY,
    usuario_id        INT NOT NULL CONSTRAINT fk_dosfeq_usuario REFERENCES dbo.usuarios(id),
    token_hash        CHAR(64) NOT NULL CONSTRAINT uq_dosfeq_token UNIQUE,
    equipo            NVARCHAR(300) NULL,
    ip                VARCHAR(45) NULL,
    fecha_creacion    DATETIME2(0) NOT NULL CONSTRAINT df_dosfeq_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_expiracion  DATETIME2(0) NOT NULL,
    revocado          BIT NOT NULL CONSTRAINT df_dosfeq_revocado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_dosfeq_usuario')
    CREATE INDEX ix_dosfeq_usuario ON dbo.dosf_equipos(usuario_id, revocado);
GO
IF OBJECT_ID(N'dbo.dosf_desafios', N'U') IS NULL
CREATE TABLE dbo.dosf_desafios (
    id                BIGINT IDENTITY(1,1) CONSTRAINT pk_dosf_desafios PRIMARY KEY,
    token_hash        CHAR(64) NOT NULL CONSTRAINT uq_dosfde_token UNIQUE,
    usuario_id        INT NOT NULL CONSTRAINT fk_dosfde_usuario REFERENCES dbo.usuarios(id),
    proposito         VARCHAR(10) NOT NULL CONSTRAINT ck_dosfde_proposito CHECK (proposito IN ('LOGIN','ACTIVAR')),
    codigo_hash       CHAR(64) NULL,
    codigo_expira     DATETIME2(0) NULL,
    envios            INT NOT NULL CONSTRAINT df_dosfde_envios DEFAULT (0),
    intentos          INT NOT NULL CONSTRAINT df_dosfde_intentos DEFAULT (0),
    usado             BIT NOT NULL CONSTRAINT df_dosfde_usado DEFAULT (0),
    fecha_creacion    DATETIME2(0) NOT NULL CONSTRAINT df_dosfde_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_expiracion  DATETIME2(0) NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_dosfde_usuario')
    CREATE INDEX ix_dosfde_usuario ON dbo.dosf_desafios(usuario_id, proposito, usado);
GO

/* ---------------- 26. Catálogo de servicios ---------------- */
IF OBJECT_ID(N'dbo.servicios_catalogo', N'U') IS NULL
CREATE TABLE dbo.servicios_catalogo (
    id                  INT IDENTITY(1,1) CONSTRAINT pk_servicios_catalogo PRIMARY KEY,
    nombre              NVARCHAR(120) NOT NULL,
    descripcion         NVARCHAR(400) NOT NULL,
    icono               VARCHAR(30) NOT NULL CONSTRAINT df_servcat_icono DEFAULT ('servicio'),
    grupo               NVARCHAR(30) NOT NULL CONSTRAINT df_servcat_grupo DEFAULT (N'Accesos'),
    categoria_id        INT NOT NULL CONSTRAINT fk_servcat_categoria REFERENCES dbo.categorias(id),
    subcategoria_id     INT NOT NULL CONSTRAINT fk_servcat_subcategoria REFERENCES dbo.subcategorias(id),
    plazo_horas         INT NOT NULL CONSTRAINT df_servcat_plazo DEFAULT (8),
    plazo_texto         NVARCHAR(40) NULL,
    requiere_aprobacion BIT NOT NULL CONSTRAINT df_servcat_aprob DEFAULT (0),
    lo_pide             NVARCHAR(100) NULL,
    titulo_campos       NVARCHAR(150) NULL,
    titulo_opciones     NVARCHAR(150) NULL,
    aviso               NVARCHAR(500) NULL,
    campos              NVARCHAR(MAX) NULL,
    opciones            NVARCHAR(MAX) NULL,
    orden               INT NOT NULL CONSTRAINT df_servcat_orden DEFAULT (0),
    activo              BIT NOT NULL CONSTRAINT df_servcat_activo DEFAULT (1),
    creado_por          INT NULL CONSTRAINT fk_servcat_creado REFERENCES dbo.usuarios(id),
    fecha_creacion      DATETIME2(0) NOT NULL CONSTRAINT df_servcat_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion DATETIME2(0) NULL
);
GO
IF OBJECT_ID(N'dbo.ticket_solicitudes_servicio', N'U') IS NULL
CREATE TABLE dbo.ticket_solicitudes_servicio (
    ticket_id    BIGINT NOT NULL CONSTRAINT pk_ticket_solicitudes_servicio PRIMARY KEY CONSTRAINT fk_tksol_ticket REFERENCES dbo.tickets(id),
    servicio_id  INT NOT NULL CONSTRAINT fk_tksol_servicio REFERENCES dbo.servicios_catalogo(id),
    respuestas   NVARCHAR(MAX) NOT NULL,
    fecha        DATETIME2(0) NOT NULL CONSTRAINT df_tksol_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'dbo.ticket_tareas', N'U') IS NULL
CREATE TABLE dbo.ticket_tareas (
    id                BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_tareas PRIMARY KEY,
    ticket_id         BIGINT NOT NULL CONSTRAINT fk_tktarea_ticket REFERENCES dbo.tickets(id),
    titulo            NVARCHAR(200) NOT NULL,
    responsable_id    INT NULL CONSTRAINT fk_tktarea_responsable REFERENCES dbo.usuarios(id),
    estado            VARCHAR(10) NOT NULL CONSTRAINT df_tktarea_estado DEFAULT ('PENDIENTE')
                      CONSTRAINT ck_tktarea_estado CHECK (estado IN ('PENDIENTE','LISTA')),
    orden             INT NOT NULL CONSTRAINT df_tktarea_orden DEFAULT (0),
    completada_por    INT NULL CONSTRAINT fk_tktarea_completada REFERENCES dbo.usuarios(id),
    fecha_completada  DATETIME2(0) NULL,
    fecha             DATETIME2(0) NOT NULL CONSTRAINT df_tktarea_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tktarea_ticket')
    CREATE INDEX ix_tktarea_ticket ON dbo.ticket_tareas(ticket_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tktarea_responsable')
    CREATE INDEX ix_tktarea_responsable ON dbo.ticket_tareas(responsable_id, estado);
GO

/* ---------------- 27. Gestión de cambios ---------------- */
IF OBJECT_ID(N'dbo.cambios', N'U') IS NULL
CREATE TABLE dbo.cambios (
    id                   INT IDENTITY(1,1) CONSTRAINT pk_cambios PRIMARY KEY,
    numero               VARCHAR(20) NOT NULL CONSTRAINT uq_cambios_numero UNIQUE,
    anio                 INT NOT NULL,
    secuencia            INT NOT NULL,
    formato              VARCHAR(10) NOT NULL CONSTRAINT df_cambios_formato DEFAULT ('MESA') CONSTRAINT ck_cambios_formato CHECK (formato IN ('MESA','GENERAL')),
    titulo               NVARCHAR(200) NOT NULL,
    solicitante_id       INT NOT NULL CONSTRAINT fk_cambios_solicitante REFERENCES dbo.usuarios(id),
    telefono             NVARCHAR(30) NULL,
    tipo_solicitud       VARCHAR(15) NOT NULL,
    aplicacion           NVARCHAR(150) NULL,
    partes               NVARCHAR(500) NULL,
    pantalla             NVARCHAR(200) NULL,
    desde_donde          VARCHAR(12) NULL,
    ticket_relacionado   NVARCHAR(200) NULL,
    situacion_actual     NVARCHAR(MAX) NOT NULL,
    situacion_deseada    NVARCHAR(MAX) NOT NULL,
    justificacion        NVARCHAR(MAX) NULL,
    beneficiados         VARCHAR(15) NULL,
    prioridad_sugerida   VARCHAR(5) NOT NULL CONSTRAINT df_cambios_prioridad DEFAULT ('MEDIA'),
    clasificacion        VARCHAR(15) NULL,
    tipo_cambio          VARCHAR(12) NULL CONSTRAINT ck_cambios_tipo CHECK (tipo_cambio IN ('ESTANDAR','NORMAL','EMERGENCIA')),
    impacto              VARCHAR(5) NULL,
    probabilidad         VARCHAR(5) NULL,
    riesgo               VARCHAR(5) NULL,
    esfuerzo             VARCHAR(10) NULL,
    prioridad_ti         VARCHAR(5) NULL,
    evaluacion           NVARCHAR(MAX) NULL,
    plan_implementacion  NVARCHAR(MAX) NULL,
    plan_reversion       NVARCHAR(MAX) NULL,
    responsable_id       INT NULL CONSTRAINT fk_cambios_responsable REFERENCES dbo.usuarios(id),
    evaluado_por_id      INT NULL CONSTRAINT fk_cambios_evaluado REFERENCES dbo.usuarios(id),
    fecha_evaluacion     DATETIME2(0) NULL,
    ventana_inicio       DATETIME2(0) NULL,
    ventana_fin          DATETIME2(0) NULL,
    fecha_implementado   DATETIME2(0) NULL,
    version_ref          NVARCHAR(100) NULL,
    resultado            VARCHAR(15) NULL,
    probado_solicitante  BIT NULL,
    fecha_informado      DATETIME2(0) NULL,
    observaciones        NVARCHAR(MAX) NULL,
    motivo               NVARCHAR(1000) NULL,
    estado               VARCHAR(15) NOT NULL CONSTRAINT df_cambios_estado DEFAULT ('SOLICITADO')
                         CONSTRAINT ck_cambios_estado CHECK (estado IN ('SOLICITADO','EN_ESPERA','EN_APROBACION','PROGRAMADO','EN_REVISION','IMPLEMENTADO','REVERTIDO','RECHAZADO')),
    fecha_creacion       DATETIME2(0) NOT NULL CONSTRAINT df_cambios_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion  DATETIME2(0) NULL,
    CONSTRAINT uq_cambios_secuencia UNIQUE (anio, secuencia)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_cambios_ventana')
    CREATE INDEX ix_cambios_ventana ON dbo.cambios(ventana_inicio, ventana_fin) INCLUDE (estado);
GO
IF OBJECT_ID(N'dbo.cambio_aprobaciones', N'U') IS NULL
CREATE TABLE dbo.cambio_aprobaciones (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_cambio_aprobaciones PRIMARY KEY,
    cambio_id        INT NOT NULL CONSTRAINT fk_camapr_cambio REFERENCES dbo.cambios(id),
    rol              VARCHAR(10) NOT NULL CONSTRAINT ck_camapr_rol CHECK (rol IN ('JEFE_TI','GERENCIA')),
    aprobador_id     INT NOT NULL CONSTRAINT fk_camapr_aprobador REFERENCES dbo.usuarios(id),
    estado           VARCHAR(10) NOT NULL CONSTRAINT df_camapr_estado DEFAULT ('PENDIENTE')
                     CONSTRAINT ck_camapr_estado CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','ANULADO')),
    comentario       NVARCHAR(1000) NULL,
    fecha_solicitud  DATETIME2(0) NOT NULL CONSTRAINT df_camapr_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_respuesta  DATETIME2(0) NULL,
    recordado        BIT NOT NULL CONSTRAINT df_camapr_recordado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_camapr_cambio')
    CREATE INDEX ix_camapr_cambio ON dbo.cambio_aprobaciones(cambio_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_camapr_aprobador')
    CREATE INDEX ix_camapr_aprobador ON dbo.cambio_aprobaciones(aprobador_id, estado);
GO
IF OBJECT_ID(N'dbo.cambio_historial', N'U') IS NULL
CREATE TABLE dbo.cambio_historial (
    id          BIGINT IDENTITY(1,1) CONSTRAINT pk_cambio_historial PRIMARY KEY,
    cambio_id   INT NOT NULL CONSTRAINT fk_camhist_cambio REFERENCES dbo.cambios(id),
    usuario_id  INT NULL CONSTRAINT fk_camhist_usuario REFERENCES dbo.usuarios(id),
    accion      VARCHAR(30) NOT NULL,
    detalle     NVARCHAR(1000) NULL,
    fecha       DATETIME2(0) NOT NULL CONSTRAINT df_camhist_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_camhist_cambio')
    CREATE INDEX ix_camhist_cambio ON dbo.cambio_historial(cambio_id);
GO
IF OBJECT_ID(N'dbo.cambio_adjuntos', N'U') IS NULL
CREATE TABLE dbo.cambio_adjuntos (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_cambio_adjuntos PRIMARY KEY,
    cambio_id        INT NOT NULL CONSTRAINT fk_camadj_cambio REFERENCES dbo.cambios(id),
    nombre_original  NVARCHAR(255) NOT NULL,
    ruta             NVARCHAR(400) NOT NULL,
    tipo_mime        VARCHAR(100) NULL,
    tamano_bytes     INT NOT NULL,
    usuario_id       INT NULL CONSTRAINT fk_camadj_usuario REFERENCES dbo.usuarios(id),
    fecha            DATETIME2(0) NOT NULL CONSTRAINT df_camadj_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'dbo.cambio_congelamientos', N'U') IS NULL
CREATE TABLE dbo.cambio_congelamientos (
    id          INT IDENTITY(1,1) CONSTRAINT pk_cambio_congelamientos PRIMARY KEY,
    titulo      NVARCHAR(150) NOT NULL,
    inicio      DATETIME2(0) NOT NULL,
    fin         DATETIME2(0) NOT NULL,
    motivo      NVARCHAR(500) NULL,
    creado_por  INT NULL CONSTRAINT fk_camcong_creado REFERENCES dbo.usuarios(id),
    fecha       DATETIME2(0) NOT NULL CONSTRAINT df_camcong_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT ck_camcong_rango CHECK (fin > inicio)
);
GO

/* ---------------- Permisos nuevos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('servicios.gestionar', N'Catálogo de servicios', N'Crear y editar los servicios del catálogo, sus formularios y tareas'),
    ('cambios.gestionar',   N'Gestión de cambios',    N'Evaluar (sección 7), programar, implementar y revisar cambios; definir congelamientos'),
    ('cambios.ver',         N'Gestión de cambios',    N'Ver el registro completo de cambios')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);
GO
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', 'servicios.gestionar' UNION ALL SELECT 'SUPER_ADMIN', 'cambios.gestionar' UNION ALL SELECT 'SUPER_ADMIN', 'cambios.ver'
    UNION ALL SELECT 'ADMIN_MESA', 'servicios.gestionar' UNION ALL SELECT 'ADMIN_MESA', 'cambios.gestionar' UNION ALL SELECT 'ADMIN_MESA', 'cambios.ver'
    UNION ALL SELECT 'SUPERVISOR', 'cambios.ver' UNION ALL SELECT 'GERENCIA', 'cambios.ver'
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
    ('TAREA_ASIGNADA', N'[{numero}] Tarea para usted: {asunto}',
        N'<p>Hola {destinatario},</p><p>La solicitud <b>{numero}</b> «{asunto}» tiene tareas para usted:</p><p><b>{tarea}</b></p><p>Márquelas como listas en la Mesa de Servicios cuando las termine.</p><p><a href="{url}">Abrir el ticket</a></p>')
) AS s (codigo, asunto, cuerpo)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (s.codigo, s.asunto, s.cuerpo);
GO

/* ---------------- Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('cambios.jefe_ti',              N'squezada@aducorp.com.ec', N'Correo del Jefe de TI: aprueba los cambios normales y de emergencia'),
    ('cambios.gerencia',             N'',                        N'Correo de quien aprueba por Gerencia los cambios de riesgo medio o alto (vacío = sin esa aprobación)'),
    ('cambios.congelar_cierre_mes',  N'si',                      N'No permitir cambios el último día hábil de cada mes (cierre), salvo emergencias (si/no)'),
    ('cambios.aplicaciones',         N'Mesa de Servicios, Correo / Microsoft 365, ECUAPASS, Sistema contable, Página web aducorp.com.ec, Servidor de archivos, Red e internet, Otra',
                                     N'Aplicaciones que se pueden elegir en el formato TI-FOR-002, separadas por coma'),
    ('seguridad.2fa_admin',          N'no',  N'Verificación en dos pasos obligatoria para Administrador y Supervisor (si/no)'),
    ('seguridad.2fa_analistas',      N'no',  N'Verificación en dos pasos obligatoria para Analistas (si/no)'),
    ('seguridad.2fa_opcional_otros', N'si',  N'Verificación en dos pasos opcional para clientes internos y gerencia (si = opcional, no = obligatoria)'),
    ('seguridad.2fa_correo',         N'si',  N'Permitir el código por correo como alternativa al celular (solo si el envío de correos está activo)'),
    ('seguridad.2fa_solo_fuera_oficina', N'no', N'Pedir el código solo al entrar desde fuera de la oficina (si/no)'),
    ('seguridad.2fa_redes_oficina',  N'',    N'IP o redes de la oficina separadas por coma, p. ej. 186.46.10.20, 192.168.1.0/24'),
    ('seguridad.2fa_dias_confianza', N'30',  N'Días que se recuerda un equipo de confianza (0 = no ofrecer)'),
    ('seguridad.2fa_exentos',        N'admin@aducorp.com.ec', N'Cuentas de emergencia fuera de la política, separadas por coma')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO

/* ---------------- 26. Categoría «Servicios de TI» y servicios iniciales ----------------
   Solo la primera vez (catálogo vacío). Después se administran en Administración › Catálogo de servicios.
   La categoría queda sin responsables: asígnelos en Categorías y clientes para que las solicitudes se repartan solas. */
IF NOT EXISTS (SELECT 1 FROM dbo.servicios_catalogo)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.categorias WHERE codigo = 'SERVICIOS_TI')
        INSERT INTO dbo.categorias (codigo, nombre, descripcion, palabras_clave, color, orden, modo_asignacion)
        VALUES ('SERVICIOS_TI', N'Servicios de TI', N'Solicitudes del catálogo de servicios: accesos, equipos, altas y bajas de personal',
                N'acceso,usuario nuevo,alta,baja,equipo,portátil,laptop,impresora,vpn,carpeta,buzón,token,firma electrónica', '#1367AC', 10, 'PRINCIPAL');

    DECLARE @cat INT = (SELECT id FROM dbo.categorias WHERE codigo = 'SERVICIOS_TI');
    INSERT INTO dbo.subcategorias (categoria_id, nombre, palabras_clave)
    SELECT @cat, s.nombre, LOWER(s.nombre)
    FROM (VALUES (N'Accesos'), (N'Equipos'), (N'Personal'), (N'Aduanas')) AS s (nombre)
    WHERE NOT EXISTS (SELECT 1 FROM dbo.subcategorias x WHERE x.categoria_id = @cat AND x.nombre = s.nombre);

    INSERT INTO dbo.servicios_catalogo (orden, nombre, descripcion, icono, grupo, categoria_id, subcategoria_id, plazo_horas, plazo_texto,
                                        requiere_aprobacion, lo_pide, titulo_campos, titulo_opciones, aviso, campos, opciones)
    SELECT v.orden, v.nombre, v.descripcion, v.icono, v.grupo, @cat, sc.id, v.plazo_horas, v.plazo_texto, v.requiere_aprobacion, v.lo_pide,
           v.titulo_campos, v.titulo_opciones, v.aviso, v.campos, v.opciones
    FROM (VALUES
    (1, N'Alta de usuario nuevo', N'Correo, equipo, carpetas y accesos para quien ingresa a la empresa.', N'alta', N'Personal', N'Personal', 16, NULL, 1, N'Talento Humano', N'Datos de la persona que ingresa', N'¿Qué necesita para trabajar?', NULL, N'[{"clave": "nombres", "etiqueta": "Nombres y apellidos", "tipo": "texto", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "fecha_ingreso", "etiqueta": "Fecha de ingreso", "tipo": "fecha", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "area", "etiqueta": "Área", "tipo": "area", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "cargo", "etiqueta": "Cargo", "tipo": "texto", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "jefe", "etiqueta": "Jefe directo", "tipo": "usuario", "requerido": true, "opciones": [], "ancho": 2, "aprobador": true, "ayuda": null}, {"clave": "sucursal", "etiqueta": "Sucursal", "tipo": "lista", "requerido": true, "opciones": ["Guayaquil · Matriz", "Guayaquil · Puerto Marítimo", "Quito · Aeropuerto", "Manta"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "correo", "etiqueta": "Correo @aducorp.com.ec", "tarea": "Crear correo y licencia M365", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "portatil", "etiqueta": "Portátil", "tarea": "Preparar portátil e imagen", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "ecuapass", "etiqueta": "Usuario en ECUAPASS (perfil liquidador)", "tarea": "Alta en ECUAPASS · perfil liquidador", "responsable_id": null, "marcado": false, "siempre": false, "aviso": "ECUAPASS requiere que la persona esté registrada como auxiliar del agente en SENAE. TI le enviará el formulario a firmar."}, {"clave": "carpeta", "etiqueta": "Carpeta Importaciones 2026", "tarea": "Permiso carpeta Importaciones 2026", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "contable", "etiqueta": "Sistema contable (consulta)", "tarea": "Usuario de consulta en el sistema contable", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "vpn", "etiqueta": "VPN para teletrabajo", "tarea": "Configurar VPN", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "token", "etiqueta": "Token de firma electrónica", "tarea": "Tramitar token de firma electrónica", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "extension", "etiqueta": "Extensión telefónica", "tarea": "Extensión telefónica", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "buzon_operaciones", "etiqueta": "Buzón operaciones@", "tarea": "Acceso a buzón operaciones@", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}]'),
    (2, N'Acceso a ECUAPASS', N'Alta, cambio de perfil o renovación del usuario del agente en el portal de SENAE.', N'llave', N'Aduanas', N'Aduanas', 8, NULL, 1, N'Operaciones', N'Datos del usuario', N'¿Qué necesita?', N'ECUAPASS requiere que la persona esté registrada como auxiliar del agente en SENAE.', N'[{"clave": "persona", "etiqueta": "Persona", "tipo": "usuario", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "perfil", "etiqueta": "Perfil", "tipo": "lista", "requerido": true, "opciones": ["Liquidador", "Tramitador", "Consulta"], "ancho": 1, "aprobador": false, "ayuda": null}]', N'[{"clave": "alta", "etiqueta": "Alta de usuario", "tarea": "Alta en ECUAPASS", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "perfil", "etiqueta": "Cambio de perfil", "tarea": "Cambio de perfil en ECUAPASS", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "renovacion", "etiqueta": "Renovación", "tarea": "Renovación del usuario ECUAPASS", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}]'),
    (3, N'Token de firma electrónica', N'Emisión o renovación del certificado (Security Data / BCE) para firmar DAI.', N'token', N'Aduanas', N'Aduanas', 24, NULL, 1, N'Operaciones', N'Datos del titular', NULL, NULL, N'[{"clave": "titular", "etiqueta": "Titular", "tipo": "usuario", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "cedula", "etiqueta": "Cédula", "tipo": "cedula", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "tramite", "etiqueta": "Trámite", "tipo": "lista", "requerido": true, "opciones": ["Emisión", "Renovación"], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "entidad", "etiqueta": "Entidad", "tipo": "lista", "requerido": true, "opciones": ["Security Data", "Banco Central (BCE)"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "tramitar", "etiqueta": "Tramitar el certificado", "tarea": "Tramitar token de firma electrónica", "responsable_id": null, "marcado": false, "siempre": true, "aviso": null}]'),
    (4, N'Equipo nuevo o reemplazo', N'Portátil, monitor, impresora o periférico, con entrega y acta.', N'equipo', N'Equipos', N'Equipos', 40, NULL, 1, NULL, N'¿Para quién y por qué?', N'¿Qué equipo necesita?', NULL, N'[{"clave": "para", "etiqueta": "Para", "tipo": "usuario", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "motivo", "etiqueta": "Motivo", "tipo": "lista", "requerido": true, "opciones": ["Equipo nuevo", "Reemplazo por daño", "Reemplazo por antigüedad"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "portatil", "etiqueta": "Portátil", "tarea": "Preparar portátil e imagen", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "monitor", "etiqueta": "Monitor", "tarea": "Entregar monitor", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "impresora", "etiqueta": "Impresora", "tarea": "Instalar impresora", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "periferico", "etiqueta": "Teclado, mouse u otro periférico", "tarea": "Entregar periférico", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}, {"clave": "acta", "etiqueta": "Acta de entrega", "tarea": "Firmar acta de entrega", "responsable_id": null, "marcado": false, "siempre": true, "aviso": null}]'),
    (5, N'Acceso a carpeta compartida', N'Lectura o escritura en carpetas del servidor de archivos (p. ej. Importaciones 2026).', N'carpeta', N'Accesos', N'Accesos', 4, NULL, 1, NULL, NULL, NULL, NULL, N'[{"clave": "carpeta", "etiqueta": "Carpeta", "tipo": "texto", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "permiso", "etiqueta": "Permiso", "tipo": "lista", "requerido": true, "opciones": ["Solo lectura", "Lectura y escritura"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "permiso", "etiqueta": "Dar el permiso", "tarea": "Dar permiso en la carpeta", "responsable_id": null, "marcado": false, "siempre": true, "aviso": null}]'),
    (6, N'Buzón compartido o lista', N'Acceso a buzones como facturacion@ u operaciones@, o crear una lista de correo.', N'buzon', N'Accesos', N'Accesos', 4, NULL, 0, NULL, NULL, NULL, NULL, N'[{"clave": "buzon", "etiqueta": "Buzón o lista", "tipo": "texto", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "accion", "etiqueta": "¿Qué necesita?", "tipo": "lista", "requerido": true, "opciones": ["Acceso a un buzón existente", "Crear una lista de correo"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "configurar", "etiqueta": "Configurar", "tarea": "Configurar el buzón o la lista", "responsable_id": null, "marcado": false, "siempre": true, "aviso": null}]'),
    (7, N'VPN para teletrabajo', N'Conexión segura desde casa al sistema contable y al servidor de archivos.', N'vpn', N'Accesos', N'Accesos', 8, NULL, 1, NULL, NULL, NULL, NULL, N'[{"clave": "desde", "etiqueta": "Desde", "tipo": "fecha", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "hasta", "etiqueta": "Hasta (opcional)", "tipo": "fecha", "requerido": false, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "equipo", "etiqueta": "Equipo desde el que se conecta", "tipo": "lista", "requerido": true, "opciones": ["Portátil de la empresa", "Computadora personal"], "ancho": 2, "aprobador": false, "ayuda": null}]', N'[{"clave": "vpn", "etiqueta": "Configurar VPN", "tarea": "Configurar VPN", "responsable_id": null, "marcado": false, "siempre": true, "aviso": null}]'),
    (8, N'Baja de usuario', N'Quitar accesos, respaldar correo y recuperar equipos de quien sale de la empresa.', N'baja', N'Personal', N'Personal', 8, N'El mismo día', 0, N'Talento Humano', N'Datos de quien sale', N'¿Qué hay que hacer?', NULL, N'[{"clave": "persona", "etiqueta": "Persona que sale", "tipo": "usuario", "requerido": true, "opciones": [], "ancho": 2, "aprobador": false, "ayuda": null}, {"clave": "fecha_salida", "etiqueta": "Último día", "tipo": "fecha", "requerido": true, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}, {"clave": "reenviar", "etiqueta": "Reenviar su correo a", "tipo": "usuario", "requerido": false, "opciones": [], "ancho": 1, "aprobador": false, "ayuda": null}]', N'[{"clave": "accesos", "etiqueta": "Quitar todos los accesos", "tarea": "Desactivar usuario y accesos", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "correo", "etiqueta": "Respaldar el correo", "tarea": "Respaldar buzón y reenviar", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "equipos", "etiqueta": "Recuperar equipos", "tarea": "Recuperar equipos y actualizar inventario", "responsable_id": null, "marcado": true, "siempre": false, "aviso": null}, {"clave": "ecuapass", "etiqueta": "Dar de baja en ECUAPASS", "tarea": "Baja en ECUAPASS", "responsable_id": null, "marcado": false, "siempre": false, "aviso": null}]')

    ) AS v (orden, nombre, descripcion, icono, grupo, sub, plazo_horas, plazo_texto, requiere_aprobacion, lo_pide, titulo_campos, titulo_opciones, aviso, campos, opciones)
    JOIN dbo.subcategorias sc ON sc.categoria_id = @cat AND sc.nombre = v.sub;
END
GO
PRINT N'14_cuarta_ronda.sql aplicado';
GO
