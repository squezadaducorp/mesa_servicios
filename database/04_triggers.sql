/* =====================================================================
   Mesa de Servicios ADUCORP
   04 · Triggers
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* La auditoría es inmutable: no se permite modificar ni borrar registros. */
CREATE OR ALTER TRIGGER dbo.tr_auditoria_inmutable
ON dbo.auditoria
INSTEAD OF UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    THROW 50001, N'La tabla de auditoría es inmutable: no se permite UPDATE ni DELETE.', 1;
END
GO

/* Bloquea el borrado físico de tickets: se usa borrado lógico (eliminado = 1). */
CREATE OR ALTER TRIGGER dbo.tr_tickets_sin_borrado_fisico
ON dbo.tickets
INSTEAD OF DELETE
AS
BEGIN
    SET NOCOUNT ON;
    THROW 50002, N'Los tickets no se borran físicamente. Use el borrado lógico (eliminado = 1).', 1;
END
GO

PRINT N'04_triggers.sql aplicado.';
GO
