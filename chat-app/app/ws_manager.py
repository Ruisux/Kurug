"""
Gestor de conexiones WebSocket.

Mantiene, por cada canal, el conjunto de clientes conectados. Cuando llega
un mensaje nuevo lo reenvía a todos los del mismo canal (broadcast).

OJO: esto vive en memoria. Funciona perfecto con UN proceso del servidor.
Si algún día corres varias instancias (escalado horizontal), necesitarás
un backend compartido tipo Redis Pub/Sub para que todas se enteren.
"""
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[channel_id].add(ws)

    def disconnect(self, channel_id: int, ws: WebSocket) -> None:
        self.rooms[channel_id].discard(ws)
        if not self.rooms[channel_id]:
            self.rooms.pop(channel_id, None)

    async def broadcast(self, channel_id: int, message: dict) -> None:
        for ws in list(self.rooms.get(channel_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                # Si un cliente falla al recibir, lo sacamos de la sala.
                self.disconnect(channel_id, ws)


manager = ConnectionManager()
