/* =====================================================================
   Mesa de Servicios ADUCORP
   02 · Vistas para reportería (Power BI, Excel, consultas ad hoc)
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

CREATE OR ALTER VIEW dbo.vw_tickets_detalle
AS
SELECT
    t.id,
    t.numero,
    t.asunto,
    t.fecha_creacion,
    t.solicitante_id,
    t.solicitante_nombre,
    t.solicitante_cargo,
    a.nombre                AS area,
    t.cliente_id,
    cl.razon_social         AS cliente,
    t.correo,
    t.telefono,
    t.categoria_id,
    c.nombre                AS categoria,
    t.subcategoria_id,
    s.nombre                AS subcategoria,
    t.prioridad_id,
    p.nombre                AS prioridad,
    t.responsable_id,
    r.nombre                AS responsable,
    t.estado,
    e.nombre                AS estado_nombre,
    e.es_final,
    t.fecha_primera_respuesta,
    t.fecha_resolucion,
    t.fecha_cierre,
    t.sla_respuesta_min,
    t.sla_resolucion_min,
    t.sla_respuesta_vence,
    t.sla_resolucion_vence,
    t.sla_consumido_pct,
    t.sla_respuesta_cumplido,
    t.sla_resolucion_cumplido,
    t.sla_incumplido,
    t.cumplimiento_sla,
    t.reaperturas,
    t.minutos_respuesta,
    t.minutos_resolucion,
    DATEDIFF(MINUTE, t.fecha_creacion, t.fecha_primera_respuesta) AS minutos_respuesta_calendario,
    DATEDIFF(MINUTE, t.fecha_creacion, t.fecha_resolucion)        AS minutos_resolucion_calendario
FROM dbo.tickets t
JOIN dbo.categorias    c  ON c.id = t.categoria_id
JOIN dbo.subcategorias s  ON s.id = t.subcategoria_id
JOIN dbo.prioridades   p  ON p.id = t.prioridad_id
JOIN dbo.estados       e  ON e.codigo = t.estado
LEFT JOIN dbo.usuarios r  ON r.id = t.responsable_id
LEFT JOIN dbo.clientes cl ON cl.id = t.cliente_id
LEFT JOIN dbo.areas    a  ON a.id = t.area_id
WHERE t.eliminado = 0;
GO

CREATE OR ALTER VIEW dbo.vw_tickets_abiertos_sla
AS
SELECT d.*
FROM dbo.vw_tickets_detalle d
WHERE d.es_final = 0 AND d.estado <> 'RESUELTO';
GO

CREATE OR ALTER VIEW dbo.vw_carga_responsables
AS
SELECT
    u.id        AS usuario_id,
    u.nombre,
    COUNT(t.id) AS tickets_abiertos,
    SUM(CASE WHEN t.sla_consumido_pct >= 75 THEN 1 ELSE 0 END) AS tickets_en_riesgo
FROM dbo.usuarios u
LEFT JOIN dbo.tickets t
       ON t.responsable_id = u.id AND t.eliminado = 0
      AND t.estado IN ('ASIGNADO','EN_PROCESO','PENDIENTE_CLIENTE','ESCALADO')
WHERE u.activo = 1 AND u.eliminado = 0
GROUP BY u.id, u.nombre;
GO

PRINT N'02_vistas.sql aplicado.';
GO
