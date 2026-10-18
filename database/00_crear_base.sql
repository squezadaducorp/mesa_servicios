/* =====================================================================
   Mesa de Servicios ADUCORP
   00 · Creación de base de datos y usuario de aplicación
   Ejecutar como sysadmin. Variables sqlcmd:
     DB_NAME       (p. ej. AducorpMesaServicios)
     APP_LOGIN     (p. ej. aducorp_app)
     APP_PASSWORD  (obligatoria)
   ===================================================================== */
:on error exit

IF DB_ID(N'$(DB_NAME)') IS NULL
BEGIN
    PRINT N'Creando base de datos $(DB_NAME)...';
    CREATE DATABASE [$(DB_NAME)] COLLATE Modern_Spanish_CI_AS;
END
GO

-- Solo la primera vez: ROLLBACK IMMEDIATE cortaría sesiones activas en una actualización
IF (SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name = N'$(DB_NAME)') = 0
    ALTER DATABASE [$(DB_NAME)] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
IF (SELECT snapshot_isolation_state FROM sys.databases WHERE name = N'$(DB_NAME)') = 0
    ALTER DATABASE [$(DB_NAME)] SET ALLOW_SNAPSHOT_ISOLATION ON;
IF (SELECT recovery_model_desc FROM sys.databases WHERE name = N'$(DB_NAME)') <> N'FULL'
    ALTER DATABASE [$(DB_NAME)] SET RECOVERY FULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'$(APP_LOGIN)')
BEGIN
    PRINT N'Creando login $(APP_LOGIN)...';
    CREATE LOGIN [$(APP_LOGIN)] WITH PASSWORD = N'$(APP_PASSWORD)', CHECK_POLICY = ON, DEFAULT_DATABASE = [$(DB_NAME)];
END
GO

USE [$(DB_NAME)];
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(APP_LOGIN)')
BEGIN
    CREATE USER [$(APP_LOGIN)] FOR LOGIN [$(APP_LOGIN)];
END
GO

/* La aplicación lee, escribe y ejecuta procedimientos; no modifica el esquema. */
ALTER ROLE db_datareader ADD MEMBER [$(APP_LOGIN)];
ALTER ROLE db_datawriter ADD MEMBER [$(APP_LOGIN)];
GRANT EXECUTE ON SCHEMA::dbo TO [$(APP_LOGIN)];
GO
