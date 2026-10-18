import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["STORAGE_PATH"] = tempfile.mkdtemp(prefix="adjuntos_")
os.environ["AI_PROVIDER"] = "local"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.routers.auth import limitador_login  # noqa: E402
from app.application.services import sla_service  # noqa: E402
from app.infrastructure.db.semilla import sembrar  # noqa: E402
from app.infrastructure.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
CLAVE = "Aducorp2026!"


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sla_service.invalidar_calendario()
    limitador_login.reiniciar()
    with SessionLocal() as s:
        sembrar(s)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c


def login(client, usuario: str) -> dict:
    r = client.post(f"{API}/auth/login", json={"correo": f"{usuario}@aducorp.com.ec", "clave": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def como(client):
    cache = {}

    def _h(usuario):
        if usuario not in cache:
            cache[usuario] = login(client, usuario)
        return cache[usuario]

    return _h
