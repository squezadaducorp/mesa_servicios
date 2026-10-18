from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def crear_engine(url: str):
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        eng = create_engine(url, echo=settings.DB_ECHO, **kwargs)

        @event.listens_for(eng, "connect")
        def _fk(dbapi_con, _):
            dbapi_con.execute("PRAGMA foreign_keys=ON")

        return eng
    opciones = dict(echo=settings.DB_ECHO, pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_POOL_SIZE,
                    pool_pre_ping=True, pool_recycle=1800)
    if url.startswith("mssql+pyodbc"):
        opciones["fast_executemany"] = True
    return create_engine(url, **opciones)

engine = crear_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Unidad de trabajo por request: commit si todo sale bien, rollback si hay error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
