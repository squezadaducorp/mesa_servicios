/* =====================================================================
   Seguridad: auditoría 2026-11 y mejoras ISO 27001 (37 acceso). Idempotente (db-init lo ejecuta en cada arranque).
   - Acuse del formulario público sin el asunto ni el nombre que escribió la persona (hallazgo 1).
   - 37: historial de contraseñas (usuario_claves_previas), días de gracia para la verificación en dos pasos,
         aviso de cuenta bloqueada y de ingreso con la cuenta de emergencia. La verificación pasa a ser
         obligatoria para Administradores y Supervisores UNA sola vez (si luego se apaga a mano, no se vuelve a encender).
   ===================================================================== */
SET NOCOUNT ON;
GO

/* ---------------- Hallazgo 1: acuse del formulario web con texto fijo ---------------- */
UPDATE dbo.plantillas_correo
SET asunto = N'[{numero}] Recibimos su solicitud',
    cuerpo_html = N'<p>Hola,</p><p>Recibimos su solicitud y registramos el ticket <b>{numero}</b> en la Mesa de Servicios de ADUCORP.</p><p>Categoría: <b>{categoria}</b><br>Prioridad: <b>{prioridad}</b><br>Responsable: <b>{responsable}</b></p><p>Resolución comprometida: {sla_resolucion_vence}</p><p>Le escribiremos a este correo con las novedades. Si necesita agregar información, registre una nueva solicitud en <a href="{url}">{url}</a> indicando el número <b>{numero}</b>.</p><p style="font-size:12px;color:#5A6577">Si usted no envió ninguna solicitud, puede ignorar este mensaje.</p>'
WHERE codigo = 'ACUSE_WEB' AND (asunto LIKE N'%{asunto}%' OR cuerpo_html LIKE N'%{asunto}%' OR cuerpo_html LIKE N'%{destinatario}%');
GO

/* ---------------- 37. Contraseñas anteriores ---------------- */
IF OBJECT_ID(N'dbo.usuario_claves_previas', N'U') IS NULL
CREATE TABLE dbo.usuario_claves_previas (
    id          BIGINT IDENTITY(1,1) CONSTRAINT pk_usuario_claves_previas PRIMARY KEY,
    usuario_id  INT NOT NULL CONSTRAINT fk_claves_previas_usuario REFERENCES dbo.usuarios(id),
    clave_hash  VARCHAR(100) NOT NULL,
    fecha       DATETIME2(0) NOT NULL CONSTRAINT df_claves_previas_fecha DEFAULT (SYSUTCDATETIME())
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_claves_previas_usuario')
    CREATE INDEX ix_claves_previas_usuario ON dbo.usuario_claves_previas(usuario_id, fecha DESC);
GO

/* ---------------- 37. Parámetros (solo se agregan si no existen) ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('seguridad.2fa_dias_gracia', N'7',  N'Días para configurar la verificación cuando pasa a ser obligatoria (0 = se exige en el siguiente ingreso)'),
    ('seguridad.claves_previas',  N'5',  N'Contraseñas anteriores que no se pueden repetir (incluye la actual; 0 = sin historial)'),
    ('seguridad.aviso_bloqueo',   N'si', N'Enviar un correo a la persona cuando su cuenta se bloquea por intentos fallidos (si/no)'),
    ('seguridad.correos_alerta',  N'squezada@aducorp.com.ec', N'Correos que reciben las alertas de seguridad (ingreso con la cuenta de emergencia), separados por coma')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO

/* ---------------- 37. Verificación obligatoria para Administradores y Supervisores (una sola vez) ---------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.configuracion WHERE clave = 'seguridad.iso37_aplicado')
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.configuracion WHERE clave = 'seguridad.2fa_admin')
        UPDATE dbo.configuracion SET valor = N'si', fecha_actualizacion = SYSUTCDATETIME() WHERE clave = 'seguridad.2fa_admin';
    ELSE
        INSERT INTO dbo.configuracion (clave, valor, descripcion)
        VALUES ('seguridad.2fa_admin', N'si', N'Verificación en dos pasos obligatoria para Administrador y Supervisor (si/no)');
    -- El plazo de gracia empieza hoy para quienes todavía no la configuraron
    UPDATE u SET dosf_exigido_desde = SYSUTCDATETIME()
    FROM dbo.usuarios u JOIN dbo.roles r ON r.id = u.rol_id
    WHERE r.codigo IN ('SUPER_ADMIN','ADMIN_MESA','SUPERVISOR') AND u.dosf_metodo IS NULL AND u.dosf_exigido_desde IS NULL
      AND u.activo = 1 AND u.eliminado = 0;
    INSERT INTO dbo.configuracion (clave, valor, descripcion)
    VALUES ('seguridad.iso37_aplicado', CONVERT(NVARCHAR(30), SYSUTCDATETIME(), 126),
            N'Fecha en que se activó la verificación obligatoria para Administradores y Supervisores (no editar)');
END
GO

PRINT N'18_seguridad_iso.sql aplicado';
GO
