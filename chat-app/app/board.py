"""
Pizarra colaborativa por canal de voz.

Un tablero por canal, EN MEMORIA (igual que música/presencia: un solo worker;
se pierde al reiniciar el server — es un lienzo de reunión, no un documento).
El servidor es la autoridad: guarda la lista de elementos, valida/clampa todo
lo que llega y lo difunde a quienes tienen la pizarra abierta.

Protocolo (WS /ws/board/{channel_id}):
- cliente→server: add {el}, points {id, points} (lotes del lápiz en vivo),
  update {id, patch}, remove {id}, undo {}, clear {}.
- server→cliente: snapshot {elements} al conectar, y added/points/updated/
  removed/cleared. En add/points/update se EXCLUYE al emisor (él ya pintó
  localmente); removed/cleared van a todos (undo no sabe qué id cayó).

Elemento: {id, user_id, kind, points, color, width, text?}
- kind: pen|line|arrow|rect|ellipse|text
- points: [[x,y], ...] en el lienzo lógico 1920×1080 (enteros)
"""
import re
from collections import defaultdict

from fastapi import WebSocket

CANVAS_W, CANVAS_H = 1920, 1080
MAX_ELEMENTS = 1000     # por canal; al superarlo caen los más viejos (FIFO)
MAX_POINTS = 2000       # por trazo de lápiz
MAX_BATCH = 200         # puntos por mensaje "points"
MAX_TEXT = 256
KINDS = {"pen", "line", "arrow", "rect", "ellipse", "text"}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")


def _clamp_points(raw, limit):
    out = []
    if not isinstance(raw, list):
        return out
    for p in raw[:limit]:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            continue
        try:
            x, y = int(p[0]), int(p[1])
        except (TypeError, ValueError):
            continue
        out.append([max(0, min(CANVAS_W, x)), max(0, min(CANVAS_H, y))])
    return out


def _sanitize(raw, user_id) -> dict | None:
    """Valida un elemento entrante; None si no es aceptable."""
    if not isinstance(raw, dict):
        return None
    el_id = raw.get("id")
    kind = raw.get("kind")
    if not isinstance(el_id, str) or not _ID_RE.match(el_id) or kind not in KINDS:
        return None
    color = raw.get("color") if isinstance(raw.get("color"), str) else ""
    if not _COLOR_RE.match(color):
        color = "#e2553b"
    try:
        width = max(1, min(32, int(raw.get("width", 4))))
    except (TypeError, ValueError):
        width = 4
    points = _clamp_points(raw.get("points"), MAX_POINTS)
    if not points:
        return None
    el = {"id": el_id, "user_id": user_id, "kind": kind, "points": points,
          "color": color, "width": width}
    if kind == "text":
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        el["text"] = text.strip()[:MAX_TEXT]
    return el


class Board:
    def __init__(self) -> None:
        self.elements: dict[str, dict] = {}  # dict = orden de llegada (para pintar)
        self.by_user: dict[int, list[str]] = defaultdict(list)  # pila para undo


class BoardManager:
    def __init__(self) -> None:
        self.boards: dict[int, Board] = defaultdict(Board)
        self.ui: dict[int, set[WebSocket]] = defaultdict(set)

    # ---- suscripción ----
    async def subscribe(self, cid: int, ws: WebSocket) -> None:
        self.ui[cid].add(ws)
        await ws.send_json({
            "type": "snapshot",
            "elements": list(self.boards[cid].elements.values()),
        })

    def unsubscribe(self, cid: int, ws: WebSocket) -> None:
        self.ui[cid].discard(ws)

    async def _broadcast(self, cid: int, msg: dict, exclude: WebSocket | None = None) -> None:
        for ws in list(self.ui.get(cid, set())):
            if ws is exclude:
                continue
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    # ---- operaciones ----
    async def add(self, cid: int, user_id: int, raw, exclude: WebSocket) -> None:
        el = _sanitize(raw, user_id)
        board = self.boards[cid]
        if el is None or el["id"] in board.elements:
            return
        board.elements[el["id"]] = el
        board.by_user[user_id].append(el["id"])
        await self._broadcast(cid, {"type": "added", "el": el}, exclude=exclude)
        # Tope FIFO: caen los elementos más viejos (el tablero sigue usable).
        while len(board.elements) > MAX_ELEMENTS:
            old_id = next(iter(board.elements))
            board.elements.pop(old_id)
            await self._broadcast(cid, {"type": "removed", "id": old_id})

    async def add_points(self, cid: int, user_id: int, el_id, raw_points, exclude: WebSocket) -> None:
        board = self.boards[cid]
        el = board.elements.get(el_id) if isinstance(el_id, str) else None
        if el is None or el["user_id"] != user_id or el["kind"] != "pen":
            return
        room_left = MAX_POINTS - len(el["points"])
        pts = _clamp_points(raw_points, min(MAX_BATCH, max(0, room_left)))
        if not pts:
            return
        el["points"].extend(pts)
        await self._broadcast(cid, {"type": "points", "id": el_id, "points": pts}, exclude=exclude)

    async def update(self, cid: int, user_id: int, el_id, patch, exclude: WebSocket) -> None:
        """Editar lo PROPIO (hoy: el texto de un elemento de texto)."""
        board = self.boards[cid]
        el = board.elements.get(el_id) if isinstance(el_id, str) else None
        if el is None or el["user_id"] != user_id or not isinstance(patch, dict):
            return
        clean = {}
        if el["kind"] == "text" and isinstance(patch.get("text"), str) and patch["text"].strip():
            clean["text"] = patch["text"].strip()[:MAX_TEXT]
        if isinstance(patch.get("points"), list):
            pts = _clamp_points(patch["points"], 2)
            if pts:
                clean["points"] = pts
        if not clean:
            return
        el.update(clean)
        await self._broadcast(cid, {"type": "updated", "id": el_id, "patch": clean}, exclude=exclude)

    async def remove(self, cid: int, el_id) -> None:
        """La goma es colaborativa: cualquiera puede borrar cualquier elemento."""
        board = self.boards[cid]
        if isinstance(el_id, str) and board.elements.pop(el_id, None) is not None:
            await self._broadcast(cid, {"type": "removed", "id": el_id})

    async def undo(self, cid: int, user_id: int) -> None:
        """Deshace el último elemento PROPIO que siga vivo."""
        board = self.boards[cid]
        stack = board.by_user.get(user_id) or []
        while stack:
            el_id = stack.pop()
            if board.elements.pop(el_id, None) is not None:
                await self._broadcast(cid, {"type": "removed", "id": el_id})
                return

    async def clear(self, cid: int) -> None:
        board = self.boards[cid]
        board.elements.clear()
        board.by_user.clear()
        await self._broadcast(cid, {"type": "cleared"})


board = BoardManager()
