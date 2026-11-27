"""Gestión de cambios (mejora 27). Reemplaza el Excel «Registro de cambios» y los formatos TI-FOR-001/002.

Flujo: Solicitado (secciones 1-6, cualquier persona) → Evaluado por TI (sección 7: tipo, matriz de riesgo, plan de
implementación y de reversión, ventana) → aprobaciones (Jefe de TI y, si el riesgo es medio o alto, Gerencia) →
Programado → Implementado (queda «En revisión») → Revisión posterior (exitoso, con problemas o revertido).

- Estándar (ya probado): no necesita aprobación. Emergencia: solo Jefe de TI y puede saltar el congelamiento.
- Congelamientos: periodos sin cambios definidos por TI y, si está activo, el último día hábil de cada mes (cierre).
- Jefe de TI y Gerencia se configuran en Configuración (cambios.jefe_ti y cambios.gerencia, por correo).
"""
from __future__ import annotations

import calendar
import io
from html import escape
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.errores import Contexto, NoEncontrado, Prohibido, ReglaNegocio
from app.application.services.auditoria_service import AuditoriaService
from app.application.services.notificacion_service import NotificacionService
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import AccionAuditoria, Permiso
from app.infrastructure.db import models as m
from app.infrastructure.repositories.repositorios import CatalogoRepository

TZ = ZoneInfo(settings.ZONA_HORARIA)
MATRIZ = {   # impacto × probabilidad de falla
    "ALTO": {"BAJA": "MEDIO", "MEDIA": "MEDIO", "ALTA": "ALTO"},
    "MEDIO": {"BAJA": "BAJO", "MEDIA": "MEDIO", "ALTA": "ALTO"},
    "BAJO": {"BAJA": "BAJO", "MEDIA": "BAJO", "ALTA": "MEDIO"},
}
ABIERTOS = ("SOLICITADO", "EN_ESPERA", "EN_APROBACION", "PROGRAMADO", "EN_REVISION")
FINALES = ("IMPLEMENTADO", "REVERTIDO", "RECHAZADO")
NOMBRE_ESTADO = {"SOLICITADO": "Solicitado", "EN_ESPERA": "En espera", "EN_APROBACION": "En aprobación", "PROGRAMADO": "Programado",
                 "EN_REVISION": "En revisión", "IMPLEMENTADO": "Implementado", "REVERTIDO": "Revertido", "RECHAZADO": "Rechazado"}
TEXTO = {
    "tipo_solicitud": {"ERROR": "Algo no funciona (error)", "MEJORA": "Mejora", "NUEVA": "Nueva función",
                       "CATALOGO": "Cambio de configuración o catálogo", "ACCESO": "Acceso o permisos", "OTRO": "Otro"},
    "clasificacion": {"CORRECCION": "Corrección", "MEJORA": "Mejora", "NUEVA": "Nueva función", "CONFIGURACION": "Configuración / catálogo",
                      "PERMISOS": "Permisos"},
    "tipo_cambio": {"ESTANDAR": "Estándar", "NORMAL": "Normal", "EMERGENCIA": "Emergencia"},
    "esfuerzo": {"MENOS_1": "Menos de 1 día", "1_3": "1 a 3 días", "MAS_3": "Más de 3 días"},
    "beneficiados": {"SOLO_YO": "Solo yo", "MI_AREA": "Mi área", "VARIAS_AREAS": "Varias áreas", "TODA_EMPRESA": "Toda la empresa / clientes"},
    "desde_donde": {"COMPUTADORA": "Computadora", "CELULAR": "Celular", "AMBOS": "Ambos"},
    "resultado": {"EXITOSO": "Exitoso", "CON_PROBLEMAS": "Con problemas", "REVERTIDO": "Revertido"},
}
APLICACIONES = "Mesa de Servicios, Correo / Microsoft 365, ECUAPASS, Sistema contable, Página web aducorp.com.ec, Servidor de archivos, Red e internet, Otra"


def iso(v: datetime | None) -> str | None:
    return v.isoformat() + "Z" if v else None


def a_utc(v: datetime | None) -> datetime | None:
    """Las fechas llegan con zona (navegador); se guardan en UTC sin zona como el resto del sistema."""
    if v is None:
        return None
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v


def local(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc).astimezone(TZ)


def riesgo(impacto: str | None, probabilidad: str | None) -> str | None:
    return MATRIZ.get(impacto or "", {}).get(probabilidad or "")



def motivo_cambio(texto: str | None) -> str:
    """Cada cambio de estado del cambio (evaluar, aprobar o rechazar, implementar, revisar) lleva motivo."""
    motivo = (texto or "").strip()
    if len(motivo) < 5:
        raise ReglaNegocio("Indique el motivo del cambio de estado")
    return motivo

class CambioService:
    def __init__(self, session: Session):
        self.session = session
        self.auditoria = AuditoriaService(session)
        self.notif = NotificacionService(session)

    # ============================================================ configuración
    def _config(self) -> dict:
        return CatalogoRepository(self.session).configuracion()

    def _usuario_config(self, clave: str) -> m.Usuario | None:
        correo = (self._config().get(clave) or "").strip().lower()
        if not correo:
            return None
        u = self.session.scalar(select(m.Usuario).where(func.lower(m.Usuario.correo) == correo))
        return u if u and u.activo and not u.eliminado else None

    def jefe_ti(self) -> m.Usuario | None:
        return self._usuario_config("cambios.jefe_ti")

    def gerencia(self) -> m.Usuario | None:
        return self._usuario_config("cambios.gerencia")

    def aplicaciones(self) -> list[str]:
        return [a.strip() for a in (self._config().get("cambios.aplicaciones") or APLICACIONES).split(",") if a.strip()]

    # ================================================================ permisos
    @staticmethod
    def gestor(u: m.Usuario) -> bool:
        return u.tiene(Permiso.CAMBIOS_GESTIONAR)

    def _ve_todo(self, u: m.Usuario) -> bool:
        return self.gestor(u) or u.tiene(Permiso.CAMBIOS_VER)

    def obtener(self, cambio_id: int, u: m.Usuario) -> m.Cambio:
        c = self.session.get(m.Cambio, cambio_id)
        if c is None or not self.puede_ver(c, u):
            raise NoEncontrado("Cambio no encontrado")
        return c

    def puede_ver(self, c: m.Cambio, u: m.Usuario) -> bool:
        if self._ve_todo(u) or u.id in (c.solicitante_id, c.responsable_id):
            return True
        A = m.CambioAprobacion
        return self.session.scalar(select(A.id).where(A.cambio_id == c.id, A.aprobador_id == u.id).limit(1)) is not None

    def acciones(self, c: m.Cambio, u: m.Usuario) -> list[str]:
        g = self.gestor(u)
        a = []
        if g and c.estado in ("SOLICITADO", "EN_ESPERA"):
            a.append("evaluar")
        if g and c.estado in ("EN_APROBACION", "PROGRAMADO"):
            a.append("reprogramar")
        if (g or c.responsable_id == u.id) and c.estado == "PROGRAMADO":
            a.append("implementar")
        if g and c.estado == "EN_REVISION":
            a.append("revisar")
        if c.estado not in FINALES and (g or c.solicitante_id == u.id):
            a.append("adjuntar")
        if c.solicitante_id == u.id and c.estado in ("SOLICITADO", "EN_ESPERA"):
            a.append("editar")
        return a

    def _hist(self, c: m.Cambio, u: m.Usuario | None, accion: str, detalle: str | None = None) -> None:
        self.session.add(m.CambioHistorial(cambio_id=c.id, usuario_id=u.id if u else None, accion=accion,
                                           detalle=(detalle or "")[:1000] or None, fecha=utcnow()))

    # ================================================================== crear
    def _siguiente_numero(self, anio: int) -> tuple[int, str]:
        ultimo = self.session.scalar(select(func.max(m.Cambio.secuencia)).where(m.Cambio.anio == anio)) or 0
        return ultimo + 1, f"CAM-{anio}-{ultimo + 1:03d}"

    def crear(self, dto, ctx: Contexto) -> m.Cambio:
        u = ctx.usuario
        anio = datetime.now(TZ).year
        seq, numero = self._siguiente_numero(anio)
        c = m.Cambio(numero=numero, anio=anio, secuencia=seq, solicitante_id=u.id, estado="SOLICITADO", fecha_creacion=utcnow())
        self._aplicar_solicitud(c, dto)
        self.session.add(c)
        self.session.flush()
        self._hist(c, u, "SOLICITADO", f"Formato {'TI-FOR-001 (Mesa de Servicios)' if c.formato == 'MESA' else 'TI-FOR-002 (general)'}")
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_SOLICITADO, "cambio", c.id, {"numero": c.numero, "titulo": c.titulo})
        gestores = [x for x in self._gestores() if x.id != u.id]
        self.notif.notificar(gestores, "CAMBIO_SOLICITADO", f"{c.numero}: nueva solicitud de cambio",
                             f"{u.nombre}: «{c.titulo}». Falta la evaluación de TI.")
        return c

    def _aplicar_solicitud(self, c: m.Cambio, dto) -> None:
        c.formato, c.titulo = dto.formato, dto.titulo.strip()
        c.telefono, c.tipo_solicitud = (dto.telefono or "").strip() or None, dto.tipo_solicitud
        c.aplicacion = ((dto.aplicacion or "").strip() or None) if dto.formato == "GENERAL" else "Mesa de Servicios"
        c.partes = ", ".join(p.strip() for p in dto.partes if p.strip())[:500] or None
        c.pantalla, c.desde_donde = (dto.pantalla or "").strip() or None, dto.desde_donde
        c.ticket_relacionado = (dto.ticket_relacionado or "").strip() or None
        c.situacion_actual, c.situacion_deseada = dto.situacion_actual.strip(), dto.situacion_deseada.strip()
        c.justificacion = (dto.justificacion or "").strip() or None
        c.beneficiados, c.prioridad_sugerida = dto.beneficiados, dto.prioridad_sugerida
        if dto.formato == "GENERAL" and not c.aplicacion:
            raise ReglaNegocio("Indique la aplicación o sistema")
        c.fecha_actualizacion = utcnow()

    def editar(self, cambio_id: int, dto, ctx: Contexto) -> m.Cambio:
        c = self.obtener(cambio_id, ctx.usuario)
        if "editar" not in self.acciones(c, ctx.usuario):
            raise Prohibido("Solo quien lo solicitó puede editarlo, y antes de la evaluación de TI")
        self._aplicar_solicitud(c, dto)
        self._hist(c, ctx.usuario, "EDITADO", "El solicitante actualizó la solicitud")
        return c

    def _gestores(self) -> list[m.Usuario]:
        U = m.Usuario
        return [u for u in self.session.scalars(select(U).where(U.activo == True, U.eliminado == False)).unique()
                if u.tiene(Permiso.CAMBIOS_GESTIONAR)]

    # ========================================================= congelamientos
    def congelamientos(self, desde: datetime, hasta: datetime) -> list[dict]:
        """Periodos sin cambios que tocan [desde, hasta) (UTC). Incluye el cierre de mes automático."""
        C = m.CambioCongelamiento
        filas = [{"id": x.id, "titulo": x.titulo, "inicio": x.inicio, "fin": x.fin, "motivo": x.motivo, "automatico": False}
                 for x in self.session.scalars(select(C).where(C.inicio < hasta, C.fin > desde).order_by(C.inicio))]
        if (self._config().get("cambios.congelar_cierre_mes") or "si").strip().lower() in ("si", "sí", "true", "1"):
            d0, d1 = local(desde).date(), local(hasta).date()
            meses = {(d0.year, d0.month), (d1.year, d1.month)}
            for anio, mes in sorted(meses):
                dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
                while dia.weekday() >= 5:
                    dia -= timedelta(days=1)
                ini = datetime.combine(dia, time(0, 0), TZ).astimezone(timezone.utc).replace(tzinfo=None)
                fin = ini + timedelta(days=1)
                if ini < hasta and fin > desde:
                    filas.append({"id": None, "titulo": "Congelamiento", "inicio": ini, "fin": fin,
                                  "motivo": "Cierre de mes · sin cambios", "automatico": True})
        return filas

    def _validar_ventana(self, c: m.Cambio, inicio: datetime | None, fin: datetime | None, tipo: str | None) -> None:
        if inicio is None or fin is None:
            raise ReglaNegocio("Indique la ventana de cambio (inicio y fin)")
        if fin <= inicio:
            raise ReglaNegocio("La ventana debe terminar después de empezar")
        if fin - inicio > timedelta(days=3):
            raise ReglaNegocio("La ventana no puede durar más de 3 días: divida el cambio")
        if tipo != "EMERGENCIA":
            for f in self.congelamientos(inicio, fin):
                raise ReglaNegocio(f"La ventana cae en un periodo congelado: {f['titulo']} ({f['motivo'] or ''}, "
                                   f"{local(f['inicio']):%d/%m %H:%M}). Elija otra fecha o márquelo como emergencia.")

    def choques(self, c: m.Cambio) -> list[str]:
        if not c.ventana_inicio or not c.ventana_fin:
            return []
        C = m.Cambio
        return list(self.session.scalars(select(C.numero).where(C.id != c.id, C.estado.in_(["EN_APROBACION", "PROGRAMADO"]),
                                                                C.ventana_inicio < c.ventana_fin, C.ventana_fin > c.ventana_inicio)))

    # =============================================================== evaluar
    def evaluar(self, cambio_id: int, dto, ctx: Contexto) -> m.Cambio:
        u = ctx.usuario
        c = self.obtener(cambio_id, u)
        if "evaluar" not in self.acciones(c, u):
            raise Prohibido("Solo TI evalúa los cambios, antes de aprobarlos")
        ahora = utcnow()
        comentario = motivo_cambio(dto.comentario)
        for k in ("clasificacion", "tipo_cambio", "impacto", "probabilidad", "esfuerzo", "prioridad_ti"):
            setattr(c, k, getattr(dto, k))
        for k in ("evaluacion", "plan_implementacion", "plan_reversion"):
            setattr(c, k, (getattr(dto, k) or "").strip() or None)
        c.riesgo = riesgo(dto.impacto, dto.probabilidad)
        c.evaluado_por_id, c.fecha_evaluacion, c.fecha_actualizacion = u.id, ahora, ahora
        if dto.responsable_id:
            r = self.session.get(m.Usuario, dto.responsable_id)
            if r is None or not r.activo or r.eliminado:
                raise ReglaNegocio("El responsable de implementar no es un usuario activo")
            c.responsable_id = r.id
        c.responsable_id = c.responsable_id or u.id
        c.ventana_inicio, c.ventana_fin = a_utc(dto.ventana_inicio), a_utc(dto.ventana_fin)
        self._anular_pendientes(c, "Se volvió a evaluar")
        detalle = f"{TEXTO['tipo_cambio'][c.tipo_cambio]} · riesgo {c.riesgo.lower()} (impacto {c.impacto.lower()}, probabilidad {c.probabilidad.lower()})"
        if dto.decision in ("RECHAZAR", "EN_ESPERA"):
            if not comentario:
                raise ReglaNegocio("Escriba el motivo: el solicitante lo verá")
            c.estado, c.motivo = ("RECHAZADO" if dto.decision == "RECHAZAR" else "EN_ESPERA"), comentario
            self._hist(c, u, c.estado, f"{detalle}. {comentario}")
            self._avisar_solicitante(c, "fue rechazado" if c.estado == "RECHAZADO" else "necesita más información", comentario)
            self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_EVALUADO, "cambio", c.id, {"numero": c.numero, "decision": dto.decision})
            return c
        if not c.plan_implementacion:
            raise ReglaNegocio("Escriba el plan de implementación")
        if c.tipo_cambio != "ESTANDAR" and not c.plan_reversion:
            raise ReglaNegocio("Escriba el plan de reversión: qué se hace si algo falla")
        self._validar_ventana(c, c.ventana_inicio, c.ventana_fin, c.tipo_cambio)
        c.motivo = None
        self._hist(c, u, "EVALUADO", detalle + (f". {comentario}" if comentario else ""))
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_EVALUADO, "cambio", c.id,
                                 {"numero": c.numero, "tipo": c.tipo_cambio, "riesgo": c.riesgo})
        if c.tipo_cambio == "ESTANDAR":
            self._programar(c, u, "Cambio estándar (ya probado): no necesita aprobación")
            return c
        jefe = self.jefe_ti()
        if jefe is None or jefe.id == u.id:   # quien evalúa es el Jefe de TI: su evaluación es la aprobación
            self.session.add(m.CambioAprobacion(cambio_id=c.id, rol="JEFE_TI", aprobador_id=u.id, estado="APROBADO",
                                                comentario=comentario, fecha_solicitud=ahora, fecha_respuesta=ahora))
            self.session.flush()
            self._siguiente(c, u)
        else:
            self._pedir(c, "JEFE_TI", jefe)
        return c

    def _anular_pendientes(self, c: m.Cambio, motivo: str) -> None:
        A = m.CambioAprobacion
        for f in self.session.scalars(select(A).where(A.cambio_id == c.id, A.estado.in_(["PENDIENTE", "APROBADO"]))):
            f.estado, f.comentario, f.fecha_respuesta = "ANULADO", (f.comentario or motivo)[:1000], f.fecha_respuesta or utcnow()

    def _pedir(self, c: m.Cambio, rol: str, aprobador: m.Usuario) -> None:
        fila = m.CambioAprobacion(cambio_id=c.id, rol=rol, aprobador_id=aprobador.id, fecha_solicitud=utcnow())
        self.session.add(fila)
        c.estado = "EN_APROBACION"
        quien = "Jefe de TI" if rol == "JEFE_TI" else "Gerencia"
        self._hist(c, None, "APROBACION_PEDIDA", f"Espera la aprobación de {aprobador.nombre} ({quien})")
        self.session.flush()
        self._avisar_aprobador(c, aprobador)

    def _avisar_aprobador(self, c: m.Cambio, aprobador: m.Usuario, recordatorio: bool = False) -> None:
        titulo = f"{c.numero} {'sigue esperando' if recordatorio else 'necesita'} su aprobación"
        ventana = f" · ventana {local(c.ventana_inicio):%d/%m %H:%M}" if c.ventana_inicio else ""
        self.notif.notificar([aprobador], "CAMBIO_APROBACION", titulo, f"«{c.titulo}» · riesgo {(c.riesgo or '').lower()}{ventana}", None, "AVISO")
        url = f"{settings.APP_URL.rstrip('/')}/cambios/{c.id}"
        self._correo(aprobador, f"[{'Recordatorio' if recordatorio else 'Aprobación'}] {c.numero} · {c.titulo}",
                     f"<p>Hola {escape(aprobador.nombre)}:</p><p>El cambio <b>{c.numero}</b> «{escape(c.titulo)}» necesita su aprobación.</p>"
                     f"<p>Tipo: {TEXTO['tipo_cambio'].get(c.tipo_cambio or '', '')} · Riesgo: {(c.riesgo or '').lower()}{ventana}</p>"
                     f"<p><b>Plan de reversión:</b> {escape(c.plan_reversion or '—')}</p>"
                     f'<p><a href="{url}" style="background:#1367AC;color:#fff;padding:9px 18px;border-radius:6px;text-decoration:none">'
                     f"Revisar y aprobar</a></p>")

    def _correo(self, u: m.Usuario, asunto: str, cuerpo: str) -> None:
        from app.infrastructure.email.smtp import plantilla_base

        self.session.add(m.ColaCorreo(para=u.correo, asunto=asunto[:250], cuerpo_html=plantilla_base(cuerpo), plantilla="CAMBIO",
                                      estado="PENDIENTE", proximo_intento=utcnow(), fecha_creacion=utcnow()))

    def _siguiente(self, c: m.Cambio, u: m.Usuario | None) -> None:
        """Después del Jefe de TI: Gerencia si el riesgo es medio o alto (salvo emergencia, que solo se le informa)."""
        if c.riesgo in ("MEDIO", "ALTO") and c.tipo_cambio != "EMERGENCIA":
            ger = self.gerencia()
            if ger is not None and ger.id != (u.id if u else None):
                self._pedir(c, "GERENCIA", ger)
                return
            if ger is None:
                self._hist(c, None, "SIN_GERENCIA", "No hay Gerencia configurada (Configuración › cambios.gerencia): sigue sin esa aprobación")
            else:
                self.session.add(m.CambioAprobacion(cambio_id=c.id, rol="GERENCIA", aprobador_id=ger.id, estado="APROBADO",
                                                    comentario="Quien aprueba como Jefe de TI es también Gerencia",
                                                    fecha_solicitud=utcnow(), fecha_respuesta=utcnow()))
        if c.tipo_cambio == "EMERGENCIA" and c.riesgo in ("MEDIO", "ALTO") and self.gerencia():
            self.notif.notificar([self.gerencia()], "CAMBIO_EMERGENCIA", f"{c.numero}: cambio de emergencia",
                                 f"«{c.titulo}» se implementa sin esperar su aprobación (emergencia). Queda en revisión posterior.")
        self._programar(c, u, None)

    def _programar(self, c: m.Cambio, u: m.Usuario | None, detalle: str | None) -> None:
        c.estado = "PROGRAMADO"
        ventana = f"{local(c.ventana_inicio):%a %d/%m %H:%M}" if c.ventana_inicio else "sin ventana"
        self._hist(c, u, "PROGRAMADO", (detalle + ". " if detalle else "") + f"Ventana: {ventana}")
        personas = [c.solicitante, c.responsable]
        self.notif.notificar(personas, "CAMBIO_PROGRAMADO", f"{c.numero} programado", f"«{c.titulo}» · {ventana}")

    def _avisar_solicitante(self, c: m.Cambio, que: str, comentario: str | None) -> None:
        self.notif.notificar([c.solicitante], "CAMBIO_RESULTADO", f"{c.numero} {que}", (comentario or c.titulo)[:900], None,
                             "AVISO" if "rechaz" in que or "más información" in que else "INFO")

    # ============================================================== aprobar
    def responder(self, cambio_id: int, aprobar: bool, comentario: str | None, ctx: Contexto) -> m.Cambio:
        u = ctx.usuario
        c = self.obtener(cambio_id, u)
        A = m.CambioAprobacion
        fila = self.session.scalar(select(A).where(A.cambio_id == c.id, A.aprobador_id == u.id, A.estado == "PENDIENTE"))
        if fila is None or c.estado != "EN_APROBACION":
            raise ReglaNegocio("No tiene una aprobación pendiente en este cambio")
        comentario = motivo_cambio(comentario)
        ahora = utcnow()
        fila.estado, fila.comentario, fila.fecha_respuesta = ("APROBADO" if aprobar else "RECHAZADO"), comentario, ahora
        quien = "Jefe de TI" if fila.rol == "JEFE_TI" else "Gerencia"
        self._hist(c, u, "APROBADO" if aprobar else "RECHAZADO", f"{quien}: {'aprobado' if aprobar else 'rechazado'}" + (f". {comentario}" if comentario else ""))
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_APROBACION, "cambio", c.id, {"numero": c.numero, "rol": fila.rol, "resultado": fila.estado})
        c.fecha_actualizacion = ahora
        if not aprobar:
            c.estado, c.motivo = "RECHAZADO", comentario
            self._avisar_solicitante(c, "fue rechazado", f"{u.nombre} ({quien}): {comentario}")
            return c
        if fila.rol == "JEFE_TI":
            self._siguiente(c, u)
        else:
            self._programar(c, u, "Aprobado por Gerencia")
        return c

    # ============================================================ programación
    def reprogramar(self, cambio_id: int, dto, ctx: Contexto) -> m.Cambio:
        c = self.obtener(cambio_id, ctx.usuario)
        if "reprogramar" not in self.acciones(c, ctx.usuario):
            raise Prohibido("No puede cambiar la ventana de este cambio")
        inicio, fin = a_utc(dto.ventana_inicio), a_utc(dto.ventana_fin)
        self._validar_ventana(c, inicio, fin, c.tipo_cambio)
        antes = f"{local(c.ventana_inicio):%d/%m %H:%M}" if c.ventana_inicio else "—"
        c.ventana_inicio, c.ventana_fin, c.fecha_actualizacion = inicio, fin, utcnow()
        self._hist(c, ctx.usuario, "REPROGRAMADO", f"Ventana {antes} → {local(inicio):%d/%m %H:%M}" + (f". {dto.comentario}" if dto.comentario else ""))
        self.notif.notificar([c.solicitante, c.responsable], "CAMBIO_PROGRAMADO", f"{c.numero} cambió de fecha",
                             f"«{c.titulo}» · nueva ventana {local(inicio):%a %d/%m %H:%M}")
        return c

    def implementar(self, cambio_id: int, dto, ctx: Contexto) -> m.Cambio:
        c = self.obtener(cambio_id, ctx.usuario)
        if "implementar" not in self.acciones(c, ctx.usuario):
            raise Prohibido("El cambio no está programado o no le corresponde")
        motivo_cambio(dto.comentario)
        c.estado, c.fecha_implementado = "EN_REVISION", utcnow()
        c.version_ref = (dto.version_ref or "").strip() or c.version_ref
        c.fecha_actualizacion = c.fecha_implementado
        self._hist(c, ctx.usuario, "IMPLEMENTADO", "Implementado; queda la revisión posterior" + (f". {dto.comentario}" if dto.comentario else ""))
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_AVANCE, "cambio", c.id, {"numero": c.numero, "estado": c.estado})
        return c

    def revisar(self, cambio_id: int, dto, ctx: Contexto) -> m.Cambio:
        c = self.obtener(cambio_id, ctx.usuario)
        if "revisar" not in self.acciones(c, ctx.usuario):
            raise Prohibido("El cambio no está en revisión posterior")
        ahora = utcnow()
        c.resultado, c.probado_solicitante = dto.resultado, dto.probado_solicitante
        c.observaciones = motivo_cambio(dto.observaciones)
        c.estado = "REVERTIDO" if dto.resultado == "REVERTIDO" else "IMPLEMENTADO"
        if dto.informado:
            c.fecha_informado = ahora
        c.fecha_actualizacion = ahora
        self._hist(c, ctx.usuario, "REVISION", f"Revisión posterior: {TEXTO['resultado'][dto.resultado].lower()}" + (f". {c.observaciones}" if c.observaciones else ""))
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_AVANCE, "cambio", c.id, {"numero": c.numero, "estado": c.estado, "resultado": c.resultado})
        if dto.informado:
            self._avisar_solicitante(c, "se implementó" if c.estado == "IMPLEMENTADO" else "se revirtió", c.observaciones)
        return c

    # ============================================================ adjuntos
    def adjuntar(self, cambio_id: int, nombre: str, tipo_mime: str, contenido: bytes, ctx: Contexto) -> m.CambioAdjunto:
        from app.application.services.ticket_service import TicketService
        from app.infrastructure.storage.local import AlmacenamientoLocal

        c = self.obtener(cambio_id, ctx.usuario)
        if "adjuntar" not in self.acciones(c, ctx.usuario):
            raise Prohibido("No puede adjuntar archivos a este cambio")
        tsvc = TicketService(self.session)
        max_mb, permitidas = tsvc.reglas_adjuntos()
        extension = tsvc.validar_archivo(nombre, contenido, max_mb, permitidas)
        ruta, _ = AlmacenamientoLocal().guardar(contenido, extension)
        a = m.CambioAdjunto(cambio_id=c.id, nombre_original=Path(nombre).name[:255], ruta=ruta, tipo_mime=(tipo_mime or "")[:100] or None,
                            tamano_bytes=len(contenido), usuario_id=ctx.usuario.id, fecha=utcnow())
        self.session.add(a)
        self.session.flush()
        self._hist(c, ctx.usuario, "ADJUNTO", a.nombre_original)
        return a

    def adjunto(self, cambio_id: int, adjunto_id: int, ctx: Contexto):
        from app.infrastructure.storage.local import AlmacenamientoLocal

        c = self.obtener(cambio_id, ctx.usuario)
        a = self.session.get(m.CambioAdjunto, adjunto_id)
        if a is None or a.cambio_id != c.id:
            raise NoEncontrado("Adjunto no encontrado")
        return a, AlmacenamientoLocal().ruta(a.ruta)

    # ============================================================ consultas
    def _consulta(self, u: m.Usuario):
        C = m.Cambio
        stmt = select(C)
        if not self._ve_todo(u):
            A = m.CambioAprobacion
            stmt = stmt.where(or_(C.solicitante_id == u.id, C.responsable_id == u.id,
                                  C.id.in_(select(A.cambio_id).where(A.aprobador_id == u.id))))
        return stmt

    def listar(self, u: m.Usuario, estado: str | None = None, texto: str | None = None) -> list[m.Cambio]:
        C = m.Cambio
        stmt = self._consulta(u)
        if estado == "ABIERTOS":
            stmt = stmt.where(C.estado.in_(ABIERTOS))
        elif estado:
            stmt = stmt.where(C.estado == estado)
        if texto:
            like = f"%{texto.strip()}%"
            stmt = stmt.where(or_(C.numero.like(like), C.titulo.like(like)))
        return list(self.session.scalars(stmt.order_by(C.anio.desc(), C.secuencia.desc())).unique())

    def resumen(self, u: m.Usuario) -> dict:
        cambios = self.listar(u)
        anio = datetime.now(TZ).year
        implementados = [c for c in cambios if c.fecha_implementado and local(c.fecha_implementado).year == anio]
        cerrados = [c for c in implementados if c.estado in ("IMPLEMENTADO", "REVERTIDO")]
        exitosos = [c for c in cerrados if c.estado == "IMPLEMENTADO" and c.resultado == "EXITOSO"]
        return {
            "por_aprobar": sum(c.estado in ("SOLICITADO", "EN_APROBACION", "EN_ESPERA") for c in cambios),
            "programados": sum(c.estado == "PROGRAMADO" for c in cambios),
            "implementados_anio": len(implementados), "anio": anio,
            "exitosos_pct": round(100 * len(exitosos) / len(cerrados)) if cerrados else None,
        }

    def calendario(self, u: m.Usuario, lunes: date | None = None) -> dict:
        hoy = datetime.now(TZ).date()
        lunes = lunes or hoy - timedelta(days=hoy.weekday())
        lunes -= timedelta(days=lunes.weekday())
        ini = datetime.combine(lunes, time(0, 0), TZ).astimezone(timezone.utc).replace(tzinfo=None)
        fin = ini + timedelta(days=7)
        C = m.Cambio
        cambios = list(self.session.scalars(self._consulta(u).where(C.ventana_inicio < fin, C.ventana_fin > ini,
                                                                    C.estado.notin_(["RECHAZADO"]))).unique())
        congelados = self.congelamientos(ini, fin)
        dias = []
        for i in range(7):
            d = lunes + timedelta(days=i)
            d0 = datetime.combine(d, time(0, 0), TZ).astimezone(timezone.utc).replace(tzinfo=None)
            d1 = d0 + timedelta(days=1)
            dias.append({
                "fecha": d.isoformat(),
                "cambios": [{"id": c.id, "numero": c.numero, "titulo": c.titulo, "estado": c.estado, "riesgo": c.riesgo, "tipo": c.tipo_cambio,
                             "inicio": iso(c.ventana_inicio), "fin": iso(c.ventana_fin)}
                            for c in sorted(cambios, key=lambda x: x.ventana_inicio) if local(c.ventana_inicio).date() == d],
                "congelamientos": [{"id": f["id"], "titulo": f["titulo"], "motivo": f["motivo"], "automatico": f["automatico"]}
                                   for f in congelados if f["inicio"] < d1 and f["fin"] > d0],
            })
        return {"desde": lunes.isoformat(), "hasta": (lunes + timedelta(days=6)).isoformat(), "dias": dias}

    def salida_lista(self, c: m.Cambio) -> dict:
        return {"id": c.id, "numero": c.numero, "titulo": c.titulo, "formato": c.formato, "tipo_cambio": c.tipo_cambio, "riesgo": c.riesgo,
                "estado": c.estado, "estado_nombre": NOMBRE_ESTADO.get(c.estado, c.estado), "ventana_inicio": iso(c.ventana_inicio),
                "ventana_fin": iso(c.ventana_fin), "solicitante": c.solicitante.nombre, "aplicacion": c.aplicacion,
                "fecha_creacion": iso(c.fecha_creacion), "prioridad_sugerida": c.prioridad_sugerida}

    def salida(self, c: m.Cambio, u: m.Usuario) -> dict:
        A, H, J = m.CambioAprobacion, m.CambioHistorial, m.CambioAdjunto
        aprob = list(self.session.scalars(select(A).where(A.cambio_id == c.id).order_by(A.id)).unique())
        hist = list(self.session.scalars(select(H).where(H.cambio_id == c.id).order_by(H.id)).unique())
        adj = list(self.session.scalars(select(J).where(J.cambio_id == c.id).order_by(J.id)))
        persona = lambda x: {"id": x.id, "nombre": x.nombre, "cargo": x.cargo, "area": x.area.nombre if x.area else None,  # noqa: E731
                             "correo": x.correo} if x else None
        pendiente = next((f for f in aprob if f.estado == "PENDIENTE" and f.aprobador_id == u.id), None)
        jefe, ger = self.jefe_ti(), self.gerencia()
        return {
            **self.salida_lista(c),
            "partes": [x.strip() for x in (c.partes or "").split(",") if x.strip()],
            **{k: getattr(c, k) for k in ("telefono", "tipo_solicitud", "pantalla", "desde_donde", "ticket_relacionado",
                                          "situacion_actual", "situacion_deseada", "justificacion", "beneficiados", "clasificacion",
                                          "impacto", "probabilidad", "esfuerzo", "prioridad_ti", "evaluacion", "plan_implementacion",
                                          "plan_reversion", "version_ref", "resultado", "probado_solicitante", "observaciones", "motivo")},
            "fecha_evaluacion": iso(c.fecha_evaluacion), "fecha_implementado": iso(c.fecha_implementado),
            "fecha_informado": iso(c.fecha_informado), "fecha_actualizacion": iso(c.fecha_actualizacion),
            "solicitante": persona(c.solicitante), "responsable": persona(c.responsable), "evaluado_por": persona(c.evaluado_por),
            "aprobaciones": [{"id": f.id, "rol": f.rol, "estado": f.estado, "comentario": f.comentario, "aprobador": persona(f.aprobador),
                              "fecha_solicitud": iso(f.fecha_solicitud), "fecha_respuesta": iso(f.fecha_respuesta), "recordado": f.recordado}
                             for f in aprob if f.estado != "ANULADO"],
            "historial": [{"id": h.id, "accion": h.accion, "detalle": h.detalle, "usuario": h.usuario.nombre if h.usuario else None,
                           "fecha": iso(h.fecha)} for h in hist],
            "adjuntos": [{"id": a.id, "nombre": a.nombre_original, "tamano_bytes": a.tamano_bytes, "fecha": iso(a.fecha)} for a in adj],
            "choques": self.choques(c),
            "congelado": [f["motivo"] or f["titulo"] for f in self.congelamientos(c.ventana_inicio, c.ventana_fin)]
                         if c.ventana_inicio and c.ventana_fin else [],
            "acciones": self.acciones(c, u) + (["aprobar"] if pendiente else []),
            "aprobacion_pendiente_id": pendiente.id if pendiente else None,
            "jefe_ti": persona(jefe), "gerencia": persona(ger),
            "textos": {k: TEXTO[k].get(getattr(c, k) or "", None) for k in TEXTO},
        }

    def responsables(self) -> list[dict]:
        U = m.Usuario
        filas = [u for u in self.session.scalars(select(U).where(U.activo == True, U.eliminado == False).order_by(U.nombre)).unique()
                 if u.rol.codigo in ("SUPER_ADMIN", "ADMIN_MESA", "SUPERVISOR", "ANALISTA")]
        return [{"id": u.id, "nombre": u.nombre} for u in filas]

    # ============================================================ congelamientos (CRUD)
    def crear_congelamiento(self, dto, ctx: Contexto) -> m.CambioCongelamiento:
        if not self.gestor(ctx.usuario):
            raise Prohibido("Solo TI define los periodos sin cambios")
        ini, fin = a_utc(dto.inicio), a_utc(dto.fin)
        if fin <= ini:
            raise ReglaNegocio("El periodo debe terminar después de empezar")
        f = m.CambioCongelamiento(titulo=dto.titulo.strip(), inicio=ini, fin=fin, motivo=(dto.motivo or "").strip() or None,
                                  creado_por=ctx.usuario.id)
        self.session.add(f)
        self.session.flush()
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_AVANCE, "congelamiento", f.id, {"titulo": f.titulo})
        return f

    def borrar_congelamiento(self, congelamiento_id: int, ctx: Contexto) -> None:
        if not self.gestor(ctx.usuario):
            raise Prohibido("Solo TI define los periodos sin cambios")
        f = self.session.get(m.CambioCongelamiento, congelamiento_id)
        if f is None:
            raise NoEncontrado("Periodo no encontrado")
        self.session.delete(f)
        self.auditoria.registrar(ctx, AccionAuditoria.CAMBIO_AVANCE, "congelamiento", congelamiento_id, {"borrado": f.titulo})

    def proximos_congelamientos(self) -> list[dict]:
        ahora = utcnow()
        return [{**f, "inicio": iso(f["inicio"]), "fin": iso(f["fin"])} for f in self.congelamientos(ahora, ahora + timedelta(days=60))]

    # ================================================================ Excel
    def exportar(self, u: m.Usuario) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Registro de cambios"
        ws.append(["Registro de solicitudes de cambio · Mesa de Servicios ADUCORP"])
        ws.append([f"Generado el {datetime.now(TZ):%d/%m/%Y %H:%M}. Formatos TI-FOR-001 (Mesa) y TI-FOR-002 (general)."])
        ws.append([])
        cab = ["N° cambio", "Fecha recepción", "Formato", "Solicitante", "Área", "Correo", "Aplicación", "Tipo", "Pantalla / módulo",
               "Ticket relacionado", "Resumen del cambio", "Prioridad sugerida", "Prioridad TI", "Tipo de cambio", "Impacto", "Probabilidad",
               "Riesgo", "Esfuerzo", "Estado", "Responsable", "Ventana", "Fecha implementado", "Días en atención", "Versión / PR",
               "Resultado", "Probado con solicitante", "Solicitante informado", "Aprobaciones", "Observaciones"]
        ws.append(cab)
        for col in range(1, len(cab) + 1):
            celda = ws.cell(row=4, column=col)
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="10203C")
            celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws["A1"].font = Font(bold=True, size=14, color="10203C")
        A = m.CambioAprobacion
        for c in self.listar(u):
            aprob = list(self.session.scalars(select(A).where(A.cambio_id == c.id, A.estado.in_(["APROBADO", "RECHAZADO"]))).unique())
            fin = c.fecha_implementado or utcnow()
            ws.append([
                c.numero, local(c.fecha_creacion).replace(tzinfo=None), "TI-FOR-001" if c.formato == "MESA" else "TI-FOR-002",
                c.solicitante.nombre, c.solicitante.area.nombre if c.solicitante.area else "", c.solicitante.correo, c.aplicacion or "",
                TEXTO["tipo_solicitud"].get(c.tipo_solicitud, c.tipo_solicitud), c.pantalla or c.partes or "", c.ticket_relacionado or "",
                c.titulo, (c.prioridad_sugerida or "").capitalize(), (c.prioridad_ti or "").capitalize(),
                TEXTO["tipo_cambio"].get(c.tipo_cambio or "", ""), (c.impacto or "").capitalize(), (c.probabilidad or "").capitalize(),
                (c.riesgo or "").capitalize(), TEXTO["esfuerzo"].get(c.esfuerzo or "", ""), NOMBRE_ESTADO.get(c.estado, c.estado),
                c.responsable.nombre if c.responsable else "",
                f"{local(c.ventana_inicio):%d/%m/%Y %H:%M} - {local(c.ventana_fin):%H:%M}" if c.ventana_inicio and c.ventana_fin else "",
                local(c.fecha_implementado).replace(tzinfo=None) if c.fecha_implementado else None,
                (fin - c.fecha_creacion).days, c.version_ref or "", TEXTO["resultado"].get(c.resultado or "", ""),
                "" if c.probado_solicitante is None else ("Sí" if c.probado_solicitante else "No"),
                local(c.fecha_informado).replace(tzinfo=None) if c.fecha_informado else None,
                "; ".join(f"{'Jefe TI' if f.rol == 'JEFE_TI' else 'Gerencia'}: {f.aprobador.nombre} ({f.estado.lower()})" for f in aprob),
                c.observaciones or c.motivo or "",
            ])
        anchos = [15, 14, 11, 22, 18, 26, 20, 18, 20, 16, 40, 10, 10, 12, 9, 11, 9, 14, 13, 20, 22, 14, 9, 14, 13, 10, 14, 40, 40]
        for i, ancho in enumerate(anchos, 1):
            ws.column_dimensions[get_column_letter(i)].width = ancho
        for fila in ws.iter_rows(min_row=5):
            for celda in fila:
                if isinstance(celda.value, datetime):
                    celda.number_format = "dd/mm/yyyy hh:mm" if celda.value.time() != time(0, 0) else "dd/mm/yyyy"
        ws.freeze_panes = "B5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(cab))}{max(ws.max_row, 4)}"
        salida = io.BytesIO()
        wb.save(salida)
        return salida.getvalue()

    # ================================================================ worker
    def procesar(self, ahora: datetime | None = None) -> dict:
        """Recordatorio único al aprobador que lleva más de 24 horas sin responder; limpia desafíos de 2FA viejos."""
        ahora = ahora or utcnow()
        A = m.CambioAprobacion
        recordados = 0
        for f in list(self.session.scalars(select(A).where(A.estado == "PENDIENTE", A.recordado == False,
                                                           A.fecha_solicitud < ahora - timedelta(hours=24))).unique()):
            c = self.session.get(m.Cambio, f.cambio_id)
            if c is None or c.estado != "EN_APROBACION":
                continue
            f.recordado = True
            self._avisar_aprobador(c, f.aprobador, recordatorio=True)
            self._hist(c, None, "RECORDATORIO", f"Recordatorio enviado a {f.aprobador.nombre}")
            recordados += 1
        D = m.DosfDesafio
        viejos = list(self.session.scalars(select(D).where(D.fecha_expiracion < ahora - timedelta(days=1))))
        for d in viejos:
            self.session.delete(d)
        return {"recordados": recordados, "desafios_borrados": len(viejos)}
