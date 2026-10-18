"""Enumeraciones del dominio. Los valores coinciden con los códigos en base de datos."""
from enum import StrEnum


class Estado(StrEnum):
    NUEVO = "NUEVO"
    ASIGNADO = "ASIGNADO"
    EN_PROCESO = "EN_PROCESO"
    PENDIENTE_CLIENTE = "PENDIENTE_CLIENTE"
    ESCALADO = "ESCALADO"
    RESUELTO = "RESUELTO"
    CERRADO = "CERRADO"
    CANCELADO = "CANCELADO"


# Estados en los que el reloj del SLA está detenido.
ESTADOS_PAUSA_SLA = {Estado.PENDIENTE_CLIENTE, Estado.RESUELTO, Estado.CERRADO, Estado.CANCELADO}
# Estados que cuentan como "abierto" en los indicadores.
ESTADOS_ABIERTOS = {Estado.NUEVO, Estado.ASIGNADO, Estado.EN_PROCESO, Estado.PENDIENTE_CLIENTE, Estado.ESCALADO}
ESTADOS_CERRADOS = {Estado.RESUELTO, Estado.CERRADO}
ESTADOS_FINALES = {Estado.CERRADO, Estado.CANCELADO}


class Prioridad(StrEnum):
    URGENTE = "URGENTE"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


class Rol(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN_MESA = "ADMIN_MESA"
    SUPERVISOR = "SUPERVISOR"
    ANALISTA = "ANALISTA"
    CLIENTE = "CLIENTE"
    GERENCIA = "GERENCIA"


class Permiso(StrEnum):
    SISTEMA_ADMINISTRAR = "sistema.administrar"
    USUARIO_ADMINISTRAR = "usuario.administrar"
    ROL_ADMINISTRAR = "rol.administrar"
    CATEGORIA_ADMINISTRAR = "categoria.administrar"
    SLA_MODIFICAR = "sla.modificar"
    TICKET_VER_TODOS = "ticket.ver_todos"
    TICKET_VER_AREA = "ticket.ver_area"
    TICKET_VER_ASIGNADOS = "ticket.ver_asignados"
    TICKET_VER_PROPIOS = "ticket.ver_propios"
    TICKET_CREAR = "ticket.crear"
    TICKET_EDITAR = "ticket.editar"
    TICKET_ASIGNAR = "ticket.asignar"
    TICKET_ESCALAR = "ticket.escalar"
    TICKET_CAMBIAR_ESTADO = "ticket.cambiar_estado"
    TICKET_CERRAR = "ticket.cerrar"
    TICKET_REABRIR = "ticket.reabrir"
    TICKET_COMENTAR = "ticket.comentar"
    TICKET_ADJUNTAR = "ticket.adjuntar"
    REGISTRO_ELIMINAR = "registro.eliminar"
    REPORTE_VER = "reporte.ver"
    DASHBOARD_VER = "dashboard.ver"
    DATOS_EXPORTAR = "datos.exportar"
    AUDITORIA_VER = "auditoria.ver"
    IA_USAR = "ia.usar"


class AccionAuditoria(StrEnum):
    LOGIN = "LOGIN"
    LOGIN_FALLIDO = "LOGIN_FALLIDO"
    LOGOUT = "LOGOUT"
    TICKET_CREADO = "TICKET_CREADO"
    TICKET_MODIFICADO = "TICKET_MODIFICADO"
    CAMBIO_ESTADO = "CAMBIO_ESTADO"
    ASIGNACION = "ASIGNACION"
    ESCALAMIENTO = "ESCALAMIENTO"
    CIERRE = "CIERRE"
    REAPERTURA = "REAPERTURA"
    EXPORTACION = "EXPORTACION"
    CAMBIO_SLA = "CAMBIO_SLA"
    CAMBIO_ROL = "CAMBIO_ROL"
    USUARIO_MODIFICADO = "USUARIO_MODIFICADO"
    CATEGORIA_MODIFICADA = "CATEGORIA_MODIFICADA"
    REGISTRO_ELIMINADO = "REGISTRO_ELIMINADO"
    ADJUNTO_SUBIDO = "ADJUNTO_SUBIDO"
    ADJUNTO_DESCARGADO = "ADJUNTO_DESCARGADO"
    CAMBIO_CLAVE = "CAMBIO_CLAVE"
