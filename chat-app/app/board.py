"""
Pizarra colaborativa por canal de voz.

Un tablero por canal, en memoria (igual que música/presencia: un solo worker)
con HISTORIAL en disco: cada cambio se guarda (con un pequeño debounce) en un
JSON por canal, así el dibujo sobrevive reinicios del server. Un tablero sin
actividad durante más de `TTL_DAYS` días se borra (de disco y de memoria).
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
import asyncio
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from fastapi import WebSocket

CANVAS_W, CANVAS_H = 1920, 1080
TTL_DAYS = 15           # historial: tableros sin actividad más de esto se borran
SAVE_DELAY = 3.0        # debounce de guardado a disco (segundos)


def _data_dir() -> Path:
    """Carpeta del historial (KURUG_BOARD_DIR para tests/despliegues raros)."""
    return Path(os.environ.get("KURUG_BOARD_DIR", "data/boards"))
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
        self.updated_at: float = time.time()  # última actividad (para el TTL)


class BoardManager:
    def __init__(self) -> None:
        self.boards: dict[int, Board] = defaultdict(Board)
        self.ui: dict[int, set[WebSocket]] = defaultdict(set)
        self._save_tasks: dict[int, asyncio.Task] = {}

    # ---- historial en disco ----
    def _path(self, cid: int) -> Path:
        return _data_dir() / f"{cid}.json"

    def _load(self, cid: int) -> None:
        """Carga el historial del canal si existe y no ha caducado."""
        path = self._path(cid)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        updated = float(raw.get("updated_at") or 0)
        if time.time() - updated > TTL_DAYS * 86400:
            path.unlink(missing_ok=True)
            return
        b = self.boards[cid]
        b.updated_at = updated
        for el in raw.get("elements", []):
            if not isinstance(el, dict):
                continue
            try:
                uid = int(el.get("user_id") or 0)
            except (TypeError, ValueError):
                uid = 0
            clean = _sanitize(el, uid)
            if clean is not None:
                b.elements[clean["id"]] = clean
                b.by_user[uid].append(clean["id"])

    def _write(self, cid: int) -> None:
        board = self.boards.get(cid)
        path = self._path(cid)
        if board is None or not board.elements:
            path.unlink(missing_ok=True)
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "updated_at": board.updated_at,
                "elements": list(board.elements.values()),
            }, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # sin disco no hay historial, pero la sesión en vivo sigue

    def _touch(self, cid: int) -> None:
        """Marca actividad y programa un guardado (con debounce)."""
        self.boards[cid].updated_at = time.time()
        task = self._save_tasks.get(cid)
        if task is not None and not task.done():
            return  # ya hay un guardado pendiente: escribirá el estado más nuevo
        self._save_tasks[cid] = asyncio.get_running_loop().create_task(
            self._save_soon(cid)
        )

    async def _save_soon(self, cid: int) -> None:
        try:
            await asyncio.sleep(SAVE_DELAY)
        except asyncio.CancelledError:
            return
        self._write(cid)

    async def flush(self) -> None:
        """Escribe ya lo pendiente (apagado ordenado del server)."""
        for cid, task in list(self._save_tasks.items()):
            if not task.done():
                task.cancel()
                self._write(cid)
        self._save_tasks.clear()

    def purge_stale(self) -> None:
        """Borra tableros caducados: archivos en disco y memoria sin uso."""
        cutoff = time.time() - TTL_DAYS * 86400
        try:
            files = list(_data_dir().glob("*.json"))
        except OSError:
            files = []
        for path in files:
            try:
                updated = float(json.loads(path.read_text(encoding="utf-8")).get("updated_at") or 0)
            except (OSError, ValueError):
                updated = 0
            if updated < cutoff:
                path.unlink(missing_ok=True)
        for cid in list(self.boards):
            if self.boards[cid].updated_at < cutoff and not self.ui.get(cid):
                del self.boards[cid]

    async def purge_loop(self) -> None:
        """Tarea de fondo del lifespan: purga el historial caducado a diario."""
        while True:
            try:
                self.purge_stale()
            except Exception:
                pass
            await asyncio.sleep(24 * 3600)

    # ---- suscripción ----
    async def subscribe(self, cid: int, ws: WebSocket) -> None:
        if cid not in self.boards:
            self._load(cid)  # primer uso tras un reinicio: recuperar historial
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
        self._touch(cid)
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
        self._touch(cid)
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
        self._touch(cid)
        await self._broadcast(cid, {"type": "updated", "id": el_id, "patch": clean}, exclude=exclude)

    async def remove(self, cid: int, el_id) -> None:
        """La goma es colaborativa: cualquiera puede borrar cualquier elemento."""
        board = self.boards[cid]
        if isinstance(el_id, str) and board.elements.pop(el_id, None) is not None:
            self._touch(cid)
            await self._broadcast(cid, {"type": "removed", "id": el_id})

    async def undo(self, cid: int, user_id: int) -> None:
        """Deshace el último elemento PROPIO que siga vivo."""
        board = self.boards[cid]
        stack = board.by_user.get(user_id) or []
        while stack:
            el_id = stack.pop()
            if board.elements.pop(el_id, None) is not None:
                self._touch(cid)
                await self._broadcast(cid, {"type": "removed", "id": el_id})
                return

    async def clear(self, cid: int) -> None:
        board = self.boards[cid]
        board.elements.clear()
        board.by_user.clear()
        self._touch(cid)
        await self._broadcast(cid, {"type": "cleared"})


board = BoardManager()
