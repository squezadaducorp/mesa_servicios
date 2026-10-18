/* =====================================================================
   Mesa de Servicios ADUCORP
   03 · Procedimientos almacenados
   Las definiciones de los indicadores son las mismas que usa la API
   (backend/app/application/services/report_service.py):
     - Abiertos:      estado no final y distinto de RESUELTO
     - Cerrados:      RESUELTO o CERRADO
     - Escalados:     escalamiento manual o automático desde el 90 %
     - Vencidos:      sla_incumplido = 1
     - Cumplimiento:  cumplidos / (cumplidos + incumplidos), sin excluidos
     - Tiempos:       promedio de minutos laborables (sin pausas)
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* ---------------------------------------------------------------------
   Numeración correlativa por año: ADU-2026-000001
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_GenerarNumeroTicket
    @anio   INT = NULL,
    @numero VARCHAR(20) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @anio IS NULL SET @anio = YEAR(SYSUTCDATETIME());
    DECLARE @siguiente INT;

    BEGIN TRAN;
        UPDATE dbo.ticket_secuencias WITH (UPDLOCK, HOLDLOCK)
           SET @siguiente = ultimo = ultimo + 1
         WHERE anio = @anio;

        IF @@ROWCOUNT = 0
        BEGIN
            INSERT INTO dbo.ticket_secuencias (anio, ultimo) VALUES (@anio, 1);
            SET @siguiente = 1;
        END
    COMMIT;

    SET @numero = CONCAT('ADU-', @anio, '-', RIGHT(CONCAT('000000', @siguiente), 6));
END
GO

/* ---------------------------------------------------------------------
   Filtro común de tickets (función en línea reutilizable)
   --------------------------------------------------------------------- */
CREATE OR ALTER FUNCTION dbo.fn_TicketsFiltrados
(
    @desde          DATETIME2(0),
    @hasta          DATETIME2(0),
    @categoria_id   INT = NULL,
    @responsable_id INT = NULL,
    @cliente_id     INT = NULL,
    @estado         VARCHAR(20) = NULL
)
RETURNS TABLE
AS
RETURN
    SELECT t.*,
           CASE WHEN t.estado IN ('RESUELTO','CERRADO','CANCELADO') THEN 0 ELSE 1 END AS es_abierto,
           CASE WHEN t.estado IN ('RESUELTO','CERRADO') THEN 1 ELSE 0 END             AS es_cerrado,
           -- Escalado = escalamiento manual (nivel 0) o automático desde el 90 %; el aviso del 75 % no cuenta
           CASE WHEN EXISTS (SELECT 1 FROM dbo.ticket_escalamientos x WHERE x.ticket_id = t.id AND x.nivel <> 75) THEN 1 ELSE 0 END AS fue_escalado,
           CASE WHEN t.sla_excluido = 0 AND t.sla_incumplido = 0 AND t.sla_resolucion_cumplido = 1 THEN 1 ELSE 0 END AS sla_ok,
           CASE WHEN t.sla_excluido = 0 AND t.sla_incumplido = 1 THEN 1 ELSE 0 END AS sla_ko
      FROM dbo.tickets t
     WHERE t.eliminado = 0
       AND t.fecha_creacion >= @desde
       AND t.fecha_creacion <  @hasta
       AND (@categoria_id   IS NULL OR t.categoria_id   = @categoria_id)
       AND (@responsable_id IS NULL OR t.responsable_id = @responsable_id)
       AND (@cliente_id     IS NULL OR t.cliente_id     = @cliente_id)
       AND (@estado         IS NULL OR t.estado         = @estado);
GO

/* ---------------------------------------------------------------------
   Dashboard ejecutivo (widgets)
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_DashboardEjecutivo
    @desde          DATETIME2(0),
    @hasta          DATETIME2(0),
    @categoria_id   INT = NULL,
    @responsable_id INT = NULL,
    @cliente_id     INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        COUNT(*)                                        AS tickets_totales,
        ISNULL(SUM(es_abierto), 0)                      AS tickets_abiertos,
        ISNULL(SUM(es_cerrado), 0)                      AS tickets_cerrados,
        ISNULL(SUM(fue_escalado), 0)                    AS tickets_escalados,
        ISNULL(SUM(CAST(sla_incumplido AS INT)), 0)     AS tickets_vencidos,
        CAST(CASE WHEN SUM(sla_ok + sla_ko) = 0 THEN NULL
                  ELSE 100.0 * SUM(sla_ok) / SUM(sla_ok + sla_ko) END AS DECIMAL(5,2)) AS cumplimiento_sla_pct,
        CAST(AVG(CAST(minutos_respuesta  AS DECIMAL(12,2))) / 60.0 AS DECIMAL(10,2)) AS tiempo_promedio_respuesta_h,
        CAST(AVG(CAST(minutos_resolucion AS DECIMAL(12,2))) / 60.0 AS DECIMAL(10,2)) AS tiempo_promedio_resolucion_h
    FROM dbo.fn_TicketsFiltrados(@desde, @hasta, @categoria_id, @responsable_id, @cliente_id, NULL);
END
GO

/* ---------------------------------------------------------------------
   Indicadores por categoría
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_IndicadoresCategoria
    @desde DATETIME2(0),
    @hasta DATETIME2(0)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        c.id                                            AS categoria_id,
        c.nombre                                        AS categoria,
        COUNT(f.id)                                     AS tickets_recibidos,
        ISNULL(SUM(f.es_cerrado), 0)                    AS tickets_resueltos,
        ISNULL(SUM(f.es_abierto), 0)                    AS tickets_pendientes,
        ISNULL(SUM(CAST(f.sla_incumplido AS INT)), 0)   AS tickets_vencidos,
        CAST(CASE WHEN SUM(f.sla_ok + f.sla_ko) = 0 THEN NULL
                  ELSE 100.0 * SUM(f.sla_ok) / SUM(f.sla_ok + f.sla_ko) END AS DECIMAL(5,2)) AS cumplimiento_sla_pct,
        CAST(AVG(CAST(f.minutos_respuesta  AS DECIMAL(12,2))) / 60.0 AS DECIMAL(10,2)) AS tiempo_promedio_respuesta_h,
        CAST(AVG(CAST(f.minutos_resolucion AS DECIMAL(12,2))) / 60.0 AS DECIMAL(10,2)) AS tiempo_promedio_resolucion_h,
        (SELECT COUNT(*) FROM dbo.tickets b
          WHERE b.categoria_id = c.id AND b.eliminado = 0
            AND b.estado NOT IN ('RESUELTO','CERRADO','CANCELADO'))          AS backlog
    FROM dbo.categorias c
    LEFT JOIN dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, NULL, NULL) f ON f.categoria_id = c.id
    WHERE c.eliminado = 0
    GROUP BY c.id, c.nombre, c.orden
    ORDER BY c.orden;
END
GO

/* ---------------------------------------------------------------------
   Indicadores por responsable + ranking
   Productividad = tickets cerrados por día laborable del período.
   Puntaje ranking = 60 % cumplimiento SLA + 40 % cerrados relativos al mejor.
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_IndicadoresResponsable
    @desde DATETIME2(0),
    @hasta DATETIME2(0)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @dias_laborables DECIMAL(10,2) =
        (SELECT COUNT(*) FROM (
            SELECT TOP (DATEDIFF(DAY, @desde, @hasta)) DATEADD(DAY, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1, CAST(@desde AS DATE)) AS d
              FROM sys.all_objects) x
          WHERE DATEDIFF(DAY, '19000101', x.d) % 7 < 5   -- lunes..viernes (1900-01-01 fue lunes), independiente de DATEFIRST
            AND NOT EXISTS (SELECT 1 FROM dbo.calendario_excepciones ce WHERE ce.fecha = x.d AND ce.tipo = 'FERIADO'));
    IF @dias_laborables = 0 SET @dias_laborables = 1;

    ;WITH base AS (
        SELECT
            u.id                                            AS responsable_id,
            u.nombre                                        AS responsable,
            COUNT(f.id)                                     AS tickets_asignados,
            ISNULL(SUM(f.es_cerrado), 0)                    AS tickets_cerrados,
            ISNULL(SUM(f.es_abierto), 0)                    AS tickets_abiertos,
            ISNULL(SUM(f.sla_ok), 0)                        AS sla_cumplido,
            ISNULL(SUM(f.sla_ko), 0)                        AS sla_incumplido,
            CAST(AVG(CAST(f.minutos_resolucion AS DECIMAL(12,2))) / 60.0 AS DECIMAL(10,2)) AS tiempo_promedio_resolucion_h
        FROM dbo.usuarios u
        JOIN dbo.roles r ON r.id = u.rol_id AND r.codigo IN ('ANALISTA','SUPERVISOR')
        LEFT JOIN dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, NULL, NULL) f ON f.responsable_id = u.id
        WHERE u.eliminado = 0
        GROUP BY u.id, u.nombre
    ), calc AS (
        SELECT b.*,
               CAST(CASE WHEN b.sla_cumplido + b.sla_incumplido = 0 THEN NULL
                         ELSE 100.0 * b.sla_cumplido / (b.sla_cumplido + b.sla_incumplido) END AS DECIMAL(5,2)) AS cumplimiento_sla_pct,
               CAST(b.tickets_cerrados / @dias_laborables AS DECIMAL(10,2)) AS productividad_dia,
               MAX(b.tickets_cerrados) OVER () AS max_cerrados
        FROM base b
    )
    SELECT responsable_id, responsable, tickets_asignados, tickets_cerrados, tickets_abiertos,
           sla_cumplido, sla_incumplido, cumplimiento_sla_pct, productividad_dia, tiempo_promedio_resolucion_h,
           CAST(0.6 * ISNULL(cumplimiento_sla_pct, 0)
              + 0.4 * CASE WHEN max_cerrados = 0 THEN 0 ELSE 100.0 * tickets_cerrados / max_cerrados END AS DECIMAL(5,2)) AS puntaje,
           RANK() OVER (ORDER BY 0.6 * ISNULL(cumplimiento_sla_pct, 0)
              + 0.4 * CASE WHEN max_cerrados = 0 THEN 0 ELSE 100.0 * tickets_cerrados / max_cerrados END DESC) AS ranking
    FROM calc
    ORDER BY ranking;
END
GO

/* ---------------------------------------------------------------------
   Indicadores por cliente
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_IndicadoresCliente
    @desde DATETIME2(0),
    @hasta DATETIME2(0)
AS
BEGIN
    SET NOCOUNT ON;
    -- 1) Tickets y cumplimiento por cliente
    SELECT
        cl.id AS cliente_id,
        cl.razon_social AS cliente,
        COUNT(f.id) AS tickets,
        CAST(CASE WHEN SUM(f.sla_ok + f.sla_ko) = 0 THEN NULL
                  ELSE 100.0 * SUM(f.sla_ok) / SUM(f.sla_ok + f.sla_ko) END AS DECIMAL(5,2)) AS cumplimiento_sla_pct,
        (SELECT TOP 1 c.nombre FROM dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, cl.id, NULL) x
           JOIN dbo.categorias c ON c.id = x.categoria_id
          GROUP BY c.nombre ORDER BY COUNT(*) DESC) AS categoria_mas_usada
    FROM dbo.clientes cl
    JOIN dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, NULL, NULL) f ON f.cliente_id = cl.id
    GROUP BY cl.id, cl.razon_social
    ORDER BY tickets DESC;

    -- 2) Categorías más utilizadas por cliente
    SELECT f.cliente_id, c.nombre AS categoria, COUNT(*) AS tickets
    FROM dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, NULL, NULL) f
    JOIN dbo.categorias c ON c.id = f.categoria_id
    WHERE f.cliente_id IS NOT NULL
    GROUP BY f.cliente_id, c.nombre
    ORDER BY f.cliente_id, tickets DESC;

    -- 3) Tendencia mensual por cliente
    SELECT f.cliente_id, FORMAT(f.fecha_creacion, 'yyyy-MM') AS periodo, COUNT(*) AS tickets
    FROM dbo.fn_TicketsFiltrados(@desde, @hasta, NULL, NULL, NULL, NULL) f
    WHERE f.cliente_id IS NOT NULL
    GROUP BY f.cliente_id, FORMAT(f.fecha_creacion, 'yyyy-MM')
    ORDER BY f.cliente_id, periodo;
END
GO

/* ---------------------------------------------------------------------
   Tendencia de tickets: DIA | SEMANA | MES | ANIO
   (fechas agrupadas en hora de Ecuador, UTC-5)
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_TendenciaTickets
    @desde      DATETIME2(0),
    @hasta      DATETIME2(0),
    @agrupacion VARCHAR(10) = 'DIA',
    @categoria_id INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    ;WITH f AS (
        SELECT DATEADD(HOUR, -5, fecha_creacion) AS fecha_local, sla_ok, sla_ko, es_cerrado
        FROM dbo.fn_TicketsFiltrados(@desde, @hasta, @categoria_id, NULL, NULL, NULL)
    ), g AS (
        SELECT CASE @agrupacion
                   WHEN 'DIA'    THEN FORMAT(fecha_local, 'yyyy-MM-dd')
                   WHEN 'SEMANA' THEN -- año ISO = año del jueves de esa semana (1900-01-01 fue lunes)
                                      CONCAT(YEAR(DATEADD(DAY, 3 - DATEDIFF(DAY, '19000101', fecha_local) % 7, fecha_local)),
                                             '-S', RIGHT(CONCAT('0', DATEPART(ISO_WEEK, fecha_local)), 2))
                   WHEN 'MES'    THEN FORMAT(fecha_local, 'yyyy-MM')
                   ELSE CAST(YEAR(fecha_local) AS VARCHAR(4))
               END AS periodo,
               sla_ok, sla_ko, es_cerrado
        FROM f
    )
    SELECT periodo,
           COUNT(*)          AS tickets,
           SUM(es_cerrado)   AS cerrados,
           SUM(sla_ok)       AS sla_cumplido,
           SUM(sla_ko)       AS sla_incumplido
    FROM g
    GROUP BY periodo
    ORDER BY periodo;
END
GO

/* ---------------------------------------------------------------------
   Tickets abiertos con SLA consumido >= umbral
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_TicketsPorVencer
    @umbral_pct DECIMAL(5,2) = 75
AS
BEGIN
    SET NOCOUNT ON;
    SELECT numero, asunto, categoria, prioridad, responsable, estado_nombre,
           sla_consumido_pct, sla_resolucion_vence
    FROM dbo.vw_tickets_abiertos_sla
    WHERE sla_consumido_pct >= @umbral_pct
    ORDER BY sla_consumido_pct DESC;
END
GO

/* ---------------------------------------------------------------------
   Registro de auditoría (para integraciones externas o jobs SQL)
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_RegistrarAuditoria
    @usuario_id     INT = NULL,
    @usuario_correo NVARCHAR(150) = NULL,
    @accion         VARCHAR(40),
    @entidad        VARCHAR(40) = NULL,
    @entidad_id     VARCHAR(40) = NULL,
    @detalle        NVARCHAR(MAX) = NULL,
    @ip             VARCHAR(45) = NULL,
    @equipo         NVARCHAR(300) = NULL,
    @resultado      VARCHAR(10) = 'OK'
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.auditoria (usuario_id, usuario_correo, accion, entidad, entidad_id, detalle, ip, equipo, resultado)
    VALUES (@usuario_id, @usuario_correo, @accion, @entidad, @entidad_id, @detalle, @ip, @equipo, @resultado);
END
GO

/* ---------------------------------------------------------------------
   Consulta paginada de auditoría
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_ConsultarAuditoria
    @desde      DATETIME2(0),
    @hasta      DATETIME2(0),
    @usuario_id INT = NULL,
    @accion     VARCHAR(40) = NULL,
    @pagina     INT = 1,
    @tamano     INT = 50
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COUNT(*) AS total
      FROM dbo.auditoria
     WHERE fecha_hora >= @desde AND fecha_hora < @hasta
       AND (@usuario_id IS NULL OR usuario_id = @usuario_id)
       AND (@accion IS NULL OR accion = @accion);

    SELECT id, usuario_id, usuario_correo, fecha_hora, accion, entidad, entidad_id, detalle, ip, equipo, resultado
      FROM dbo.auditoria
     WHERE fecha_hora >= @desde AND fecha_hora < @hasta
       AND (@usuario_id IS NULL OR usuario_id = @usuario_id)
       AND (@accion IS NULL OR accion = @accion)
     ORDER BY fecha_hora DESC
     OFFSET (@pagina - 1) * @tamano ROWS FETCH NEXT @tamano ROWS ONLY;
END
GO

/* ---------------------------------------------------------------------
   Mantenimiento: depuración de refresh tokens y notificaciones antiguas
   (programar en SQL Server Agent, diario)
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_Mantenimiento
    @dias_notificaciones INT = 180
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.refresh_tokens
     WHERE fecha_expiracion < DATEADD(DAY, -1, SYSUTCDATETIME());

    DELETE FROM dbo.notificaciones
     WHERE leida = 1 AND fecha < DATEADD(DAY, -@dias_notificaciones, SYSUTCDATETIME());

    DELETE FROM dbo.cola_correos
     WHERE estado IN ('ENVIADO','DESCARTADO') AND fecha_creacion < DATEADD(DAY, -90, SYSUTCDATETIME());
END
GO

PRINT N'03_procedimientos.sql aplicado.';
GO
