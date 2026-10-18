from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DbSession, contexto, requiere
from app.application.errores import Contexto
from app.application.schemas import esquemas as s
from app.application.services.admin_service import categoria_salida
from app.application.services.ia_service import IaService
from app.application.services.ticket_service import responsables_disponibles
from app.domain.enums import Permiso
from app.infrastructure.repositories.repositorios import CatalogoRepository

router = APIRouter(tags=["Catálogos e IA"])


@router.get("/catalogos", response_model=s.CatalogosSalida, summary="Catálogos para formularios y filtros")
def catalogos(ctx: Contexto = Depends(contexto), session: Session = DbSession):
    repo = CatalogoRepository(session)
    return {
        "categorias": [categoria_salida(c) for c in repo.categorias()],
        "prioridades": repo.prioridades(),
        "estados": repo.estados(),
        "areas": repo.areas(),
        "clientes": repo.clientes(),
        "responsables": responsables_disponibles(session),
    }


@router.post("/ia/sugerir", response_model=s.SugerenciaTicketSalida,
             summary="Clasificación, prioridad y responsable sugeridos para un ticket nuevo")
def sugerir(dto: s.IaEntrada, ctx: Contexto = Depends(requiere(Permiso.TICKET_CREAR)), session: Session = DbSession):
    return IaService(session).sugerir_ticket(dto.asunto, dto.descripcion, dto.cliente_id, ctx.usuario.id)
