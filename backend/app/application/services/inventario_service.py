"""Inventario de equipos: cada ticket puede indicar el equipo afectado y así se arma el historial de fallas."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.application.errores import Conflicto, Contexto, NoEncontrado, Prohibido
from app.application.schemas import mejoras2 as s
from app.application.services.auditoria_service import AuditoriaService
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Permiso
from app.infrastructure.db import models as m

TIPOS = {"ESCRITORIO": "Escritorio", "PORTATIL": "Portátil", "IMPRESORA": "Impresora", "RED": "Red", "TOKEN": "Token",
         "TELEFONO": "Teléfono", "MONITOR": "Monitor", "SERVIDOR": "Servidor", "OTRO": "Otro"}
ESTADOS = {"EN_USO": "En uso", "BODEGA": "Bodega", "REPARACION": "En reparación", "BAJA": "De baja"}
UMBRAL_AVISO = 3            # fallas en 6 meses que disparan el aviso de equipo problemático
COLUMNAS_IMPORTAR = ("codigo", "tipo", "marca_modelo", "serie", "correo_usuario", "area", "compartido", "ubicacion", "estado",
                     "fecha_compra", "garantia_hasta", "sistema", "notas")


def _tipo_desde_texto(v: str) -> str:
    n = (v or "").strip().upper().replace("Á", "A").replace("Í", "I").replace("É", "E").replace(" ", "_")
    alias = {"PC": "ESCRITORIO", "DESKTOP": "ESCRITORIO", "LAPTOP": "PORTATIL", "NOTEBOOK": "PORTATIL", "ROUTER": "RED", "SWITCH": "RED"}
    n = alias.get(n, n)
    return n if n in TIPOS else "OTRO"


class InventarioService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)

    # -------------------------------------------------------------- conteos
    def fallas(self, equipo_ids: list[int], meses: int = 12) -> dict[int, int]:
        if not equipo_ids:
            return {}
        desde = utcnow() - timedelta(days=30 * meses)
        T = m.Ticket
        filas = self.session.execute(
            select(T.equipo_id, func.count(T.id)).where(T.equipo_id.in_(equipo_ids), T.eliminado == False, T.recurrente_id.is_(None),
                                                       T.estado != "CANCELADO", T.fecha_creacion >= desde)
            .group_by(T.equipo_id)).all()
        return {e: n for e, n in filas}

    def historial(self, equipo_id: int, limite: int = 50) -> list[m.Ticket]:
        T = m.Ticket
        return list(self.session.scalars(
            select(T).where(T.equipo_id == equipo_id, T.eliminado == False).order_by(T.fecha_creacion.desc()).limit(limite)).unique())

    def aviso(self, e: m.Equipo, historial: list[m.Ticket] | None = None, excluir_ticket: int | None = None) -> str | None:
        """Texto de alerta si el equipo falla seguido (3 o más tickets en 6 meses, sin contar mantenimientos programados)."""
        historial = historial if historial is not None else self.historial(e.id)
        limite = utcnow() - timedelta(days=182)
        recientes = [t for t in historial if t.fecha_creacion >= limite and t.recurrente_id is None and t.estado != "CANCELADO"]
        n = len(recientes)
        if n < UMBRAL_AVISO:
            return None
        if excluir_ticket and any(t.id == excluir_ticket for t in recientes):
            return f"Es la {n}.ª falla reportada en este equipo en 6 meses. Revise el historial antes de repetir la misma solución."
        return f"{n} fallas en 6 meses. Conviene evaluar reparación o reemplazo."

    def salida(self, e: m.Equipo, fallas: int | None = None) -> dict:
        return {
            "id": e.id, "codigo": e.codigo, "tipo": e.tipo, "marca_modelo": e.marca_modelo, "serie": e.serie, "usuario_id": e.usuario_id,
            "usuario": e.usuario.nombre if e.usuario else None, "area_id": e.area_id, "area": e.area.nombre if e.area else None,
            "compartido": e.compartido, "ubicacion": e.ubicacion, "estado": e.estado, "fecha_compra": e.fecha_compra,
            "garantia_hasta": e.garantia_hasta, "sistema": e.sistema, "notas": e.notas,
            "fallas_12m": fallas if fallas is not None else self.fallas([e.id]).get(e.id, 0),
        }

    @staticmethod
    def ve_todo(u: m.Usuario) -> bool:
        """Solo quien administra el inventario lo ve completo; los demás ven únicamente los equipos asignados a ellos."""
        return u.tiene(Permiso.INVENTARIO_GESTIONAR)

    def detalle(self, equipo_id: int, u: m.Usuario | None = None) -> dict:
        e = self.obtener(equipo_id)
        if u is not None and not self.ve_todo(u) and e.usuario_id != u.id:
            raise NoEncontrado("Equipo no encontrado")
        hist = self.historial(e.id)
        return {**self.salida(e), "aviso": self.aviso(e, hist), "historial": [
            {"ticket_id": t.id, "numero": t.numero, "asunto": t.asunto, "estado": t.estado, "fecha_creacion": t.fecha_creacion,
             "minutos_resolucion": t.minutos_resolucion} for t in hist]}

    def para_ticket(self, t: m.Ticket) -> dict | None:
        if t.equipo is None:
            return None
        e = t.equipo
        return {"id": e.id, "codigo": e.codigo, "tipo": e.tipo, "marca_modelo": e.marca_modelo,
                "aviso": self.aviso(e, excluir_ticket=t.id)}

    # --------------------------------------------------------------- listar
    def obtener(self, equipo_id: int) -> m.Equipo:
        e = self.session.get(m.Equipo, equipo_id)
        if e is None or e.eliminado:
            raise NoEncontrado("Equipo no encontrado")
        return e

    def listar(self, texto: str | None, tipo: str | None, estado: str | None, u: m.Usuario | None = None) -> list[dict]:
        E = m.Equipo
        stmt = select(E).outerjoin(m.Usuario, m.Usuario.id == E.usuario_id).where(E.eliminado == False)
        if u is not None and not self.ve_todo(u):
            stmt = stmt.where(E.usuario_id == u.id)
        if tipo:
            stmt = stmt.where(E.tipo == tipo)
        if estado:
            stmt = stmt.where(E.estado == estado)
        if texto and texto.strip():
            p = f"%{texto.strip()}%"
            stmt = stmt.where(or_(E.codigo.ilike(p), E.marca_modelo.ilike(p), E.serie.ilike(p), E.ubicacion.ilike(p), m.Usuario.nombre.ilike(p)))
        equipos = list(self.session.scalars(stmt.order_by(E.codigo)).unique())
        conteo = self.fallas([e.id for e in equipos])
        return [self.salida(e, conteo.get(e.id, 0)) for e in equipos]

    @staticmethod
    def ve_todo_al_registrar(u: m.Usuario | None) -> bool:
        """Al crear un ticket, el administrador del inventario y la mesa que registra para cualquiera eligen entre todos los equipos."""
        return u is None or u.tiene(Permiso.INVENTARIO_GESTIONAR) or (u.tiene(Permiso.TICKET_VER_TODOS) and u.tiene(Permiso.TICKET_ASIGNAR))

    @staticmethod
    def disponible_para(e: m.Equipo, persona: m.Usuario) -> bool:
        """Equipo propio, compartido o de uso común del área (sin persona asignada)."""
        return e.usuario_id == persona.id or e.compartido or (e.usuario_id is None and e.area_id is not None and e.area_id == persona.area_id)

    def _persona(self, u: m.Usuario, solicitante_id: int | None) -> m.Usuario:
        """La persona cuyos equipos se ofrecen: uno mismo, o el beneficiario si se puede registrar en su nombre."""
        if not solicitante_id or solicitante_id == u.id:
            return u
        otro = self.session.get(m.Usuario, solicitante_id)
        if otro is None:
            return u
        if self.ve_todo_al_registrar(u):
            return otro
        from app.application.services.ticket_service import TicketService

        d = TicketService(self.session).delegacion_vigente(u)
        if d is not None and (not d.area_ids or otro.area_id in d.area_ids):
            return otro
        return u

    def opciones(self, u: m.Usuario, solicitante_id: int | None = None) -> list[dict]:
        """Equipos que se pueden elegir al crear un ticket: los de la persona y los compartidos o comunes de su área."""
        persona = self._persona(u, solicitante_id)
        E = m.Equipo
        stmt = select(E).where(E.eliminado == False, E.estado != "BAJA")
        if not self.ve_todo_al_registrar(u):
            condiciones = [E.usuario_id == persona.id, E.compartido == True]
            if persona.area_id:
                condiciones.append(and_(E.usuario_id.is_(None), E.area_id == persona.area_id))
            stmt = stmt.where(or_(*condiciones))
        equipos = list(self.session.scalars(stmt).unique())
        conteo = self.fallas([e.id for e in equipos])
        filas = [{"id": e.id, "codigo": e.codigo, "tipo": e.tipo, "marca_modelo": e.marca_modelo, "propio": e.usuario_id == persona.id,
                  "compartido": e.compartido, "fallas_12m": conteo.get(e.id, 0)} for e in equipos]
        filas.sort(key=lambda f: (not f["propio"], not f["compartido"], f["codigo"]))
        return filas

    # ------------------------------------------------------------ registrar
    def _exigir(self, u: m.Usuario) -> None:
        if not u.tiene(Permiso.INVENTARIO_GESTIONAR):
            raise Prohibido("No tiene permiso para modificar el inventario")

    def guardar(self, dto: s.EquipoEntrada, ctx: Contexto, equipo_id: int | None = None) -> m.Equipo:
        self._exigir(ctx.usuario)
        otro = self.session.scalar(select(m.Equipo).where(m.Equipo.codigo == dto.codigo, m.Equipo.id != (equipo_id or 0)))
        if otro is not None:
            raise Conflicto(f"Ya existe un equipo con el código {dto.codigo}")
        if equipo_id is None:
            e = m.Equipo(fecha_creacion=utcnow())
            self.session.add(e)
            antes = None
        else:
            e = self.obtener(equipo_id)
            antes = {"usuario_id": e.usuario_id, "estado": e.estado}
        for k, v in dto.model_dump().items():
            setattr(e, k, v.strip() if isinstance(v, str) else v)
        if e.usuario_id and not e.area_id:
            u = self.session.get(m.Usuario, e.usuario_id)
            e.area_id = u.area_id if u else None
        e.fecha_actualizacion = utcnow()
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.EQUIPO_MODIFICADO, "equipo", e.id,
                                 {"codigo": e.codigo, "antes": antes, "usuario_id": e.usuario_id, "estado": e.estado})
        self.session.refresh(e)
        return e

    def eliminar(self, equipo_id: int, ctx: Contexto) -> None:
        self._exigir(ctx.usuario)
        e = self.obtener(equipo_id)
        e.eliminado = True
        self.auditoria.registrar(ctx, AccionAuditoria.EQUIPO_MODIFICADO, "equipo", e.id, {"codigo": e.codigo, "eliminado": True})

    def importar(self, contenido: bytes, ctx: Contexto) -> dict:
        """Importa o actualiza equipos desde un Excel (una fila por equipo; la primera fila son los títulos)."""
        from openpyxl import load_workbook

        self._exigir(ctx.usuario)
        try:
            libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except Exception as exc:   # archivo dañado o no es Excel
            raise Conflicto(f"No se pudo leer el Excel: {exc}") from exc
        hoja = libro.active
        filas = list(hoja.iter_rows(values_only=True))
        if not filas:
            return {"creados": 0, "actualizados": 0, "errores": ["El archivo está vacío"]}
        titulos = [str(c or "").strip().lower().replace(" ", "_") for c in filas[0]]
        usuarios = {u.correo.lower(): u for u in self.session.scalars(select(m.Usuario).where(m.Usuario.eliminado == False)).unique()}
        areas = {a.nombre.lower(): a for a in self.session.scalars(select(m.Area))}
        creados = actualizados = 0
        errores: list[str] = []
        for n, fila in enumerate(filas[1:1001], start=2):
            d = {titulos[i]: v for i, v in enumerate(fila) if i < len(titulos) and titulos[i] in COLUMNAS_IMPORTAR}
            codigo = str(d.get("codigo") or "").strip().upper()
            if not codigo:
                continue
            try:
                correo = str(d.get("correo_usuario") or "").strip().lower()
                usuario = usuarios.get(correo) if correo else None
                if correo and usuario is None:
                    raise ValueError(f"no existe el usuario {correo}")
                area = areas.get(str(d.get("area") or "").strip().lower())
                fecha = lambda v: v.date() if isinstance(v, datetime) else (v or None)  # noqa: E731
                estado = str(d.get("estado") or "EN_USO").strip().upper().replace(" ", "_")
                dto = s.EquipoEntrada(
                    codigo=codigo, tipo=_tipo_desde_texto(str(d.get("tipo") or "")), marca_modelo=str(d.get("marca_modelo") or codigo),
                    serie=(str(d["serie"]).strip() if d.get("serie") else None), usuario_id=usuario.id if usuario else None,
                    area_id=area.id if area else (usuario.area_id if usuario else None),
                    compartido=str(d.get("compartido") or "").strip().lower() in ("si", "sí", "x", "1", "true"),
                    ubicacion=(str(d["ubicacion"]) if d.get("ubicacion") else None),
                    estado=estado if estado in ESTADOS else "EN_USO", fecha_compra=fecha(d.get("fecha_compra")),
                    garantia_hasta=fecha(d.get("garantia_hasta")), sistema=(str(d["sistema"]) if d.get("sistema") else None),
                    notas=(str(d["notas"]) if d.get("notas") else None))
                existente = self.session.scalar(select(m.Equipo).where(m.Equipo.codigo == codigo))
                if existente is not None and existente.eliminado:
                    existente.eliminado = False
                self.guardar(dto, ctx, existente.id if existente else None)
                if existente:
                    actualizados += 1
                else:
                    creados += 1
            except Exception as exc:   # se informa la fila y se sigue con las demás
                errores.append(f"Fila {n} ({codigo}): {getattr(exc, 'mensaje', None) or str(exc)[:150]}")
        return {"creados": creados, "actualizados": actualizados, "errores": errores[:50]}

    @staticmethod
    def plantilla_excel() -> bytes:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Equipos"
        ws.append(list(COLUMNAS_IMPORTAR))
        ws.append(["ADU-PC-001", "Escritorio", "Dell OptiPlex 7010", "7XK2M93", "usuario@aducorp.com.ec", "Operaciones Aduaneras", "no",
                   "Planta baja · puesto 4", "EN_USO", "2022-03-15", "2025-03-15", "Windows 11 Pro · 16 GB", ""])
        ws.append(["ADU-IMP-001", "Impresora", "HP LaserJet M428", "", "", "", "si", "2.º piso", "EN_USO", "", "", "", "Compartida"])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
