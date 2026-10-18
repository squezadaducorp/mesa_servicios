"""Genera database/06_datos_demo.sql con datos de demostración coherentes.

Usa el mismo motor de SLA del backend, de modo que vencimientos, porcentajes
y cumplimientos de los tickets demo son exactamente los que calcularía la API.

Uso:
    python -m scripts.generar_datos_demo [--tickets 650] [--desde 2026-04-01] [--salida ../database/06_datos_demo.sql]
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.domain.sla import CalendarioLaboral, DatosSla, calcular_sla

SEMILLA = 2026

FERIADOS = [date.fromisoformat(d) for d in (
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-05-01", "2026-05-25", "2026-08-10",
    "2026-10-09", "2026-11-02", "2026-11-03", "2026-12-25",
)]

PRIORIDADES = {  # código: (respuesta, resolución, peso)
    "URGENTE": (60, 240, 0.10),
    "ALTA": (120, 480, 0.25),
    "MEDIA": (240, 1440, 0.45),
    "BAJA": (480, 2880, 0.20),
}

CATEGORIAS = {
    "CLASIF_ARANCEL": dict(peso=0.24, responsables=["david.medina"], sup="supervisor.tecnico", subs=[
        "Recursos Legales", "Control Posterior", "Análisis Comerciales", "Procesos Logísticos", "Proceso de Embarque",
        "Documentos de Control Previo", "Captación de Clientes", "Proceso de Aforo", "Presentación DAI", "Presentación DAE",
        "Exigencias Comerciales"]),
    "LEGAL_ADUANERO": dict(peso=0.14, responsables=["juan.villamar"], sup="supervisor.tecnico", subs=[
        "Recursos de Revisión", "Demandas", "Impugnaciones", "Pago Indebido", "Sanciones Operativas", "Consultas Legales",
        "Legal Operativo", "Legal Logístico"]),
    "CONSULTAS_FEDEX": dict(peso=0.18, responsables=["denisse.quinga"], sup="supervisor.operativo", subs=[
        "Tracking", "Entregas", "Costos", "Incidencias", "Reclamos", "Desaduanización"]),
    "REGIMENES_ESP": dict(peso=0.10, responsables=["claudia.vasquez"], sup="supervisor.tecnico", subs=[
        "Admisión Temporal", "Drawback", "Zona Franca", "Depósito Aduanero", "Transformación Bajo Control Aduanero"]),
    "TRAMITES_ADUANA": dict(peso=0.34, responsables=["jorge.caicedo", "debbie.diaz", "carlos.torres"], sup="supervisor.operativo", subs=[
        "Consultas Clasificación", "Hojas de Cambio", "Corregir Regularización", "Creación Usuarios", "Certificados de Origen",
        "Revisión Etiquetas", "Garantías", "Declaraciones Vehiculares", "Regularización DAEs", "Regímenes Especiales",
        "Gestiones DCP", "Sustitutivas", "Exportaciones Posteriores", "Fichas Técnicas", "Preliquidaciones Fantasma",
        "Nacionalización"]),
}

# Asuntos de ejemplo por subcategoría ({cliente} se reemplaza)
ASUNTOS = {
    "Presentación DAI": ["Transmisión de DAI para contenedor de {cliente}", "DAI con observación en valor en aduana"],
    "Presentación DAE": ["Presentación de DAE de exportación de banano", "DAE pendiente de transmisión para {cliente}"],
    "Proceso de Aforo": ["Aforo físico asignado a carga de {cliente}", "Canal rojo: coordinar inspección"],
    "Documentos de Control Previo": ["Registro sanitario ARCSA para importación", "Permiso INEN para mercancía de {cliente}"],
    "Tracking": ["Guía FedEx sin movimiento hace 3 días", "Rastreo de paquete urgente de {cliente}"],
    "Desaduanización": ["Paquete FedEx retenido en aduana", "Liberación de envío 4x4 para {cliente}"],
    "Recursos de Revisión": ["Recurso de revisión contra rectificación de tributos", "Plazo de recurso de revisión para {cliente}"],
    "Sanciones Operativas": ["Multa por falta reglamentaria a {cliente}", "Notificación de sanción operativa SENAE"],
    "Pago Indebido": ["Reclamo por pago indebido de tributos", "Devolución de pago en exceso a {cliente}"],
    "Drawback": ["Solicitud de drawback para exportaciones del trimestre", "Devolución condicionada {cliente}"],
    "Admisión Temporal": ["Admisión temporal de maquinaria para feria", "Prórroga de admisión temporal de {cliente}"],
    "Creación Usuarios": ["Creación de usuario Ecuapass para nuevo cliente", "Renovación de token de firma electrónica"],
    "Certificados de Origen": ["Certificado de origen para exportación a la UE", "Validación de certificado de origen de {cliente}"],
    "Nacionalización": ["Nacionalización de mercancía en depósito", "Nacionalización parcial de {cliente}"],
}

DESCRIPCIONES = [
    "Se requiere apoyo para gestionar el trámite indicado. Adjunto factura comercial y documento de transporte.",
    "El cliente solicita información sobre el estado y los próximos pasos. Favor revisar con prioridad.",
    "Existe una observación de SENAE que debe atenderse dentro del plazo. Se adjunta la notificación.",
    "Por favor confirmar los requisitos y el tiempo estimado de atención para informar al cliente.",
    "La carga se encuentra en puerto y el cliente necesita la liberación lo antes posible.",
]

CLIENTES = [
    ("0992345678001", "Importadora Andina del Pacífico S.A.", True),
    ("1791234567001", "Comercial Quitumbe Cía. Ltda.", False),
    ("0991122334001", "Exportadora Bananera Costa Verde S.A.", True),
    ("0190012345001", "Industrias Cuencanas del Austro S.A.", False),
    ("1792233445001", "Distribuidora Farmacéutica Equinoccio S.A.", True),
    ("0993344556001", "Agroexportadora El Oro S.A.", False),
    ("1793344556001", "Tecnología y Repuestos Sierra Cía. Ltda.", False),
    ("0994455667001", "Camaronera Golfo de Guayaquil S.A.", True),
    ("1794455667001", "Textiles Otavalo Internacional S.A.", False),
    ("0995566778001", "Maquinarias del Litoral S.A.", False),
    ("1795566778001", "Floricola Cotopaxi Rosas S.A.", False),
    ("0996677889001", "Automotriz Guayas Motors S.A.", True),
    ("1796677889001", "Cosméticos Naturales Pichincha Cía. Ltda.", False),
    ("0997788990001", "Química Industrial Salinas S.A.", False),
    ("1797788990001", "Electrodomésticos Hogar Andino S.A.", False),
]

CLIENTES_INTERNOS = [  # nombre, correo, cargo, área
    ("María Fernanda Andrade", "maria.andrade", "Ejecutiva de Cuenta", "Comercial"),
    ("Luis Alberto Paredes", "luis.paredes", "Coordinador Logístico", "Logística"),
    ("Gabriela Salazar", "gabriela.salazar", "Asistente de Operaciones", "Operaciones Aduaneras"),
    ("Andrés Mora", "andres.mora", "Ejecutivo Comercial", "Comercial"),
    ("Valeria Jaramillo", "valeria.jaramillo", "Analista Financiera", "Finanzas"),
    ("Diego Benítez", "diego.benitez", "Agente de Servicio al Cliente", "Atención al Cliente"),
    ("Paola Cevallos", "paola.cevallos", "Coordinadora de Courier", "Courier"),
    ("Santiago Espinoza", "santiago.espinoza", "Jefe de Logística", "Logística"),
    ("Carolina Vera", "carolina.vera", "Asistente Legal", "Legal"),
    ("Fernando Ruiz", "fernando.ruiz", "Ejecutivo de Cuenta", "Comercial"),
]

DOMINIO = "aducorp.com.ec"

NOMBRES_RESPONSABLES = {
    "david.medina": "David Medina", "juan.villamar": "Juan Manuel Villamar", "denisse.quinga": "Denisse Quinga",
    "claudia.vasquez": "Claudia Vásquez", "jorge.caicedo": "Jorge Caicedo", "debbie.diaz": "Debbie Díaz",
    "carlos.torres": "Carlos Torres",
}


def q(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "N'" + str(s).replace("'", "''") + "'"


def f(d: datetime | None) -> str:
    return "NULL" if d is None else f"'{d:%Y-%m-%dT%H:%M:%S}'"


def b(v: bool | None) -> str:
    return "NULL" if v is None else ("1" if v else "0")


def var(correo_local: str) -> str:
    return "@u_" + correo_local.replace(".", "_")


class Generador:
    def __init__(self, n: int, desde: date, ahora: datetime):
        self.rnd = random.Random(SEMILLA)
        self.n, self.desde, self.ahora = n, desde, ahora
        self.cal = CalendarioLaboral.por_defecto()
        self.cal.feriados.update(FERIADOS)
        self.sql: list[str] = []
        self.carga: dict[str, int] = {}

    def w(self, linea: str) -> None:
        self.sql.append(linea)

    # --------------------------------------------------------------- fechas
    def fecha_creacion_aleatoria(self) -> datetime:
        dias = (self.ahora.date() - self.desde).days
        while True:
            d = self.desde + timedelta(days=self.rnd.randint(0, dias))
            if d.weekday() >= 5 and self.rnd.random() > 0.05:   # pocos fines de semana
                continue
            hora_local = self.rnd.choices([8, 9, 10, 11, 12, 14, 15, 16, 17, 19], [3, 9, 10, 9, 6, 8, 8, 6, 3, 1])[0]
            local = datetime(d.year, d.month, d.day, hora_local, self.rnd.randint(0, 59), tzinfo=self.cal.tz)
            utc = local.astimezone(timezone.utc).replace(tzinfo=None)
            if utc < self.ahora - timedelta(minutes=20):
                return utc

    def en(self, inicio: datetime, minutos: int) -> datetime:
        return self.cal.sumar_minutos(inicio, minutos)

    # ------------------------------------------------------------- cabecera
    def cabecera(self) -> None:
        self.w("/* =====================================================================")
        self.w("   Mesa de Servicios ADUCORP")
        self.w("   06 · Datos de demostración (generado por backend/scripts/generar_datos_demo.py)")
        self.w(f"   Tickets: {self.n} · Desde {self.desde} · Corte {self.ahora:%Y-%m-%d %H:%M} UTC")
        self.w("   NO ejecutar en producción. Solo se aplica si la tabla tickets está vacía.")
        self.w("   ===================================================================== */")
        self.w(":on error exit")
        self.w("SET NOCOUNT ON;\nSET QUOTED_IDENTIFIER ON;\nSET ANSI_NULLS ON;\nSET XACT_ABORT ON;\nGO")
        self.w("IF EXISTS (SELECT 1 FROM dbo.tickets)\nBEGIN\n    PRINT N'Ya existen tickets: se omiten los datos demo.';\n    SET NOEXEC ON;\nEND\nGO")
        self.w("BEGIN TRAN;")
        clave = "(SELECT TOP 1 clave_hash FROM dbo.usuarios WHERE correo = N'admin@" + DOMINIO + "')"
        rol_cli = "(SELECT id FROM dbo.roles WHERE codigo = 'CLIENTE')"
        for nombre, correo, cargo, area in CLIENTES_INTERNOS:
            self.w(
                f"INSERT INTO dbo.usuarios (nombre, correo, clave_hash, debe_cambiar_clave, cargo, area_id, rol_id) "
                f"SELECT {q(nombre)}, {q(correo + '@' + DOMINIO)}, {clave}, 0, {q(cargo)}, "
                f"(SELECT id FROM dbo.areas WHERE nombre = {q(area)}), {rol_cli} "
                f"WHERE NOT EXISTS (SELECT 1 FROM dbo.usuarios WHERE correo = {q(correo + '@' + DOMINIO)});"
            )
        for ruc, rs, vip in CLIENTES:
            correo = "comex@" + rs.split()[0].lower().replace("í", "i").replace("á", "a") + ".com.ec"
            self.w(
                f"INSERT INTO dbo.clientes (ruc, razon_social, correo, telefono, es_vip) SELECT '{ruc}', {q(rs)}, {q(correo)}, "
                f"'04-2{self.rnd.randint(100000, 999999)}', {b(vip)} WHERE NOT EXISTS (SELECT 1 FROM dbo.clientes WHERE ruc = '{ruc}');"
            )
        # Variables de búsqueda
        todos = {c for c in ("admin", "mesa.servicios", "gerencia", "supervisor.tecnico", "supervisor.operativo")}
        for cat in CATEGORIAS.values():
            todos.update(cat["responsables"])
        todos.update(c for _, c, _, _ in CLIENTES_INTERNOS)
        for c in sorted(todos):
            self.w(f"DECLARE {var(c)} INT = (SELECT id FROM dbo.usuarios WHERE correo = {q(c + '@' + DOMINIO)});")
        for i, (ruc, _, _) in enumerate(CLIENTES):
            self.w(f"DECLARE @c{i} INT = (SELECT id FROM dbo.clientes WHERE ruc = '{ruc}');")
        for cod in PRIORIDADES:
            self.w(f"DECLARE @p_{cod} INT = (SELECT id FROM dbo.prioridades WHERE codigo = '{cod}');")
        for cod, cat in CATEGORIAS.items():
            self.w(f"DECLARE @k_{cod} INT = (SELECT id FROM dbo.categorias WHERE codigo = '{cod}');")
            for j, s in enumerate(cat["subs"]):
                self.w(f"DECLARE @s_{cod}_{j} INT = (SELECT id FROM dbo.subcategorias WHERE categoria_id = @k_{cod} AND nombre = {q(s)});")
        self.w("SET IDENTITY_INSERT dbo.tickets ON;")

    # --------------------------------------------------------------- ticket
    def ticket(self, tid: int, creado: datetime) -> None:
        r = self.rnd
        cod_cat = r.choices(list(CATEGORIAS), [c["peso"] for c in CATEGORIAS.values()])[0]
        cat = CATEGORIAS[cod_cat]
        j = r.randrange(len(cat["subs"]))
        sub = cat["subs"][j]
        prio = r.choices(list(PRIORIDADES), [p[2] for p in PRIORIDADES.values()])[0]
        sla_resp, sla_res, _ = PRIORIDADES[prio]
        if len(cat["responsables"]) > 1:   # balanceo de carga
            resp = min(cat["responsables"], key=lambda x: (self.carga.get(x, 0), r.random()))
        else:
            resp = cat["responsables"][0]
        self.carga[resp] = self.carga.get(resp, 0) + 1
        sol_nombre, sol_correo, sol_cargo, sol_area = r.choice(CLIENTES_INTERNOS)
        ic = r.randrange(len(CLIENTES)) if r.random() < 0.85 else None
        cliente_nombre = CLIENTES[ic][1] if ic is not None else "cliente"
        asunto = r.choice(ASUNTOS.get(sub, [f"{sub}: solicitud de {{cliente}}", f"Consulta sobre {sub.lower()}"])).format(cliente=cliente_nombre)
        descripcion = r.choice(DESCRIPCIONES)
        numero = f"ADU-{creado.year}-{tid:06d}"

        # Tiempos simulados en minutos laborables desde la creación
        asignacion_m = r.randint(2, 25)
        excede_resp = r.random() < 0.10
        resp_m = max(asignacion_m + 1, int(sla_resp * (r.uniform(1.05, 1.9) if excede_resp else r.uniform(0.15, 0.95))))
        excede_res = r.random() < 0.13
        res_m = max(resp_m + 10, int(sla_res * (r.uniform(1.02, 1.8) if excede_res else r.uniform(0.25, 0.97))))
        # Backlog realista: parte de lo reciente sigue abierto o sin asignar
        reciente = creado > self.ahora - timedelta(days=12)
        if reciente and r.random() < 0.45:
            res_m = int(res_m * r.uniform(1.6, 5.0))
            resp_m = min(resp_m, res_m - 10)
        if creado > self.ahora - timedelta(days=2) and r.random() < 0.2:
            asignacion_m = resp_m = res_m = 10**6   # todavía en cola
        pausa_m = r.randint(45, int(sla_res * 0.6)) if r.random() < 0.22 else 0
        pausa_inicio_m = resp_m + r.randint(5, 60) if pausa_m else None

        t_asig = self.en(creado, min(asignacion_m, 200000))
        t_resp = self.en(creado, min(resp_m, 200000))
        t_pausa_ini = self.en(creado, pausa_inicio_m) if pausa_m else None
        t_pausa_fin = self.en(creado, pausa_inicio_m + pausa_m) if pausa_m else None
        t_res = self.en(creado, min(res_m + pausa_m, 200000))
        t_cierre = self.en(t_res, r.randint(60, 1200)) if r.random() < 0.9 else None
        ahora = self.ahora

        estado = "NUEVO"
        fecha_asig = fecha_resp = fecha_res = fecha_cierre = None
        minutos_pausa = 0
        pausa_desde = None
        historial: list[tuple[datetime, str | None, str, str | None, str | None, str | None]] = []
        pausas: list[tuple[str, datetime, datetime | None, int | None]] = []

        def hist(t, usuario, accion, campo=None, ant=None, nuevo=None):
            historial.append((t, usuario, accion, campo, ant, nuevo))

        hist(creado, sol_correo, "CREACION", None, None, numero)
        if t_asig <= ahora:
            estado, fecha_asig = "ASIGNADO", t_asig
            hist(t_asig, None, "ASIGNACION", "responsable_id", None, resp)
            hist(t_asig, None, "CAMBIO_ESTADO", "estado", "NUEVO", "ASIGNADO")
        if t_resp <= ahora:
            hist(t_resp, resp, "CAMBIO_ESTADO", "estado", estado, "EN_PROCESO")
            estado, fecha_resp = "EN_PROCESO", t_resp
        if t_pausa_ini and t_pausa_ini <= ahora:
            hist(t_pausa_ini, resp, "CAMBIO_ESTADO", "estado", estado, "PENDIENTE_CLIENTE")
            estado, pausa_desde = "PENDIENTE_CLIENTE", t_pausa_ini
            if t_pausa_fin <= ahora:
                hist(t_pausa_fin, sol_correo, "CAMBIO_ESTADO", "estado", "PENDIENTE_CLIENTE", "EN_PROCESO")
                minutos_pausa = self.cal.minutos_laborables(t_pausa_ini, t_pausa_fin)
                pausas.append(("PENDIENTE_CLIENTE", t_pausa_ini, t_pausa_fin, minutos_pausa))
                estado, pausa_desde = "EN_PROCESO", None
            else:
                pausas.append(("PENDIENTE_CLIENTE", t_pausa_ini, None, None))
        if t_res <= ahora and estado != "PENDIENTE_CLIENTE":
            hist(t_res, resp, "CAMBIO_ESTADO", "estado", estado, "RESUELTO")
            estado, fecha_res = "RESUELTO", t_res
            if t_cierre and t_cierre <= ahora:
                hist(t_cierre, resp, "CIERRE", "estado", "RESUELTO", "CERRADO")
                estado, fecha_cierre = "CERRADO", t_cierre
        cancelado = estado in ("NUEVO", "ASIGNADO") and r.random() < 0.02
        if cancelado:
            hist(t_asig if fecha_asig else creado, "mesa.servicios", "CAMBIO_ESTADO", "estado", estado, "CANCELADO")
            estado = "CANCELADO"

        datos = DatosSla(creado, sla_resp, sla_res, minutos_pausa, 0, pausa_desde, fecha_resp, fecha_res)
        sla = calcular_sla(datos, ahora, self.cal)
        resp_cumplido = None
        minutos_resp = None
        if fecha_resp:
            minutos_resp = self.cal.minutos_laborables(creado, fecha_resp)
            resp_cumplido = fecha_resp <= sla.respuesta_vence
        res_cumplido = None
        minutos_res = None
        if fecha_res:
            minutos_res = sla.minutos_consumidos
            res_cumplido = minutos_res <= sla_res
        incumplido = sla.porcentaje >= 100 and estado != "CANCELADO"
        if incumplido and fecha_res:
            res_cumplido = False

        # Escalamientos por umbrales alcanzados
        escalamientos = []
        nivel = 0
        if estado != "CANCELADO":
            for u in (75, 90, 100):
                if sla.porcentaje >= u:
                    nivel = u
                    t_u = self.en(creado, int(sla_res * u / 100) + minutos_pausa)
                    if t_u <= ahora:
                        escalamientos.append((u, t_u))
        if incumplido and estado in ("ASIGNADO", "EN_PROCESO"):
            hist(escalamientos[-1][1] if escalamientos else ahora, None, "CAMBIO_ESTADO", "estado", estado, "ESCALADO")
            estado = "ESCALADO"
        if fecha_res:
            pausas.append(("RESUELTO", fecha_res, fecha_cierre, None if not fecha_cierre else self.cal.minutos_laborables(fecha_res, fecha_cierre)))
        responsable = resp if fecha_asig else None

        # --- INSERT ticket
        self.w(
            "INSERT INTO dbo.tickets (id, numero, asunto, descripcion, solicitante_id, solicitante_nombre, solicitante_cargo, area_id, cliente_id, "
            "correo, telefono, categoria_id, subcategoria_id, prioridad_id, responsable_id, estado, canal, fecha_creacion, fecha_asignacion, "
            "fecha_primera_respuesta, fecha_resolucion, fecha_cierre, fecha_actualizacion, sla_respuesta_min, sla_resolucion_min, sla_respuesta_vence, "
            "sla_resolucion_vence, sla_minutos_pausa, sla_pausa_desde, sla_minutos_consumidos, sla_consumido_pct, sla_respuesta_cumplido, "
            "sla_resolucion_cumplido, sla_incumplido, sla_nivel_alerta, minutos_respuesta, minutos_resolucion) VALUES ("
            f"{tid}, '{numero}', {q(asunto)}, {q(descripcion)}, {var(sol_correo)}, {q(sol_nombre)}, {q(sol_cargo)}, "
            f"(SELECT id FROM dbo.areas WHERE nombre = {q(sol_area)}), {('@c' + str(ic)) if ic is not None else 'NULL'}, "
            f"{q(sol_correo + '@' + DOMINIO)}, '09{r.randint(80000000, 99999999)}', @k_{cod_cat}, @s_{cod_cat}_{j}, @p_{prio}, "
            f"{var(responsable) if responsable else 'NULL'}, '{estado}', '{r.choices(['PORTAL', 'CORREO', 'TELEFONO'], [7, 2, 1])[0]}', "
            f"{f(creado)}, {f(fecha_asig)}, {f(fecha_resp)}, {f(fecha_res)}, {f(fecha_cierre)}, {f(max(h[0] for h in historial))}, "
            f"{sla_resp}, {sla_res}, {f(sla.respuesta_vence)}, {f(sla.resolucion_vence)}, {minutos_pausa}, {f(pausa_desde)}, "
            f"{sla.minutos_consumidos}, {sla.porcentaje:.2f}, {b(resp_cumplido)}, {b(res_cumplido)}, {b(incumplido)}, {nivel}, "
            f"{minutos_resp if minutos_resp is not None else 'NULL'}, {minutos_res if minutos_res is not None else 'NULL'});"
        )
        # --- Historial
        for t, usuario, accion, campo, ant, nuevo in sorted(historial, key=lambda h: h[0]):
            if campo == "responsable_id":
                nuevo = NOMBRES_RESPONSABLES[nuevo]
            self.w(
                f"INSERT INTO dbo.ticket_historial (ticket_id, usuario_id, accion, campo, valor_anterior, valor_nuevo, fecha) VALUES "
                f"({tid}, {var(usuario) if usuario else 'NULL'}, '{accion}', {q(campo)}, {q(ant)}, {q(nuevo)}, {f(t)});"
            )
        if fecha_asig:
            self.w(
                f"INSERT INTO dbo.ticket_asignaciones (ticket_id, responsable_anterior_id, responsable_nuevo_id, asignado_por, tipo, motivo, fecha) "
                f"VALUES ({tid}, NULL, {var(resp)}, NULL, 'AUTOMATICA', N'Asignación automática por catálogo', {f(fecha_asig)});"
            )
        # --- Comentarios
        if fecha_resp:
            self.w(
                f"INSERT INTO dbo.ticket_comentarios (ticket_id, usuario_id, texto, es_interno, tipo, fecha) VALUES ({tid}, {var(resp)}, "
                f"N'Recibido. Estamos revisando la documentación y le informaremos los próximos pasos.', 0, 'COMENTARIO', {f(fecha_resp)});"
            )
        if t_pausa_ini and t_pausa_ini <= ahora:
            self.w(
                f"INSERT INTO dbo.ticket_comentarios (ticket_id, usuario_id, texto, es_interno, tipo, fecha) VALUES ({tid}, {var(resp)}, "
                f"N'Para continuar necesitamos la factura comercial definitiva y el documento de transporte.', 0, 'COMENTARIO', {f(t_pausa_ini)});"
            )
            if t_pausa_fin <= ahora:
                self.w(
                    f"INSERT INTO dbo.ticket_comentarios (ticket_id, usuario_id, texto, es_interno, tipo, fecha) VALUES ({tid}, {var(sol_correo)}, "
                    f"N'Adjunto la documentación solicitada.', 0, 'COMENTARIO', {f(t_pausa_fin)});"
                )
        if fecha_res:
            self.w(
                f"INSERT INTO dbo.ticket_comentarios (ticket_id, usuario_id, texto, es_interno, tipo, minutos_invertidos, fecha) VALUES ({tid}, {var(resp)}, "
                f"N'Trámite gestionado y documentación enviada al solicitante.', 0, 'ACTIVIDAD', {r.randint(20, 240)}, {f(fecha_res)});"
            )
        # --- Pausas
        for est, ini, fin, mins in pausas:
            self.w(
                f"INSERT INTO dbo.sla_pausas (ticket_id, estado, inicio, fin, minutos_laborables) VALUES ({tid}, '{est}', {f(ini)}, {f(fin)}, "
                f"{mins if mins is not None else 'NULL'});"
            )
        # --- Escalamientos, notificaciones e incumplimientos
        for u, t_u in escalamientos:
            destino = resp if u == 75 else cat["sup"]
            self.w(
                f"INSERT INTO dbo.ticket_escalamientos (ticket_id, nivel, tipo, escalado_a, motivo, sla_consumido_pct, fecha) VALUES "
                f"({tid}, {u}, 'AUTOMATICO', {var(destino)}, N'SLA consumido al {u} %', {u}, {f(t_u)});"
            )
            if estado not in ("RESUELTO", "CERRADO", "CANCELADO"):
                sev = {75: "AVISO", 90: "AVISO", 100: "CRITICO"}[u]
                tipo = {75: "SLA_75", 90: "SLA_90", 100: "SLA_VENCIDO"}[u]
                self.w(
                    f"INSERT INTO dbo.notificaciones (usuario_id, ticket_id, tipo, severidad, titulo, mensaje, fecha) VALUES ({var(destino)}, {tid}, "
                    f"'{tipo}', '{sev}', {q(f'{numero}: SLA al {u} %')}, {q(f'El ticket «{asunto}» consumió el {u} % de su SLA.')}, {f(t_u)});"
                )
        if incumplido:
            self.w(
                f"INSERT INTO dbo.sla_incumplimientos (ticket_id, tipo, responsable_id, categoria_id, prioridad_id, fecha_vencimiento, fecha_registro) "
                f"VALUES ({tid}, 'RESOLUCION', {var(resp)}, @k_{cod_cat}, @p_{prio}, {f(sla.resolucion_vence)}, {f(min(sla.resolucion_vence, ahora))});"
            )
        if resp_cumplido is False:
            self.w(
                f"INSERT INTO dbo.sla_incumplimientos (ticket_id, tipo, responsable_id, categoria_id, prioridad_id, fecha_vencimiento, fecha_registro) "
                f"VALUES ({tid}, 'RESPUESTA', {var(resp)}, @k_{cod_cat}, @p_{prio}, {f(sla.respuesta_vence)}, {f(fecha_resp)});"
            )
        # --- Auditoría
        self.w(
            f"INSERT INTO dbo.auditoria (usuario_id, usuario_correo, fecha_hora, accion, entidad, entidad_id, detalle, ip, equipo) VALUES "
            f"({var(sol_correo)}, {q(sol_correo + '@' + DOMINIO)}, {f(creado)}, 'TICKET_CREADO', 'ticket', '{tid}', "
            f"{q('{\"numero\": \"' + numero + '\"}')}, '10.10.1.{r.randint(10, 200)}', N'Chrome / Windows 11');"
        )
        if fecha_cierre:
            self.w(
                f"INSERT INTO dbo.auditoria (usuario_id, usuario_correo, fecha_hora, accion, entidad, entidad_id, ip, equipo) VALUES "
                f"({var(resp)}, {q(resp + '@' + DOMINIO)}, {f(fecha_cierre)}, 'CIERRE', 'ticket', '{tid}', '10.10.2.{r.randint(10, 200)}', N'Edge / Windows 11');"
            )

    def logins(self) -> None:
        usuarios = ["admin", "mesa.servicios", "gerencia", "supervisor.tecnico", "supervisor.operativo"]
        for cat in CATEGORIAS.values():
            usuarios += cat["responsables"]
        d = max(self.desde, (self.ahora - timedelta(days=30)).date())
        while d <= self.ahora.date():
            if d.weekday() < 5:
                for u in usuarios:
                    if self.rnd.random() < 0.8:
                        t = datetime(d.year, d.month, d.day, 13, self.rnd.randint(25, 59))
                        if t < self.ahora:
                            self.w(
                                f"INSERT INTO dbo.auditoria (usuario_id, usuario_correo, fecha_hora, accion, entidad, ip, equipo) VALUES "
                                f"({var(u)}, {q(u + '@' + DOMINIO)}, {f(t)}, 'LOGIN', 'sesion', '10.10.1.{self.rnd.randint(10, 200)}', N'Chrome / Windows 11');"
                            )
            d += timedelta(days=1)

    def generar(self) -> str:
        self.cabecera()
        fechas = sorted(self.fecha_creacion_aleatoria() for _ in range(self.n))
        for i, creado in enumerate(fechas, start=1):
            self.ticket(i, creado)
        self.w("SET IDENTITY_INSERT dbo.tickets OFF;")
        self.w(
            f"MERGE dbo.ticket_secuencias AS d USING (SELECT {self.ahora.year} AS anio, {self.n} AS ultimo) s ON d.anio = s.anio "
            "WHEN MATCHED THEN UPDATE SET ultimo = s.ultimo WHEN NOT MATCHED THEN INSERT (anio, ultimo) VALUES (s.anio, s.ultimo);"
        )
        self.logins()
        self.w("COMMIT;")
        self.w(f"PRINT N'06_datos_demo.sql aplicado: {self.n} tickets.';")
        self.w("GO\nSET NOEXEC OFF;\nGO")
        return "\n".join(self.sql) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", type=int, default=650)
    ap.add_argument("--desde", type=date.fromisoformat, default=date(2026, 4, 1))
    ap.add_argument("--ahora", type=datetime.fromisoformat, default=None, help="Fecha de corte UTC (por defecto, ahora)")
    ap.add_argument("--salida", type=Path, default=Path(__file__).resolve().parents[2] / "database" / "06_datos_demo.sql")
    a = ap.parse_args()
    ahora = a.ahora or datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0, second=0)
    if ahora.year != a.desde.year:
        raise SystemExit("La numeración demo asume un solo año: use --desde del mismo año que la fecha de corte")
    sql = Generador(a.tickets, a.desde, ahora).generar()
    a.salida.write_text(sql, encoding="utf-8")
    print(f"Generado {a.salida} ({len(sql) // 1024} KB)")


if __name__ == "__main__":
    main()
