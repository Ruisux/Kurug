"""
Tests de mensajes directos (DMs), roles/permisos y propagación de perfil.
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


def reg_login(client, username, password="secret123"):
    token = register_token(client, username, password)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/users/me", headers=headers).json()
    return token, headers, me


def recv_until(ws, type_, tries=6):
    for _ in range(tries):
        msg = ws.receive_json()
        if msg.get("type") == type_:
            return msg
    raise AssertionError(f"no llegó un mensaje de tipo {type_}")


# ---------- Roles ----------

def test_first_user_is_admin(client):
    _, _, alice = reg_login(client, "alice")
    _, _, bob = reg_login(client, "bob")
    assert alice["is_admin"] is True
    assert bob["is_admin"] is False


def test_delete_channel_permissions(client):
    _, ha, _ = reg_login(client, "alice")   # admin
    _, hb, _ = reg_login(client, "bob")     # no admin
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]

    assert client.delete(f"/channels/{cid}", headers=hb).status_code == 403
    assert client.delete(f"/channels/{cid}", headers=ha).status_code == 204
    assert "general" not in [c["name"] for c in client.get("/channels", headers=ha).json()]


def test_message_delete_via_ws(client):
    ta, ha, _ = reg_login(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    with client.websocket_connect(f"/ws/{cid}?token={ta}") as ws:
        ws.send_json({"content": "borrame"})
        m = recv_until(ws, "message")
        ws.send_json({"type": "delete", "id": m["id"]})
        d = recv_until(ws, "deleted")
        assert d["id"] == m["id"]
    assert client.get(f"/channels/{cid}/messages", headers=ha).json() == []


def test_message_edit_and_reply(client):
    ta, ha, _ = reg_login(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    with client.websocket_connect(f"/ws/{cid}?token={ta}") as ws:
        ws.send_json({"content": "original"})
        m1 = recv_until(ws, "message")
        # editar
        ws.send_json({"type": "edit", "id": m1["id"], "content": "corregido"})
        ed = recv_until(ws, "edited")
        assert ed["id"] == m1["id"] and ed["content"] == "corregido"
        # responder citando el primero
        ws.send_json({"content": "te respondo", "reply_to": m1["id"]})
        m2 = recv_until(ws, "message")
        assert m2["reply_to"]["id"] == m1["id"]
        assert m2["reply_to"]["content"] == "corregido"  # cita refleja la edición

    # el historial conserva edición y cita
    hist = client.get(f"/channels/{cid}/messages", headers=ha).json()
    assert hist[0]["edited_at"] is not None
    assert hist[1]["reply_to"]["id"] == hist[0]["id"]


def _tiny_png():
    """Devuelve los bytes de un PNG mínimo (2x2) generado con Pillow."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_image_upload_and_message(client):
    ta, ha, _ = reg_login(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]

    # subir una imagen -> devuelve una URL en /static/uploads
    r = client.post(
        "/uploads/image",
        files={"file": ("foto.png", _tiny_png(), "image/png")},
        headers=ha,
    )
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("/static/uploads/")

    # un archivo que no es imagen se rechaza
    bad = client.post(
        "/uploads/image",
        files={"file": ("x.txt", b"no soy imagen", "text/plain")},
        headers=ha,
    )
    assert bad.status_code == 400

    # mensaje SOLO con imagen (sin texto) se acepta y se difunde con image_url
    with client.websocket_connect(f"/ws/{cid}?token={ta}") as ws:
        ws.send_json({"content": "", "image_url": url})
        m = recv_until(ws, "message")
        assert m["image_url"] == url
        # una image_url que no es nuestra se ignora (queda None)
        ws.send_json({"content": "hola", "image_url": "http://evil/x.png"})
        m2 = recv_until(ws, "message")
        assert m2["image_url"] is None

    hist = client.get(f"/channels/{cid}/messages", headers=ha).json()
    assert hist[0]["image_url"] == url


def test_unread_counts(client):
    ta, ha, _ = reg_login(client, "alice")
    tb, hb, _ = reg_login(client, "bob")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]

    ids = []
    with client.websocket_connect(f"/ws/{cid}?token={tb}") as ws:
        for txt in ["uno", "dos", "tres"]:
            ws.send_json({"content": txt})
            ids.append(recv_until(ws, "message")["id"])

    # alice no ha leído nada -> 3 no leídos (todos de bob)
    r = client.post("/channels/unread", json={"last_read": {}}, headers=ha).json()
    assert r[str(cid)] == 3

    # si alice ya leyó hasta el 2º, quedan 1
    r2 = client.post("/channels/unread", json={"last_read": {str(cid): ids[1]}}, headers=ha).json()
    assert r2[str(cid)] == 1

    # los mensajes propios no cuentan: para bob, 0 no leídos
    r3 = client.post("/channels/unread", json={"last_read": {}}, headers=hb).json()
    assert str(cid) not in r3


def test_channel_search(client):
    ta, ha, _ = reg_login(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    with client.websocket_connect(f"/ws/{cid}?token={ta}") as ws:
        for txt in ["hola mundo", "otra cosa", "el MUNDO es grande"]:
            ws.send_json({"content": txt})
            recv_until(ws, "message")

    res = client.get(f"/channels/{cid}/search", params={"q": "mundo"}, headers=ha).json()
    contents = [m["content"] for m in res]
    assert "hola mundo" in contents
    assert "el MUNDO es grande" in contents  # case-insensitive
    assert "otra cosa" not in contents
    # consulta vacía -> sin resultados
    assert client.get(f"/channels/{cid}/search", params={"q": "  "}, headers=ha).json() == []


def test_dm_search(client):
    ta, ha, alice = reg_login(client, "alice")
    tb, hb, bob = reg_login(client, "bob")
    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()
        with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
            wb.receive_json()
            for txt in ["nos vemos el viernes", "vale", "viernes a las 8"]:
                wa.send_json({"type": "dm", "to": bob["id"], "content": txt})
                recv_until(wa, "dm")

    res = client.get(f"/dms/{alice['id']}/search", params={"q": "viernes"}, headers=hb).json()
    contents = [m["content"] for m in res]
    assert "nos vemos el viernes" in contents
    assert "viernes a las 8" in contents
    assert "vale" not in contents


def test_reactions_toggle(client):
    ta, ha, _ = reg_login(client, "alice")
    cid = client.post("/channels", json={"name": "general"}, headers=ha).json()["id"]
    with client.websocket_connect(f"/ws/{cid}?token={ta}") as ws:
        ws.send_json({"content": "reacciona"})
        m = recv_until(ws, "message")
        ws.send_json({"type": "react", "id": m["id"], "emoji": "👍"})
        r = recv_until(ws, "reactions")
        assert r["reactions"][0]["emoji"] == "👍" and r["reactions"][0]["count"] == 1
        # toggle: misma reacción otra vez -> se quita
        ws.send_json({"type": "react", "id": m["id"], "emoji": "👍"})
        r2 = recv_until(ws, "reactions")
        assert r2["reactions"] == []


# ---------- DMs ----------

def test_dm_send_history_conversations(client):
    ta, ha, alice = reg_login(client, "alice")
    tb, hb, bob = reg_login(client, "bob")

    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()  # snapshot
        with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
            wb.receive_json()  # snapshot
            wa.send_json({"type": "dm", "to": bob["id"], "content": "hola bob"})
            # ambos reciben el DM
            ma = recv_until(wa, "dm")
            mb = recv_until(wb, "dm")
            assert ma["message"]["content"] == "hola bob"
            assert mb["message"]["sender_display_name"] == "alice"

    # historial (ambos sentidos) y lista de conversaciones
    hist = client.get(f"/dms/{bob['id']}", headers=ha).json()
    assert [m["content"] for m in hist] == ["hola bob"]
    convs = client.get("/dms/conversations", headers=hb).json()
    assert convs[0]["user"]["username"] == "alice"


def test_dm_reply(client):
    ta, ha, alice = reg_login(client, "alice")
    tb, hb, bob = reg_login(client, "bob")
    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()  # snapshot
        with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
            wb.receive_json()
            wa.send_json({"type": "dm", "to": bob["id"], "content": "primero"})
            m1 = recv_until(wa, "dm")
            fid = m1["message"]["id"]
            wa.send_json({"type": "dm", "to": bob["id"], "content": "te cito", "reply_to": fid})
            m2 = recv_until(wa, "dm")
            assert m2["message"]["reply_to"]["id"] == fid
            assert m2["message"]["reply_to"]["content"] == "primero"

    hist = client.get(f"/dms/{bob['id']}", headers=ha).json()
    assert hist[1]["reply_to"]["id"] == hist[0]["id"]


def test_dm_parity_edit_react_pin_delete(client):
    ta, ha, alice = reg_login(client, "alice")
    tb, hb, bob = reg_login(client, "bob")
    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()
        with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
            wb.receive_json()
            wa.send_json({"type": "dm", "to": bob["id"], "content": "hola"})
            mid = recv_until(wa, "dm")["message"]["id"]
            recv_until(wb, "dm")

            # Editar (autor) -> ambos reciben dm_edited
            wa.send_json({"type": "dm_edit", "id": mid, "content": "editado"})
            assert recv_until(wa, "dm_edited")["content"] == "editado"
            assert recv_until(wb, "dm_edited")["content"] == "editado"

            # Reaccionar (el receptor) -> ambos reciben dm_reactions
            wb.send_json({"type": "dm_react", "id": mid, "emoji": "🔥"})
            ra = recv_until(wa, "dm_reactions")
            assert ra["reactions"][0]["emoji"] == "🔥" and bob["id"] in ra["reactions"][0]["users"]
            recv_until(wb, "dm_reactions")

            # Fijar -> ambos reciben dm_pinned con fecha
            wa.send_json({"type": "dm_pin", "id": mid})
            assert recv_until(wa, "dm_pinned")["pinned_at"] is not None
            recv_until(wb, "dm_pinned")

    # El endpoint de fijados lo devuelve
    pins = client.get(f"/dms/{bob['id']}/pins", headers=ha).json()
    assert [p["id"] for p in pins] == [mid]

    # Borrar (autor) y comprobar que desaparece del historial
    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()
        wa.send_json({"type": "dm_delete", "id": mid})
        assert recv_until(wa, "dm_deleted")["id"] == mid
    assert client.get(f"/dms/{bob['id']}", headers=ha).json() == []


def test_dm_delete_only_author(client):
    ta, ha, alice = reg_login(client, "alice")
    tb, hb, bob = reg_login(client, "bob")
    with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
        wa.receive_json()
        wa.send_json({"type": "dm", "to": bob["id"], "content": "mío"})
        mid = recv_until(wa, "dm")["message"]["id"]
    # bob (no autor) intenta borrar -> se ignora, sigue en el historial
    with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
        wb.receive_json()
        wb.send_json({"type": "dm_delete", "id": mid})
    assert len(client.get(f"/dms/{bob['id']}", headers=ha).json()) == 1


def test_dm_history_unknown_user(client):
    _, ha, _ = reg_login(client, "alice")
    assert client.get("/dms/999", headers=ha).status_code == 404


# ---------- Propagación de perfil ----------

def test_sync_profile_propagates(client):
    ta, ha, _ = reg_login(client, "alice")
    tb, hb, _ = reg_login(client, "bob")

    with client.websocket_connect(f"/ws/presence?token={tb}") as wb:
        wb.receive_json()  # snapshot
        with client.websocket_connect(f"/ws/presence?token={ta}") as wa:
            wa.receive_json()  # snapshot
            wb.receive_json()  # bob ve entrar a alice (presence_update)
            # alice cambia su nickname por REST y avisa por el socket
            client.patch("/users/me", json={"nickname": "Alicia"}, headers=ha)
            wa.send_json({"type": "sync_profile"})
            evt = recv_until(wb, "presence_update")
            assert evt["user"]["display_name"] == "Alicia"
