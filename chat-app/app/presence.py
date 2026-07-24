"""
Gestor de presencia: quién está conectado y con qué estado.

A diferencia del `ConnectionManager` (que agrupa sockets por canal para el chat),
la presencia es GLOBAL: alimenta el panel de "conectados" de la derecha, que es
el mismo sin importar el canal que estés viendo.

Reglas:
- Un usuario puede tener varias conexiones a la vez (web + escritorio). Está
  "conectado" mientras tenga al menos un socket abierto.
- El estado `invisible` hace que el usuario aparezca como desconectado para los
  demás, aunque tenga sockets abiertos.

OJO: vive en memoria, igual que el ConnectionManager. Un solo worker (ver
CLAUDE.md). Para varias instancias haría falta Redis Pub/Sub.
"""
from collections import defaultdict

from fastapi import WebSocket

# Estados válidos (debe coincidir con StatusLiteral en schemas.py).
VALID_STATUSES = {"online", "away", "dnd", "invisible"}


def _info_from_user(user) -> dict:
    from .gamify import level_from_xp, parse_badges
    lv = level_from_xp(getattr(user, "xp", 0) or 0)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "banner_url": getattr(user, "banner_url", None),
        "status": user.status,
        "custom_status": user.custom_status,
        "accent_color": user.accent_color,
        # Personalización: rango, nivel e insignias (para teñir el nombre en el
        # chat y las mini-tarjetas; el detalle completo lo trae GET /users/{id}).
        "rank": getattr(user, "rank", None),
        "level": lv["level"],
        "badges": parse_badges(getattr(user, "badges", "[]")),
        # Actividad ("jugando X" / "escuchando Y"): NO está en la BD (la manda
        # la app de escritorio en vivo); connect/update_profile la PRESERVAN.
        "activity": None,
    }


def _is_visible(info: dict) -> bool:
    return info.get("status") != "invisible"


class PresenceManager:
    def __init__(self) -> None:
        self.sockets: dict[int, set[WebSocket]] = defaultdict(set)
        self.info: dict[int, dict] = {}
        # user_id -> {"cid", "muted", "deafened", "sharing", "rtt"} de la sala
        # de voz donde está. Sirve para mostrar "quién está en cada canal de
        # voz" (su micro, si comparte pantalla y su ping) ANTES de entrar.
        self.voice: dict[int, dict] = {}

    def voice_map(self) -> dict[int, list[dict]]:
        """channel_id -> lista de ocupantes (visibles) de esa sala de voz."""
        out: dict[int, list[dict]] = {}
        for uid, v in self.voice.items():
            info = self.info.get(uid)
            if not info or not _is_visible(info):
                continue  # los invisibles no aparecen tampoco en la voz
            out.setdefault(v["cid"], []).append({
                "id": uid,
                "display_name": info["display_name"],
                "avatar_url": info["avatar_url"],
                "muted": v.get("muted", False),
                "deafened": v.get("deafened", False),
                "sharing": v.get("sharing", False),
                "rtt": v.get("rtt"),
            })
        return out

    def _voice_message(self) -> dict:
        return {"type": "voice_presence", "by_channel": self.voice_map()}

    async def set_voice(self, user_id: int, channel_id: int | None) -> None:
        """Marca en qué sala de voz está un usuario (o None si salió) y difunde."""
        if channel_id is None:
            if self.voice.pop(user_id, None) is None:
                return  # no estaba en voz: nada que difundir
        else:
            cur = self.voice.get(user_id)
            if cur is not None and cur["cid"] == channel_id:
                return  # sin cambios
            self.voice[user_id] = {
                "cid": channel_id, "muted": False, "deafened": False,
                "sharing": False, "rtt": None,
            }
        await self._broadcast(self._voice_message())

    async def set_voice_state(
        self, user_id: int, muted: bool, deafened: bool,
        sharing: bool = False, rtt: int | None = None,
    ) -> None:
        """Actualiza micro/auriculares/compartir/ping de alguien en voz y difunde."""
        v = self.voice.get(user_id)
        if v is None:
            return
        same_flags = (
            v.get("muted") == muted
            and v.get("deafened") == deafened
            and v.get("sharing") == sharing
        )
        old_rtt = v.get("rtt")
        v["muted"] = muted
        v["deafened"] = deafened
        v["sharing"] = sharing
        if rtt is not None:
            v["rtt"] = rtt
        # El ping llega cada pocos segundos: si solo se movió un poco (<15 ms)
        # y los flags no cambiaron, no vale la pena un broadcast global.
        rtt_similar = rtt is None or (old_rtt is not None and abs(rtt - old_rtt) < 15)
        if same_flags and rtt_similar:
            return
        await self._broadcast(self._voice_message())

    def online_users(self) -> list[dict]:
        """Usuarios visibles con al menos una conexión (para el panel)."""
        return [
            info
            for uid, info in self.info.items()
            if self.sockets.get(uid) and _is_visible(info)
        ]

    async def connect(self, user, ws: WebSocket) -> None:
        await ws.accept()
        first_connection = not self.sockets.get(user.id)
        self.sockets[user.id].add(ws)
        prev = self.info.get(user.id)
        self.info[user.id] = _info_from_user(user)
        if prev is not None:  # otra conexión ya había publicado actividad
            self.info[user.id]["activity"] = prev.get("activity")

        # El recién llegado recibe la foto actual de quién está conectado y de
        # quién ocupa cada sala de voz (todo en el mismo snapshot).
        await ws.send_json({
            "type": "presence_snapshot",
            "users": self.online_users(),
            "voice": self.voice_map(),
        })

        # Y, si pasa a estar visible, se anuncia a los demás.
        if first_connection and _is_visible(self.info[user.id]):
            await self._broadcast(
                {"type": "presence_update", "user": self.info[user.id]},
                exclude=ws,
            )

    async def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self.sockets[user_id].discard(ws)
        if self.sockets[user_id]:
            return  # le quedan otras conexiones abiertas
        self.sockets.pop(user_id, None)
        info = self.info.pop(user_id, None)
        in_voice = self.voice.pop(user_id, None) is not None
        if info is not None and _is_visible(info):
            await self._broadcast({"type": "presence_offline", "user_id": user_id})
        if in_voice:
            await self._broadcast(self._voice_message())

    async def set_status(self, user_id: int, status: str, custom_status=...) -> None:
        """Actualiza estado/custom_status y difunde el cambio en vivo."""
        info = self.info.get(user_id)
        if info is None:
            return
        was_visible = _is_visible(info)
        info["status"] = status
        if custom_status is not ...:
            info["custom_status"] = custom_status
        now_visible = _is_visible(info)

        if now_visible:
            # Aparece o cambia de estado.
            await self._broadcast({"type": "presence_update", "user": info})
        elif was_visible:
            # Pasó a invisible: para los demás es como desconectarse.
            await self._broadcast({"type": "presence_offline", "user_id": user_id})
        # Si estaba en voz y cambió su visibilidad, refrescar el mapa de voz.
        if was_visible != now_visible and user_id in self.voice:
            await self._broadcast(self._voice_message())

    async def update_profile(self, user) -> None:
        """Refresca el perfil cacheado (nickname/avatar/color/estado…) y lo difunde."""
        if user.id not in self.info:
            return
        was_visible = _is_visible(self.info[user.id])
        activity = self.info[user.id].get("activity")  # no vive en la BD: preservar
        self.info[user.id] = _info_from_user(user)
        self.info[user.id]["activity"] = activity
        now_visible = _is_visible(self.info[user.id])

        if now_visible:
            await self._broadcast({"type": "presence_update", "user": self.info[user.id]})
        elif was_visible:
            await self._broadcast({"type": "presence_offline", "user_id": user.id})
        if was_visible != now_visible and user.id in self.voice:
            await self._broadcast(self._voice_message())

    async def set_activity(self, user_id: int, activity: dict | None) -> None:
        """Actividad automática (jugando/escuchando) de la app de escritorio."""
        info = self.info.get(user_id)
        if info is None or info.get("activity") == activity:
            return
        info["activity"] = activity
        if _is_visible(info):
            await self._broadcast({"type": "presence_update", "user": info})

    async def broadcast_all(self, message: dict) -> None:
        """Difunde un evento a TODAS las conexiones (p. ej. actividad de canal
        para los contadores de no leídos, que deben llegar aunque no estés en
        ese canal)."""
        await self._broadcast(message)

    async def send_to(self, user_id: int, message: dict) -> None:
        """Envía un mensaje a todas las conexiones de un usuario (para DMs)."""
        for ws in list(self.sockets.get(user_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def _broadcast(self, message: dict, exclude: WebSocket | None = None) -> None:
        for sockets in list(self.sockets.values()):
            for ws in list(sockets):
                if ws is exclude:
                    continue
                try:
                    await ws.send_json(message)
                except Exception:
                    pass  # el cierre real lo maneja disconnect()


presence = PresenceManager()
