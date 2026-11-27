"""Proveedores y contratos (33): escalar un ticket a un proveedor externo y medir si cumple el plazo de su contrato.

- Al escalar, el ticket pasa a «Escalado» y nuestro SLA queda en pausa mientras el proveedor trabaja.
- El plazo del proveedor se cuenta en horas reloj si el contrato es 24/7, o en horas laborables si no.
- 30 minutos antes de que venza el plazo se avisa al responsable del ticket; 30 días antes de que venza
  un contrato se avisa por correo a los destinatarios de «proveedores.aviso_correo».
- Las multas reclamables se calculan con el % de la mensualidad por cada hora (o fracción) fuera de plazo.
"""
from __future__ import annotations

import html
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService
from app.application.services.sla_service import cargar_calendario
from app.core.config import settings
from app.core.security import utcnow
from app.domain.correos import separar, unir
from app.domain.enums import AccionAuditoria, Estado, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.email.smtp import plantilla_base
from app.infrastructure.repositories.repositorios import CatalogoRepository

TZ = ZoneInfo(settings.ZONA_HORARIA)
MESES_CORTOS = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
AVISO_PLAZO_MIN = 30
AVISO_CONTRATO_DIAS = 30


def local(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc).astimezone(TZ)


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def ids(texto: str | None) -> list[int]:
    return [int(x) for x in (texto or "").replace(";", ",").split(",") if x.strip().isdigit()]


def texto_horas(minutos: int | None) -> str:
    if minutos is None:
        return "—"
    h, mi = divmod(int(minutos), 60)
    if h >= 48:
        return f"{round(minutos / 1440)} días"
    return f"{h} h {mi:02d} min" if h else f"{mi} min"


def texto_plazo(horas: int) -> str:
    return f"{horas // 24} días" if horas >= 48 and horas % 24 == 0 else f"{horas} h"


class ProveedorService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)
        self.notif = NotificacionService(session)

    # ------------------------------------------------------------ permisos
    @staticmethod
    def gestor(u: m.Usuario) -> bool:
        return u.tiene(Permiso.PROVEEDORES_GESTIONAR)

    def _exigir_gestor(self, u: m.Usuario) -> None:
        if not self.gestor(u):
            raise Prohibido("No tiene permiso para administrar proveedores")

    def obtener(self, proveedor_id: int) -> m.Proveedor:
        p = self.session.get(m.Proveedor, proveedor_id)
        if p is None or p.eliminado:
            raise NoEncontrado("Proveedor no encontrado")
        return p

    def activos(self) -> list[m.Proveedor]:
        P = m.Proveedor
        return list(self.session.scalars(select(P).where(P.eliminado == False, P.activo == True).order_by(P.nombre)))

    # ------------------------------------------------------------- plazos
    def vence(self, p: m.Proveedor, desde: datetime) -> datetime:
        if p.atencion_24x7:
            return desde + timedelta(hours=p.plazo_horas)
        return cargar_calendario(self.session).sumar_minutos(desde, p.plazo_horas * 60)

    def minutos_entre(self, p: m.Proveedor, desde: datetime, hasta: datetime) -> int:
        if p.atencion_24x7:
            return max(int((hasta - desde).total_seconds() // 60), 0)
        return cargar_calendario(self.session).minutos_laborables(desde, hasta)

    def multa(self, p: m.Proveedor, c: m.ProveedorCaso) -> Decimal:
        """% de la mensualidad por cada hora o fracción fuera de plazo."""
        if c.cumplido is not False or not p.valor_mensual or not p.multa_pct_hora or not c.fecha_solucion:
            return Decimal("0")
        exceso = self.minutos_entre(p, c.vence, c.fecha_solucion)
        horas = max(math.ceil(exceso / 60), 1)
        return (Decimal(p.valor_mensual) * Decimal(p.multa_pct_hora) / 100 * horas).quantize(Decimal("0.01"))

    # ------------------------------------------------------------ casos
    def _casos(self, proveedor_id: int | None = None, ticket_id: int | None = None) -> list[m.ProveedorCaso]:
        C = m.ProveedorCaso
        stmt = select(C)
        if proveedor_id:
            stmt = stmt.where(C.proveedor_id == proveedor_id)
        if ticket_id:
            stmt = stmt.where(C.ticket_id == ticket_id)
        return list(self.session.scalars(stmt.order_by(C.fecha_reporte.desc())).unique())

    def caso_abierto(self, ticket_id: int) -> m.ProveedorCaso | None:
        C = m.ProveedorCaso
        return self.session.scalar(select(C).where(C.ticket_id == ticket_id, C.estado == "ABIERTO").limit(1))

    def caidas_mes(self, proveedor_id: int, ahora: datetime | None = None) -> int:
        hoy = local(ahora or utcnow())
        inicio = datetime(hoy.year, hoy.month, 1, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
        C = m.ProveedorCaso
        return len(list(self.session.scalars(select(C.id).where(C.proveedor_id == proveedor_id, C.fecha_reporte >= inicio))))

    def caso_salida(self, c: m.ProveedorCaso, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        p = c.proveedor
        return {
            "id": c.id, "proveedor_id": p.id, "proveedor": p.nombre, "servicio": p.servicio, "numero_caso": c.numero_caso,
            "reporte": c.reporte, "medio": c.medio, "contacto": c.contacto, "estado": c.estado, "fecha_reporte": iso(c.fecha_reporte),
            "vence": iso(c.vence), "fecha_solucion": iso(c.fecha_solucion), "minutos_solucion": c.minutos_solucion, "cumplido": c.cumplido,
            "vencido": c.estado == "ABIERTO" and ahora > c.vence, "solucion": c.solucion, "correo_enviado": c.correo_enviado,
            "ticket_id": c.ticket_id, "ticket_numero": c.ticket.numero, "ticket_asunto": c.ticket.asunto,
            "plazo": texto_plazo(p.plazo_horas), "multa": float(self.multa(p, c)),
        }

    def para_ticket(self, ticket_id: int, u: m.Usuario) -> dict:
        """Datos del diálogo «Escalar a proveedor»: proveedores (primero los de la subcategoría) y su contrato."""
        from app.application.services.ticket_service import TicketService

        svc = TicketService(self.session)
        t = svc.obtener(ticket_id, u)
        if "escalar_proveedor" not in svc.acciones(u, t):
            raise Prohibido("No puede escalar este ticket a un proveedor")
        ahora = utcnow()
        lista = []
        for p in self.activos():
            sugerido = t.subcategoria_id in ids(p.subcategorias)
            lista.append({**self.ficha_corta(p, ahora), "sugerido": sugerido, "caida_mes": self.caidas_mes(p.id, ahora) + 1,
                          "vence_caso": iso(self.vence(p, ahora)), "medios": self.medios(p)})
        lista.sort(key=lambda x: (not x["sugerido"], x["nombre"]))
        return {"proveedores": lista, "mes": MESES[local(ahora).month - 1]}

    @staticmethod
    def medios(p: m.Proveedor) -> list[str]:
        medios = []
        if p.telefono:
            medios.append(f"Teléfono {p.telefono}")
        if p.correo:
            medios.append(f"Correo {p.correo}")
        if p.portal:
            medios.append("Portal web")
        medios.append("Otro")
        return medios

    def escalar(self, ticket_id: int, dto, ctx: Contexto) -> m.ProveedorCaso:
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        svc = TicketService(self.session)
        t = svc.obtener(ticket_id, u)
        if "escalar_proveedor" not in svc.acciones(u, t):
            raise Prohibido("No puede escalar este ticket a un proveedor")
        p = self.obtener(dto.proveedor_id)
        if not p.activo:
            raise ReglaNegocio("El proveedor está inactivo")
        if dto.enviar_correo and not p.correo:
            raise ReglaNegocio(f"{p.nombre} no tiene correo de soporte registrado")
        ahora = utcnow()
        c = m.ProveedorCaso(proveedor_id=p.id, ticket_id=t.id, numero_caso=(dto.numero_caso or "").strip() or None,
                            reporte=dto.reporte.strip(), medio=(dto.medio or "").strip() or None,
                            contacto=(dto.contacto or "").strip() or None, estado="ABIERTO", fecha_reporte=ahora,
                            vence=self.vence(p, ahora), creado_por=u.id)
        self.session.add(c)
        anterior = t.estado
        # Nuestro SLA se pausa mientras el proveedor trabaja
        svc.sla.pausar(t, "PROVEEDOR", u.id, ahora)
        t.estado = Estado.ESCALADO
        t.fecha_actualizacion = ahora
        caso = f", caso {c.numero_caso}" if c.numero_caso else ""
        svc._hist(t, u, "ESCALAMIENTO_PROVEEDOR", "estado", anterior, Estado.ESCALADO, f"En manos de {p.nombre}{caso}", ahora)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.ESCALAMIENTO_PROVEEDOR, "ticket", t.id,
                                 {"numero": t.numero, "proveedor": p.nombre, "caso": c.numero_caso})
        self.notif.notificar([t.solicitante], "TICKET_PROVEEDOR", f"{t.numero} en manos de {p.nombre}",
                             f"Escalamos «{t.asunto}» a {p.nombre}{caso}. Le avisaremos apenas haya novedades.", t)
        if dto.enviar_correo:
            vence = local(c.vence)
            c.correo_enviado = self.notif.correo_directo(
                "PROVEEDOR_CASO", p.correo, p.nombre, t, cc=separar(p.correos_copia), proveedor=p.nombre,
                caso=c.numero_caso or "(por asignar)", reporte=c.reporte, contrato=p.contrato_numero or "—",
                plazo=texto_plazo(p.plazo_horas), vence=f"{vence:%d/%m/%Y %H:%M}", reporta=u.nombre)
        return c

    def resolver(self, caso_id: int, solucion: str | None, ctx: Contexto) -> m.ProveedorCaso:
        """El proveedor dio solución: el caso se cierra y el ticket vuelve a «En proceso» con nuestro SLA corriendo."""
        from app.application.services.ticket_service import TicketService

        u = ctx.usuario
        c = self.session.get(m.ProveedorCaso, caso_id)
        if c is None:
            raise NoEncontrado("Caso no encontrado")
        svc = TicketService(self.session)
        t = svc.obtener(c.ticket_id, u)
        if not svc.es_gestor(u, t) and not self.gestor(u):
            raise Prohibido("Solo quien atiende el ticket registra la solución del proveedor")
        if c.estado != "ABIERTO":
            raise ReglaNegocio("El caso ya está cerrado")
        ahora = utcnow()
        self._cerrar(c, ahora, (solucion or "").strip() or None)
        if t.estado == Estado.ESCALADO:
            svc._aplicar_estado(t, Estado.ESCALADO, Estado.EN_PROCESO, u, ctx, ahora, motivo=f"{c.proveedor.nombre} dio solución al caso")
        texto = f"{c.proveedor.nombre} dio solución" + (f" al caso {c.numero_caso}" if c.numero_caso else "")
        texto += f" en {texto_horas(c.minutos_solucion)} ({'dentro' if c.cumplido else 'fuera'} del plazo de {texto_plazo(c.proveedor.plazo_horas)})."
        if c.solucion:
            texto += f"\n\n{c.solucion}"
        svc._agregar_comentario(t, u, texto, True, "COMENTARIO", None, ahora)
        return c

    def _cerrar(self, c: m.ProveedorCaso, ahora: datetime, solucion: str | None = None) -> None:
        c.estado = "RESUELTO"
        c.fecha_solucion = ahora
        c.minutos_solucion = self.minutos_entre(c.proveedor, c.fecha_reporte, ahora)
        c.cumplido = ahora <= c.vence
        c.solucion = solucion or c.solucion

    def cerrar_abiertos(self, t: m.Ticket, ahora: datetime) -> None:
        """El ticket salió de «Escalado» por otro camino (se resolvió, se canceló...): el caso se da por solucionado."""
        c = self.caso_abierto(t.id)
        if c is not None:
            self._cerrar(c, ahora)

    # ------------------------------------------------------- administración
    def guardar(self, dto, ctx: Contexto, proveedor_id: int | None = None) -> m.Proveedor:
        self._exigir_gestor(ctx.usuario)
        p = self.obtener(proveedor_id) if proveedor_id else m.Proveedor(fecha_creacion=utcnow())
        datos = dto.model_dump()
        subs = datos.pop("subcategorias", []) or []
        validas = {s.id for s in self.session.scalars(select(m.Subcategoria).where(m.Subcategoria.id.in_(subs or [0])))}
        datos["correos_copia"] = unir(datos.pop("correos_copia", []) or [])
        for k, v in datos.items():
            setattr(p, k, v.strip() if isinstance(v, str) else v)
        p.subcategorias = ",".join(str(x) for x in subs if x in validas) or None
        if proveedor_id is None:
            self.session.add(p)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.PROVEEDOR_MODIFICADO, "proveedor", p.id, {"nombre": p.nombre})
        return p

    def eliminar(self, proveedor_id: int, ctx: Contexto) -> None:
        self._exigir_gestor(ctx.usuario)
        p = self.obtener(proveedor_id)
        p.eliminado = True
        self.auditoria.registrar(ctx, AccionAuditoria.PROVEEDOR_MODIFICADO, "proveedor", p.id, {"nombre": p.nombre, "eliminado": True})

    # ------------------------------------------------------------- salidas
    def _cumplimiento(self, p: m.Proveedor, ahora: datetime) -> str:
        """Cumple, Al límite (un caso fuera de plazo en el mes) o Incumple (dos o más)."""
        hoy = local(ahora)
        inicio = datetime(hoy.year, hoy.month, 1, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
        fuera = sum(1 for c in self._casos(p.id) if c.fecha_reporte >= inicio and
                    (c.cumplido is False or (c.estado == "ABIERTO" and ahora > c.vence)))
        return "INCUMPLE" if fuera >= 2 else "AL_LIMITE" if fuera == 1 else "CUMPLE"

    def ficha_corta(self, p: m.Proveedor, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        hoy = local(ahora).date()
        return {
            "id": p.id, "nombre": p.nombre, "servicio": p.servicio, "contrato_numero": p.contrato_numero,
            "contrato_vence": p.contrato_vence, "dias_para_vencer": (p.contrato_vence - hoy).days if p.contrato_vence else None,
            "atencion_24x7": bool(p.atencion_24x7), "plazo_horas": p.plazo_horas, "plazo": texto_plazo(p.plazo_horas),
            "multa_texto": (f"{coma(p.multa_pct_hora)} % de la mensualidad por hora extra" if p.multa_pct_hora else None),
            "contacto": p.contacto, "telefono": p.telefono, "correo": p.correo,
        }

    def salida(self, p: m.Proveedor, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        casos = self._casos(p.id)
        resueltos = [c for c in casos if c.minutos_solucion is not None]
        return {
            **self.ficha_corta(p, ahora), "activo": p.activo,
            "casos_abiertos": sum(1 for c in casos if c.estado == "ABIERTO"),
            "solucion_promedio_min": round(sum(c.minutos_solucion for c in resueltos) / len(resueltos)) if resueltos else None,
            "cumplimiento": self._cumplimiento(p, ahora),
        }

    def detalle(self, proveedor_id: int, u: m.Usuario) -> dict:
        self._exigir_gestor(u)
        p = self.obtener(proveedor_id)
        ahora = utcnow()
        anio = local(ahora).year
        casos = self._casos(p.id)
        del_anio = [c for c in casos if local(c.fecha_reporte).year == anio]
        por_mes = defaultdict(lambda: {"casos": 0, "fuera": 0})
        for c in del_anio:
            mes = local(c.fecha_reporte).month
            por_mes[mes]["casos"] += 1
            if c.cumplido is False or (c.estado == "ABIERTO" and ahora > c.vence):
                por_mes[mes]["fuera"] += 1
        subs = ids(p.subcategorias)
        nombres = [f"{s.categoria.nombre} › {s.nombre}" for s in self.session.scalars(
            select(m.Subcategoria).where(m.Subcategoria.id.in_(subs or [0])))] if subs else []
        return {
            **self.salida(p, ahora), "correos_copia": separar(p.correos_copia), "portal": p.portal,
            "contrato_detalle": p.contrato_detalle, "valor_mensual": float(p.valor_mensual) if p.valor_mensual is not None else None,
            "multa_pct_hora": float(p.multa_pct_hora) if p.multa_pct_hora is not None else None, "notas": p.notas,
            "subcategorias": subs, "subcategorias_nombres": nombres, "anio": anio,
            "meses": [{"mes": i + 1, "letra": MESES_CORTOS[i], **por_mes[i + 1]} for i in range(12)],
            "caidas_anio": len(del_anio), "fuera_plazo_anio": sum(v["fuera"] for v in por_mes.values()),
            "multas_anio": float(sum((self.multa(p, c) for c in del_anio), Decimal("0"))),
            "casos": [self.caso_salida(c, ahora) for c in casos[:20]],
        }

    def listar(self, u: m.Usuario) -> dict:
        self._exigir_gestor(u)
        ahora = utcnow()
        P = m.Proveedor
        lista = [self.salida(p, ahora) for p in self.session.scalars(select(P).where(P.eliminado == False).order_by(P.nombre))]
        alertas = []
        for x in lista:
            if x["activo"] and x["dias_para_vencer"] is not None and x["dias_para_vencer"] <= AVISO_CONTRATO_DIAS:
                p = self.obtener(x["id"])
                alertas.append({"id": x["id"], "nombre": x["nombre"], "contrato_vence": x["contrato_vence"],
                                "dias": x["dias_para_vencer"], "fuera_mes": self._fuera_mes(p, ahora),
                                "avisado": p.aviso_vencimiento == p.contrato_vence})
        return {"proveedores": lista, "alertas": alertas, "aviso_correo": self.destinatarios_aviso()}

    def _fuera_mes(self, p: m.Proveedor, ahora: datetime) -> int:
        hoy = local(ahora)
        inicio = datetime(hoy.year, hoy.month, 1, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
        return sum(1 for c in self._casos(p.id) if c.fecha_reporte >= inicio and
                   (c.cumplido is False or (c.estado == "ABIERTO" and ahora > c.vence)))

    def opciones(self) -> dict:
        subs = self.session.scalars(select(m.Subcategoria).where(m.Subcategoria.eliminado == False)).unique()
        return {"subcategorias": sorted(({"id": s.id, "nombre": f"{s.categoria.nombre} › {s.nombre}"} for s in subs),
                                        key=lambda x: x["nombre"])}

    def del_mes(self, desde_utc: datetime, hasta_utc: datetime) -> list[dict]:
        """Resumen por proveedor para el panel gerencial."""
        C = m.ProveedorCaso
        casos = list(self.session.scalars(select(C).where(C.fecha_reporte >= desde_utc, C.fecha_reporte < hasta_utc)).unique())
        ahora = utcnow()
        por: dict[int, dict] = {}
        for c in casos:
            x = por.setdefault(c.proveedor_id, {"nombre": c.proveedor.nombre, "servicio": c.proveedor.servicio, "casos": 0, "fuera": 0,
                                                "minutos": [], "multas": Decimal("0")})
            x["casos"] += 1
            if c.cumplido is False or (c.estado == "ABIERTO" and ahora > c.vence):
                x["fuera"] += 1
            if c.minutos_solucion is not None:
                x["minutos"].append(c.minutos_solucion)
            x["multas"] += self.multa(c.proveedor, c)
        return [{"nombre": x["nombre"], "servicio": x["servicio"], "casos": x["casos"], "fuera": x["fuera"],
                 "solucion_promedio_min": round(sum(x["minutos"]) / len(x["minutos"])) if x["minutos"] else None,
                 "multas": float(x["multas"])} for x in sorted(por.values(), key=lambda v: -v["casos"])]

    # ------------------------------------------------------------- worker
    def destinatarios_aviso(self) -> list[str]:
        return separar(CatalogoRepository(self.session).configuracion().get("proveedores.aviso_correo", ""))

    def procesar(self, ahora: datetime | None = None) -> dict:
        ahora = ahora or utcnow()
        C = m.ProveedorCaso
        avisados = 0
        for c in list(self.session.scalars(select(C).where(C.estado == "ABIERTO", C.aviso_enviado == False,
                                                           C.vence <= ahora + timedelta(minutes=AVISO_PLAZO_MIN))).unique()):
            c.aviso_enviado = True
            t = c.ticket
            if t.responsable is None:
                continue
            caso = f" (caso {c.numero_caso})" if c.numero_caso else ""
            if ahora >= c.vence:
                titulo, msg = f"{t.numero}: {c.proveedor.nombre} pasó su plazo", f"Venció el plazo del contrato{caso}. Reclame al proveedor."
            else:
                titulo, msg = f"{t.numero}: {c.proveedor.nombre} vence en 30 min", f"El plazo del contrato{caso} vence a las {local(c.vence):%H:%M}."
            self.notif.notificar([t.responsable], "PROVEEDOR_PLAZO", titulo, msg, t, "AVISO")
            self.notif.correo("PROVEEDOR_PLAZO", [t.responsable], t, proveedor=c.proveedor.nombre, caso=c.numero_caso or "—",
                              vence=f"{local(c.vence):%d/%m/%Y %H:%M}")
            avisados += 1
        contratos = 0
        para = self.destinatarios_aviso()
        hoy = local(ahora).date()
        for p in self.activos():
            if not p.contrato_vence or p.aviso_vencimiento == p.contrato_vence or not para:
                continue
            dias = (p.contrato_vence - hoy).days
            if dias > AVISO_CONTRATO_DIAS or dias < 0:
                continue
            p.aviso_vencimiento = p.contrato_vence
            fuera = self._fuera_mes(p, ahora)
            cuerpo = (f"<p>El contrato con <b>{html.escape(p.nombre)}</b> ({html.escape(p.servicio)}"
                      f"{', ' + html.escape(p.contrato_numero) if p.contrato_numero else ''}) vence en <b>{dias} días</b> "
                      f"({p.contrato_vence:%d/%m/%Y}).</p>"
                      + (f"<p>Este mes lleva <b>{fuera} caso{'s' if fuera != 1 else ''} fuera de plazo</b>.</p>" if fuera else "")
                      + f'<p><a href="{settings.APP_URL.rstrip("/")}/proveedores?id={p.id}">Ver el proveedor en la Mesa</a></p>')
            self.session.add(m.ColaCorreo(para=", ".join(para)[:500], asunto=f"Contrato con {p.nombre} vence en {dias} días"[:250],
                                          cuerpo_html=plantilla_base(cuerpo), plantilla="PROVEEDOR_CONTRATO", estado="PENDIENTE",
                                          proximo_intento=ahora, fecha_creacion=ahora))
            contratos += 1
        return {"avisos_plazo": avisados, "avisos_contrato": contratos}


def coma(v) -> str:
    texto = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")
