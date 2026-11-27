"""Acciones en lote sobre tickets y traspaso de la cartera de un analista (mejora 23).

Cada ticket del lote pasa por las mismas validaciones y permisos que si se hiciera uno por uno;
los que no se pueden cambiar se informan sin detener el resto. El SLA de cada ticket no se reinicia.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, ErrorAplicacion, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as s
from app.application.services.auditoria_service import AuditoriaService
from app.core.security import utcnow
from app.domain.enums import ESTADOS_ABIERTOS, AccionAuditoria, Estado
from app.infrastructure.db import models as m

MAX_TRASPASO = 500


class LoteService:
    def __init__(self, session: Session):
        from app.application.services.ticket_service import TicketService

        self.session = session
        self.svc = TicketService(session)
        self.auditoria = AuditoriaService(session)

    # ================================================================ lote
    def aplicar(self, dto, ctx: Contexto) -> dict:
        u = ctx.usuario
        ok, sin_cambio, errores = [], [], []
        if dto.accion == "REASIGNAR" and not dto.responsable_id:
            raise ReglaNegocio("Elija a quién reasignar")
        if dto.accion == "PRIORIDAD" and not dto.prioridad_id:
            raise ReglaNegocio("Elija la prioridad")
        if dto.accion == "ESTADO" and not dto.estado:
            raise ReglaNegocio("Elija el estado")
        if dto.accion == "ESTADO" and len((dto.texto or "").strip()) < 5:
            raise ReglaNegocio("Indique el motivo del cambio de estado")
        if dto.accion == "CATEGORIA" and not (dto.categoria_id and dto.subcategoria_id):
            raise ReglaNegocio("Elija la categoría y la subcategoría")
        if dto.accion == "NOTA" and not (dto.texto or "").strip():
            raise ReglaNegocio("Escriba la nota interna")
        if dto.accion == "REASIGNAR":
            self.svc._validar_responsable(dto.responsable_id)
        for tid in dict.fromkeys(dto.ids):
            numero = str(tid)
            try:
                with self.session.begin_nested():
                    t = self.svc.obtener(tid, u)
                    numero = t.numero
                    if self._uno(t, dto, ctx):
                        ok.append(numero)
                    else:
                        sin_cambio.append(numero)
            except ErrorAplicacion as e:
                errores.append({"numero": numero, "error": e.mensaje})
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.TICKET_LOTE, "ticket", None,
                                 {"accion": dto.accion, "ok": ok, "sin_cambio": sin_cambio, "errores": [e["numero"] for e in errores]})
        return {"ok": ok, "sin_cambio": sin_cambio, "errores": errores}

    def _uno(self, t: m.Ticket, dto, ctx: Contexto) -> bool:
        if dto.accion == "REASIGNAR":
            if t.responsable_id == dto.responsable_id:
                return False
            self.svc.asignar(t.id, s.AsignarEntrada(responsable_id=dto.responsable_id, motivo=dto.motivo or "Reasignación en lote"), ctx)
        elif dto.accion == "PRIORIDAD":
            if t.prioridad_id == dto.prioridad_id:
                return False
            self.svc.editar(t.id, s.TicketEditar(prioridad_id=dto.prioridad_id), ctx)
        elif dto.accion == "CATEGORIA":
            if (t.categoria_id, t.subcategoria_id) == (dto.categoria_id, dto.subcategoria_id):
                return False
            self.svc.editar(t.id, s.TicketEditar(categoria_id=dto.categoria_id, subcategoria_id=dto.subcategoria_id), ctx)
        elif dto.accion == "ESTADO":
            if t.estado == dto.estado:
                return False
            if dto.estado == "CERRADO":
                self.svc.cerrar(t.id, dto.texto, ctx)
            else:
                self.svc.cambiar_estado(t.id, dto.estado, dto.texto, ctx)
        elif dto.accion == "NOTA":
            self.svc.comentar(t.id, s.ComentarioEntrada(texto=dto.texto.strip(), es_interno=True), ctx)
        return True

    # ============================================================ traspaso
    def _origen(self, usuario_id: int) -> m.Usuario:
        o = self.session.get(m.Usuario, usuario_id)
        if o is None or o.eliminado:
            raise NoEncontrado("Usuario no encontrado")
        return o

    def _abiertos(self, usuario_id: int) -> list[m.Ticket]:
        T = m.Ticket
        return list(self.session.scalars(
            select(T).where(T.responsable_id == usuario_id, T.eliminado == False, T.estado.in_([e.value for e in ESTADOS_ABIERTOS]))
            .order_by(T.sla_resolucion_vence, T.id)).unique())

    def _destinos(self, ids: list[int], origen_id: int) -> list[m.Usuario]:
        destinos = []
        for i in dict.fromkeys(ids):
            if i == origen_id:
                raise ReglaNegocio("No puede traspasar los tickets a la misma persona")
            destinos.append(self.svc._validar_responsable(i))
        return destinos

    def plan(self, usuario_id: int, dto) -> dict:
        """Vista previa: a quién iría cada ticket. No cambia nada."""
        origen = self._origen(usuario_id)
        tickets = self._abiertos(origen.id)
        if len(tickets) > MAX_TRASPASO:
            raise ReglaNegocio(f"{origen.nombre} tiene más de {MAX_TRASPASO} tickets abiertos: use primero la reasignación en lote por categoría")
        destinos = self._destinos(dto.destinos, origen.id)
        if dto.modo in ("UNO", "EQUILIBRADO") and not destinos:
            raise ReglaNegocio("Elija al menos un analista que reciba los tickets")
        if dto.modo == "UNO" and len(destinos) > 1:
            destinos = destinos[:1]
        from app.infrastructure.repositories.repositorios import UsuarioRepository

        carga = UsuarioRepository(self.session).carga_abierta([d.id for d in destinos]) if destinos else {}
        tiene = dict(carga)
        recibe = {d.id: 0 for d in destinos}
        por_id = {d.id: d for d in destinos}
        filas = []
        for t in tickets:
            destino = None
            if t.id in dto.asignaciones and dto.asignaciones[t.id] in por_id:
                destino = por_id[dto.asignaciones[t.id]]
            elif dto.modo != "COLA":
                atienden = {r.usuario_id for r in t.categoria.responsables}
                candidatos = [d for d in destinos if d.id in atienden] or destinos
                destino = min(candidatos, key=lambda d: (carga[d.id], d.nombre))
            if destino:
                carga[destino.id] += 1
                recibe[destino.id] += 1
            filas.append({"id": t.id, "numero": t.numero, "asunto": t.asunto, "estado": t.estado, "categoria": t.categoria.nombre,
                          "vence": t.sla_resolucion_vence, "destino_id": destino.id if destino else None,
                          "destino": destino.nombre if destino else "Cola (asignación automática)"})
        R = m.TicketRecurrente
        recurrentes = self.session.scalars(select(R).where(R.responsable_id == origen.id, R.activo == True)).all()
        A = m.TicketAprobacion
        aprobaciones = self.session.scalars(select(A).where(A.aprobador_id == origen.id, A.estado == "PENDIENTE")).all()
        jefe = self.session.get(m.Usuario, origen.supervisor_id) if origen.supervisor_id else None
        return {
            "origen": {"id": origen.id, "nombre": origen.nombre, "abiertos": len(tickets)},
            "tickets": filas,
            "destinos": [{"id": d.id, "nombre": d.nombre, "tiene": tiene[d.id], "recibe": recibe[d.id]} for d in destinos],
            "recurrentes": len(recurrentes), "aprobaciones": len(aprobaciones),
            "jefe": {"id": jefe.id, "nombre": jefe.nombre} if jefe else None,
        }

    def traspasar(self, usuario_id: int, dto, ctx: Contexto) -> dict:
        u = ctx.usuario
        plan = self.plan(usuario_id, dto)
        origen = self._origen(usuario_id)
        if dto.desactivar and origen.id == u.id:
            raise ReglaNegocio("No puede desactivar su propia cuenta")
        ahora = utcnow()
        motivo = f"Traspaso de cartera: {dto.motivo.strip()}"
        movidos, en_cola = 0, 0
        for fila in plan["tickets"]:
            t = self.session.get(m.Ticket, fila["id"])
            if fila["destino_id"]:
                nuevo = self.session.get(m.Usuario, fila["destino_id"])
                self.svc._asignar(t, nuevo, u, "REASIGNACION", motivo, ctx, ahora)
                movidos += 1
            else:
                self._a_la_cola(t, origen, u, motivo, ctx, ahora)
                en_cola += 1
            if dto.avisar and t.responsable_id != origen.id:
                self.svc.notif.notificar([t.solicitante], "TICKET_NUEVO_RESPONSABLE", f"{t.numero}: cambio de responsable",
                                         f"Su solicitud ahora la atiende {t.responsable.nombre if t.responsable else 'la Mesa de Servicios'}.", t)
                if t.responsable:
                    self.svc.correo_solicitante("TICKET_NUEVO_RESPONSABLE", t)
        recurrentes = 0
        if dto.traspasar_recurrentes:
            destino_rec = self.svc._validar_responsable(dto.recurrentes_a_id) if dto.recurrentes_a_id else None
            for r in self.session.scalars(select(m.TicketRecurrente).where(m.TicketRecurrente.responsable_id == origen.id,
                                                                           m.TicketRecurrente.activo == True)):
                r.responsable_id = destino_rec.id if destino_rec else None
                recurrentes += 1
        aprobaciones = 0
        if dto.traspasar_aprobaciones and plan["aprobaciones"]:
            from app.application.services.aprobacion_service import AprobacionService

            a_id = dto.aprobaciones_a_id or origen.supervisor_id
            destino_apr = self.session.get(m.Usuario, a_id) if a_id else None
            if destino_apr is None or not destino_apr.activo or destino_apr.eliminado or destino_apr.id == origen.id:
                raise ReglaNegocio(f"Indique quién responde las {plan['aprobaciones']} aprobaciones pendientes de {origen.nombre}")
            aprobaciones = AprobacionService(self.session).reasignar_pendientes(origen, destino_apr, motivo, ahora)
        if dto.desactivar:
            from app.application.services.admin_service import AdminService

            AdminService(self.session).editar_usuario(origen.id, s.UsuarioEditar(activo=False), ctx)
        self.session.flush()
        resumen = {"tickets": movidos, "en_cola": en_cola, "recurrentes": recurrentes, "aprobaciones": aprobaciones,
                   "desactivado": dto.desactivar}
        self.auditoria.registrar(ctx, AccionAuditoria.TRASPASO_CARTERA, "usuario", origen.id,
                                 {"de": origen.nombre, "modo": dto.modo, "motivo": dto.motivo,
                                  "destinos": [d["nombre"] for d in plan["destinos"]], **resumen})
        return resumen

    def _a_la_cola(self, t: m.Ticket, origen: m.Usuario, u: m.Usuario, motivo: str, ctx: Contexto, ahora: datetime) -> None:
        """Devuelve el ticket para que lo tome la asignación automática (sin volver a darlo a quien se va)."""
        sugerido = self.svc.ia.sugerir_responsable(t.categoria)
        if sugerido and sugerido.id != origen.id:
            self.svc._asignar(t, sugerido, u, "REASIGNACION", f"{motivo} (asignación automática)", ctx, ahora)
            return
        t.responsable_id, t.responsable = None, None
        if t.estado == Estado.ASIGNADO:
            t.estado = Estado.NUEVO
            self.svc._hist(t, u, "CAMBIO_ESTADO", "estado", Estado.ASIGNADO, Estado.NUEVO, motivo, ahora)
        self.svc._hist(t, u, "ASIGNACION", "responsable", origen.nombre, None, f"{motivo}. Devuelto a la cola", ahora)
        t.fecha_actualizacion = ahora
        self.svc.notif.notificar([self.svc._supervisor(t)], "TICKET_SIN_ASIGNAR", f"{t.numero} pendiente de asignación",
                                 f"«{t.asunto}» volvió a la cola ({origen.nombre} ya no lo atiende).", t, "AVISO")
