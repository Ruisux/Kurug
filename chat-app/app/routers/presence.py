"""
Endpoint REST de presencia para la carga inicial del panel de conectados.

En vivo, los cambios llegan por el WebSocket /ws/presence; este GET es para
poblar la lista la primera vez (o como respaldo).
"""
from fastapi import APIRouter

from ..deps import CurrentUser
from ..presence import presence

router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("")
def list_online(_: CurrentUser):
    """Usuarios actualmente conectados y visibles."""
    return presence.online_users()
