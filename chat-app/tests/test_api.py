"""
Tests de la API con TestClient.

Cubren el flujo principal: registro, login, canales, historial y los rechazos
de autenticación. Usan la BD temporal configurada en conftest.py.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from conftest import register_token


@pytest.fixture(autouse=True)
def fresh_db():
    """Cada test arranca con tablas limpias."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def auth_header(client, username="alice", password="secret123"):
    token = register_token(client, username, password)
    return {"Authorization": f"Bearer {token}"}


def _code_for(email):
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        return u.verification_code if u else None


def test_register_verify_and_login(client):
    # Registro: aún NO hay token, hay que verificar el correo.
    r = client.post("/auth/register", json={"email": "bob@x.com", "username": "bob", "password": "secret123"})
    assert r.status_code == 201
    assert r.json()["email"] == "bob@x.com"
    assert "access_token" not in r.json()

    # Login sin verificar -> 403.
    r = client.post("/auth/login", data={"username": "bob", "password": "secret123"})
    assert r.status_code == 403

    # Verificar con el código -> token.
    code = _code_for("bob@x.com")
    r = client.post("/auth/verify", json={"email": "bob@x.com", "code": code})
    assert r.status_code == 200 and r.json()["access_token"]

    # Ahora login funciona, por usuario o por correo.
    assert client.post("/auth/login", data={"username": "bob", "password": "secret123"}).status_code == 200
    assert client.post("/auth/login", data={"username": "bob@x.com", "password": "secret123"}).status_code == 200


def test_verify_wrong_code(client):
    client.post("/auth/register", json={"email": "bob@x.com", "username": "bob", "password": "secret123"})
    r = client.post("/auth/verify", json={"email": "bob@x.com", "code": "000000"})
    assert r.status_code == 400


def test_register_duplicate(client):
    client.post("/auth/register", json={"email": "bob@x.com", "username": "bob", "password": "secret123"})
    # mismo usuario, otro correo
    r = client.post("/auth/register", json={"email": "otro@x.com", "username": "bob", "password": "secret123"})
    assert r.status_code == 400
    # mismo correo, otro usuario
    r = client.post("/auth/register", json={"email": "bob@x.com", "username": "bobby", "password": "secret123"})
    assert r.status_code == 400


def test_login_bad_credentials(client):
    register_token(client, "bob")  # registrado y verificado
    r = client.post("/auth/login", data={"username": "bob", "password": "malísima1"})
    assert r.status_code == 401


def test_weak_password_rejected(client):
    # Sin números -> 422; demasiado larga (>72 bytes) -> 422.
    assert client.post("/auth/register", json={"email": "a@x.com", "username": "abc", "password": "sololetras"}).status_code == 422
    assert client.post("/auth/register", json={"email": "b@x.com", "username": "abcd", "password": "a1" * 40}).status_code == 422


def test_bad_username_rejected(client):
    # Espacios / @ no permitidos en el handle.
    assert client.post("/auth/register", json={"email": "c@x.com", "username": "ab", "password": "secret123"}).status_code == 422
    assert client.post("/auth/register", json={"email": "d@x.com", "username": "a b", "password": "secret123"}).status_code == 422


def test_channels_require_auth(client):
    assert client.get("/channels").status_code == 401
    assert client.get("/channels", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_create_and_list_channel(client):
    headers = auth_header(client)
    r = client.post("/channels", json={"name": "general"}, headers=headers)
    assert r.status_code == 201

    r = client.get("/channels", headers=headers)
    assert r.status_code == 200
    assert "general" in [c["name"] for c in r.json()]

    # Duplicado -> 400
    r = client.post("/channels", json={"name": "general"}, headers=headers)
    assert r.status_code == 400


def test_channel_history_empty(client):
    headers = auth_header(client)
    cid = client.post("/channels", json={"name": "general"}, headers=headers).json()["id"]
    r = client.get(f"/channels/{cid}/messages", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_websocket_broadcast_and_persist(client):
    headers = auth_header(client)
    login = client.post("/auth/login", data={"username": "alice", "password": "secret123"})
    token = login.json()["access_token"]
    cid = client.post("/channels", json={"name": "general"}, headers=headers).json()["id"]

    with client.websocket_connect(f"/ws/{cid}?token={token}") as ws:
        ws.send_json({"content": "hola"})
        msg = ws.receive_json()
        assert msg["content"] == "hola"
        assert msg["author_username"] == "alice"
        # JSON inválido no debe tumbar la conexión.
        ws.send_text("esto no es json")
        ws.send_json({"content": "sigo vivo"})
        assert ws.receive_json()["content"] == "sigo vivo"

    # Persistencia: el historial trae los dos mensajes en orden.
    r = client.get(f"/channels/{cid}/messages", headers=headers)
    assert [m["content"] for m in r.json()] == ["hola", "sigo vivo"]


def test_websocket_rejects_bad_token(client):
    headers = auth_header(client)
    cid = client.post("/channels", json={"name": "general"}, headers=headers).json()["id"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/{cid}?token=invalido") as ws:
            ws.receive_json()


def test_pin_toggle_and_list(client):
    headers = auth_header(client)  # alice = primer usuario = admin
    token = client.post("/auth/login", data={"username": "alice", "password": "secret123"}).json()["access_token"]
    cid = client.post("/channels", json={"name": "general"}, headers=headers).json()["id"]

    with client.websocket_connect(f"/ws/{cid}?token={token}") as ws:
        ws.send_json({"content": "fíjame"})
        mid = ws.receive_json()["id"]
        # Fijar
        ws.send_json({"type": "pin", "id": mid})
        ev = ws.receive_json()
        assert ev["type"] == "pinned" and ev["id"] == mid and ev["pinned_at"]

    # El endpoint de fijados lo devuelve
    pins = client.get(f"/channels/{cid}/pins", headers=headers).json()
    assert [p["id"] for p in pins] == [mid]

    # Desfijar (toggle) deja la lista vacía
    with client.websocket_connect(f"/ws/{cid}?token={token}") as ws:
        ws.send_json({"type": "pin", "id": mid})
        ev = ws.receive_json()
        assert ev["type"] == "pinned" and ev["pinned_at"] is None
    assert client.get(f"/channels/{cid}/pins", headers=headers).json() == []


def test_upload_file_and_attach(client):
    headers = auth_header(client)
    token = client.post("/auth/login", data={"username": "alice", "password": "secret123"}).json()["access_token"]
    cid = client.post("/channels", json={"name": "general"}, headers=headers).json()["id"]

    # Subir un archivo genérico
    r = client.post(
        "/uploads/file",
        headers=headers,
        files={"file": ("informe.pdf", b"%PDF-1.4 datos", "application/pdf")},
    )
    assert r.status_code == 200
    up = r.json()
    assert up["url"].startswith("/static/uploads/files/")
    assert up["name"] == "informe.pdf" and up["size"] == len(b"%PDF-1.4 datos")

    # Adjuntarlo a un mensaje por WS (sin texto)
    with client.websocket_connect(f"/ws/{cid}?token={token}") as ws:
        ws.send_json({"content": "", "file": up})
        msg = ws.receive_json()
        assert msg["file_url"] == up["url"]
        assert msg["file_name"] == "informe.pdf"

    # Persiste en el historial
    hist = client.get(f"/channels/{cid}/messages", headers=headers).json()
    assert hist[-1]["file_name"] == "informe.pdf"

    # Limpieza del archivo de prueba
    import os
    path = "static/uploads/files/" + up["url"].rsplit("/", 1)[-1]
    if os.path.exists(path):
        os.remove(path)


def test_users_list_excludes_bot(client):
    auth_header(client, "alice")
    headers = auth_header(client, "bob")
    users = client.get("/users", headers=headers).json()
    names = [u["username"] for u in users]
    assert "alice" in names and "bob" in names
    assert "kurug-bot" not in names  # el bot no aparece para mencionar


def test_mentions_detected(client):
    headers = auth_header(client, "alice")  # admin (primer usuario)
    register_token(client, "bob")  # verificado
    bob_id = next(u["id"] for u in client.get("/users", headers=headers).json() if u["username"] == "bob")
    token = client.post("/auth/login", data={"username": "alice", "password": "secret123"}).json()["access_token"]
    cid = client.post("/channels", json={"name": "general"}, headers={"Authorization": f"Bearer {token}"}).json()["id"]

    with client.websocket_connect(f"/ws/{cid}?token={token}") as ws:
        ws.send_json({"content": "hola @bob mira esto"})
        msg = ws.receive_json()
        assert bob_id in msg["mentions"]
        assert msg["mention_everyone"] is False

        ws.send_json({"content": "atención @everyone"})
        msg2 = ws.receive_json()
        assert msg2["mention_everyone"] is True


def test_gif_search_requires_config(client):
    """Sin TENOR_API_KEY el buscador responde 503 (no rompe el resto)."""
    headers = auth_header(client)
    r = client.get("/gifs/featured", headers=headers)
    assert r.status_code == 503
