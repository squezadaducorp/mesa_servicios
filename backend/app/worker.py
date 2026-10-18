"""Proceso en segundo plano: motor de SLA, escalamiento, cierre automático y envío de correos.

Uso:  python -m app.worker          (bucle continuo)
      python -m app.worker --una-vez
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time
from datetime import timedelta

from sqlalchemy import select

from app.application.services.ia_service import IaService
from app.application.services.sla_service import SlaService
from app.application.services.ticket_service import TicketService
from app.application.errores import Contexto
from app.core.config import settings
from app.core.security import utcnow
from app.domain.enums import Estado
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.email.smtp import EnviadorSmtp
from app.infrastructure.repositories.repositorios import CatalogoRepository, UsuarioRepository

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s [worker] %(message)s")
log = logging.getLogger("aducorp.worker")

PROPIETARIO = f"{socket.gethostname()}:{os.getpid()}"
_detener = False


def _senal(*_):
    global _detener
    _detener = True
    log.info("Señal de parada recibida; terminando el ciclo actual")


def tomar_bloqueo(session, nombre: str, segundos: int) -> bool:
    """Lease en BD para que solo un worker procese a la vez (si se levantan varios)."""
    ahora = utcnow()
    b = session.get(m.BloqueoProceso, nombre, with_for_update=True)
    if b is None:
        session.add(m.BloqueoProceso(nombre=nombre, propietario=PROPIETARIO, expira=ahora + timedelta(seconds=segundos)))
    elif b.propietario != PROPIETARIO and b.expira > ahora:
        return False
    else:
        b.propietario, b.expira = PROPIETARIO, ahora + timedelta(seconds=segundos)
    session.commit()
    return True


def liberar_bloqueos() -> None:
    with SessionLocal() as session:
        for b in session.scalars(select(m.BloqueoProceso).where(m.BloqueoProceso.propietario == PROPIETARIO)):
            b.expira = utcnow()
        session.commit()


def ciclo_sla() -> dict:
    with SessionLocal() as session:
        if not tomar_bloqueo(session, "motor_sla", settings.WORKER_INTERVALO_SEG * 3):
            return {"omitido": "otro worker tiene el bloqueo"}
        stats = SlaService(session).evaluar_tickets_abiertos()
        # Riesgo de incumplimiento (IA local) para tickets abiertos
        ia = IaService(session)
        abiertos = session.scalars(select(m.Ticket).where(m.Ticket.eliminado == False,
                                                          m.Ticket.estado.in_(["NUEVO", "ASIGNADO", "EN_PROCESO", "ESCALADO"]))).unique().all()
        carga = UsuarioRepository(session).carga_abierta(list({t.responsable_id for t in abiertos if t.responsable_id}))
        for t in abiertos:
            ia.riesgo(t, carga.get(t.responsable_id, 0))
        session.commit()
        return stats


def ciclo_cierre_automatico() -> int:
    """Cierra los tickets resueltos tras N horas laborables sin reapertura (configuración ticket.cierre_automatico_h)."""
    with SessionLocal() as session:
        horas = int(CatalogoRepository(session).configuracion().get("ticket.cierre_automatico_h", "72"))
        if horas <= 0:
            return 0
        svc = TicketService(session)
        ahora = utcnow()
        cerrados = 0
        for t in session.scalars(select(m.Ticket).where(m.Ticket.estado == Estado.RESUELTO, m.Ticket.eliminado == False)).unique():
            if t.fecha_resolucion and svc.sla.cal.minutos_laborables(t.fecha_resolucion, ahora) >= horas * 60:
                svc._aplicar_estado(t, Estado.RESUELTO, Estado.CERRADO, None, Contexto(ip="worker", equipo=PROPIETARIO), ahora)
                svc._hist(t, None, "CIERRE", None, None, None, f"Cierre automático tras {horas} h laborables en Resuelto", ahora)
                cerrados += 1
        session.commit()
        return cerrados


def ciclo_correos(lote: int = 50) -> dict:
    enviador = EnviadorSmtp()
    enviados = errores = 0
    with SessionLocal() as session:
        pendientes = session.scalars(
            select(m.ColaCorreo).where(m.ColaCorreo.estado.in_(["PENDIENTE", "ERROR"]), m.ColaCorreo.proximo_intento <= utcnow(),
                                       m.ColaCorreo.intentos < 6).order_by(m.ColaCorreo.id).limit(lote)
        ).all()
        for c in pendientes:
            try:
                enviador.enviar(c.para, c.asunto, c.cuerpo_html, c.cc)
                c.estado, c.fecha_envio = "ENVIADO", utcnow()
                enviados += 1
            except Exception as exc:   # reintento con backoff exponencial: 1, 2, 4, 8, 16 min
                c.intentos += 1
                c.estado, c.ultimo_error = "ERROR", str(exc)[:1000]
                c.proximo_intento = utcnow() + timedelta(minutes=2 ** (c.intentos - 1))
                if c.intentos >= 6:
                    c.estado = "DESCARTADO"
                errores += 1
                log.warning("Error enviando correo %s a %s: %s", c.id, c.para, exc)
            session.commit()
    return {"enviados": enviados, "errores": errores}


def ejecutar_ciclo() -> None:
    for nombre, fn in (("sla", ciclo_sla), ("cierre", ciclo_cierre_automatico), ("correo", ciclo_correos)):
        try:
            r = fn()
            log.info("Ciclo %s: %s", nombre, r)
        except Exception:
            log.exception("Fallo en el ciclo %s", nombre)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--una-vez", action="store_true")
    args = ap.parse_args()
    signal.signal(signal.SIGTERM, _senal)
    signal.signal(signal.SIGINT, _senal)
    log.info("Worker iniciado (%s), intervalo %ss, correo %s", PROPIETARIO, settings.WORKER_INTERVALO_SEG,
             "habilitado" if settings.EMAIL_ENABLED else "simulado")
    while not _detener:
        inicio = time.monotonic()
        ejecutar_ciclo()
        if args.una_vez:
            break
        while not _detener and time.monotonic() - inicio < settings.WORKER_INTERVALO_SEG:
            time.sleep(1)
    liberar_bloqueos()


if __name__ == "__main__":
    main()
