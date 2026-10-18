"""Administración: usuarios, roles, catálogo, SLA, calendario y configuración."""
from __future__ import annotations

import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.sla_service import invalidar_calendario
from app.core.security import hash_clave, utcnow, validar_politica_clave
from app.domain.enums import AccionAuditoria, Rol
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository, RefreshTokenRepository, UsuarioRepository


def clave_temporal() -> str:
    while True:
        c = "".join(secrets.choice(string.ascii_letters + string.digits + "!#$%&*") for _ in range(14))
        if not validar_politica_clave(c):
            return c


def usuario_salida(u: m.Usuario) -> dict:
    return {
        "id": u.id, "nombre": u.nombre, "correo": u.correo, "usuario_ad": u.usuario_ad, "origen_autenticacion": u.origen_autenticacion,
        "cargo": u.cargo, "telefono": u.telefono, "area_id": u.area_id, "rol_id": u.rol_id, "rol": u.rol.codigo,
        "supervisor_id": u.supervisor_id, "activo": u.activo, "bloqueado": bool(u.bloqueado_hasta and u.bloqueado_hasta > utcnow()),
        "ultimo_login": u.ultimo_login,
    }


def categoria_salida(c: m.Categoria) -> dict:
    return {
        "id": c.id, "codigo": c.codigo, "nombre": c.nombre, "descripcion": c.descripcion, "palabras_clave": c.palabras_clave,
        "color": c.color, "orden": c.orden, "modo_asignacion": c.modo_asignacion, "activo": c.activo,
        "supervisor": {"id": c.supervisor.id, "nombre": c.supervisor.nombre, "correo": c.supervisor.correo, "cargo": c.supervisor.cargo} if c.supervisor else None,
        "responsables": [{"usuario_id": r.usuario_id, "nombre": r.usuario.nombre, "es_principal": r.es_principal} for r in c.responsables],
        "subcategorias": [x for x in c.subcategorias if not x.eliminado],
    }


class AdminService:
    def __init__(self, session: Session):
        self.session = session
        self.usuarios = UsuarioRepository(session)
        self.catalogo = CatalogoRepository(session)
        self.auditoria = AuditoriaService(session)

    # ================================================================ usuarios
    def listar_usuarios(self, texto: str | None, rol_id: int | None, pagina: int, tamano: int):
        stmt = select(m.Usuario).where(m.Usuario.eliminado == False)
        if texto:
            p = f"%{texto}%"
            stmt = stmt.where(m.Usuario.nombre.ilike(p) | m.Usuario.correo.ilike(p))
        if rol_id:
            stmt = stmt.where(m.Usuario.rol_id == rol_id)
        return self.usuarios.paginar(stmt.order_by(m.Usuario.nombre), pagina, tamano)

    def _rol(self, rol_id: int) -> m.Rol:
        rol = self.session.get(m.Rol, rol_id)
        if rol is None:
            raise ReglaNegocio("Rol no válido")
        return rol

    def crear_usuario(self, dto: s.UsuarioCrear, ctx: Contexto) -> tuple[m.Usuario, str | None]:
        if self.usuarios.por_correo(dto.correo):
            raise Conflicto("Ya existe un usuario con ese correo")
        rol = self._rol(dto.rol_id)
        temporal = None
        clave_hash = None
        if dto.origen_autenticacion == "LOCAL":
            if dto.clave:
                errores = validar_politica_clave(dto.clave)
                if errores:
                    raise ReglaNegocio("La contraseña no cumple la política", {"errores": errores})
                clave_hash = hash_clave(dto.clave)
            else:
                temporal = clave_temporal()
                clave_hash = hash_clave(temporal)
        u = self.usuarios.add(m.Usuario(
            nombre=dto.nombre, correo=str(dto.correo).lower(), rol_id=rol.id, cargo=dto.cargo, telefono=dto.telefono, area_id=dto.area_id,
            supervisor_id=dto.supervisor_id, origen_autenticacion=dto.origen_autenticacion, usuario_ad=dto.usuario_ad,
            clave_hash=clave_hash, debe_cambiar_clave=dto.origen_autenticacion == "LOCAL", fecha_creacion=utcnow(),
        ))
        self.session.refresh(u)
        self.auditoria.registrar(ctx, AccionAuditoria.USUARIO_MODIFICADO, "usuario", u.id, {"operacion": "crear", "correo": u.correo, "rol": rol.codigo})
        return u, temporal

    def editar_usuario(self, usuario_id: int, dto: s.UsuarioEditar, ctx: Contexto) -> m.Usuario:
        u = self.usuarios.get(usuario_id)
        if u is None or u.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        datos = dto.model_dump(exclude_unset=True)
        if "rol_id" in datos and datos["rol_id"] != u.rol_id:
            nuevo = self._rol(datos["rol_id"])
            if u.id == ctx.usuario.id:
                raise ReglaNegocio("No puede cambiar su propio rol")
            self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_ROL, "usuario", u.id, {"de": u.rol.codigo, "a": nuevo.codigo})
            RefreshTokenRepository(self.session).revocar_usuario(u.id, utcnow())
        if datos.get("activo") is False:
            if u.id == ctx.usuario.id:
                raise ReglaNegocio("No puede desactivar su propia cuenta")
            RefreshTokenRepository(self.session).revocar_usuario(u.id, utcnow())
        for k, v in datos.items():
            setattr(u, k, v)
        u.fecha_actualizacion = utcnow()
        self.session.flush()
        self.session.refresh(u)
        self.auditoria.registrar(ctx, AccionAuditoria.USUARIO_MODIFICADO, "usuario", u.id, {"operacion": "editar", "campos": list(datos)})
        return u

    def restablecer_clave(self, usuario_id: int, ctx: Contexto) -> str:
        u = self.usuarios.get(usuario_id)
        if u is None or u.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        if u.origen_autenticacion == "AD":
            raise ReglaNegocio("La contraseña de esta cuenta se administra en Active Directory")
        temporal = clave_temporal()
        u.clave_hash, u.debe_cambiar_clave, u.intentos_fallidos, u.bloqueado_hasta = hash_clave(temporal), True, 0, None
        RefreshTokenRepository(self.session).revocar_usuario(u.id, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.USUARIO_MODIFICADO, "usuario", u.id, {"operacion": "restablecer_clave"})
        return temporal

    def eliminar_usuario(self, usuario_id: int, ctx: Contexto) -> None:
        u = self.usuarios.get(usuario_id)
        if u is None or u.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        if u.id == ctx.usuario.id:
            raise ReglaNegocio("No puede eliminar su propia cuenta")
        u.eliminado, u.activo = True, False
        u.correo = f"{u.correo}#eliminado{u.id}"[:150]
        RefreshTokenRepository(self.session).revocar_usuario(u.id, utcnow())
        self.auditoria.registrar(ctx, AccionAuditoria.REGISTRO_ELIMINADO, "usuario", u.id)

    # =================================================================== roles
    def roles(self) -> list[dict]:
        return [{"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "descripcion": r.descripcion, "permisos": sorted(p.codigo for p in r.permisos)}
                for r in self.session.scalars(select(m.Rol).order_by(m.Rol.id))]

    def permisos(self) -> list[m.Permiso]:
        return list(self.session.scalars(select(m.Permiso).order_by(m.Permiso.modulo, m.Permiso.codigo)))

    def actualizar_permisos_rol(self, rol_id: int, codigos: list[str], ctx: Contexto) -> None:
        rol = self._rol(rol_id)
        if rol.codigo == Rol.SUPER_ADMIN:
            raise ReglaNegocio("Los permisos del Super Administrador no se pueden reducir")
        permisos = list(self.session.scalars(select(m.Permiso).where(m.Permiso.codigo.in_(codigos))))
        if len(permisos) != len(set(codigos)):
            raise ReglaNegocio("Hay permisos inexistentes en la lista")
        antes = sorted(p.codigo for p in rol.permisos)
        rol.permisos = permisos
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_ROL, "rol", rol.id, {"rol": rol.codigo, "antes": antes, "despues": sorted(codigos)})

    # =============================================================== catálogo
    def guardar_categoria(self, dto: s.CategoriaEntrada, ctx: Contexto, categoria_id: int | None = None) -> m.Categoria:
        if categoria_id:
            c = self.catalogo.categoria(categoria_id)
            if c is None or c.eliminado:
                raise NoEncontrado("Categoría no encontrada")
        else:
            if self.session.scalar(select(m.Categoria).where(m.Categoria.codigo == dto.codigo)):
                raise Conflicto("Ya existe una categoría con ese código")
            c = m.Categoria(fecha_creacion=utcnow())
            self.session.add(c)
        for k in ("codigo", "nombre", "descripcion", "palabras_clave", "color", "orden", "modo_asignacion", "supervisor_id", "activo"):
            setattr(c, k, getattr(dto, k))
        self.session.flush()
        c.responsables = [m.CategoriaResponsable(categoria_id=c.id, usuario_id=r.usuario_id, es_principal=r.es_principal) for r in dto.responsables]
        self.session.flush()
        self.session.refresh(c)
        self.auditoria.registrar(ctx, AccionAuditoria.CATEGORIA_MODIFICADA, "categoria", c.id, {"codigo": c.codigo, "operacion": "editar" if categoria_id else "crear"})
        return c

    def guardar_subcategoria(self, categoria_id: int, dto: s.SubcategoriaEntrada, ctx: Contexto, sub_id: int | None = None) -> m.Subcategoria:
        if self.catalogo.categoria(categoria_id) is None:
            raise NoEncontrado("Categoría no encontrada")
        if sub_id:
            sub = self.catalogo.subcategoria(sub_id)
            if sub is None or sub.categoria_id != categoria_id:
                raise NoEncontrado("Subcategoría no encontrada")
        else:
            sub = m.Subcategoria(categoria_id=categoria_id)
            self.session.add(sub)
        for k, v in dto.model_dump().items():
            setattr(sub, k, v)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.CATEGORIA_MODIFICADA, "subcategoria", sub.id, {"nombre": sub.nombre})
        return sub

    def eliminar_categoria(self, categoria_id: int, ctx: Contexto) -> None:
        c = self.catalogo.categoria(categoria_id)
        if c is None:
            raise NoEncontrado("Categoría no encontrada")
        c.eliminado, c.activo = True, False
        self.auditoria.registrar(ctx, AccionAuditoria.REGISTRO_ELIMINADO, "categoria", c.id)

    def guardar_cliente(self, dto: s.ClienteEntrada, ctx: Contexto, cliente_id: int | None = None) -> m.Cliente:
        if cliente_id:
            c = self.session.get(m.Cliente, cliente_id)
            if c is None or c.eliminado:
                raise NoEncontrado("Cliente no encontrado")
        else:
            c = m.Cliente(fecha_creacion=utcnow())
            self.session.add(c)
        for k, v in dto.model_dump().items():
            setattr(c, k, str(v) if k == "correo" and v else v)
        self.session.flush()
        self.auditoria.registrar(ctx, "CLIENTE_MODIFICADO", "cliente", c.id, {"razon_social": c.razon_social})
        return c

    # ==================================================================== SLA
    def actualizar_sla_prioridad(self, prioridad_id: int, dto: s.PrioridadSlaEntrada, ctx: Contexto) -> m.Prioridad:
        p = self.catalogo.prioridad(prioridad_id)
        if p is None:
            raise NoEncontrado("Prioridad no encontrada")
        if dto.sla_resolucion_min < dto.sla_respuesta_min:
            raise ReglaNegocio("El SLA de resolución no puede ser menor que el de respuesta")
        antes = {"respuesta": p.sla_respuesta_min, "resolucion": p.sla_resolucion_min}
        p.sla_respuesta_min, p.sla_resolucion_min = dto.sla_respuesta_min, dto.sla_resolucion_min
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "prioridad", p.id,
                                 {"prioridad": p.codigo, "antes": antes, "despues": dto.model_dump(), "nota": "aplica a tickets nuevos"})
        return p

    def politicas(self) -> list[m.SlaPolitica]:
        return list(self.session.scalars(select(m.SlaPolitica)))

    def guardar_politica(self, dto: s.PoliticaSlaEntrada, ctx: Contexto) -> m.SlaPolitica:
        pol = self.catalogo.politica(dto.categoria_id, dto.prioridad_id) or self.session.scalar(
            select(m.SlaPolitica).where(m.SlaPolitica.categoria_id == dto.categoria_id, m.SlaPolitica.prioridad_id == dto.prioridad_id))
        if pol is None:
            pol = m.SlaPolitica()
            self.session.add(pol)
        for k, v in dto.model_dump().items():
            setattr(pol, k, v)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "sla_politica", pol.id, dto.model_dump())
        return pol

    def horario(self) -> m.HorarioLaboral | None:
        return self.catalogo.horario_predeterminado()

    def guardar_horario(self, dto: s.HorarioEntrada, ctx: Contexto) -> m.HorarioLaboral:
        if not dto.tramos:
            raise ReglaNegocio("El horario debe tener al menos un tramo laborable")
        for t in dto.tramos:
            if t.hora_fin <= t.hora_inicio:
                raise ReglaNegocio("Cada tramo debe terminar después de empezar")
        h = self.catalogo.horario_predeterminado()
        if h is None:
            h = m.HorarioLaboral(es_predeterminado=True, activo=True)
            self.session.add(h)
        h.nombre, h.zona_horaria = dto.nombre, dto.zona_horaria
        h.tramos = [m.HorarioTramo(dia_semana=t.dia_semana, hora_inicio=t.hora_inicio, hora_fin=t.hora_fin) for t in dto.tramos]
        self.session.flush()
        invalidar_calendario()
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "horario", h.id, {"tramos": [t.model_dump(mode="json") for t in dto.tramos]})
        return h

    def guardar_excepcion(self, dto: s.ExcepcionCalendarioEntrada, ctx: Contexto) -> m.CalendarioExcepcion:
        if dto.tipo == "HORARIO_ESPECIAL" and not (dto.hora_inicio and dto.hora_fin and dto.hora_fin > dto.hora_inicio):
            raise ReglaNegocio("Un horario especial requiere hora de inicio y fin válidas")
        e = m.CalendarioExcepcion(**dto.model_dump())
        if e.tipo == "FERIADO":
            e.hora_inicio = e.hora_fin = None
        self.session.add(e)
        self.session.flush()
        invalidar_calendario()
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "calendario", e.id, dto.model_dump(mode="json"))
        return e

    def eliminar_excepcion(self, excepcion_id: int, ctx: Contexto) -> None:
        e = self.session.get(m.CalendarioExcepcion, excepcion_id)
        if e is None:
            raise NoEncontrado("Excepción no encontrada")
        self.session.delete(e)
        invalidar_calendario()
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SLA, "calendario", excepcion_id, {"operacion": "eliminar"})

    # ========================================================== configuración
    def configuracion(self) -> list[m.Configuracion]:
        return list(self.session.scalars(select(m.Configuracion).order_by(m.Configuracion.clave)))

    def guardar_configuracion(self, valores: dict[str, str], ctx: Contexto) -> None:
        for clave, valor in valores.items():
            c = self.session.get(m.Configuracion, clave)
            if c is None:
                raise ReglaNegocio(f"Clave de configuración desconocida: {clave}")
            c.valor, c.fecha_actualizacion, c.actualizado_por = valor, utcnow(), ctx.usuario.id
        self.auditoria.registrar(ctx, "CONFIGURACION", "configuracion", None, valores)
