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
from ..music_resolve import resolve

router = APIRouter()


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
                # yt-dlp es bloqueante: fuera del event loop.
                tracks = await asyncio.get_event_loop().run_in_executor(None, resolve, query)
                if tracks:
                    await music.add(channel_id, tracks, user)
                else:
                    await websocket.send_json({"type": "error", "message": "No encontré nada para eso."})
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
                if isinstance(pos, (int, float)):
                    await music.on_progress(channel_id, float(pos))
    except WebSocketDisconnect:
        pass
    finally:
        music.clear_bot(channel_id, websocket)
