/* =====================================================================
   Mesa de Servicios ADUCORP · revisión antes de publicar en internet
   La contraseña inicial Aducorp2026! aparece en el README y en los manuales, y los
   usuarios de demostración la comparten. Este script:
     1. se detiene si algún Super Admin activo todavía la usa (cámbiela primero);
     2. desactiva las demás cuentas que la siguen usando.
   Las cuentas desactivadas se reactivan desde Administración > Usuarios con
   «Generar contraseña temporal». Es idempotente: puede ejecutarse varias veces.
   ===================================================================== */
SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @inicial VARCHAR(100) = '$2b$12$sSwVHCSigHQMEw1oActf9.uA2NlGP17XMuRMVjduvaPgndWJQIHRS';   -- Aducorp2026!

IF EXISTS (SELECT 1 FROM dbo.usuarios u JOIN dbo.roles r ON r.id = u.rol_id
           WHERE r.codigo = 'SUPER_ADMIN' AND u.activo = 1 AND u.eliminado = 0 AND u.clave_hash = @inicial)
    THROW 50100, N'Un Super Admin todavía usa la contraseña inicial Aducorp2026!. Ingrese con esa cuenta en la Mesa, cámbiela y vuelva a ejecutar.', 1;

IF NOT EXISTS (SELECT 1 FROM dbo.usuarios u JOIN dbo.roles r ON r.id = u.rol_id
               WHERE r.codigo = 'SUPER_ADMIN' AND u.activo = 1 AND u.eliminado = 0)
    THROW 50101, N'No hay ningún Super Admin activo; no se desactiva nada para no dejar la Mesa sin administrador.', 1;

DECLARE @desactivadas TABLE (correo NVARCHAR(150));
UPDATE dbo.usuarios
SET activo = 0, fecha_actualizacion = SYSUTCDATETIME()
OUTPUT inserted.correo INTO @desactivadas
WHERE clave_hash = @inicial AND activo = 1 AND eliminado = 0;

DECLARE @n INT = (SELECT COUNT(*) FROM @desactivadas);
IF @n = 0
    PRINT N'Listo: ninguna cuenta activa usa la contraseña inicial.';
ELSE
BEGIN
    PRINT CONCAT(N'Listo: se desactivaron ', @n, N' cuentas que usaban la contraseña inicial:');
    SELECT correo AS cuenta_desactivada FROM @desactivadas ORDER BY correo;
END
