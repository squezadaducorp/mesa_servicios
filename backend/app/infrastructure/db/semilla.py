"""Semilla mínima para desarrollo local y pruebas (SQLite).

En SQL Server la fuente de verdad son database/05_datos_iniciales.sql y 06_datos_demo.sql.
Uso: python -m app.infrastructure.db.semilla
"""
from datetime import date, time

from sqlalchemy.orm import Session

from app.core.security import hash_clave
from app.infrastructure.db import models as m
from app.infrastructure.db.session import Base, SessionLocal, engine
from scripts.generar_datos_demo import CATEGORIAS, NOMBRES_RESPONSABLES

DOMINIO = "aducorp.com.ec"
CLAVE_DEMO = "Aducorp2026!"

PERMISOS_POR_ROL = {
    "ADMIN_MESA": ["sla.modificar", "ticket.ver_todos", "ticket.ver_area", "ticket.ver_asignados", "ticket.ver_propios", "ticket.crear",
                   "ticket.editar", "ticket.asignar", "ticket.escalar", "ticket.cambiar_estado", "ticket.cerrar", "ticket.reabrir",
                   "ticket.comentar", "ticket.adjuntar", "reporte.ver", "dashboard.ver", "datos.exportar", "ia.usar"],
    "SUPERVISOR": ["ticket.ver_area", "ticket.ver_asignados", "ticket.ver_propios", "ticket.crear", "ticket.editar", "ticket.asignar",
                   "ticket.escalar", "ticket.cambiar_estado", "ticket.cerrar", "ticket.reabrir", "ticket.comentar", "ticket.adjuntar",
                   "reporte.ver", "dashboard.ver", "ia.usar"],
    "ANALISTA": ["ticket.ver_asignados", "ticket.ver_propios", "ticket.crear", "ticket.editar", "ticket.escalar", "ticket.cambiar_estado",
                 "ticket.cerrar", "ticket.comentar", "ticket.adjuntar", "ia.usar"],
    "CLIENTE": ["ticket.ver_propios", "ticket.crear", "ticket.reabrir", "ticket.comentar", "ticket.adjuntar"],
    "GERENCIA": ["ticket.ver_todos", "reporte.ver", "dashboard.ver", "datos.exportar"],
}
TODOS_PERMISOS = sorted({p for ps in PERMISOS_POR_ROL.values() for p in ps} | {
    "sistema.administrar", "usuario.administrar", "rol.administrar", "categoria.administrar", "registro.eliminar", "auditoria.ver"})

NOMBRES_CATEGORIA = {"CLASIF_ARANCEL": "Clasificación Arancelaria", "LEGAL_ADUANERO": "Legal Aduanero", "CONSULTAS_FEDEX": "Consultas FedEx",
                     "REGIMENES_ESP": "Regímenes Especiales", "TRAMITES_ADUANA": "Trámites Aduaneros"}
PALABRAS_CATEGORIA = {
    "CLASIF_ARANCEL": "clasificación,arancel,partida,subpartida,aforo,dai,dae,embarque,control previo",
    "LEGAL_ADUANERO": "legal,recurso,demanda,impugnación,pago indebido,sanción,multa,abogado",
    "CONSULTAS_FEDEX": "fedex,courier,tracking,guía,envío,paquete,entrega,desaduanización",
    "REGIMENES_ESP": "régimen,admisión temporal,drawback,zona franca,depósito aduanero,transformación",
    "TRAMITES_ADUANA": "trámite,senae,ecuapass,hoja de cambio,regularización,certificado de origen,garantía,nacionalización",
}


def sembrar(session: Session, clave: str = CLAVE_DEMO) -> None:
    if session.query(m.Rol).count():
        return
    h = hash_clave(clave)
    for i, (c, n, pausa, final) in enumerate([("NUEVO", "Nuevo", 0, 0), ("ASIGNADO", "Asignado", 0, 0), ("EN_PROCESO", "En Proceso", 0, 0),
                                              ("PENDIENTE_CLIENTE", "Pendiente Cliente", 1, 0), ("ESCALADO", "Escalado", 0, 0),
                                              ("RESUELTO", "Resuelto", 1, 0), ("CERRADO", "Cerrado", 1, 1), ("CANCELADO", "Cancelado", 1, 1)], 1):
        session.add(m.EstadoTicket(codigo=c, nombre=n, orden=i, pausa_sla=bool(pausa), es_final=bool(final)))
    for i, (c, n, r1, r2) in enumerate([("URGENTE", "Urgente", 60, 240), ("ALTA", "Alta", 120, 480), ("MEDIA", "Media", 240, 1440),
                                        ("BAJA", "Baja", 480, 2880)], 1):
        session.add(m.Prioridad(codigo=c, nombre=n, orden=i, sla_respuesta_min=r1, sla_resolucion_min=r2))
    permisos = {c: m.Permiso(codigo=c, modulo=c.split(".")[0], descripcion=c) for c in TODOS_PERMISOS}
    session.add_all(permisos.values())
    roles = {"SUPER_ADMIN": m.Rol(codigo="SUPER_ADMIN", nombre="Super Administrador", permisos=list(permisos.values()))}
    nombres = {"ADMIN_MESA": "Administrador Mesa de Servicio", "SUPERVISOR": "Supervisor", "ANALISTA": "Analista",
               "CLIENTE": "Cliente Interno", "GERENCIA": "Gerencia"}
    for codigo, ps in PERMISOS_POR_ROL.items():
        roles[codigo] = m.Rol(codigo=codigo, nombre=nombres[codigo], permisos=[permisos[p] for p in ps])
    session.add_all(roles.values())
    areas = {n: m.Area(nombre=n) for n in ("Operaciones Aduaneras", "Comercial", "Legal", "Gerencia General", "Tecnología", "Courier")}
    session.add_all(areas.values())
    session.flush()

    def usuario(local, nombre, rol, area="Operaciones Aduaneras", cargo=None):
        u = m.Usuario(nombre=nombre, correo=f"{local}@{DOMINIO}", clave_hash=h, rol_id=roles[rol].id, area_id=areas[area].id, cargo=cargo)
        session.add(u)
        return u

    usuario("admin", "Administrador del Sistema", "SUPER_ADMIN", "Tecnología")
    usuario("mesa.servicios", "Coordinador Mesa de Servicio", "ADMIN_MESA")
    usuario("gerencia", "Gerencia General", "GERENCIA", "Gerencia General")
    sup_t = usuario("supervisor.tecnico", "Supervisor Técnico Legal", "SUPERVISOR", "Legal")
    sup_o = usuario("supervisor.operativo", "Supervisor Operativo", "SUPERVISOR")
    analistas = {k: usuario(k, v, "ANALISTA") for k, v in NOMBRES_RESPONSABLES.items()}
    usuario("maria.andrade", "María Fernanda Andrade", "CLIENTE", "Comercial", "Ejecutiva de Cuenta")
    usuario("luis.paredes", "Luis Alberto Paredes", "CLIENTE", "Comercial", "Coordinador Logístico")
    session.flush()

    for orden, (codigo, cat) in enumerate(CATEGORIAS.items(), 1):
        c = m.Categoria(codigo=codigo, nombre=NOMBRES_CATEGORIA[codigo], orden=orden, palabras_clave=PALABRAS_CATEGORIA[codigo],
                        supervisor_id=(sup_t if cat["sup"] == "supervisor.tecnico" else sup_o).id,
                        modo_asignacion="BALANCEO" if len(cat["responsables"]) > 1 else "PRINCIPAL")
        session.add(c)
        session.flush()
        for i, r in enumerate(cat["responsables"]):
            session.add(m.CategoriaResponsable(categoria_id=c.id, usuario_id=analistas[r].id, es_principal=i == 0))
        for sub in cat["subs"]:
            session.add(m.Subcategoria(categoria_id=c.id, nombre=sub, palabras_clave=sub.lower(),
                                       respuesta_plantilla="Estimado/a {solicitante}: recibimos su solicitud {numero}. {responsable} la está revisando."))
    session.add(m.Cliente(ruc="0992345678001", razon_social="Importadora Andina del Pacífico S.A.", es_vip=True))
    session.add(m.Cliente(ruc="1791234567001", razon_social="Comercial Quitumbe Cía. Ltda."))

    horario = m.HorarioLaboral(nombre="Horario ADUCORP", es_predeterminado=True)
    horario.tramos = [m.HorarioTramo(dia_semana=d, hora_inicio=i, hora_fin=f) for d in range(1, 6)
                      for i, f in ((time(8, 30), time(13, 0)), (time(14, 0), time(17, 30)))]
    session.add(horario)
    session.add(m.CalendarioExcepcion(fecha=date(2026, 11, 2), tipo="FERIADO", descripcion="Día de los Difuntos"))
    for codigo, asunto in (("TICKET_CREADO", "[{numero}] Ticket creado"), ("TICKET_ASIGNADO", "[{numero}] Ticket asignado"),
                           ("TICKET_ESCALADO", "[{numero}] Ticket escalado"), ("SLA_75", "[{numero}] Próximo a vencer"),
                           ("SLA_90", "[{numero}] SLA 90 %"), ("SLA_VENCIDO", "[{numero}] SLA incumplido"), ("TICKET_CERRADO", "[{numero}] Ticket cerrado"),
                           ("ACUSE_CORREO", "[{numero}] Recibimos su solicitud: {asunto}"),
                           ("RESPUESTA_TICKET", "[{numero}] Respuesta: {asunto}")):
        session.add(m.PlantillaCorreo(codigo=codigo, asunto=asunto, cuerpo_html="<p>Hola {destinatario}: {asunto} {comentario} <a href='{url}'>ver</a></p>"))
    for k, v in (("empresa.nombre", "ADUCORP Asesores Aduaneros y Logísticos Cía. Ltda."), ("sla.umbral_aviso_1", "75"),
                 ("sla.umbral_aviso_2", "90"), ("ticket.cierre_automatico_h", "72"), ("adjuntos.max_mb", "20"),
                 ("adjuntos.extensiones", "pdf,doc,docx,xls,xlsx,csv,jpg,jpeg,png,txt,xml,zip,msg,eml"),
                 ("seguridad.max_intentos", "5"), ("seguridad.bloqueo_min", "15")):
        session.add(m.Configuracion(clave=k, valor=v))
    session.commit()


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        sembrar(s)
    print("Base de desarrollo lista. Usuario: admin@aducorp.com.ec / Aducorp2026!")
