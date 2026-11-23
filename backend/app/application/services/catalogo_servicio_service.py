"""Catálogo de servicios (mejora 26).

Cada servicio (alta de usuario, acceso a ECUAPASS, token de firma, equipo…) trae su propio formulario. Al enviarlo:
- se crea un ticket en la categoría/subcategoría del servicio, con el plazo comprometido como SLA de resolución;
- se guardan las respuestas y se genera una tarea por cada casilla marcada, repartida al responsable de cada una;
- si el servicio lo pide, primero aprueba el jefe (reutiliza las aprobaciones de la mejora 21: «Por aprobar», SLA en pausa).
  El jefe puede salir del propio formulario (campo «Jefe directo» de quien ingresa) o ser el jefe directo de quien pide.
"""
from __future__ import annotations

import json
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.schemas import esquemas as es
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Estado, Permiso
from app.infrastructure.db import models as m

TIPOS_CAMPO = {"texto", "parrafo", "fecha", "numero", "cedula", "correo", "telefono", "area", "usuario", "lista"}
HORAS_DIA = 8   # jornada de ADUCORP: 08:30-13:00 y 14:00-17:30


def plazo_texto(horas: int, texto: str | None = None) -> str | None:
    if texto:
        return texto
    if not horas:
        return None
    if horas < HORAS_DIA:
        return f"{horas} h"
    dias = round(horas / HORAS_DIA, 1)
    dias_txt = f"{dias:g}".replace(".", ",")
    return f"{dias_txt} día hábil" if dias == 1 else f"{dias_txt} días hábiles"


def _json(valor: str | None) -> list:
    try:
        datos = json.loads(valor or "[]")
        return datos if isinstance(datos, list) else []
    except ValueError:
        return []


def iso(v) -> str | None:
    return v.isoformat() + "Z" if v else None


class CatalogoServicioService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)
        self.notif = NotificacionService(session)

    # ============================================================ servicios
    def listar(self, incluir_inactivos: bool = False) -> list[m.ServicioCatalogo]:
        S = m.ServicioCatalogo
        stmt = select(S).order_by(S.orden, S.nombre)
        if not incluir_inactivos:
            stmt = stmt.where(S.activo == True)
        return list(self.session.scalars(stmt).unique())

    def obtener(self, servicio_id: int, solo_activo: bool = True) -> m.ServicioCatalogo:
        s = self.session.get(m.ServicioCatalogo, servicio_id)
        if s is None or (solo_activo and not s.activo):
            raise NoEncontrado("Servicio no encontrado")
        return s

    def salida(self, s: m.ServicioCatalogo, completo: bool = False) -> dict:
        nombres = self._nombres_usuarios([o.get("responsable_id") for o in _json(s.opciones)])
        opciones = [{**o, "responsable": nombres.get(o.get("responsable_id"))} for o in _json(s.opciones)]
        d = {
            "id": s.id, "nombre": s.nombre, "descripcion": s.descripcion, "icono": s.icono, "grupo": s.grupo,
            "plazo_horas": s.plazo_horas, "plazo_texto": s.plazo_texto, "plazo": plazo_texto(s.plazo_horas, s.plazo_texto),
            "requiere_aprobacion": s.requiere_aprobacion or any(c.get("aprobador") for c in _json(s.campos)),
            "lo_pide": s.lo_pide or "Todos", "orden": s.orden, "activo": s.activo,
            "categoria_id": s.categoria_id, "subcategoria_id": s.subcategoria_id,
            "categoria": s.categoria.nombre, "subcategoria": s.subcategoria.nombre,
        }
        if completo:
            d.update({"titulo_campos": s.titulo_campos, "titulo_opciones": s.titulo_opciones, "aviso": s.aviso,
                      "campos": _json(s.campos), "opciones": opciones,
                      "responsable_categoria": self._responsable_categoria(s.categoria)})
        return d

    def _responsable_categoria(self, c: m.Categoria) -> str | None:
        """Quien recibe las tareas sin responsable propio (el principal de la categoría)."""
        fila = self.session.scalar(select(m.CategoriaResponsable).where(m.CategoriaResponsable.categoria_id == c.id)
                                   .order_by(m.CategoriaResponsable.es_principal.desc()))
        if fila is None:
            return None
        u = self.session.get(m.Usuario, fila.usuario_id)
        return u.nombre if u else None

    def _nombres_usuarios(self, ids) -> dict[int, str]:
        ids = {i for i in ids if isinstance(i, int)}
        if not ids:
            return {}
        return {u.id: u.nombre for u in self.session.scalars(select(m.Usuario).where(m.Usuario.id.in_(ids))).unique()}

    def guardar(self, dto, ctx: Contexto, servicio_id: int | None = None) -> m.ServicioCatalogo:
        cat = self.session.get(m.Categoria, dto.categoria_id)
        sub = self.session.get(m.Subcategoria, dto.subcategoria_id)
        if cat is None or cat.eliminado or not cat.activo:
            raise ReglaNegocio("Elija una categoría activa")
        if sub is None or sub.categoria_id != cat.id or sub.eliminado:
            raise ReglaNegocio("La subcategoría no pertenece a la categoría")
        claves = set()
        campos = []
        for c in dto.campos:
            c = c.model_dump()
            c["clave"] = re.sub(r"[^a-z0-9_]", "_", (c["clave"] or c["etiqueta"]).strip().lower())[:40] or f"campo{len(campos) + 1}"
            if c["clave"] in claves:
                raise ReglaNegocio(f"Hay dos campos con la clave «{c['clave']}»")
            if c["tipo"] == "lista" and not c.get("opciones"):
                raise ReglaNegocio(f"Escriba las opciones de la lista «{c['etiqueta']}»")
            if c.get("aprobador") and c["tipo"] != "usuario":
                c["aprobador"] = False
            claves.add(c["clave"])
            campos.append(c)
        if sum(1 for c in campos if c.get("aprobador")) > 1:
            raise ReglaNegocio("Solo un campo puede indicar quién aprueba")
        opciones = []
        for o in dto.opciones:
            o = o.model_dump()
            o["clave"] = re.sub(r"[^a-z0-9_]", "_", (o["clave"] or o["etiqueta"]).strip().lower())[:40]
            if o["clave"] in claves:
                raise ReglaNegocio(f"La clave «{o['clave']}» está repetida")
            if o.get("responsable_id"):
                r = self.session.get(m.Usuario, o["responsable_id"])
                if r is None or not r.activo or r.eliminado:
                    raise ReglaNegocio(f"El responsable de «{o['etiqueta']}» no es un usuario activo")
            claves.add(o["clave"])
            opciones.append(o)
        s = self.session.get(m.ServicioCatalogo, servicio_id) if servicio_id else m.ServicioCatalogo(creado_por=ctx.usuario.id)
        if s is None:
            raise NoEncontrado("Servicio no encontrado")
        for k in ("nombre", "descripcion", "icono", "grupo", "categoria_id", "subcategoria_id", "plazo_horas", "plazo_texto",
                  "requiere_aprobacion", "lo_pide", "titulo_campos", "titulo_opciones", "aviso", "orden", "activo"):
            v = getattr(dto, k)
            setattr(s, k, v.strip() or None if isinstance(v, str) and k not in ("nombre", "descripcion", "grupo", "icono") else v)
        s.campos, s.opciones = json.dumps(campos, ensure_ascii=False), json.dumps(opciones, ensure_ascii=False)
        s.fecha_actualizacion = utcnow()
        if servicio_id is None:
            self.session.add(s)
        self.session.flush()
        self.session.refresh(s)
        self.auditoria.registrar(ctx, AccionAuditoria.SERVICIO_MODIFICADO, "servicio", s.id, {"nombre": s.nombre, "activo": s.activo})
        return s

    # ============================================================ solicitar
    def _valor(self, campo: dict, crudo) -> tuple[str | None, object]:
        """Valida una respuesta. Devuelve (texto para el ticket, valor guardado)."""
        tipo, etiqueta = campo.get("tipo", "texto"), campo.get("etiqueta", "Campo")
        if crudo is None or (isinstance(crudo, str) and not crudo.strip()):
            if campo.get("requerido"):
                raise ReglaNegocio(f"Complete «{etiqueta}»")
            return None, None
        texto = str(crudo).strip()[:2000]
        if tipo == "fecha":
            try:
                f = date.fromisoformat(texto[:10])
            except ValueError as exc:
                raise ReglaNegocio(f"«{etiqueta}» no es una fecha válida") from exc
            return f.strftime("%d/%m/%Y"), f.isoformat()
        if tipo == "cedula" and not re.fullmatch(r"\d{10}(\d{3})?", texto):
            raise ReglaNegocio(f"«{etiqueta}» debe tener 10 dígitos (o 13 si es RUC)")
        if tipo == "numero":
            try:
                float(texto.replace(",", "."))
            except ValueError as exc:
                raise ReglaNegocio(f"«{etiqueta}» debe ser un número") from exc
        if tipo == "correo" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto):
            raise ReglaNegocio(f"«{etiqueta}» no es un correo válido")
        if tipo == "area":
            a = self.session.get(m.Area, int(crudo)) if str(crudo).isdigit() else None
            if a is None:
                raise ReglaNegocio(f"Elija «{etiqueta}» de la lista")
            return a.nombre, a.id
        if tipo == "usuario":
            u = self.session.get(m.Usuario, int(crudo)) if str(crudo).isdigit() else None
            if u is None or not u.activo or u.eliminado:
                raise ReglaNegocio(f"Elija «{etiqueta}» de la lista")
            return u.nombre + (f" · {u.cargo}" if u.cargo else ""), u.id
        if tipo == "lista" and texto not in (campo.get("opciones") or []):
            raise ReglaNegocio(f"Elija una opción válida en «{etiqueta}»")
        return texto, texto

    def solicitar(self, servicio_id: int, dto, ctx: Contexto) -> m.Ticket:
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        if not u.tiene(Permiso.TICKET_CREAR):
            raise Prohibido("No tiene permiso para crear solicitudes")
        s = self.obtener(servicio_id)
        campos, opciones = _json(s.campos), _json(s.opciones)
        respuestas, lineas, aprobador_id, resumen = [], [], None, []
        for c in campos:
            texto, valor = self._valor(c, (dto.respuestas or {}).get(c.get("clave")))
            if texto is None:
                continue
            respuestas.append({"clave": c["clave"], "etiqueta": c["etiqueta"], "valor": texto})
            lineas.append(f"{c['etiqueta']}: {texto}")
            if c.get("aprobador"):
                aprobador_id = valor
            if c.get("tipo") in ("texto", "area") and len(resumen) < 2:
                resumen.append(texto.split(" · ")[0])
        marcadas = set(dto.opciones or [])
        elegidas = [o for o in opciones if o.get("siempre") or o.get("clave") in marcadas]
        casillas = [o for o in opciones if not o.get("siempre")]
        if casillas and len(casillas) == len(opciones) and not any(o.get("clave") in marcadas for o in casillas):
            raise ReglaNegocio("Marque al menos una opción de lo que necesita")
        visibles = [o for o in elegidas if not o.get("siempre")]
        if visibles:
            lineas.append("")
            lineas.append(f"{s.titulo_opciones or 'Necesita'}:")
            lineas += [f"• {o['etiqueta']}" for o in visibles]
        obs = (dto.observaciones or "").strip()
        if obs:
            respuestas.append({"clave": "observaciones", "etiqueta": "Observaciones", "valor": obs[:2000]})
            lineas += ["", f"Observaciones: {obs[:2000]}"]
        asunto = s.nombre + (f" · {resumen[0]}" + (f" ({resumen[1]})" if len(resumen) > 1 else "") if resumen else "")
        descripcion = f"Solicitud del catálogo de servicios: {s.nombre}.\n\n" + "\n".join(lineas)
        ticket_dto = es.TicketCrear(asunto=asunto[:200], descripcion=descripcion, categoria_id=s.categoria_id,
                                    subcategoria_id=s.subcategoria_id, solicitante_id=dto.solicitante_id,
                                    en_nombre_motivo=dto.en_nombre_motivo)
        if aprobador_id and aprobador_id != u.id:
            aprobacion = ("PERSONA", aprobador_id)
        elif s.requiere_aprobacion:
            aprobacion = ("JEFE_DIRECTO", None)
        else:
            aprobacion = None

        def guardar_solicitud(t: m.Ticket) -> None:
            self.session.add(m.TicketSolicitudServicio(ticket_id=t.id, servicio_id=s.id, respuestas=json.dumps(respuestas, ensure_ascii=False)))
            for i, o in enumerate(elegidas):
                self.session.add(m.TicketTarea(ticket_id=t.id, titulo=(o.get("tarea") or o["etiqueta"])[:200],
                                               responsable_id=o.get("responsable_id"), orden=i))
            self.session.flush()

        svc = TicketService(self.session)
        t = svc.crear(ticket_dto, ctx, canal="CATALOGO", aprobacion=aprobacion,
                      resolucion_min=s.plazo_horas * 60 if s.plazo_horas else None, al_crear=guardar_solicitud)
        self.auditoria.registrar(ctx, AccionAuditoria.SOLICITUD_SERVICIO, "ticket", t.id,
                                 {"numero": t.numero, "servicio": s.nombre, "tareas": len(elegidas)})
        if t.estado != Estado.POR_APROBAR:
            self.avisar_tareas(t)
        return t

    def avisar_tareas(self, t: m.Ticket) -> None:
        """Las tareas sin responsable quedan con el responsable del ticket; cada uno recibe su aviso."""
        tareas = self.tareas(t.id)
        if not tareas:
            return
        por_persona: dict[int, list[str]] = {}
        for x in tareas:
            if x.responsable_id is None and t.responsable_id:
                x.responsable_id = t.responsable_id
            if x.responsable_id and x.estado == "PENDIENTE":
                por_persona.setdefault(x.responsable_id, []).append(x.titulo)
        for uid, titulos in por_persona.items():
            persona = self.session.get(m.Usuario, uid)
            texto = "; ".join(titulos)
            self.notif.notificar([persona], "TAREA_ASIGNADA", f"{t.numero}: {len(titulos)} tarea(s) para usted", texto[:900], t)
            if uid != t.responsable_id:   # el responsable del ticket ya recibió el correo de asignación
                self.notif.correo("TAREA_ASIGNADA", [persona], t, tarea=texto[:900])

    # ================================================================ tareas
    def tareas(self, ticket_id: int) -> list[m.TicketTarea]:
        T = m.TicketTarea
        return list(self.session.scalars(select(T).where(T.ticket_id == ticket_id).order_by(T.orden, T.id)).unique())

    def tiene_tarea(self, u: m.Usuario, ticket_id: int) -> bool:
        T = m.TicketTarea
        return self.session.scalar(select(T.id).where(T.ticket_id == ticket_id, T.responsable_id == u.id).limit(1)) is not None

    def marcar(self, ticket_id: int, tarea_id: int, lista: bool, ctx: Contexto) -> m.TicketTarea:
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        svc = TicketService(self.session)
        t = svc.obtener(ticket_id, u)
        x = self.session.get(m.TicketTarea, tarea_id)
        if x is None or x.ticket_id != t.id:
            raise NoEncontrado("Tarea no encontrada")
        if not (svc.es_gestor(u, t) or x.responsable_id == u.id):
            raise Prohibido("Esta tarea le corresponde a otra persona")
        if t.estado in (Estado.POR_APROBAR, Estado.CANCELADO, Estado.CERRADO):
            raise ReglaNegocio("El ticket no está en atención" if t.estado != Estado.POR_APROBAR else "Primero debe aprobarla el jefe")
        nuevo = "LISTA" if lista else "PENDIENTE"
        if x.estado == nuevo:
            return x
        ahora = utcnow()
        x.estado = nuevo
        x.completada_por, x.fecha_completada = (u.id, ahora) if lista else (None, None)
        svc._hist(t, u, "TAREA", "tarea", None if lista else "LISTA", nuevo, f"{'Lista' if lista else 'Reabierta'}: {x.titulo}"[:500], ahora)
        t.fecha_actualizacion = ahora
        self.auditoria.registrar(ctx, AccionAuditoria.TAREA_COMPLETADA, "ticket", t.id, {"numero": t.numero, "tarea": x.titulo, "estado": nuevo})
        pendientes = [y for y in self.tareas(t.id) if y.estado != "LISTA"]
        if lista and not pendientes and t.responsable:
            self.notif.notificar([t.responsable], "TAREAS_LISTAS", f"{t.numero}: todas las tareas están listas",
                                 "Confirme con el solicitante y resuelva el ticket.", t)
        return x

    def de_ticket(self, t: m.Ticket, u: m.Usuario, gestor: bool) -> dict | None:
        sol = self.session.get(m.TicketSolicitudServicio, t.id)
        tareas = self.tareas(t.id)
        if sol is None and not tareas:
            return None
        return {
            "servicio": sol.servicio.nombre if sol else None, "servicio_id": sol.servicio_id if sol else None,
            "plazo": plazo_texto(sol.servicio.plazo_horas, sol.servicio.plazo_texto) if sol else None,
            "respuestas": _json(sol.respuestas) if sol else [],
            "tareas": [{"id": x.id, "titulo": x.titulo, "estado": x.estado, "responsable": x.responsable.nombre if x.responsable else None,
                        "responsable_id": x.responsable_id, "fecha_completada": iso(x.fecha_completada),
                        "puede_marcar": t.estado not in (Estado.POR_APROBAR, Estado.CANCELADO, Estado.CERRADO)
                                        and (gestor or x.responsable_id == u.id)} for x in tareas],
        }

    def mis_solicitudes(self, u: m.Usuario) -> list[dict]:
        T, S = m.Ticket, m.TicketSolicitudServicio
        filas = list(self.session.scalars(
            select(T).join(S, S.ticket_id == T.id)
            .where(T.eliminado == False, T.estado.notin_([Estado.CERRADO, Estado.CANCELADO]),
                   (T.solicitante_id == u.id) | (T.creado_por_id == u.id))
            .order_by(T.fecha_creacion.desc()).limit(20)).unique())
        salida = []
        for t in filas:
            sol = self.session.get(S, t.id)
            tareas = self.tareas(t.id)
            listas = sum(1 for x in tareas if x.estado == "LISTA")
            if t.estado == Estado.POR_APROBAR:
                ap = self.session.scalar(select(m.TicketAprobacion).where(m.TicketAprobacion.ticket_id == t.id,
                                                                          m.TicketAprobacion.estado == "PENDIENTE"))
                avance = f"Por aprobar · {ap.aprobador.nombre}" if ap else "Por aprobar"
            elif t.estado == Estado.RESUELTO:
                avance = "Listo · confirme que todo funciona"
            else:
                avance = "Esperando a TI" + (f" · {listas} de {len(tareas)} tareas listas" if tareas else "")
            detalle = next((r["valor"] for r in _json(sol.respuestas) if r.get("clave") != "observaciones"), None)
            salida.append({"ticket_id": t.id, "numero": t.numero, "servicio": sol.servicio.nombre, "detalle": detalle,
                           "estado": t.estado, "avance": avance, "tareas": len(tareas), "tareas_listas": listas,
                           "fecha_creacion": iso(t.fecha_creacion)})
        return salida

    def opciones_formulario(self) -> dict:
        """Listas para los campos de tipo área y usuario."""
        from app.application.services.notificacion_service import cuentas_sistema

        U = m.Usuario
        sistema = cuentas_sistema()
        usuarios = [u for u in self.session.scalars(select(U).where(U.activo == True, U.eliminado == False).order_by(U.nombre)).unique()
                    if u.correo.lower() not in sistema]
        areas = list(self.session.scalars(select(m.Area).where(m.Area.activo == True).order_by(m.Area.nombre)))
        return {"areas": [{"id": a.id, "nombre": a.nombre} for a in areas],
                "usuarios": [{"id": u.id, "nombre": u.nombre, "cargo": u.cargo, "area": u.area.nombre if u.area else None} for u in usuarios]}
