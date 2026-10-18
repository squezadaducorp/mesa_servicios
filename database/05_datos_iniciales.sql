/* =====================================================================
   Mesa de Servicios ADUCORP
   05 · Datos iniciales (catálogos, roles, permisos, SLA, calendario,
        categorías, responsables y usuarios base)
   Idempotente. Contraseña inicial de todos los usuarios: Aducorp2026!
   (se obliga a cambiarla en el primer ingreso).
   Los correos usan el dominio aducorp.com.ec; ajústelos si difiere.
   ===================================================================== */
:on error exit
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET XACT_ABORT ON;
GO

BEGIN TRAN;

/* ---------------- Estados ---------------- */
MERGE dbo.estados AS d
USING (VALUES
    ('NUEVO',             N'Nuevo',             1, '#1367AC', 0, 0),
    ('ASIGNADO',          N'Asignado',          2, '#70A9CE', 0, 0),
    ('EN_PROCESO',        N'En Proceso',        3, '#0B255B', 0, 0),
    ('PENDIENTE_CLIENTE', N'Pendiente Cliente', 4, '#ED6C02', 1, 0),
    ('ESCALADO',          N'Escalado',          5, '#D32F2F', 0, 0),
    ('RESUELTO',          N'Resuelto',          6, '#2E7D32', 1, 0),
    ('CERRADO',           N'Cerrado',           7, '#455A64', 1, 1),
    ('CANCELADO',         N'Cancelado',         8, '#9E9E9E', 1, 1)
) AS s (codigo, nombre, orden, color, pausa_sla, es_final)
ON d.codigo = s.codigo
WHEN MATCHED THEN UPDATE SET nombre = s.nombre, orden = s.orden, color = s.color, pausa_sla = s.pausa_sla, es_final = s.es_final
WHEN NOT MATCHED THEN INSERT (codigo, nombre, orden, color, pausa_sla, es_final)
                      VALUES (s.codigo, s.nombre, s.orden, s.color, s.pausa_sla, s.es_final);

/* ---------------- Prioridades y SLA (minutos laborables) ---------------- */
MERGE dbo.prioridades AS d
USING (VALUES
    ('URGENTE', N'Urgente', 1, '#D32F2F',  60,  240),
    ('ALTA',    N'Alta',    2, '#ED6C02', 120,  480),
    ('MEDIA',   N'Media',   3, '#1367AC', 240, 1440),
    ('BAJA',    N'Baja',    4, '#70A9CE', 480, 2880)
) AS s (codigo, nombre, orden, color, resp, res)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, nombre, orden, color, sla_respuesta_min, sla_resolucion_min)
                      VALUES (s.codigo, s.nombre, s.orden, s.color, s.resp, s.res);

/* ---------------- Roles ---------------- */
MERGE dbo.roles AS d
USING (VALUES
    ('SUPER_ADMIN', N'Super Administrador',            N'Administración total del sistema'),
    ('ADMIN_MESA',  N'Administrador Mesa de Servicio', N'Coordina la mesa: tickets, asignaciones, SLA y reportes'),
    ('SUPERVISOR',  N'Supervisor',                     N'Supervisa las categorías a su cargo'),
    ('ANALISTA',    N'Analista',                       N'Atiende los tickets asignados'),
    ('CLIENTE',     N'Cliente Interno',                N'Colaborador que solicita servicios'),
    ('GERENCIA',    N'Gerencia',                       N'Consulta de indicadores, solo lectura')
) AS s (codigo, nombre, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, nombre, descripcion) VALUES (s.codigo, s.nombre, s.descripcion);

/* ---------------- Permisos ---------------- */
MERGE dbo.permisos AS d
USING (VALUES
    ('sistema.administrar',  N'Sistema',    N'Administrar configuración general'),
    ('usuario.administrar',  N'Seguridad',  N'Crear, editar y desactivar usuarios'),
    ('rol.administrar',      N'Seguridad',  N'Cambiar roles y permisos'),
    ('categoria.administrar',N'Catálogo',   N'Crear y editar categorías, subcategorías y responsables'),
    ('sla.modificar',        N'SLA',        N'Modificar SLA, horario laboral y excepciones'),
    ('ticket.ver_todos',     N'Tickets',    N'Ver todos los tickets'),
    ('ticket.ver_area',      N'Tickets',    N'Ver tickets de las categorías supervisadas'),
    ('ticket.ver_asignados', N'Tickets',    N'Ver tickets asignados'),
    ('ticket.ver_propios',   N'Tickets',    N'Ver tickets propios'),
    ('ticket.crear',         N'Tickets',    N'Crear tickets'),
    ('ticket.editar',        N'Tickets',    N'Editar datos del ticket'),
    ('ticket.asignar',       N'Tickets',    N'Asignar y reasignar responsables'),
    ('ticket.escalar',       N'Tickets',    N'Escalar tickets'),
    ('ticket.cambiar_estado',N'Tickets',    N'Cambiar estado y registrar actividades'),
    ('ticket.cerrar',        N'Tickets',    N'Resolver y cerrar tickets'),
    ('ticket.reabrir',       N'Tickets',    N'Reabrir tickets'),
    ('ticket.comentar',      N'Tickets',    N'Agregar comentarios'),
    ('ticket.adjuntar',      N'Tickets',    N'Adjuntar documentos'),
    ('registro.eliminar',    N'Sistema',    N'Eliminar registros (borrado lógico)'),
    ('reporte.ver',          N'Reportes',   N'Ver reportes e indicadores'),
    ('dashboard.ver',        N'Reportes',   N'Ver dashboard ejecutivo'),
    ('datos.exportar',       N'Reportes',   N'Exportar a Excel, PDF y CSV'),
    ('auditoria.ver',        N'Seguridad',  N'Consultar la auditoría completa'),
    ('ia.usar',              N'IA',         N'Usar sugerencias de inteligencia artificial')
) AS s (codigo, modulo, descripcion)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, modulo, descripcion) VALUES (s.codigo, s.modulo, s.descripcion);

/* ---------------- Rol → permisos ---------------- */
;WITH m (rol, permiso) AS (
    SELECT 'SUPER_ADMIN', codigo FROM dbo.permisos
    UNION ALL SELECT 'ADMIN_MESA', v FROM (VALUES ('sla.modificar'),('ticket.ver_todos'),('ticket.ver_area'),('ticket.ver_asignados'),('ticket.ver_propios'),
        ('ticket.crear'),('ticket.editar'),('ticket.asignar'),('ticket.escalar'),('ticket.cambiar_estado'),('ticket.cerrar'),('ticket.reabrir'),
        ('ticket.comentar'),('ticket.adjuntar'),('reporte.ver'),('dashboard.ver'),('datos.exportar'),('ia.usar')) x(v)
    UNION ALL SELECT 'SUPERVISOR', v FROM (VALUES ('ticket.ver_area'),('ticket.ver_asignados'),('ticket.ver_propios'),('ticket.crear'),('ticket.editar'),
        ('ticket.asignar'),('ticket.escalar'),('ticket.cambiar_estado'),('ticket.cerrar'),('ticket.reabrir'),('ticket.comentar'),('ticket.adjuntar'),
        ('reporte.ver'),('dashboard.ver'),('ia.usar')) x(v)
    UNION ALL SELECT 'ANALISTA', v FROM (VALUES ('ticket.ver_asignados'),('ticket.ver_propios'),('ticket.crear'),('ticket.editar'),('ticket.escalar'),
        ('ticket.cambiar_estado'),('ticket.cerrar'),('ticket.comentar'),('ticket.adjuntar'),('ia.usar')) x(v)
    UNION ALL SELECT 'CLIENTE', v FROM (VALUES ('ticket.ver_propios'),('ticket.crear'),('ticket.reabrir'),('ticket.comentar'),('ticket.adjuntar')) x(v)
    UNION ALL SELECT 'GERENCIA', v FROM (VALUES ('ticket.ver_todos'),('reporte.ver'),('dashboard.ver'),('datos.exportar')) x(v)
)
INSERT INTO dbo.rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM m
JOIN dbo.roles r ON r.codigo = m.rol
JOIN dbo.permisos p ON p.codigo = m.permiso
WHERE NOT EXISTS (SELECT 1 FROM dbo.rol_permisos rp WHERE rp.rol_id = r.id AND rp.permiso_id = p.id);

/* ---------------- Áreas ---------------- */
MERGE dbo.areas AS d
USING (VALUES (N'Gerencia General'), (N'Operaciones Aduaneras'), (N'Comercial'), (N'Logística'), (N'Legal'),
              (N'Finanzas'), (N'Atención al Cliente'), (N'Tecnología'), (N'Courier')) AS s (nombre)
ON d.nombre = s.nombre
WHEN NOT MATCHED THEN INSERT (nombre) VALUES (s.nombre);

/* ---------------- Horario laboral: L-V 08:30-13:00 y 14:00-17:30 (8 h) ---------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.horarios_laborales WHERE es_predeterminado = 1)
BEGIN
    INSERT INTO dbo.horarios_laborales (nombre, zona_horaria, es_predeterminado)
    VALUES (N'Horario ADUCORP', 'America/Guayaquil', 1);
    DECLARE @h INT = SCOPE_IDENTITY();
    INSERT INTO dbo.horario_tramos (horario_id, dia_semana, hora_inicio, hora_fin)
    SELECT @h, d.n, t.i, t.f
    FROM (VALUES (1),(2),(3),(4),(5)) d(n)
    CROSS JOIN (VALUES (CAST('08:30' AS TIME), CAST('13:00' AS TIME)), (CAST('14:00' AS TIME), CAST('17:30' AS TIME))) t(i, f);
END

/* ---------------- Feriados Ecuador (referenciales; validar con el decreto anual) ---------------- */
MERGE dbo.calendario_excepciones AS d
USING (VALUES
    ('2026-01-01', N'Año Nuevo'), ('2026-02-16', N'Carnaval'), ('2026-02-17', N'Carnaval'), ('2026-04-03', N'Viernes Santo'),
    ('2026-05-01', N'Día del Trabajo'), ('2026-05-25', N'Batalla de Pichincha (trasladado)'), ('2026-08-10', N'Primer Grito de Independencia'),
    ('2026-10-09', N'Independencia de Guayaquil'), ('2026-11-02', N'Día de los Difuntos'), ('2026-11-03', N'Independencia de Cuenca'),
    ('2026-12-25', N'Navidad'),
    ('2027-01-01', N'Año Nuevo'), ('2027-02-08', N'Carnaval'), ('2027-02-09', N'Carnaval'), ('2027-03-26', N'Viernes Santo'),
    ('2027-04-30', N'Día del Trabajo (trasladado)'), ('2027-05-24', N'Batalla de Pichincha'), ('2027-08-09', N'Primer Grito de Independencia (trasladado)'),
    ('2027-10-08', N'Independencia de Guayaquil (trasladado)'), ('2027-11-01', N'Día de los Difuntos (trasladado)'), ('2027-11-02', N'Día de los Difuntos'),
    ('2027-11-03', N'Independencia de Cuenca'), ('2027-12-24', N'Navidad (trasladado)')
) AS s (fecha, descripcion)
ON d.fecha = s.fecha AND d.tipo = 'FERIADO'
WHEN NOT MATCHED THEN INSERT (fecha, tipo, descripcion) VALUES (s.fecha, 'FERIADO', s.descripcion);

MERGE dbo.calendario_excepciones AS d
USING (VALUES ('2026-12-24', N'Nochebuena: jornada reducida'), ('2026-12-31', N'Fin de año: jornada reducida')) AS s (fecha, descripcion)
ON d.fecha = s.fecha AND d.tipo = 'HORARIO_ESPECIAL'
WHEN NOT MATCHED THEN INSERT (fecha, tipo, hora_inicio, hora_fin, descripcion) VALUES (s.fecha, 'HORARIO_ESPECIAL', '08:30', '13:00', s.descripcion);

/* ---------------- Usuarios base ---------------- */
DECLARE @clave VARCHAR(100) = '$2b$12$sSwVHCSigHQMEw1oActf9.uA2NlGP17XMuRMVjduvaPgndWJQIHRS';   -- Aducorp2026!

;WITH u (orden, nombre, correo, cargo, area, rol) AS (
    SELECT * FROM (VALUES
        (1, N'Administrador del Sistema',  N'admin@aducorp.com.ec',               N'Administrador de TI',            N'Tecnología',            'SUPER_ADMIN'),
        (2, N'Coordinador Mesa de Servicio',N'mesa.servicios@aducorp.com.ec',     N'Coordinador de Mesa de Servicio', N'Operaciones Aduaneras', 'ADMIN_MESA'),
        (3, N'Gerencia General',           N'gerencia@aducorp.com.ec',            N'Gerente General',                N'Gerencia General',      'GERENCIA'),
        (4, N'Supervisor Técnico Legal',   N'supervisor.tecnico@aducorp.com.ec',  N'Supervisor Técnico Legal',       N'Legal',                 'SUPERVISOR'),
        (5, N'Supervisor Operativo',       N'supervisor.operativo@aducorp.com.ec',N'Supervisor de Operaciones',      N'Operaciones Aduaneras', 'SUPERVISOR'),
        (6, N'David Medina',               N'david.medina@aducorp.com.ec',        N'Especialista en Clasificación Arancelaria', N'Operaciones Aduaneras', 'ANALISTA'),
        (7, N'Juan Manuel Villamar',       N'juan.villamar@aducorp.com.ec',       N'Abogado Aduanero',               N'Legal',                 'ANALISTA'),
        (8, N'Denisse Quinga',             N'denisse.quinga@aducorp.com.ec',      N'Analista Courier FedEx',         N'Courier',               'ANALISTA'),
        (9, N'Claudia Vásquez',            N'claudia.vasquez@aducorp.com.ec',     N'Especialista en Regímenes Especiales', N'Operaciones Aduaneras', 'ANALISTA'),
        (10, N'Jorge Caicedo',              N'jorge.caicedo@aducorp.com.ec',       N'Analista de Trámites Aduaneros', N'Operaciones Aduaneras', 'ANALISTA'),
        (11, N'Debbie Díaz',                N'debbie.diaz@aducorp.com.ec',         N'Analista de Trámites Aduaneros', N'Operaciones Aduaneras', 'ANALISTA'),
        (12, N'Carlos Torres',              N'carlos.torres@aducorp.com.ec',       N'Analista de Trámites Aduaneros', N'Operaciones Aduaneras', 'ANALISTA')
    ) v (orden, nombre, correo, cargo, area, rol)
)
INSERT INTO dbo.usuarios (nombre, correo, clave_hash, debe_cambiar_clave, cargo, area_id, rol_id)
SELECT u.nombre, u.correo, @clave, 1, u.cargo, a.id, r.id
FROM u
JOIN dbo.roles r ON r.codigo = u.rol
LEFT JOIN dbo.areas a ON a.nombre = u.area
WHERE NOT EXISTS (SELECT 1 FROM dbo.usuarios x WHERE x.correo = u.correo)
ORDER BY u.orden;

/* Analistas reportan a su supervisor */
UPDATE a SET supervisor_id = s.id
FROM dbo.usuarios a
JOIN dbo.usuarios s ON s.correo = CASE WHEN a.correo IN (N'david.medina@aducorp.com.ec', N'juan.villamar@aducorp.com.ec', N'claudia.vasquez@aducorp.com.ec')
                                       THEN N'supervisor.tecnico@aducorp.com.ec' ELSE N'supervisor.operativo@aducorp.com.ec' END
WHERE a.rol_id = (SELECT id FROM dbo.roles WHERE codigo = 'ANALISTA') AND a.supervisor_id IS NULL;

/* ---------------- Categorías ---------------- */
MERGE dbo.categorias AS d
USING (VALUES
    ('CLASIF_ARANCEL', N'Clasificación Arancelaria', N'Clasificación de mercancías, partidas arancelarias y análisis técnico-comercial', 1, '#1367AC', 'PRINCIPAL',
        N'clasificación,arancel,arancelaria,partida,subpartida,nandina,código arancelario,ad valorem,aforo,dai,dae,embarque,control previo,mercancía'),
    ('LEGAL_ADUANERO', N'Legal Aduanero', N'Recursos, impugnaciones, demandas y asesoría legal aduanera', 2, '#0B255B', 'PRINCIPAL',
        N'legal,recurso,revisión,demanda,impugnación,reclamo administrativo,pago indebido,sanción,multa,abogado,tribunal,senae,resolución,contencioso'),
    ('CONSULTAS_FEDEX', N'Consultas FedEx', N'Consultas e incidencias de envíos courier FedEx', 3, '#4D148C', 'PRINCIPAL',
        N'fedex,courier,tracking,guía,envío,paquete,entrega,rastreo,desaduanización,4x4,incidencia,reclamo,costo envío'),
    ('REGIMENES_ESP', N'Regímenes Especiales', N'Admisión temporal, drawback, zonas francas, depósitos y transformación', 4, '#70A9CE', 'PRINCIPAL',
        N'régimen,regimen especial,admisión temporal,drawback,zona franca,depósito aduanero,transformación,perfeccionamiento activo,reexportación,garantía'),
    ('TRAMITES_ADUANA', N'Trámites Aduaneros', N'Gestiones y trámites operativos ante SENAE y entidades de control', 5, '#10203C', 'BALANCEO',
        N'trámite,senae,ecuapass,hoja de cambio,regularización,certificado de origen,etiqueta,garantía,vehicular,dcp,sustitutiva,ficha técnica,preliquidación,nacionalización,usuario')
) AS s (codigo, nombre, descripcion, orden, color, modo, palabras)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, nombre, descripcion, orden, color, modo_asignacion, palabras_clave)
                      VALUES (s.codigo, s.nombre, s.descripcion, s.orden, s.color, s.modo, s.palabras);

UPDATE dbo.categorias SET supervisor_id = (SELECT id FROM dbo.usuarios WHERE correo = N'supervisor.tecnico@aducorp.com.ec')
 WHERE codigo IN ('CLASIF_ARANCEL','LEGAL_ADUANERO','REGIMENES_ESP') AND supervisor_id IS NULL;
UPDATE dbo.categorias SET supervisor_id = (SELECT id FROM dbo.usuarios WHERE correo = N'supervisor.operativo@aducorp.com.ec')
 WHERE codigo IN ('CONSULTAS_FEDEX','TRAMITES_ADUANA') AND supervisor_id IS NULL;

/* ---------------- Subcategorías ---------------- */
;WITH s (cat, nombre, palabras) AS (
    SELECT * FROM (VALUES
        ('CLASIF_ARANCEL', N'Recursos Legales',              N'recurso,impugnar clasificación'),
        ('CLASIF_ARANCEL', N'Control Posterior',             N'control posterior,auditoría posterior,rectificación'),
        ('CLASIF_ARANCEL', N'Análisis Comerciales',          N'análisis comercial,cotización,costo de importación,tributos'),
        ('CLASIF_ARANCEL', N'Procesos Logísticos',           N'logística,transporte,naviera,consolidado'),
        ('CLASIF_ARANCEL', N'Proceso de Embarque',           N'embarque,bl,booking,conocimiento de embarque'),
        ('CLASIF_ARANCEL', N'Documentos de Control Previo',  N'control previo,dcp,permiso,inen,arcsa,agrocalidad,registro sanitario'),
        ('CLASIF_ARANCEL', N'Captación de Clientes',         N'nuevo cliente,captación,prospecto,propuesta'),
        ('CLASIF_ARANCEL', N'Proceso de Aforo',              N'aforo,físico,documental,canal rojo,canal aforo'),
        ('CLASIF_ARANCEL', N'Presentación DAI',              N'dai,declaración de importación,importación'),
        ('CLASIF_ARANCEL', N'Presentación DAE',              N'dae,declaración de exportación,exportación'),
        ('CLASIF_ARANCEL', N'Exigencias Comerciales',        N'exigencia,requisito comercial,factura comercial'),
        ('LEGAL_ADUANERO', N'Recursos de Revisión',          N'recurso de revisión,revisión'),
        ('LEGAL_ADUANERO', N'Demandas',                      N'demanda,tribunal,contencioso,juicio'),
        ('LEGAL_ADUANERO', N'Impugnaciones',                 N'impugnación,impugnar,reclamo administrativo'),
        ('LEGAL_ADUANERO', N'Pago Indebido',                 N'pago indebido,devolución,pago en exceso'),
        ('LEGAL_ADUANERO', N'Sanciones Operativas',          N'sanción,multa,contravención,falta reglamentaria'),
        ('LEGAL_ADUANERO', N'Consultas Legales',             N'consulta legal,criterio,normativa,copci'),
        ('LEGAL_ADUANERO', N'Legal Operativo',               N'legal operativo,operación,despacho'),
        ('LEGAL_ADUANERO', N'Legal Logístico',               N'legal logístico,transporte,contrato'),
        ('CONSULTAS_FEDEX', N'Tracking',                     N'tracking,rastreo,guía,dónde está'),
        ('CONSULTAS_FEDEX', N'Entregas',                     N'entrega,domicilio,recibir'),
        ('CONSULTAS_FEDEX', N'Costos',                       N'costo,tarifa,cobro,factura fedex'),
        ('CONSULTAS_FEDEX', N'Incidencias',                  N'incidencia,daño,pérdida,retraso'),
        ('CONSULTAS_FEDEX', N'Reclamos',                     N'reclamo,queja,reembolso'),
        ('CONSULTAS_FEDEX', N'Desaduanización',              N'desaduanización,liberación,retenido,4x4'),
        ('REGIMENES_ESP', N'Admisión Temporal',              N'admisión temporal,reexportación'),
        ('REGIMENES_ESP', N'Drawback',                       N'drawback,devolución condicionada'),
        ('REGIMENES_ESP', N'Zona Franca',                    N'zona franca,zede'),
        ('REGIMENES_ESP', N'Depósito Aduanero',              N'depósito aduanero,almacenamiento'),
        ('REGIMENES_ESP', N'Transformación Bajo Control Aduanero', N'transformación,control aduanero,perfeccionamiento'),
        ('TRAMITES_ADUANA', N'Consultas Clasificación',      N'consulta clasificación,partida'),
        ('TRAMITES_ADUANA', N'Hojas de Cambio',              N'hoja de cambio,corrección'),
        ('TRAMITES_ADUANA', N'Corregir Regularización',      N'corregir regularización,regularización'),
        ('TRAMITES_ADUANA', N'Creación Usuarios',            N'creación de usuario,ecuapass,firma electrónica,token'),
        ('TRAMITES_ADUANA', N'Certificados de Origen',       N'certificado de origen,origen,preferencia arancelaria'),
        ('TRAMITES_ADUANA', N'Revisión Etiquetas',           N'etiqueta,etiquetado,rotulado'),
        ('TRAMITES_ADUANA', N'Garantías',                    N'garantía,póliza,fianza'),
        ('TRAMITES_ADUANA', N'Declaraciones Vehiculares',    N'vehículo,vehicular,declaración vehicular'),
        ('TRAMITES_ADUANA', N'Regularización DAEs',          N'regularización dae,dae'),
        ('TRAMITES_ADUANA', N'Regímenes Especiales',         N'régimen especial'),
        ('TRAMITES_ADUANA', N'Gestiones DCP',                N'dcp,documento de control previo,vue'),
        ('TRAMITES_ADUANA', N'Sustitutivas',                 N'sustitutiva,declaración sustitutiva'),
        ('TRAMITES_ADUANA', N'Exportaciones Posteriores',    N'exportación posterior'),
        ('TRAMITES_ADUANA', N'Fichas Técnicas',              N'ficha técnica,especificación'),
        ('TRAMITES_ADUANA', N'Preliquidaciones Fantasma',    N'preliquidación,fantasma,liquidación'),
        ('TRAMITES_ADUANA', N'Nacionalización',              N'nacionalización,nacionalizar')
    ) v (cat, nombre, palabras)
)
INSERT INTO dbo.subcategorias (categoria_id, nombre, palabras_clave, respuesta_plantilla)
SELECT c.id, s.nombre, s.palabras,
       CONCAT(N'Estimado/a {solicitante}: hemos recibido su solicitud {numero} sobre "', s.nombre,
              N'". {responsable} del equipo de ', c.nombre,
              N' la está revisando. Para avanzar, por favor confirme o adjunte la documentación de soporte (factura comercial, documento de transporte y DAI/DAE cuando aplique). Le mantendremos informado/a.')
FROM s
JOIN dbo.categorias c ON c.codigo = s.cat
WHERE NOT EXISTS (SELECT 1 FROM dbo.subcategorias x WHERE x.categoria_id = c.id AND x.nombre = s.nombre);

/* ---------------- Responsables por categoría ---------------- */
;WITH r (cat, correo, principal) AS (
    SELECT * FROM (VALUES
        ('CLASIF_ARANCEL',  N'david.medina@aducorp.com.ec',    1),
        ('LEGAL_ADUANERO',  N'juan.villamar@aducorp.com.ec',   1),
        ('CONSULTAS_FEDEX', N'denisse.quinga@aducorp.com.ec',  1),
        ('REGIMENES_ESP',   N'claudia.vasquez@aducorp.com.ec', 1),
        ('TRAMITES_ADUANA', N'jorge.caicedo@aducorp.com.ec',   1),
        ('TRAMITES_ADUANA', N'debbie.diaz@aducorp.com.ec',     0),
        ('TRAMITES_ADUANA', N'carlos.torres@aducorp.com.ec',   0)
    ) v (cat, correo, principal)
)
INSERT INTO dbo.categoria_responsables (categoria_id, usuario_id, es_principal)
SELECT c.id, u.id, r.principal
FROM r
JOIN dbo.categorias c ON c.codigo = r.cat
JOIN dbo.usuarios u ON u.correo = r.correo
WHERE NOT EXISTS (SELECT 1 FROM dbo.categoria_responsables x WHERE x.categoria_id = c.id AND x.usuario_id = u.id);

/* ---------------- Plantillas de correo ---------------- */
MERGE dbo.plantillas_correo AS d
USING (VALUES
    ('TICKET_CREADO',   N'[{numero}] Ticket creado: {asunto}',
        N'<p>Hola {destinatario},</p><p>Se registró el ticket <b>{numero}</b> «{asunto}» en la categoría <b>{categoria}</b> con prioridad <b>{prioridad}</b>.</p><p>Primera respuesta comprometida: {sla_respuesta_vence}<br>Resolución comprometida: {sla_resolucion_vence}</p><p><a href="{url}">Ver ticket</a></p>'),
    ('TICKET_ASIGNADO', N'[{numero}] Ticket asignado a usted',
        N'<p>Hola {destinatario},</p><p>Se le asignó el ticket <b>{numero}</b> «{asunto}» ({categoria} / {subcategoria}), prioridad <b>{prioridad}</b>.</p><p>Vence: {sla_resolucion_vence}</p><p><a href="{url}">Atender ticket</a></p>'),
    ('TICKET_ESCALADO', N'[{numero}] Ticket escalado',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» fue escalado. Motivo: {motivo}.</p><p>Responsable actual: {responsable}. SLA consumido: {sla_pct} %.</p><p><a href="{url}">Revisar ticket</a></p>'),
    ('SLA_75',          N'[{numero}] Ticket próximo a vencer (75 %)',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» consumió el <b>{sla_pct} %</b> de su SLA. Vence: {sla_resolucion_vence}.</p><p><a href="{url}">Atender ahora</a></p>'),
    ('SLA_90',          N'[{numero}] Alerta SLA 90 %: requiere intervención',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» asignado a <b>{responsable}</b> consumió el <b>{sla_pct} %</b> de su SLA. Vence: {sla_resolucion_vence}.</p><p><a href="{url}">Revisar ticket</a></p>'),
    ('SLA_VENCIDO',     N'[{numero}] SLA incumplido',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» venció su SLA de resolución ({sla_resolucion_vence}) y fue escalado automáticamente.</p><p>Responsable: {responsable}.</p><p><a href="{url}">Revisar ticket</a></p>'),
    ('TICKET_CERRADO',  N'[{numero}] Ticket cerrado',
        N'<p>Hola {destinatario},</p><p>El ticket <b>{numero}</b> «{asunto}» fue cerrado.</p><p>Si el problema persiste puede reabrirlo desde el portal.</p><p><a href="{url}">Ver ticket</a></p>')
) AS s (codigo, asunto, cuerpo)
ON d.codigo = s.codigo
WHEN NOT MATCHED THEN INSERT (codigo, asunto, cuerpo_html) VALUES (s.codigo, s.asunto, s.cuerpo);

/* ---------------- Configuración ---------------- */
MERGE dbo.configuracion AS d
USING (VALUES
    ('empresa.nombre',              N'ADUCORP Asesores Aduaneros y Logísticos Cía. Ltda.', N'Nombre mostrado en correos y reportes'),
    ('sla.umbral_aviso_1',          N'75',  N'% de SLA consumido para aviso al responsable'),
    ('sla.umbral_aviso_2',          N'90',  N'% de SLA consumido para aviso al supervisor'),
    ('ticket.cierre_automatico_h',  N'72',  N'Horas laborables tras Resuelto para cierre automático (0 = desactivado)'),
    ('adjuntos.max_mb',             N'20',  N'Tamaño máximo por archivo'),
    ('adjuntos.extensiones',        N'pdf,doc,docx,xls,xlsx,csv,jpg,jpeg,png,txt,xml,zip,msg,eml', N'Extensiones permitidas'),
    ('seguridad.max_intentos',      N'5',   N'Intentos fallidos antes de bloquear'),
    ('seguridad.bloqueo_min',       N'15',  N'Minutos de bloqueo')
) AS s (clave, valor, descripcion)
ON d.clave = s.clave
WHEN NOT MATCHED THEN INSERT (clave, valor, descripcion) VALUES (s.clave, s.valor, s.descripcion);

COMMIT;
PRINT N'05_datos_iniciales.sql aplicado.';
GO
