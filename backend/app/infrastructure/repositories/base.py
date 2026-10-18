from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.session import Base

T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    """Repositorio genérico. Los repositorios específicos agregan consultas de negocio."""

    model: type[T]

    def __init__(self, session: Session):
        self.session = session

    def get(self, id_) -> T | None:
        return self.session.get(self.model, id_)

    def add(self, entidad: T) -> T:
        self.session.add(entidad)
        self.session.flush()
        return entidad

    def delete(self, entidad: T) -> None:
        self.session.delete(entidad)
        self.session.flush()

    def list(self, *filtros, order_by=None) -> list[T]:
        stmt = select(self.model).where(*filtros)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return list(self.session.scalars(stmt).unique())

    def paginar(self, stmt: Select, pagina: int, tamano: int) -> tuple[list, int]:
        total = self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        items = self.session.scalars(stmt.offset((pagina - 1) * tamano).limit(tamano)).unique().all()
        return list(items), total
