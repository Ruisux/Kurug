"""
Sala de música: cola y estado de reproducción por canal.

El servidor es la AUTORIDAD de la cola y el estado (qué suena, play/pausa,
loop, aleatorio). El bot es el reproductor real: el servidor le dice "reproduce
este video_id" y el bot avisa cuando termina (`ended`) o informa progreso.

Dos tipos de cliente por canal:
- UI (navegadores): reciben el estado y mandan comandos (add/skip/…).
- bot: recibe comandos de reproducción y emite eventos.

En memoria, un solo worker (como el resto de managers).
"""
import random
import uuid
from collections import defaultdict

from fastapi import WebSocket

from .presence import presence

LOOPS = ("off", "one", "all")


class Room:
    def __init__(self) -> None:
        self.queue: list[dict] = []
        self.current: int | None = None
        self.playing: bool = False
        self.loop: str = "off"
        self.shuffle: bool = False
        self.position: float = 0.0
        # Canciones ya reproducidas (consumidas de la cola), para "anterior".
        self.history: list[dict] = []
        # Canal de VOZ donde debe sonar (el del último que pidió una canción).
        # None = aún sin destino; el bot no publica hasta que haya uno.
        self.voice_cid: int | None = None

    def state(self) -> dict:
        return {
            "type": "state",
            "queue": self.queue,
            "current": self.current,
            "playing": self.playing,
            "loop": self.loop,
            "shuffle": self.shuffle,
            "position": self.position,
        }

    def current_track(self) -> dict | None:
        if self.current is None or not (0 <= self.current < len(self.queue)):
            return None
        return self.queue[self.current]


class MusicManager:
    def __init__(self) -> None:
        self.rooms: dict[int, Room] = defaultdict(Room)
        self.ui: dict[int, set[WebSocket]] = defaultdict(set)
        self.bot: dict[int, WebSocket] = {}

    # ---- suscripciones ----
    def _state(self, channel_id: int) -> dict:
        """Estado + si el bot está conectado (la UI avisa si no lo está)."""
        return {**self.rooms[channel_id].state(), "bot_online": channel_id in self.bot}

    async def subscribe(self, channel_id: int, ws: WebSocket) -> None:
        self.ui[channel_id].add(ws)
        await ws.send_json(self._state(channel_id))

    def unsubscribe(self, channel_id: int, ws: WebSocket) -> None:
        self.ui[channel_id].discard(ws)

    async def set_bot(self, channel_id: int, ws: WebSocket) -> None:
        self.bot[channel_id] = ws
        # Si ya había algo sonando, decirle al bot que retome.
        room = self.rooms[channel_id]
        track = room.current_track()
        if track and room.playing:
            await self._play_current(channel_id)
        await self._broadcast(channel_id)  # la UI quita el aviso de "bot fuera"

    async def clear_bot(self, channel_id: int, ws: WebSocket) -> None:
        if self.bot.get(channel_id) is ws:
            self.bot.pop(channel_id, None)
            await self._broadcast(channel_id)  # la UI avisa de que el bot cayó

    # ---- comandos desde la UI ----
    async def add(self, channel_id: int, tracks: list[dict], user) -> None:
        room = self.rooms[channel_id]
        # La música suena en el canal de VOZ de quien pide la canción. Si no está
        # en ninguna voz, se mantiene el destino anterior (si lo hay).
        # presence.voice guarda un dict {"cid", "muted", "deafened"} desde que
        # la presencia lleva el estado del micro; aquí solo interesa el canal.
        v = presence.voice.get(user.id)
        target = v["cid"] if v else None
        if target is not None:
            room.voice_cid = target
        for t in tracks:
            room.queue.append({
                "id": uuid.uuid4().hex,
                "video_id": t["video_id"],
                "title": t["title"],
                "thumbnail": t.get("thumbnail"),
                "duration": t.get("duration"),
                "source": t.get("source", "youtube"),
                "added_by": user.display_name,
                "added_by_id": user.id,
            })
        if room.current is None and room.queue:
            room.current = 0
            room.playing = True
            await self._play_current(channel_id)
        await self._broadcast(channel_id)

    async def toggle_play(self, channel_id: int) -> None:
        room = self.rooms[channel_id]
        if room.current_track() is None:
            return
        room.playing = not room.playing
        await self._send_bot(channel_id, {"type": "resume" if room.playing else "pause"})
        await self._broadcast(channel_id)

    async def skip(self, channel_id: int) -> None:
        await self._advance(channel_id, auto=False)

    async def prev(self, channel_id: int) -> None:
        """Vuelve a la canción anterior usando el historial. Si no hay, reinicia
        la actual."""
        room = self.rooms[channel_id]
        if room.history:
            prev_track = room.history.pop()
            at = room.current if room.current is not None else 0
            room.queue.insert(at, prev_track)  # la actual queda justo detrás
            room.current = at
            room.playing = True
            await self._play_current(channel_id)
            await self._broadcast(channel_id)
        elif room.current is not None:
            room.playing = True
            await self._play_current(channel_id)
            await self._broadcast(channel_id)

    async def jump(self, channel_id: int, index: int) -> None:
        room = self.rooms[channel_id]
        if not (0 <= index < len(room.queue)):
            return
        # Cambiar de canción consume la que estaba sonando.
        if room.current is not None and room.current != index:
            self._push_history(room, room.queue.pop(room.current))
            if room.current < index:
                index -= 1
        room.current = index
        room.playing = True
        await self._play_current(channel_id)
        await self._broadcast(channel_id)

    async def remove(self, channel_id: int, item_id: str) -> None:
        room = self.rooms[channel_id]
        idx = next((i for i, t in enumerate(room.queue) if t["id"] == item_id), None)
        if idx is None:
            return
        removing_current = idx == room.current
        room.queue.pop(idx)
        if not room.queue:
            room.current = None
            room.playing = False
            await self._send_bot(channel_id, {"type": "stop"})
        elif removing_current:
            room.current = min(idx, len(room.queue) - 1)
            await self._play_current(channel_id)
        elif room.current is not None and idx < room.current:
            room.current -= 1
        await self._broadcast(channel_id)

    async def set_loop(self, channel_id: int, mode: str) -> None:
        if mode in LOOPS:
            self.rooms[channel_id].loop = mode
            await self._broadcast(channel_id)

    async def set_shuffle(self, channel_id: int, on: bool) -> None:
        self.rooms[channel_id].shuffle = bool(on)
        await self._broadcast(channel_id)

    # ---- eventos del bot ----
    async def on_ended(self, channel_id: int) -> None:
        await self._advance(channel_id, auto=True)

    async def on_progress(self, channel_id: int, position: float, duration=None) -> None:
        room = self.rooms[channel_id]
        room.position = position
        # El bot conoce la duración REAL (yt-dlp): rellena la que falte — las
        # entradas de playlist llegan sin duración y la barra no avanzaba.
        track = room.current_track()
        if track is not None and duration and not track.get("duration"):
            track["duration"] = duration
        await self._broadcast(channel_id)

    # ---- internos ----
    def _push_history(self, room: "Room", track: dict) -> None:
        room.history.append(track)
        if len(room.history) > 50:
            room.history.pop(0)

    async def _advance(self, channel_id: int, auto: bool) -> None:
        room = self.rooms[channel_id]
        if room.current is None or not room.queue:
            return

        # loop "one" (solo automático): repetir la misma sin consumir.
        if auto and room.loop == "one":
            room.playing = True
            await self._play_current(channel_id)
            await self._broadcast(channel_id)
            return

        # Cambiar de canción: la anterior sale de la cola.
        idx = room.current
        finished = room.queue.pop(idx)
        if room.loop == "all":
            room.queue.append(finished)  # con loop de cola, vuelve al final
        else:
            self._push_history(room, finished)  # para "anterior"

        if not room.queue:
            room.current = None
            room.playing = False
            await self._send_bot(channel_id, {"type": "stop"})
            await self._broadcast(channel_id)
            return

        if room.shuffle:
            room.current = random.randrange(len(room.queue))
        else:
            room.current = idx % len(room.queue)  # la siguiente ocupó el hueco
        room.playing = True
        await self._play_current(channel_id)
        await self._broadcast(channel_id)

    def _peek_next(self, room: "Room") -> str | None:
        """video_id de la que sonaría con 'siguiente' (sin aleatorio)."""
        if room.shuffle or room.current is None or len(room.queue) < 2:
            return None
        nxt = room.queue[(room.current + 1) % len(room.queue)]
        return nxt.get("video_id")

    async def _play_current(self, channel_id: int) -> None:
        room = self.rooms[channel_id]
        track = room.current_track()
        if track is None:
            return
        room.position = 0.0
        # Decirle al bot en qué sala de voz debe publicar (la de quien pidió).
        if room.voice_cid is not None:
            await self._send_bot(channel_id, {"type": "room", "voice_cid": room.voice_cid})
        await self._send_bot(channel_id, {
            "type": "play",
            "video_id": track["video_id"],
            "position": 0,
        })
        # Pre-resolver la siguiente para que "siguiente" sea casi instantáneo.
        nxt = self._peek_next(room)
        if nxt:
            await self._send_bot(channel_id, {"type": "prefetch", "video_id": nxt})

    async def _send_bot(self, channel_id: int, msg: dict) -> None:
        ws = self.bot.get(channel_id)
        if ws is not None:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    async def _broadcast(self, channel_id: int) -> None:
        state = self._state(channel_id)
        for ws in list(self.ui.get(channel_id, set())):
            try:
                await ws.send_json(state)
            except Exception:
                pass


music = MusicManager()
