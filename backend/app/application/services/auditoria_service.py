import json

from sqlalchemy.orm import Session

from app.application.errores import Contexto
from app.core.security import utcnow
from app.infrastructure.db import models as m


class AuditoriaService:
    def __init__(self, session: Session):
        self.session = session

    def registrar(
        self,
        ctx: Contexto,
        accion: str,
        entidad: str | None = None,
        entidad_id=None,
        detalle: dict | None = None,
        resultado: str = "OK",
        usuario: m.Usuario | None = None,
        correo: str | None = None,
    ) -> None:
        u = usuario or ctx.usuario
        self.session.add(
            m.Auditoria(
                usuario_id=getattr(u, "id", None),
                usuario_correo=getattr(u, "correo", None) or correo,
                fecha_hora=utcnow(),
                accion=accion,
                entidad=entidad,
                entidad_id=str(entidad_id) if entidad_id is not None else None,
                detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None,
                ip=ctx.ip,
                equipo=(ctx.equipo or "")[:300] or None,
                resultado=resultado,
            )
        )
