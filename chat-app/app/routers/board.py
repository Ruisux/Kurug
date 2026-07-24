"""
WebSocket de la pizarra colaborativa: /ws/board/{channel_id}.

Mismo patrón de auth que la música: token por query, validación con sesión
corta y luego solo memoria (BoardManager).
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from ..database import SessionLocal
from ..models import User
from ..security import decode_token
from ..board import board
from ..gamify import grant_badge
from ..presence import presence

router = APIRouter()

# A quién ya le concedimos la insignia de pizarra en esta ejecución del server:
# evita tocar la BD en cada trazo (la pizarra emite muchísimos "add").
_pizarra_granted: set[int] = set()


async def _award_pizarra(uid: int) -> None:
    if uid in _pizarra_granted:
        return
    _pizarra_granted.add(uid)
    with SessionLocal() as db:
        u = db.get(User, uid)
        if u is not None and grant_badge(u, "pizarra"):
            db.commit()
            db.refresh(u)
            await presence.update_profile(u)


@router.websocket("/ws/board/{channel_id}")
async def board_ws(websocket: WebSocket, channel_id: int, token: str = Query(...)):
    username = decode_token(token)
    if username is None:
        await websocket.close(code=1008)
        return
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            await websocket.close(code=1008)
            return
        uid = user.id

    await websocket.accept()
    await board.subscribe(channel_id, websocket)
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
                await board.add(channel_id, uid, data.get("el"), exclude=websocket)
                await _award_pizarra(uid)  # insignia de artista de pizarra
            elif t == "points":
                await board.add_points(
                    channel_id, uid, data.get("id"), data.get("points"), exclude=websocket,
                )
            elif t == "update":
                await board.update(
                    channel_id, uid, data.get("id"), data.get("patch"), exclude=websocket,
                )
            elif t == "remove":
                await board.remove(channel_id, data.get("id"))
            elif t == "undo":
                await board.undo(channel_id, uid)
            elif t == "clear":
                await board.clear(channel_id)
    except WebSocketDisconnect:
        pass
    finally:
        board.unsubscribe(channel_id, websocket)
