"""
Tests de la sala de música: cola, estado y comandos. La resolución (yt-dlp,
red) se mockea; el bot se simula con un WebSocket.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from app.config import settings
from app.security import create_access_token
from conftest import register_token


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # El MusicManager es un singleton en memoria: limpiar su estado entre tests.
    from app.music import music
    music.rooms.clear()
    music.ui.clear()
    music.bot.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:  # el lifespan crea el usuario bot y el canal música
        yield c


def reg(client, username, password="secret123"):
    return register_token(client, username, password)


def music_channel_id(client, headers):
    chans = client.get("/channels", headers=headers).json()
    return next(c["id"] for c in chans if c["is_music"])


def fake_resolve(query):
    return [{"video_id": "vid_" + query[:4], "title": f"Song {query}", "thumbnail": None, "duration": 120, "source": "youtube"}]


def test_music_room_flow(client, monkeypatch):
    monkeypatch.setattr("app.routers.music.resolve", fake_resolve)
    tok = reg(client, "alice")
    headers = {"Authorization": f"Bearer {tok}"}
    cid = music_channel_id(client, headers)
    bot_tok = create_access_token(settings.bot_username)

    with client.websocket_connect(f"/ws/music-bot/{cid}?token={bot_tok}") as bot:
        with client.websocket_connect(f"/ws/music/{cid}?token={tok}") as ui:
            first = ui.receive_json()
            assert first["type"] == "state" and first["queue"] == []

            ui.send_json({"type": "add", "query": "lofi"})
            # el bot recibe la orden de reproducir
            play = bot.receive_json()
            assert play["type"] == "play" and play["video_id"] == "vid_lofi"
            # la UI ve la cola con la pista, reproduciendo
            st = ui.receive_json()
            assert len(st["queue"]) == 1
            assert st["queue"][0]["title"] == "Song lofi"
            assert st["queue"][0]["added_by"] == "alice"
            assert st["playing"] is True and st["current"] == 0

            # añadir otra y saltar: la anterior (lofi) sale de la cola
            ui.send_json({"type": "add", "query": "jazz"})
            ui.receive_json()  # state con 2 en cola
            ui.send_json({"type": "skip"})
            play2 = bot.receive_json()
            assert play2["video_id"] == "vid_jazz"
            st = ui.receive_json()
            assert [t["title"] for t in st["queue"]] == ["Song jazz"]
            assert st["current"] == 0

            # loop y shuffle se reflejan
            ui.send_json({"type": "loop", "mode": "all"})
            assert ui.receive_json()["loop"] == "all"
            ui.send_json({"type": "shuffle", "on": True})
            assert ui.receive_json()["shuffle"] is True

            # progreso del bot llega a la UI
            bot.send_json({"type": "progress", "position": 12.5})
            assert ui.receive_json()["position"] == 12.5


def test_music_prev_returns_to_previous(client, monkeypatch):
    monkeypatch.setattr("app.routers.music.resolve", fake_resolve)
    tok = reg(client, "alice")
    headers = {"Authorization": f"Bearer {tok}"}
    cid = music_channel_id(client, headers)
    bot_tok = create_access_token(settings.bot_username)

    with client.websocket_connect(f"/ws/music-bot/{cid}?token={bot_tok}") as bot:
        with client.websocket_connect(f"/ws/music/{cid}?token={tok}") as ui:
            ui.receive_json()  # estado inicial
            ui.send_json({"type": "add", "query": "lofi"})
            bot.receive_json(); ui.receive_json()
            ui.send_json({"type": "add", "query": "jazz"})
            ui.receive_json()
            ui.send_json({"type": "skip"})  # lofi -> historial; suena jazz
            bot.receive_json(); ui.receive_json()

            # "anterior" debe recuperar lofi y reproducirlo de nuevo
            ui.send_json({"type": "prev"})
            play = bot.receive_json()
            assert play["video_id"] == "vid_lofi"
            st = ui.receive_json()
            assert [t["title"] for t in st["queue"]] == ["Song lofi", "Song jazz"]
            assert st["current"] == 0 and st["playing"] is True


def test_music_bot_requires_bot_token(client):
    tok = reg(client, "alice")
    headers = {"Authorization": f"Bearer {tok}"}
    cid = music_channel_id(client, headers)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/music-bot/{cid}?token={tok}") as ws:
            ws.receive_json()
