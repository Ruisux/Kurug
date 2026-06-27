"""
Voz/pantalla con LiveKit (SFU).

- /voice/token : el cliente pide un token para unirse a la sala `channel-{id}`
  y conecta directo al servidor LiveKit.
- /voice/kick  : un admin expulsa a un participante de la sala.
"""
import json

from fastapi import APIRouter, HTTPException, status
from livekit import api

from ..config import settings
from ..deps import CurrentUser, DbSession
from ..models import Channel

router = APIRouter(prefix="/voice", tags=["voice"])


def room_name(channel_id: int) -> str:
    """Nombre de sala LiveKit a partir del canal."""
    return f"channel-{channel_id}"


@router.post("/token/{channel_id}")
def livekit_token(channel_id: int, db: DbSession, user: CurrentUser):
    """Devuelve un token de acceso a la sala LiveKit del canal + la URL."""
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Canal no encontrado")

    room = room_name(channel_id)
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        room_admin=user.is_admin,  # admins pueden moderar la sala
    )
    # Metadatos para que los demás pinten avatar/acento sin otra petición.
    metadata = json.dumps({
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "accent_color": user.accent_color,
    })
    identity = str(user.id)  # identidad estable = id (la UI mapea peers por id)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(user.display_name)
        .with_metadata(metadata)
        .with_grants(grants)
        .to_jwt()
    )
    return {
        "url": settings.livekit_url,
        "token": token,
        "room": room,
        "identity": identity,
    }


@router.post("/kick/{channel_id}/{identity}", status_code=status.HTTP_204_NO_CONTENT)
async def livekit_kick(channel_id: int, identity: str, user: CurrentUser):
    """Expulsa a un participante de la sala LiveKit (solo admin)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede desconectar")
    lkapi = api.LiveKitAPI(
        settings.livekit_http_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )
    try:
        await lkapi.room.remove_participant(
            api.RoomParticipantIdentity(room=room_name(channel_id), identity=identity)
        )
    finally:
        await lkapi.aclose()
