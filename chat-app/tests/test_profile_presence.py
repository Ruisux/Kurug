"""
Tests de perfil, avatar y presencia (Fase 0).
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.database import Base, engine
from conftest import register_token


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def token_for(client, username="alice", password="secret123"):
    return register_token(client, username, password)


def headers_for(client, username="alice", password="secret123"):
    return {"Authorization": f"Bearer {token_for(client, username, password)}"}


# ---------- Perfil ----------

def test_profile_defaults_and_update(client):
    h = headers_for(client)
    me = client.get("/users/me", headers=h).json()
    assert me["display_name"] == "alice"  # sin nickname -> username
    assert me["status"] == "online"
    assert me["accent_color"] == "#d97a4a"

    r = client.patch("/users/me", json={
        "nickname": "Ali",
        "bio": "hola",
        "accent_color": "#00ff00",
        "status": "dnd",
        "custom_status": "ocupada",
    }, headers=h)
    assert r.status_code == 200
    me = r.json()
    assert me["display_name"] == "Ali"
    assert me["nickname"] == "Ali"
    assert me["status"] == "dnd"
    assert me["accent_color"] == "#00ff00"
    assert me["custom_status"] == "ocupada"


def test_profile_validation(client):
    h = headers_for(client)
    assert client.patch("/users/me", json={"accent_color": "verde"}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"status": "bailando"}, headers=h).status_code == 422


def test_get_other_user_and_404(client):
    h = headers_for(client, "alice")
    # crear a bob y obtener su id real (no asumir, hay usuario bot sembrado)
    hb = headers_for(client, "bob", "secret123")
    bob_id = client.get("/users/me", headers=hb).json()["id"]
    bob = client.get(f"/users/{bob_id}", headers=h).json()
    assert bob["username"] == "bob"
    assert "password_hash" not in bob
    assert client.get("/users/999", headers=h).status_code == 404


def test_profile_requires_auth(client):
    assert client.get("/users/me").status_code == 401


# ---------- Avatar ----------

def _png_bytes(color="red", size=(20, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_avatar_upload_and_serve(client):
    h = headers_for(client)
    files = {"file": ("a.png", _png_bytes(), "image/png")}
    r = client.post("/users/me/avatar", headers=h, files=files)
    assert r.status_code == 200
    url = r.json()["avatar_url"]
    assert url.startswith("/static/avatars/")
    # se sirve como estático
    assert client.get(url).status_code == 200


def test_avatar_rejects_non_image(client):
    h = headers_for(client)
    files = {"file": ("x.txt", b"esto no es una imagen", "text/plain")}
    assert client.post("/users/me/avatar", headers=h, files=files).status_code == 400


# ---------- Presencia ----------

def test_presence_snapshot_and_live_events(client):
    ta = token_for(client, "alice")
    tb = token_for(client, "bob")
    ha = {"Authorization": f"Bearer {ta}"}

    with client.websocket_connect(f"/ws/presence?token={ta}") as wsa:
        snap = wsa.receive_json()
        assert snap["type"] == "presence_snapshot"

        with client.websocket_connect(f"/ws/presence?token={tb}") as wsb:
            wsb.receive_json()  # snapshot de bob
            # alice se entera de que bob entró
            evt = wsa.receive_json()
            assert evt["type"] == "presence_update"
            assert evt["user"]["display_name"] == "bob"

            # bob pasa a "dnd" -> alice lo ve
            wsb.send_json({"type": "set_status", "status": "dnd"})
            evt = wsa.receive_json()
            assert evt["type"] == "presence_update"
            assert evt["user"]["status"] == "dnd"

            # GET /presence lista a los conectados visibles
            online = client.get("/presence", headers=ha).json()
            names = {u["display_name"] for u in online}
            assert {"alice", "bob"} <= names

            # bob se vuelve invisible -> para alice es como desconectarse
            wsb.send_json({"type": "set_status", "status": "invisible"})
            evt = wsa.receive_json()
            assert evt["type"] == "presence_offline"

        # bob cerró la conexión; alice no recibe doble offline porque ya estaba oculto


def test_presence_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/presence?token=invalido") as ws:
            ws.receive_json()
