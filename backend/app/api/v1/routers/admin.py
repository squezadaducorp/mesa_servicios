from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as s
from app.application.schemas import mejoras2 as s2
from app.application.services.admin_service import (AdminService, categoria_salida, delegacion_salida, guardar_delegacion,
                                                    usuario_salida)
from app.domain.enums import Permiso
from app.infrastructure.repositories.repositorios import CatalogoRepository

router = APIRouter(prefix="/admin", tags=["Administración"])

ADMIN_USUARIOS = requiere(Permiso.USUARIO_ADMINISTRAR)
ADMIN_ROLES = requiere(Permiso.ROL_ADMINISTRAR)
ADMIN_CATALOGO = requiere(Permiso.CATEGORIA_ADMINISTRAR)
ADMIN_SLA = requiere(Permiso.SLA_MODIFICAR)
ADMIN_SISTEMA = requiere(Permiso.SISTEMA_ADMINISTRAR)


# ------------------------------------------------------------------ usuarios
@router.get("/usuarios", response_model=s.Pagina[s.UsuarioSalida], summary="Listar usuarios")
def usuarios(texto: str | None = None, rol_id: int | None = None, pagina: int = Query(1, ge=1), tamano: int = Query(50, ge=1, le=500),
             ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    items, total = AdminService(session).listar_usuarios(texto, rol_id, pagina, tamano)
    return {"items": [usuario_salida(u) for u in items], "total": total, "pagina": pagina, "tamano": tamano}


@router.post("/usuarios", status_code=201, summary="Crear usuario")
def crear_usuario(dto: s.UsuarioCrear, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    u, temporal = AdminService(session).crear_usuario(dto, ctx)
    return {"usuario": usuario_salida(u), "clave_temporal": temporal}


@router.patch("/usuarios/{usuario_id}", response_model=s.UsuarioSalida, summary="Editar usuario, cambiar rol o activar/desactivar")
def editar_usuario(usuario_id: int, dto: s.UsuarioEditar, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    return usuario_salida(AdminService(session).editar_usuario(usuario_id, dto, ctx))


@router.post("/usuarios/{usuario_id}/restablecer-clave", response_model=s.ClaveTemporalSalida, summary="Generar contraseña temporal")
def restablecer(usuario_id: int, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    return {"clave_temporal": AdminService(session).restablecer_clave(usuario_id, ctx)}


@router.delete("/usuarios/{usuario_id}", response_model=s.Mensaje, summary="Eliminar usuario (lógico)")
def eliminar_usuario(usuario_id: int, ctx: Contexto = Depends(requiere(Permiso.REGISTRO_ELIMINAR)), session: Session = DbSession):
    AdminService(session).eliminar_usuario(usuario_id, ctx)
    return {"mensaje": "Usuario eliminado"}


@router.get("/usuarios/{usuario_id}/en-nombre", response_model=s2.DelegacionSalida,
            summary="Permiso para crear tickets en nombre de otras personas")
def ver_delegacion(usuario_id: int, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    from app.infrastructure.db import models as m

    return delegacion_salida(session.get(m.UsuarioDelegacion, usuario_id), session)


@router.put("/usuarios/{usuario_id}/en-nombre", response_model=s2.DelegacionSalida,
            summary="Activar, limitar por áreas y fecha, o quitar el permiso de crear tickets en nombre de otras personas")
def editar_delegacion(usuario_id: int, dto: s2.DelegacionEntrada, ctx: Contexto = Depends(ADMIN_USUARIOS), session: Session = DbSession):
    return delegacion_salida(guardar_delegacion(session, usuario_id, dto, ctx), session)


# --------------------------------------------------------------------- roles
@router.get("/roles", response_model=list[s.RolSalida], summary="Roles y sus permisos")
def roles(ctx: Contexto = Depends(requiere(Permiso.USUARIO_ADMINISTRAR, Permiso.ROL_ADMINISTRAR)), session: Session = DbSession):
    return AdminService(session).roles()


@router.get("/permisos", response_model=list[s.PermisoSalida], summary="Catálogo de permisos")
def permisos(ctx: Contexto = Depends(ADMIN_ROLES), session: Session = DbSession):
    return AdminService(session).permisos()


@router.put("/roles/{rol_id}/permisos", response_model=s.Mensaje, summary="Actualizar la matriz RBAC de un rol")
def permisos_rol(rol_id: int, dto: s.RolPermisosEntrada, ctx: Contexto = Depends(ADMIN_ROLES), session: Session = DbSession):
    AdminService(session).actualizar_permisos_rol(rol_id, dto.permisos, ctx)
    return {"mensaje": "Permisos actualizados"}


# ----------------------------------------------------------------- catálogo
@router.get("/categorias", response_model=list[s.CategoriaAdminSalida], summary="Categorías (incluye inactivas)")
def categorias(ctx: Contexto = Depends(ADMIN_CATALOGO), session: Session = DbSession):
    return [categoria_salida(c) for c in CatalogoRepository(session).categorias(solo_activas=False)]


@router.post("/categorias", response_model=s.CategoriaAdminSalida, status_code=201)
def crear_categoria(dto: s.CategoriaEntrada, ctx: Contexto = Depends(ADMIN_CATALOGO), session: Session = DbSession):
    return categoria_salida(AdminService(session).guardar_categoria(dto, ctx))


@router.put("/categorias/{categoria_id}", response_model=s.CategoriaAdminSalida)
def editar_categoria(categoria_id: int, dto: s.CategoriaEntrada, ctx: Contexto = Depends(ADMIN_CATALOGO), session: Session = DbSession):
    return categoria_salida(AdminService(session).guardar_categoria(dto, ctx, categoria_id))


@router.delete("/categorias/{categoria_id}", response_model=s.Mensaje)
def eliminar_categoria(categoria_id: int, ctx: Contexto = Depends(requiere(Permiso.REGISTRO_ELIMINAR)), session: Session = DbSession):
    AdminService(session).eliminar_categoria(categoria_id, ctx)
    return {"mensaje": "Categoría eliminada"}


@router.post("/categorias/{categoria_id}/subcategorias", response_model=s.SubcategoriaSalida, status_code=201)
def crear_sub(categoria_id: int, dto: s.SubcategoriaEntrada, ctx: Contexto = Depends(ADMIN_CATALOGO), session: Session = DbSession):
    return AdminService(session).guardar_subcategoria(categoria_id, dto, ctx)


@router.put("/categorias/{categoria_id}/subcategorias/{sub_id}", response_model=s.SubcategoriaSalida)
def editar_sub(categoria_id: int, sub_id: int, dto: s.SubcategoriaEntrada, ctx: Contexto = Depends(ADMIN_CATALOGO), session: Session = DbSession):
    return AdminService(session).guardar_subcategoria(categoria_id, dto, ctx, sub_id)


@router.get("/clientes", response_model=list[s.ClienteAdminSalida], summary="Clientes con sus correos en copia automática")
def clientes(ctx: Contexto = Depends(requiere(Permiso.CATEGORIA_ADMINISTRAR, Permiso.TICKET_VER_TODOS)), session: Session = DbSession):
    return CatalogoRepository(session).clientes()


@router.post("/clientes", response_model=s.ClienteAdminSalida, status_code=201)
def crear_cliente(dto: s.ClienteEntrada, ctx: Contexto = Depends(requiere(Permiso.CATEGORIA_ADMINISTRAR, Permiso.TICKET_VER_TODOS)),
                  session: Session = DbSession):
    return AdminService(session).guardar_cliente(dto, ctx)


@router.put("/clientes/{cliente_id}", response_model=s.ClienteAdminSalida)
def editar_cliente(cliente_id: int, dto: s.ClienteEntrada, ctx: Contexto = Depends(requiere(Permiso.CATEGORIA_ADMINISTRAR, Permiso.TICKET_VER_TODOS)),
                   session: Session = DbSession):
    return AdminService(session).guardar_cliente(dto, ctx, cliente_id)


# ---------------------------------------------------------------------- SLA
@router.put("/sla/prioridades/{prioridad_id}", response_model=s.PrioridadSalida, summary="Modificar SLA de una prioridad")
def sla_prioridad(prioridad_id: int, dto: s.PrioridadSlaEntrada, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).actualizar_sla_prioridad(prioridad_id, dto, ctx)


@router.get("/sla/politicas", response_model=list[s.PoliticaSlaSalida], summary="SLA específicos por categoría")
def politicas(ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).politicas()


@router.post("/sla/politicas", response_model=s.PoliticaSlaSalida, summary="Crear o actualizar SLA por categoría y prioridad")
def guardar_politica(dto: s.PoliticaSlaEntrada, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).guardar_politica(dto, ctx)


@router.get("/sla/horario", response_model=s.HorarioSalida | None, summary="Horario laboral")
def horario(ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).horario()


@router.put("/sla/horario", response_model=s.HorarioSalida, summary="Configurar horario laboral")
def guardar_horario(dto: s.HorarioEntrada, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).guardar_horario(dto, ctx)


@router.get("/sla/calendario", response_model=list[s.ExcepcionCalendarioSalida], summary="Feriados y jornadas especiales")
def calendario(ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return CatalogoRepository(session).excepciones_calendario()


@router.post("/sla/calendario", response_model=s.ExcepcionCalendarioSalida, status_code=201)
def crear_excepcion(dto: s.ExcepcionCalendarioEntrada, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    return AdminService(session).guardar_excepcion(dto, ctx)


@router.delete("/sla/calendario/{excepcion_id}", response_model=s.Mensaje)
def eliminar_excepcion(excepcion_id: int, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    AdminService(session).eliminar_excepcion(excepcion_id, ctx)
    return {"mensaje": "Excepción eliminada"}


# ------------------------------------------------------------ configuración
CLAVES_ALERTAS = ("sla.avisar_por", "sla.aviso_previo_1_min", "sla.aviso_previo_2_min", "sla.aviso_respuesta_min",
                  "sla.resumen_diario_hora", "sla.umbral_aviso_1", "sla.umbral_aviso_2")


@router.get("/sla/alertas", response_model=dict[str, str], summary="Avisos antes de vencer y resumen diario")
def alertas(ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    valores = {c.clave: c.valor for c in AdminService(session).configuracion()}
    return {k: valores.get(k, "") for k in CLAVES_ALERTAS}


@router.put("/sla/alertas", response_model=s.Mensaje, summary="Guardar avisos antes de vencer y resumen diario")
def guardar_alertas(dto: s.ConfiguracionEntrada, ctx: Contexto = Depends(ADMIN_SLA), session: Session = DbSession):
    from app.application.errores import ReglaNegocio
    from app.application.services.resumen_service import hora_configurada

    v = {k: str(x).strip() for k, x in dto.valores.items() if k in CLAVES_ALERTAS}
    if set(dto.valores) - set(CLAVES_ALERTAS):
        raise ReglaNegocio("Solo se pueden modificar los parámetros de alertas de SLA")
    for k in ("sla.aviso_previo_1_min", "sla.aviso_previo_2_min", "sla.aviso_respuesta_min", "sla.umbral_aviso_1", "sla.umbral_aviso_2"):
        if k in v and not v[k].isdigit():
            raise ReglaNegocio("Los minutos y porcentajes deben ser números enteros")
    actual = {c.clave: c.valor for c in AdminService(session).configuracion()} | v
    if int(actual.get("sla.aviso_previo_2_min", "30")) >= int(actual.get("sla.aviso_previo_1_min", "120")):
        raise ReglaNegocio("El 2.º aviso debe ser más cercano al vencimiento que el 1.º")
    if v.get("sla.avisar_por", "tiempo") not in ("tiempo", "porcentaje"):
        raise ReglaNegocio("Indique si se avisa por tiempo o por porcentaje")
    if v.get("sla.resumen_diario_hora") and hora_configurada(v["sla.resumen_diario_hora"]) is None:
        raise ReglaNegocio("La hora del resumen debe tener el formato HH:MM")
    AdminService(session).guardar_configuracion(v, ctx)
    return {"mensaje": "Alertas guardadas"}


@router.get("/configuracion", response_model=list[s.ConfiguracionItem])
def configuracion(ctx: Contexto = Depends(ADMIN_SISTEMA), session: Session = DbSession):
    return AdminService(session).configuracion()


@router.put("/configuracion", response_model=s.Mensaje)
def guardar_configuracion(dto: s.ConfiguracionEntrada, ctx: Contexto = Depends(ADMIN_SISTEMA), session: Session = DbSession):
    AdminService(session).guardar_configuracion(dto.valores, ctx)
    return {"mensaje": "Configuración guardada"}


# ------------------------------------------------------------ Microsoft 365
@router.get("/integraciones", summary="Estado de la integración con Microsoft 365 (Entra ID, buzón y Teams)")
def integraciones(ctx: Contexto = Depends(ADMIN_SISTEMA), session: Session = DbSession):
    from sqlalchemy import func, select

    from app.core.config import settings
    from app.infrastructure.db import models as m

    correos = session.scalars(select(m.CorreoEntrante).order_by(m.CorreoEntrante.id.desc()).limit(10)).all()
    canales = session.scalars(select(m.TeamsCanal).where(m.TeamsCanal.activo == True).order_by(m.TeamsCanal.nombre)).unique().all()
    pendientes = session.scalar(select(func.count()).select_from(m.ColaTeams).where(m.ColaTeams.estado.in_(["PENDIENTE", "ERROR"])))
    return {
        "aplicacion_configurada": settings.m365_configurado,
        "entra": {
            "activo": settings.entra_activo,
            "grupos_mapeados": len(settings.ENTRA_GRUPO_ROLES),
            "rol_defecto": settings.ENTRA_ROL_DEFECTO or None,
            "exigir_mfa": settings.ENTRA_EXIGIR_MFA,
            "usuarios": session.scalar(select(func.count()).select_from(m.Usuario).where(m.Usuario.origen_autenticacion == "ENTRA",
                                                                                        m.Usuario.eliminado == False)),
        },
        "buzon": {
            "activo": settings.BUZON_ENABLED,
            "correo": settings.BUZON_CORREO,
            "envio_por_graph": settings.EMAIL_TRANSPORTE == "graph",
            "ultimos": [{"fecha": c.fecha_proceso, "remitente": c.remitente, "asunto": c.asunto, "resultado": c.resultado,
                         "ticket_id": c.ticket_id, "detalle": c.detalle} for c in correos],
        },
        "teams": {
            "activo": settings.TEAMS_ENABLED,
            "eventos": settings.TEAMS_EVENTOS,
            "pendientes": pendientes,
            "canales": [{"nombre": c.nombre, "categoria": c.categoria.nombre if c.categoria else "General (todas)"} for c in canales],
        },
    }
