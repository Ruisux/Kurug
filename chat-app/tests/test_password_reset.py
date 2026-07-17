"""
Tests de recuperación de contraseña: /auth/forgot y /auth/reset.

Sin SMTP en tests, el código queda en la BD (el mailer solo lo loguea), así que
lo leemos de ahí igual que hace conftest.register_token.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import User
from conftest import register_token


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Los rate-limits viven en memoria del módulo: limpiarlos entre tests.
    from app.routers import auth as auth_router
    auth_router._login_fails.clear()
    auth_router._forgot_hits.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _code_for(email):
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        return u.verification_code if u else None


def test_reset_flow_completo(client):
    register_token(client, "alice", "secret123")
    email = "alice@test.com"

    # Pedir el código
    r = client.post("/auth/forgot", json={"email": email})
    assert r.status_code == 202
    code = _code_for(email)
    assert code and len(code) == 6

    # Restablecer: devuelve token que funciona (auto-login)
    r = client.post("/auth/reset", json={"email": email, "code": code, "password": "nueva1234"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["username"] == "alice"

    # La contraseña vieja ya no vale; la nueva sí
    assert client.post("/auth/login", data={"username": "alice", "password": "secret123"}).status_code == 401
    assert client.post("/auth/login", data={"username": "alice", "password": "nueva1234"}).status_code == 200

    # El código es de un solo uso
    r = client.post("/auth/reset", json={"email": email, "code": code, "password": "otra12345"})
    assert r.status_code == 400


def test_reset_codigo_incorrecto(client):
    register_token(client, "bob", "secret123")
    email = "bob@test.com"
    client.post("/auth/forgot", json={"email": email})
    code = _code_for(email)
    mal = "000000" if code != "000000" else "111111"
    r = client.post("/auth/reset", json={"email": email, "code": mal, "password": "nueva1234"})
    assert r.status_code == 400
    # La contraseña NO cambió
    assert client.post("/auth/login", data={"username": "bob", "password": "secret123"}).status_code == 200


def test_forgot_respuesta_uniforme_para_desconocidos(client):
    # No debe revelar si el correo existe o no
    r = client.post("/auth/forgot", json={"email": "nadie@test.com"})
    assert r.status_code == 202
    assert "Si la cuenta existe" in r.json()["message"]


def test_reset_password_debil_rechazada(client):
    register_token(client, "carol", "secret123")
    email = "carol@test.com"
    client.post("/auth/forgot", json={"email": email})
    code = _code_for(email)
    # Sin números -> el validador la rechaza (422 de Pydantic)
    r = client.post("/auth/reset", json={"email": email, "code": code, "password": "soloLetras"})
    assert r.status_code == 422


def test_forgot_rate_limit(client):
    # A la 6a petición en la misma ventana, 429
    for _ in range(5):
        assert client.post("/auth/forgot", json={"email": "x@test.com"}).status_code == 202
    assert client.post("/auth/forgot", json={"email": "x@test.com"}).status_code == 429
