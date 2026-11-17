/* =====================================================================
   Mejoras post-piloto. Idempotente (se ejecuta en cada arranque vía db-init).
   - Avisos antes de vencer el SLA por tiempo que falta + aviso previo de 1.ª respuesta + resumen diario
   - Encuesta de satisfacción (ticket_encuestas)
   - Ausencias / vacaciones con reemplazo (usuario_ausencias, ausencia_tickets)
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- 9. Avisos antes de vencer ---------------- */
IF COL_LENGTH(N'dbo.tickets', N'sla_aviso_respuesta') IS NULL
    ALTER TABLE dbo.tickets ADD sla_aviso_respuesta BIT NOT NULL CONSTRAINT df_tickets_aviso_respuesta DEFAULT (0);
GO
-- Pestaña «Por vencer hoy» y resumen diario: tickets abiertos por responsable y vencimiento
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_tickets_responsable_vence')
    CREATE INDEX ix_tickets_responsable_vence ON dbo.tickets(responsable_id, sla_resolucion_vence) INCLUDE (estado, sla_pausa_desde);
GO

/* ---------------- 1. Encuesta de satisfacción ---------------- */
IF OBJECT_ID(N'dbo.ticket_encuestas', N'U') IS NULL
CREATE TABLE dbo.ticket_encuestas (
    id               BIGINT IDENTITY(1,1) CONSTRAINT pk_ticket_encuestas PRIMARY KEY,
    ticket_id        BIGINT NOT NULL CONSTRAINT fk_encuestas_ticket REFERENCES dbo.tickets(id),
    calificacion     SMALLINT NOT NULL CONSTRAINT ck_encuestas_calificacion CHECK (calificacion BETWEEN 1 AND 5),
    comentario       NVARCHAR(1000) NULL,
    usuario_id       INT NULL CONSTRAINT fk_encuestas_usuario REFERENCES dbo.usuarios(id),       -- NULL = respondió desde el correo
    responsable_id   INT NULL CONSTRAINT fk_encuestas_responsable REFERENCES dbo.usuarios(id),
    categoria_id     INT NOT NULL CONSTRAINT fk_encuestas_categoria REFERENCES dbo.categorias(id),
    origen           VARCHAR(10) NOT NULL CONSTRAINT df_encuestas_origen DEFAULT ('PORTAL')
                     CONSTRAINT ck_encuestas_origen CHECK (origen IN ('PORTAL','CORREO')),
    fecha            DATETIME2(0) NOT NULL CONSTRAINT df_encuestas_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_comentario DATETIME2(0) NULL,
    CONSTRAINT ux_ticket_encuestas UNIQUE (ticket_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_encuestas_fecha')
    CREATE INDEX ix_encuestas_fecha ON dbo.ticket_encuestas(fecha) INCLUDE (calificacion, responsable_id, categoria_id);
GO

/* ---------------- 4. Ausencias con reemplazo ---------------- */
IF OBJECT_ID(N'dbo.usuario_ausencias', N'U') IS NULL
CREATE TABLE dbo.usuario_ausencias (
    id                  INT IDENTITY(1,1) CONSTRAINT pk_usuario_ausencias PRIMARY KEY,
    usuario_id          INT NOT NULL CONSTRAINT fk_ausencias_usuario REFERENCES dbo.usuarios(id),
    reemplazo_id        INT NOT NULL CONSTRAINT fk_ausencias_reemplazo REFERENCES dbo.usuarios(id),
    motivo              VARCHAR(15) NOT NULL CONSTRAINT df_ausencias_motivo DEFAULT ('VACACIONES')
                        CONSTRAINT ck_ausencias_motivo CHECK (motivo IN ('VACACIONES','PERMISO','ENFERMEDAD','CAPACITACION','OTRO')),
    desde               DATETIME2(0) NOT NULL,
    hasta               DATETIME2(0) NOT NULL,
    pasar_abiertos      BIT NOT NULL CONSTRAINT df_ausencias_pasar DEFAULT (1),
    devolver            BIT NOT NULL CONSTRAINT df_ausencias_devolver DEFAULT (1),
    avisar_solicitantes BIT NOT NULL CONSTRAINT df_ausencias_avisar DEFAULT (1),
    estado              VARCHAR(12) NOT NULL CONSTRAINT df_ausencias_estado DEFAULT ('PROGRAMADA')
                        CONSTRAINT ck_ausencias_estado CHECK (estado IN ('PROGRAMADA','ACTIVA','FINALIZADA','CANCELADA')),
    creado_por          INT NULL CONSTRAINT fk_ausencias_creado_por REFERENCES dbo.usuarios(id),
    fecha_creacion      DATETIME2(0) NOT NULL CONSTRAINT df_ausencias_fecha DEFAULT (SYSUTCDATETIME()),
    fecha_inicio_real   DATETIME2(0) NULL,
    fecha_fin_real      DATETIME2(0) NULL,
    CONSTRAINT ck_ausencias_rango CHECK (hasta > desde),
    CONSTRAINT ck_ausencias_reemplazo CHECK (reemplazo_id <> usuario_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_ausencias_estado')
    CREATE INDEX ix_ausencias_estado ON dbo.usuario_ausencias(estado, desde, hasta) INCLUDE (usuario_id, reemplazo_id);
GO
IF OBJECT_ID(N'dbo.ausencia_tickets', N'U') IS NULL
CREATE TABLE dbo.ausencia_tickets (
    ausencia_id  INT NOT NULL CONSTRAINT fk_ausencia_tickets_ausencia REFERENCES dbo.usuario_ausencias(id) ON DELETE CASCADE,
    ticket_id    BIGINT NOT NULL CONSTRAINT fk_ausencia_tickets_ticket REFERENCES dbo.tickets(id),
    devuelto     BIT NOT NULL CONSTRAINT df_ausencia_tickets_devuelto DEFAULT (0),
    CONSTRAINT pk_ausencia_tickets PRIMARY KEY (ausencia_id, ticket_id)
);
GO

/* ---------------- Plantillas de correo ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('SLA_AVISO_1', N'[{numero}] Vence en {restante}: {asunto}',
        N'<p>Hola {destinatario},</p><p>Al ticket <b>{numero}</b> «{asunto}» (prioridad <b>{prioridad}</b>) le quedan <b>{restante}</b> laborables para vencer.</p><p>Vence: {sla_resolucion_vence}</p><p><a href="{url}">Atender ahora</a></p>'),
    ('SLA_AVISO_2', N'[{numero}] Vence en {restante}: requiere acción',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» asignado a <b>{responsable}</b> vence en <b>{restante}</b> laborables ({sla_resolucion_vence}).</p><p>Resuélvalo o, si necesita más tiempo, pida una extensión al supervisor.</p><p><a href="{url}">Revisar ticket</a></p>'),
    ('SLA_AVISO_RESPUESTA', N'[{numero}] Falta la primera respuesta ({restante})',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» aún no tiene primera respuesta. Le quedan <b>{restante}</b> laborables para responder al solicitante ({sla_respuesta_vence}).</p><p><a href="{url}">Responder ahora</a></p>'),
    ('ENCUESTA', N'[{numero}] Su ticket fue resuelto: ¿cómo lo atendimos?',
        N'<p>Hola {destinatario},</p><p>Su ticket <b>{numero}</b> «{asunto}» fue resuelto por <b>{responsable}</b>. Toque una estrella para calificar la atención (toma menos de un minuto):</p><table cellpadding="0" cellspacing="6"><tr><td align="center"><a href="{url_nota_1}" style="display:inline-block;border:1px solid #E3E8F0;border-radius:6px;padding:6px 10px;color:#F5A623;font-size:22px;text-decoration:none">&#9733;<br><span style="font-size:11px;color:#5A6577">1</span></a></td><td align="center"><a href="{url_nota_2}" style="display:inline-block;border:1px solid #E3E8F0;border-radius:6px;padding:6px 10px;color:#F5A623;font-size:22px;text-decoration:none">&#9733;<br><span style="font-size:11px;color:#5A6577">2</span></a></td><td align="center"><a href="{url_nota_3}" style="display:inline-block;border:1px solid #E3E8F0;border-radius:6px;padding:6px 10px;color:#F5A623;font-size:22px;text-decoration:none">&#9733;<br><span style="font-size:11px;color:#5A6577">3</span></a></td><td align="center"><a href="{url_nota_4}" style="display:inline-block;border:1px solid #E3E8F0;border-radius:6px;padding:6px 10px;color:#F5A623;font-size:22px;text-decoration:none">&#9733;<br><span style="font-size:11px;color:#5A6577">4</span></a></td><td align="center"><a href="{url_nota_5}" style="display:inline-block;border:1px solid #E3E8F0;border-radius:6px;padding:6px 10px;color:#F5A623;font-size:22px;text-decoration:none">&#9733;<br><span style="font-size:11px;color:#5A6577">5</span></a></td></tr></table><p style="font-size:12px;color:#5A6577">1 = muy mala · 5 = excelente. Un clic registra la nota sin iniciar sesión; luego puede agregar un comentario. Si el problema persiste, puede reabrir el ticket.</p>'),
    ('ENCUESTA_BAJA', N'[{numero}] Calificación baja: {calificacion}/5',
        N'<p>Hola {destinatario},</p><p>El solicitante <b>{solicitante}</b> calificó con <b>{calificacion}/5</b> la atención del ticket <b>{numero}</b> «{asunto}» (responsable: {responsable}).</p><div style="white-space:pre-line;border-left:3px solid #C62828;padding:8px 12px;background:#F4F6FA">{comentario}</div><p><a href="{url}">Revisar ticket</a></p>'),
    ('AUSENCIA_REASIGNADO', N'[{numero}] Su ticket lo atiende {reemplazo}',
        N'<p>Hola {destinatario},</p><p>{ausente} está de {motivo} hasta el {regreso}. Su ticket <b>{numero}</b> «{asunto}» lo atiende ahora <b>{reemplazo}</b>; no necesita hacer nada.</p><p><a href="{url}">Ver ticket</a></p>')
) AS o (codigo, asunto, cuerpo_html)
ON d.codigo = o.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (o.codigo, o.asunto, o.cuerpo_html);
GO

/* ---------------- Configuración ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('sla.avisar_por',            N'tiempo', N'Avisos antes de vencer: «tiempo» (minutos que faltan) o «porcentaje» (umbral_aviso_1/2)'),
    ('sla.aviso_previo_1_min',    N'120',    N'1.er aviso al responsable: minutos laborables antes de vencer'),
    ('sla.aviso_previo_2_min',    N'30',     N'2.º aviso (responsable, supervisor y aviso en pantalla): minutos antes de vencer'),
    ('sla.aviso_respuesta_min',   N'60',     N'Aviso si falta la 1.ª respuesta: minutos antes de vencer (0 = desactivado)'),
    ('sla.resumen_diario_hora',   N'08:30',  N'Hora del correo «Hoy vencen…» a cada analista (vacío = desactivado)'),
    ('sla.resumen_diario_ultimo', N'',       N'Uso interno: último día en que se envió el resumen diario'),
    ('encuesta.activa',           N'si',     N'Encuesta de satisfacción al resolver un ticket (si/no)'),
    ('encuesta.aviso_nota_max',   N'2',      N'Calificación igual o menor que avisa al supervisor')
) AS o (clave, valor, descripcion)
ON d.clave = o.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (o.clave, o.valor, o.descripcion);
GO

PRINT N'10_mejoras_post_piloto aplicado';
GO
