"""
WebSockets de la sala de música.

- /ws/music/{channel_id}      → clientes (UI): reciben estado, mandan comandos.
- /ws/music-bot/{channel_id}  → el bot: recibe órdenes de reproducción, emite
                                eventos (ended/progress). Solo el usuario bot.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from ..database import SessionLocal
from ..models import User
from ..security import decode_token
from ..config import settings
from ..music import music
from ..music_resolve import plan, search_youtube

router = APIRouter()

# Cuántas búsquedas de YouTube a la vez al vaciar una playlist de Spotify/Apple.
_CHUNK = 4


async def _add_remaining(channel_id: int, items: list[dict], source: str, user) -> None:
    """Resuelve en segundo plano el resto de una playlist de Spotify/Apple.

    Por lotes: la cola va creciendo en vivo (cada add difunde el estado) sin
    esperar a que estén las N canciones. Los fallos individuales se saltan.
    """
    loop = asyncio.get_event_loop()
    for i in range(0, len(items), _CHUNK):
        chunk = items[i : i + _CHUNK]
        results = await asyncio.gather(
            *[
                loop.run_in_executor(None, search_youtube, it["q"], source, it["title"], it.get("duration"))
                for it in chunk
            ],
            return_exceptions=True,
        )
        tracks = [t for t in results if isinstance(t, dict)]
        if tracks:
            await music.add(channel_id, tracks, user)


async def _handle_add(channel_id: int, query: str, user, websocket: WebSocket) -> None:
    loop = asyncio.get_event_loop()
    # Aviso inmediato: la UI muestra "buscando…" mientras se resuelve.
    await websocket.send_json({"type": "adding"})
    p = await loop.run_in_executor(None, plan, query)

    if p["kind"] == "tracks":
        if p["tracks"]:
            await music.add(channel_id, p["tracks"], user)
        else:
            await websocket.send_json({"type": "error", "message": "No encontré nada para eso."})
        return

    # Spotify/Apple: buscar cada pista en YouTube. La PRIMERA se resuelve ya
    # (que la música arranque); el resto se añade solo, en segundo plano.
    items, source = p["items"], p["source"]
    if not items:
        await websocket.send_json({"type": "error", "message": "No pude leer ese enlace. ¿Es público?"})
        return
    first = await loop.run_in_executor(
        None, search_youtube, items[0]["q"], source, items[0]["title"], items[0].get("duration")
    )
    if first:
        await music.add(channel_id, [first], user)
    rest = items[1:]
    if rest:
        await websocket.send_json(
            {"type": "info", "message": f"Añadiendo {len(rest)} canciones más de la lista…"}
        )
        asyncio.create_task(_add_remaining(channel_id, rest, source, user))
    elif not first:
        await websocket.send_json({"type": "error", "message": "No encontré esa canción en YouTube."})


@router.websocket("/ws/music/{channel_id}")
async def music_ui_ws(websocket: WebSocket, channel_id: int, token: str = Query(...)):
    username = decode_token(token)
    if username is None:
        await websocket.close(code=1008)
        return
    # Sesión corta solo para validar; no se retiene durante la espera de mensajes.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            await websocket.close(code=1008)
            return
    await websocket.accept()
    await music.subscribe(channel_id, websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            t = data.get("type")
            if t == "add":
                query = (data.get("query") or "").strip()
                if not query:
                    continue
                await _handle_add(channel_id, query, user, websocket)
            elif t == "toggle":
                await music.toggle_play(channel_id)
            elif t == "skip":
                await music.skip(channel_id)
            elif t == "prev":
                await music.prev(channel_id)
            elif t == "jump":
                i = data.get("index")
                if isinstance(i, int):
                    await music.jump(channel_id, i)
            elif t == "remove":
                iid = data.get("id")
                if isinstance(iid, str):
                    await music.remove(channel_id, iid)
            elif t == "loop":
                await music.set_loop(channel_id, data.get("mode"))
            elif t == "shuffle":
                await music.set_shuffle(channel_id, bool(data.get("on")))
    except WebSocketDisconnect:
        pass
    finally:
        music.unsubscribe(channel_id, websocket)


@router.websocket("/ws/music-bot/{channel_id}")
async def music_bot_ws(websocket: WebSocket, channel_id: int, token: str = Query(...)):
    username = decode_token(token)
    if username != settings.bot_username:
        await websocket.close(code=1008)  # solo el bot
        return
    await websocket.accept()
    await music.set_bot(channel_id, websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            t = data.get("type")
            if t == "ended":
                await music.on_ended(channel_id)
            elif t == "progress":
                pos = data.get("position")
                dur = data.get("duration")
                if isinstance(pos, (int, float)):
                    await music.on_progress(
                        channel_id, float(pos),
                        float(dur) if isinstance(dur, (int, float)) else None,
                    )
    except WebSocketDisconnect:
        pass
    finally:
        await music.clear_bot(channel_id, websocket)
