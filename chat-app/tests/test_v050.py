"""
Tests de la v0.5.0: pizarra colaborativa, no-leídos de DM, "está escribiendo",
actividad en presencia y estado de voz extendido (sharing/rtt).
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
    # Los managers viven en memoria: limpiarlos entre tests.
    from app.board import board
    from app.presence import presence
    board.boards.clear()
    board.ui.clear()
    presence.info.clear()
    presence.sockets.clear()
    presence.voice.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _drain_until(ws, wanted_type, tries=10):
    """Lee mensajes hasta encontrar el tipo esperado (ignora los intermedios)."""
    for _ in range(tries):
        m = ws.receive_json()
        if m.get("type") == wanted_type:
            return m
    raise AssertionError(f"no llegó ningún mensaje '{wanted_type}'")


def _el(el_id="a1b2c3d4", kind="pen", **extra):
    base = {"id": el_id, "kind": kind, "points": [[10, 10], [20, 20]],
            "color": "#e2553b", "width": 4}
    base.update(extra)
    return base


# ---------------- Pizarra ----------------

def test_board_add_snapshot_and_sync(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")

    with client.websocket_connect(f"/ws/board/7?token={ta}") as wsa:
        assert wsa.receive_json() == {"type": "snapshot", "elements": []}
        wsa.send_json({"type": "add", "el": _el()})

        # bob entra DESPUÉS: el snapshot ya trae el trazo de alice
        with client.websocket_connect(f"/ws/board/7?token={tb}") as wsb:
            snap = wsb.receive_json()
            assert len(snap["elements"]) == 1
            assert snap["elements"][0]["id"] == "a1b2c3d4"

            # los lotes del lápiz llegan a bob (y NO rebotan a alice)
            wsa.send_json({"type": "points", "id": "a1b2c3d4", "points": [[30, 30]]})
            pts = _drain_until(wsb, "points")
            assert pts["points"] == [[30, 30]]

            # coordenadas fuera del lienzo se clampan
            wsa.send_json({"type": "points", "id": "a1b2c3d4", "points": [[99999, -50]]})
            pts = _drain_until(wsb, "points")
            assert pts["points"] == [[1920, 0]]


def test_board_undo_only_own_and_clear(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")

    with client.websocket_connect(f"/ws/board/7?token={ta}") as wsa:
        wsa.receive_json()
        with client.websocket_connect(f"/ws/board/7?token={tb}") as wsb:
            wsb.receive_json()
            wsa.send_json({"type": "add", "el": _el("aaaa1111")})
            _drain_until(wsb, "added")
            wsb.send_json({"type": "add", "el": _el("bbbb2222")})
            _drain_until(wsa, "added")

            # el undo de bob borra LO SUYO, no lo de alice
            wsb.send_json({"type": "undo"})
            rm = _drain_until(wsa, "removed")
            assert rm["id"] == "bbbb2222"

            # limpiar lo borra todo para todos
            wsb.send_json({"type": "clear"})
            assert _drain_until(wsa, "cleared")["type"] == "cleared"

    from app.board import board
    assert board.boards[7].elements == {}


def test_board_rejects_garbage(client):
    ta = register_token(client, "alice")
    with client.websocket_connect(f"/ws/board/7?token={ta}") as wsa:
        wsa.receive_json()
        # kind inválido, id inválido, sin puntos: ninguno debe entrar
        wsa.send_json({"type": "add", "el": _el(kind="bomba")})
        wsa.send_json({"type": "add", "el": _el(el_id="../etc")})
        wsa.send_json({"type": "add", "el": {"id": "cccc3333", "kind": "pen", "points": []}})
        wsa.send_json({"type": "add", "el": _el("dddd4444", kind="text")})  # texto sin text
        # uno válido para confirmar que el canal sigue vivo
        wsa.send_json({"type": "add", "el": _el("eeee5555")})

    from app.board import board
    assert list(board.boards[7].elements) == ["eeee5555"]


# ---------------- DMs: no-leídos ----------------

def test_dm_unread_counts(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")
    me_a = client.get("/users/me", headers={"Authorization": f"Bearer {ta}"}).json()
    me_b = client.get("/users/me", headers={"Authorization": f"Bearer {tb}"}).json()

    # bob le escribe 3 DMs a alice (por el WS de presencia, como el cliente real)
    with client.websocket_connect(f"/ws/presence?token={ta}") as wsa:
        wsa.receive_json()  # snapshot
        with client.websocket_connect(f"/ws/presence?token={tb}") as wsb:
            wsb.receive_json()
            for i in range(3):
                wsb.send_json({"type": "dm", "to": me_a["id"], "content": f"hola {i}"})
                _drain_until(wsa, "dm")

    # sin last_read: 3 sin leer del partner bob
    r = client.post("/dms/unread", json={"last_read": {}},
                    headers={"Authorization": f"Bearer {ta}"})
    assert r.status_code == 200
    counts = {int(k): v for k, v in r.json().items()}
    assert counts == {me_b["id"]: 3}

    # con last_read en el segundo mensaje: queda 1
    from app.models import DirectMessage
    from app.database import SessionLocal
    with SessionLocal() as db:
        ids = [dm.id for dm in db.query(DirectMessage).order_by(DirectMessage.id).all()]
    r = client.post("/dms/unread", json={"last_read": {me_b["id"]: ids[1]}},
                    headers={"Authorization": f"Bearer {ta}"})
    counts = {int(k): v for k, v in r.json().items()}
    assert counts == {me_b["id"]: 1}


# ---------------- Typing ----------------

def test_channel_typing_broadcast(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")
    headers = {"Authorization": f"Bearer {ta}"}
    cid = client.post("/channels", json={"name": "general", "kind": "text"}, headers=headers).json()["id"]

    with client.websocket_connect(f"/ws/{cid}?token={ta}") as wsa:
        with client.websocket_connect(f"/ws/{cid}?token={tb}") as wsb:
            wsb.send_json({"type": "typing"})
            m = _drain_until(wsa, "typing")
            assert m["display_name"] == "bob"
            assert isinstance(m["user_id"], int)


def test_dm_typing_directed(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")
    me_a = client.get("/users/me", headers={"Authorization": f"Bearer {ta}"}).json()

    with client.websocket_connect(f"/ws/presence?token={ta}") as wsa:
        wsa.receive_json()
        with client.websocket_connect(f"/ws/presence?token={tb}") as wsb:
            wsb.receive_json()
            wsb.send_json({"type": "typing_dm", "to": me_a["id"]})
            m = _drain_until(wsa, "dm_typing")
            assert m["display_name"] == "bob"


# ---------------- Actividad ----------------

def test_activity_set_broadcast_and_preserved(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")

    with client.websocket_connect(f"/ws/presence?token={ta}") as wsa:
        wsa.receive_json()
        with client.websocket_connect(f"/ws/presence?token={tb}") as wsb:
            wsb.receive_json()
            _drain_until(wsa, "presence_update")  # bob apareció

            wsb.send_json({"type": "set_activity", "kind": "music", "text": "Pink Floyd - Time"})
            upd = _drain_until(wsa, "presence_update")
            assert upd["user"]["activity"] == {"kind": "music", "text": "Pink Floyd - Time"}

            # Cambiar el perfil NO debe borrar la actividad (no vive en la BD).
            # Como el cliente real: PATCH + "sync_profile" por el WS para que
            # la presencia recargue el perfil y lo difunda.
            client.patch("/users/me", json={"nickname": "bobby"},
                         headers={"Authorization": f"Bearer {tb}"})
            wsb.send_json({"type": "sync_profile"})
            upd = _drain_until(wsa, "presence_update")
            assert upd["user"]["display_name"] == "bobby"
            assert upd["user"]["activity"] == {"kind": "music", "text": "Pink Floyd - Time"}

            # kind inválido = limpiar
            wsb.send_json({"type": "set_activity", "kind": "hack", "text": "x"})
            upd = _drain_until(wsa, "presence_update")
            assert upd["user"]["activity"] is None


# ---------------- Voz: sharing y rtt en la presencia ----------------

def test_voice_state_sharing_and_rtt(client):
    ta = register_token(client, "alice")
    tb = register_token(client, "bob")

    with client.websocket_connect(f"/ws/presence?token={ta}") as wsa:
        wsa.receive_json()
        with client.websocket_connect(f"/ws/presence?token={tb}") as wsb:
            wsb.receive_json()
            _drain_until(wsa, "presence_update")

            wsb.send_json({"type": "voice_join", "channel_id": 5})
            _drain_until(wsa, "voice_presence")
            wsb.send_json({"type": "voice_state", "muted": False, "deafened": False,
                           "sharing": True, "rtt": 42})
            vp = _drain_until(wsa, "voice_presence")
            occ = vp["by_channel"]["5"][0]
            assert occ["sharing"] is True
            assert occ["rtt"] == 42

            # rtt casi igual y mismos flags: NO se difunde otro broadcast global
            from app.presence import presence
            before = presence.voice[occ["id"]].copy()
            wsb.send_json({"type": "voice_state", "muted": False, "deafened": False,
                           "sharing": True, "rtt": 45})
            wsb.send_json({"type": "voice_leave"})  # esto SÍ difunde (sirve de valla)
            vp = _drain_until(wsa, "voice_presence")
            assert vp["by_channel"] == {}  # lo siguiente que llegó fue el leave
            assert before["rtt"] == 42
