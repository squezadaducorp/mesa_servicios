/* =====================================================================
   Tercera ronda de mejoras. Idempotente (se ejecuta en cada arranque vía db-init).
   No borra ni cambia datos existentes: solo agrega tablas, un estado, permisos, plantillas y parámetros.
   20. Seguimiento sin cuenta (parámetros seguimiento.*, plantilla SEGUIMIENTO_ENLACE)
   21. Aprobaciones del jefe (estado POR_APROBAR, aprobacion_reglas, ticket_aprobaciones)
   22. Tickets vinculados y unir duplicados (ticket_vinculos)
   23. Acciones en lote y traspaso de cartera (solo plantilla TICKET_NUEVO_RESPONSABLE)
   24. Avisos generales (avisos_generales, aviso_actualizaciones, aviso_afectados)
   El «Jefe directo» de cada usuario es la columna existente usuarios.supervisor_id.
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 21. Estado «Por aprobar» (SLA en pausa) ---------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.estados WHERE codigo = 'POR_APROBAR')
    INSERT INTO dbo.estados (codigo, nombre, orden, color, pausa_sla, es_final)
    VALUES ('POR_APROBAR', N'Por aprobar', 0, '#B57400', 1, 0);
GO

IF OBJECT_ID(N'dbo.aprobacion_reglas', N'U') IS NULL
CREATE TABLE dbo.aprobacion_reglas (
    id                 INT IDENTITY(1,1) CONSTRAINT pk_aprobacion_reglas PRIMARY KEY,
    categoria_id       INT NOT NULL CONSTRAINT fk_aprreg_categoria REFERENCES dbo.categorias(id),
    subcategoria_id    INT NULL CONSTRAINT fk_aprreg_subcategoria REFERENCES dbo.subcategorias(id),
    nivel1_tipo        VARCHAR(20) NOT NULL CONSTRAINT ck_aprreg_n1 CHECK (nivel1_tipo IN ('JEFE_DIRECTO','SUPERVISOR_CATEGORIA','PERSONA')),
    nivel1_usuario_id  INT NULL CONSTRAINT fk_aprreg_n1_usuario REFERENCES dbo.usuarios(id),
    nivel2_tipo        VARCHAR(20) NULL CONSTRAINT ck_aprreg_n2 CHECK (nivel2_tipo IN ('JEFE_DIRECTO','SUPERVISOR_CATEGORIA','PERSONA')),
    nivel2_usuario_id  INT NULL CONSTRAINT fk_aprreg_n2_usuario REFERENCES dbo.usuarios(id),
    recordar_horas     INT NOT NULL CONSTRAINT df_aprreg_recordar DEFAULT (4),
    escalar_horas      INT NULL,
    escalar_a_id       INT NULL CONSTRAINT fk_aprreg_escalar REFERENCES dbo.usuarios(id),
    usar_reemplazo     BIT NOT NULL CONSTRAINT df_aprreg_reemplazo DEFAULT (1),
    auto_si_aprobador  BIT NOT NULL CONSTRAINT df_aprreg_auto DEFAULT (1),
    activo             BIT NOT NULL CONSTRAINT df_aprreg_activo DEFAULT (1),
    creado_por         INT NULL CONSTRAINT fk_aprreg_creado REFERENCES dbo.usuarios(id),
    fecha_creacion     DATETIME2(0) NOT NULL CONSTRAINT df_aprreg_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_actualizacion DATETIME2(0) NULL
);
GO
IF OBJECT_ID(N'dbo.ticket_aprobaciones', N'U') IS NULL
CREATE TABLE dbo.ticket_aprobaciones (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_aprobaciones PRIMARY KEY,
    ticket_id        BIGINT NOT NULL CONSTRAINT fk_tkapr_ticket REFERENCES dbo.tickets(id),
    regla_id         INT NULL CONSTRAINT fk_tkapr_regla REFERENCES dbo.aprobacion_reglas(id),
    nivel            SMALLINT NOT NULL CONSTRAINT df_tkapr_nivel DEFAULT (1),
    aprobador_id     INT NOT NULL CONSTRAINT fk_tkapr_aprobador REFERENCES dbo.usuarios(id),
    en_lugar_de_id   INT NULL CONSTRAINT fk_tkapr_en_lugar REFERENCES dbo.usuarios(id),
    estado           VARCHAR(12) NOT NULL CONSTRAINT df_tkapr_estado DEFAULT ('PENDIENTE')
                     CONSTRAINT ck_tkapr_estado CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','REASIGNADO','ANULADO')),
    comentario       NVARCHAR(1000) NULL,
    fecha_solicitud  DATETIME2(0) NOT NULL CONSTRAINT df_tkapr_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_respuesta  DATETIME2(0) NULL,
    recordado        BIT NOT NULL CONSTRAINT df_tkapr_recordado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tkapr_aprobador')
    CREATE INDEX ix_tkapr_aprobador ON dbo.ticket_aprobaciones(aprobador_id, estado);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tkapr_ticket')
    CREATE INDEX ix_tkapr_ticket ON dbo.ticket_aprobaciones(ticket_id);
GO

/* ---------------- 22. Tickets vinculados ---------------- */
IF OBJECT_ID(N'dbo.ticket_vinculos', N'U') IS NULL
CREATE TABLE dbo.ticket_vinculos (
    id              BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_vinculos PRIMARY KEY,
    ticket_id       BIGINT NOT NULL CONSTRAINT fk_vinc_ticket REFERENCES dbo.tickets(id),
    relacionado_id  BIGINT NOT NULL CONSTRAINT fk_vinc_relacionado REFERENCES dbo.tickets(id),
    tipo            VARCHAR(15) NOT NULL CONSTRAINT ck_vinc_tipo CHECK (tipo IN ('RELACIONADO','DUPLICADO','BLOQUEADO_POR','NO_DUPLICADO')),
    creado_por      INT NULL CONSTRAINT fk_vinc_creado REFERENCES dbo.usuarios(id),
    fecha           DATETIME2(0) NOT NULL CONSTRAINT df_vinc_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT ck_vinc_distintos CHECK (ticket_id <> relacionado_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_vinc_ticket')
    CREATE INDEX ix_vinc_ticket ON dbo.ticket_vinculos(ticket_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_vinc_relacionado')
    CREATE INDEX ix_vinc_relacionado ON dbo.ticket_vinculos(relacionado_id);
GO

/* ---------------- 24. Avisos generales ---------------- */
IF OBJECT_ID(N'dbo.avisos_generales', N'U') IS NULL
CREATE TABLE dbo.avisos_generales (
    id                 INT IDENTITY(1,1) CONSTRAINT pk_avisos_generales PRIMARY KEY,
    titulo             NVARCHAR(200) NOT NULL,
    mensaje            NVARCHAR(1000) NOT NULL,
    sistema            NVARCHAR(100) NOT NULL,
    palabras_clave     NVARCHAR(500) NULL,
    areas              VARCHAR(300) NULL,
    mostrar_publico    BIT NOT NULL CONSTRAINT df_avisos_publico DEFAULT (0),
    estado             VARCHAR(15) NOT NULL CONSTRAINT df_avisos_estado DEFAULT ('INVESTIGANDO')
                       CONSTRAINT ck_avisos_estado CHECK (estado IN ('INVESTIGANDO','IDENTIFICADO','MONITOREANDO','RESUELTO')),
    ticket_maestro_id  BIGINT NULL CONSTRAINT fk_avisos_ticket REFERENCES dbo.tickets(id),
    inicio             DATETIME2(0) NOT NULL CONSTRAINT df_avisos_inicio DEFAULT (SYSUTCDATETIME()),
    fin                DATETIME2(0) NULL,
    proxima_novedad    NVARCHAR(100) NULL,
    creado_por         INT NULL CONSTRAINT fk_avisos_creado REFERENCES dbo.usuarios(id),
    fecha_actualizacion DATETIME2(0) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_avisos_estado')
    CREATE INDEX ix_avisos_estado ON dbo.avisos_generales(estado, inicio DESC);
GO
IF OBJECT_ID(N'dbo.aviso_actualizaciones', N'U') IS NULL
CREATE TABLE dbo.aviso_actualizaciones (
    id          BIGINT IDENTITY(1,1) CONSTRAINT pk_aviso_actualizaciones PRIMARY KEY,
    aviso_id    INT NOT NULL CONSTRAINT fk_avact_aviso REFERENCES dbo.avisos_generales(id),
    estado      VARCHAR(15) NOT NULL,
    texto       NVARCHAR(1000) NOT NULL,
    usuario_id  INT NULL CONSTRAINT fk_avact_usuario REFERENCES dbo.usuarios(id),
    fecha       DATETIME2(0) NOT NULL CONSTRAINT df_avact_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'dbo.aviso_afectados', N'U') IS NULL
CREATE TABLE dbo.aviso_afectados (
    aviso_id    INT NOT NULL CONSTRAINT fk_avafe_aviso REFERENCES dbo.avisos_generales(id),
    usuario_id  INT NOT NULL CONSTRAINT fk_avafe_usuario REFERENCES dbo.usuarios(id),
    comentario  NVARCHAR(500) NULL,
    ticket_id   BIGINT NULL CONSTRAINT fk_avafe_ticket REFERENCES dbo.tickets(id),
    fecha       DATETIME2(0) NOT NULL CONSTRAINT df_avafe_fecha DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT pk_aviso_afectados PRIMARY KEY (aviso_id, usuario_id)
);
GO

/* ---------------- Permisos nuevos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('aprobaciones.gestionar', N'Aprobaciones',      N'Configurar las reglas de aprobación del jefe'),
    ('avisos.gestionar',       N'Avisos generales',  N'Publicar y actualizar avisos de caídas que afectan a muchos')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);
GO
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', 'aprobaciones.gestionar' UNION ALL SELECT 'SUPER_ADMIN', 'avisos.gestionar'
    UNION ALL SELECT 'ADMIN_MESA', 'aprobaciones.gestionar' UNION ALL SELECT 'ADMIN_MESA', 'avisos.gestionar'
    UNION ALL SELECT 'SUPERVISOR', 'avisos.gestionar'
)
INSERT INTO dbo.rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM m
JOIN dbo.roles r ON r.codigo = m.rol
JOIN dbo.permisos p ON p.codigo = m.permiso
WHERE NOT EXISTS (SELECT 1 FROM dbo.rol_permisos rp WHERE rp.rol_id = r.id AND rp.permiso_id = p.id);
GO

/* ---------------- Plantillas de correo (solo se agregan si no existen) ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('APROBACION_SOLICITADA', N'[Aprobación] {numero} · {asunto}',
        N'<p>Hola {destinatario},</p><p><b>{pedido_por}</b> pide «{asunto}» ({categoria}) y necesita su visto bueno antes de que la Mesa de Servicios lo atienda.</p><p>{detalle}</p><p><a href="{url_aprobar}" style="background:#2E7D32;color:#fff;padding:9px 18px;border-radius:6px;text-decoration:none">Aprobar</a> &nbsp; <a href="{url_rechazar}" style="background:#fff;color:#C62828;border:1px solid #C62828;padding:8px 18px;border-radius:6px;text-decoration:none">Rechazar</a></p><p style="color:#5A6577;font-size:13px">Los botones abren la Mesa de Servicios; allí confirma con un clic.</p>'),
    ('APROBACION_RECORDATORIO', N'[Recordatorio] {numero} espera su aprobación',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» sigue esperando su visto bueno desde {desde}.</p><p><a href="{url_aprobar}">Revisar y responder</a></p>'),
    ('APROBACION_RESULTADO', N'[{numero}] Su solicitud fue {resultado}',
        N'<p>Hola {destinatario},</p><p>{aprobador} <b>{resultado}</b> la solicitud <b>{numero}</b> «{asunto}».</p><p>{comentario}</p><p><a href="{url}">Ver ticket</a></p>'),
    ('TICKET_NUEVO_RESPONSABLE', N'[{numero}] Ahora lo atiende {responsable}',
        N'<p>Hola {destinatario},</p><p>Su solicitud <b>{numero}</b> «{asunto}» ahora la atiende <b>{responsable}</b>. El plazo de atención se mantiene.</p><p><a href="{url}">Ver ticket</a></p>'),
    ('TICKETS_UNIDOS', N'[{numero}] Su solicitud se atiende junto con otras',
        N'<p>Hola {destinatario},</p><p>{comentario}</p><p>Su solicitud <b>{duplicado}</b> se unió a <b>{numero}</b> «{asunto}». Recibirá las novedades de ese ticket.</p><p><a href="{url}">Ver ticket</a></p>'),
    ('SEGUIMIENTO_ENLACE', N'[{numero}] Enlace para ver el estado de su solicitud',
        N'<p>Hola {destinatario},</p><p>Nos pidió un enlace para ver el estado de la solicitud <b>{numero}</b> «{asunto}».</p><p><a href="{url_seguimiento}" style="background:#1367AC;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none">Ver el estado de mi solicitud</a></p><p style="color:#5A6577;font-size:13px">No necesita usuario ni contraseña. Este enlace es solo para usted: no lo reenvíe.</p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

/* ---------------- Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('seguimiento.activo',             N'si', N'Seguimiento sin cuenta: botón «Ver el estado de mi solicitud» en los correos a externos (si/no)'),
    ('seguimiento.dias_vigencia',      N'30', N'Días que sigue funcionando el enlace de seguimiento después de cerrar el ticket'),
    ('seguimiento.permitir_responder', N'si', N'Desde el enlace de seguimiento el externo puede responder y adjuntar (si/no)')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO

/* ---------------- Clientes por dominio de correo ----------------
   Cada cliente (empresa) puede tener los dominios de correo de su gente: quien crea un ticket desde esos correos
   queda con ese cliente. El personal de ADUCORP (@aducorp.com.ec) queda como «Aducorp CIA LTDA».
   Solo completa tickets SIN cliente; nunca cambia uno ya elegido. */
IF COL_LENGTH(N'dbo.clientes', N'dominios') IS NULL
    ALTER TABLE dbo.clientes ADD dominios NVARCHAR(300) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM dbo.clientes WHERE razon_social = N'Aducorp CIA LTDA')
    AND NOT EXISTS (SELECT 1 FROM dbo.clientes WHERE dominios LIKE N'%aducorp.com.ec%')
    INSERT INTO dbo.clientes (razon_social, nombre_comercial, dominios) VALUES (N'Aducorp CIA LTDA', N'ADUCORP', N'aducorp.com.ec');
GO
UPDATE dbo.clientes SET dominios = N'aducorp.com.ec'
WHERE razon_social = N'Aducorp CIA LTDA' AND dominios IS NULL
  AND NOT EXISTS (SELECT 1 FROM dbo.clientes WHERE dominios LIKE N'%aducorp.com.ec%');
GO
/* Completar tickets sin cliente según el dominio del correo de contacto (o del solicitante, si no es una cuenta técnica) */
UPDATE t SET t.cliente_id = c.id
FROM dbo.tickets t
JOIN dbo.usuarios u ON u.id = t.solicitante_id
CROSS APPLY (SELECT TOP 1 cl.id FROM dbo.clientes cl
             WHERE cl.activo = 1 AND cl.eliminado = 0 AND cl.dominios IS NOT NULL
               AND (CONCAT(N',', REPLACE(cl.dominios, N' ', N''), N',') LIKE CONCAT(N'%,', LOWER(SUBSTRING(t.correo, CHARINDEX(N'@', t.correo) + 1, 150)), N',%')
                    OR (LOWER(u.correo) NOT LIKE N'formulario-web@%' AND LOWER(u.correo) NOT LIKE N'mesaservicios@%' AND LOWER(u.correo) NOT LIKE N'soporte@%'
                        AND CONCAT(N',', REPLACE(cl.dominios, N' ', N''), N',') LIKE CONCAT(N'%,', LOWER(SUBSTRING(u.correo, CHARINDEX(N'@', u.correo) + 1, 150)), N',%')))
             ORDER BY cl.id) c
WHERE t.cliente_id IS NULL AND CHARINDEX(N'@', t.correo) > 0;
GO

PRINT N'12_tercera_ronda aplicado';
GO
