"""
Tests de la señalización de voz (WebRTC). No prueban media real, solo el
relay de mensajes de señalización entre pares de una sala.
"""
import pytest
from fastapi.testclient import TestClient

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


def reg(client, username, password="secret123"):
    token = register_token(client, username, password)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/users/me", headers=headers).json()
    return token, headers, me


def test_livekit_token(client):
    import jwt
    from app.config import settings

    ta, ha, alice = reg(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]

    r = client.post(f"/voice/token/{cid}", headers=ha)
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == settings.livekit_url
    assert body["room"] == f"channel-{cid}"
    assert body["identity"] == str(alice["id"])

    # El token va firmado con el secret de LiveKit y concede unirse a la sala.
    payload = jwt.decode(
        body["token"], settings.livekit_api_secret,
        algorithms=["HS256"], options={"verify_aud": False},
    )
    assert payload["sub"] == str(alice["id"])
    assert payload["video"]["room"] == f"channel-{cid}"
    assert payload["video"]["roomJoin"] is True
    # alice es el primer usuario -> admin -> roomAdmin en el token
    assert payload["video"].get("roomAdmin") is True


def test_livekit_token_unknown_channel(client):
    _, ha, _ = reg(client, "alice")
    assert client.post("/voice/token/999", headers=ha).status_code == 404


def test_kick_requires_admin(client):
    _, ha, _ = reg(client, "alice")  # primer humano -> admin
    _, hb, bob = reg(client, "bob")  # no admin
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    # un no-admin no puede expulsar (rechaza antes de tocar LiveKit)
    assert client.post(f"/voice/kick/{cid}/{bob['id']}", headers=hb).status_code == 403


def test_chat_rejects_bad_token(client):
    _, ha, _ = reg(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/{cid}?token=invalido") as ws:
            ws.receive_json()
