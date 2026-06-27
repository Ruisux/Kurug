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
    return {
        "id": user.id,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "status": user.status,
        "custom_status": user.custom_status,
        "accent_color": user.accent_color,
    }


def _is_visible(info: dict) -> bool:
    return info.get("status") != "invisible"


class PresenceManager:
    def __init__(self) -> None:
        self.sockets: dict[int, set[WebSocket]] = defaultdict(set)
        self.info: dict[int, dict] = {}

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
        self.info[user.id] = _info_from_user(user)

        # El recién llegado recibe la foto actual de quién está conectado.
        await ws.send_json({"type": "presence_snapshot", "users": self.online_users()})

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
        if info is not None and _is_visible(info):
            await self._broadcast({"type": "presence_offline", "user_id": user_id})

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

    async def update_profile(self, user) -> None:
        """Refresca el perfil cacheado (nickname/avatar/color/estado…) y lo difunde."""
        if user.id not in self.info:
            return
        was_visible = _is_visible(self.info[user.id])
        self.info[user.id] = _info_from_user(user)
        now_visible = _is_visible(self.info[user.id])

        if now_visible:
            await self._broadcast({"type": "presence_update", "user": self.info[user.id]})
        elif was_visible:
            await self._broadcast({"type": "presence_offline", "user_id": user.id})

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
