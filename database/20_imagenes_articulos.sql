/* =====================================================================
   Base de conocimiento: imágenes en el paso a paso de la solución. Idempotente (db-init lo ejecuta en cada arranque).
   - Cada imagen se guarda como archivo (mismo volumen de adjuntos) y se referencia en la solución con [imagen:ID].
   - Se ve con los mismos permisos del artículo: las de un artículo interno nunca las ven clientes ni solicitantes de afuera.
   - No modifica ni borra datos existentes.
   ===================================================================== */
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.kb_imagenes', N'U') IS NULL
CREATE TABLE dbo.kb_imagenes (
    id                   INT IDENTITY(1,1) CONSTRAINT pk_kb_imagenes PRIMARY KEY,
    articulo_id          INT NULL CONSTRAINT fk_kb_imagenes_articulo REFERENCES dbo.kb_articulos(id),
    nombre_original      NVARCHAR(255) NOT NULL,
    ruta_almacenamiento  NVARCHAR(400) NOT NULL,
    tipo_mime            VARCHAR(100) NOT NULL,
    tamano_bytes         BIGINT NOT NULL,
    hash_sha256          CHAR(64) NOT NULL,
    subido_por           INT NOT NULL CONSTRAINT fk_kb_imagenes_usuario REFERENCES dbo.usuarios(id),
    fecha                DATETIME2(0) NOT NULL CONSTRAINT df_kb_imagenes_fecha DEFAULT (SYSUTCDATETIME()),
    eliminado            BIT NOT NULL CONSTRAINT df_kb_imagenes_eliminado DEFAULT (0)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_kb_imagenes_articulo')
    CREATE INDEX ix_kb_imagenes_articulo ON dbo.kb_imagenes(articulo_id);
GO
PRINT N'20_imagenes_articulos.sql aplicado';
GO
