/* =====================================================================
   Revisión de accesos al Coordinador de Sistemas y verificación en dos pasos para todos los roles.
   Idempotente (db-init lo ejecuta en cada arranque).
   - accesos.revisor_correo: quién revisa la campaña trimestral (ya no los jefes directos).
   - Verificación en dos pasos obligatoria para TODOS los roles, con 14 días de gracia desde el siguiente ingreso
     de cada persona. Se aplica UNA sola vez (marca seguridad.2fa_todos_aplicado): si después se cambia la política
     en Seguridad y cumplimiento › Política de acceso, este script no la vuelve a pisar.
   - No modifica ni borra datos de tickets ni usuarios.
   ===================================================================== */
SET NOCOUNT ON;
GO

MERGE dbo.configuracion AS d
USING (VALUES
    ('accesos.revisor_correo', N'squezada@aducorp.com.ec', N'Correo del Coordinador de Sistemas, que revisa todos los accesos en la campaña trimestral')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);
GO
UPDATE dbo.configuracion SET descripcion = N'Días que tiene el Coordinador de Sistemas para revisar los accesos'
WHERE clave = 'accesos.dias_plazo';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.configuracion WHERE clave = 'seguridad.2fa_todos_aplicado')
BEGIN
    MERGE dbo.configuracion AS d
    USING (VALUES
        ('seguridad.2fa_admin',          N'si', N'Verificación en dos pasos obligatoria para Administrador y Supervisor (si/no)'),
        ('seguridad.2fa_analistas',      N'si', N'Verificación en dos pasos obligatoria para Analistas (si/no)'),
        ('seguridad.2fa_opcional_otros', N'no', N'Verificación en dos pasos opcional para clientes internos y gerencia (si = opcional, no = obligatoria)'),
        ('seguridad.2fa_dias_gracia',    N'14', N'Días para configurar la verificación cuando pasa a ser obligatoria (0 = se exige en el siguiente ingreso)')
    ) AS s (clave, valor, descripcion)
    ON d.clave = s.clave
    WHEN MATCHED THEN UPDATE SET valor = s.valor, fecha_actualizacion = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);

    INSERT INTO dbo.configuracion (clave, valor, descripcion)
    VALUES ('seguridad.2fa_todos_aplicado', CONVERT(NVARCHAR(30), SYSUTCDATETIME(), 126),
            N'Fecha en que se activó la verificación en dos pasos para todos los roles (no editar)');
    PRINT N'Verificación en dos pasos obligatoria para todos los roles (14 días de gracia)';
END
GO

PRINT N'21_revisor_accesos_2fa_todos.sql aplicado';
GO
