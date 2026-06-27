"""
Endpoints de canales.

- GET  /channels                  -> lista los canales.
- POST /channels                  -> crea un canal.
- GET  /channels/{id}/messages    -> historial de mensajes (últimos N).

Todos requieren estar autenticado (dependen de CurrentUser).
"""
from datetime import timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from fastapi import status

from ..deps import DbSession, CurrentUser
from ..models import Channel, Message, Reaction
from ..schemas import (
    ChannelCreate, ChannelOut, MessageOut, ReplyPreview, ReactionGroup, UnreadQuery,
)

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
def list_channels(db: DbSession, user: CurrentUser):
    # id del último mensaje por canal, para que el cliente sepa qué hay sin leer.
    last_ids = dict(
        db.execute(
            select(Message.channel_id, func.max(Message.id)).group_by(Message.channel_id)
        ).all()
    )
    channels = db.scalars(select(Channel).order_by(Channel.name)).all()
    return [
        ChannelOut(
            id=c.id, name=c.name, is_music=c.is_music,
            last_message_id=last_ids.get(c.id),
        )
        for c in channels
    ]


@router.post("/unread", response_model=dict[int, int])
def unread_counts(payload: UnreadQuery, db: DbSession, user: CurrentUser):
    """Cuenta mensajes no leídos por canal (de OTROS) desde el último leído.

    El 'último leído' lo lleva el cliente (localStorage) y lo envía aquí; así
    al recargar se recuperan los contadores sin guardar estado por usuario.
    """
    out: dict[int, int] = {}
    channel_ids = db.scalars(select(Channel.id)).all()
    for cid in channel_ids:
        threshold = payload.last_read.get(cid, 0)
        count = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.channel_id == cid,
                Message.id > threshold,
                Message.author_id != user.id,
            )
        )
        if count:
            out[cid] = count
    return out


@router.post("", response_model=ChannelOut, status_code=201)
def create_channel(data: ChannelCreate, db: DbSession, user: CurrentUser):
    exists = db.scalar(select(Channel).where(Channel.name == data.name))
    if exists:
        raise HTTPException(status_code=400, detail="El canal ya existe")

    channel = Channel(name=data.name)
    db.add(channel)
    try:
        db.commit()
    except IntegrityError:
        # Otro request creó el mismo canal entre el check y el commit.
        db.rollback()
        raise HTTPException(status_code=400, detail="El canal ya existe")
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: int, db: DbSession, user: CurrentUser):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede borrar canales")
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    # Borramos primero sus mensajes (no hay ON DELETE CASCADE en SQLite por defecto).
    db.execute(delete(Message).where(Message.channel_id == channel_id))
    db.delete(channel)
    db.commit()


def _as_utc(dt):
    # SQLite devuelve naive (UTC): marcarlo explícito para el cliente.
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _reply_of(db, m):
    if not m.reply_to_id:
        return None
    t = db.get(Message, m.reply_to_id)
    if t is None:
        return None
    return ReplyPreview(id=t.id, author_display_name=t.author.display_name, content=t.content)


def _reactions_of(db, m):
    rows_r = db.scalars(select(Reaction).where(Reaction.message_id == m.id)).all()
    groups: dict[str, list[int]] = {}
    for r in rows_r:
        groups.setdefault(r.emoji, []).append(r.user_id)
    return [ReactionGroup(emoji=e, count=len(u), users=u) for e, u in groups.items()]


def _to_out(db, m):
    return MessageOut(
        id=m.id,
        content=m.content,
        created_at=_as_utc(m.created_at),
        author_username=m.author.username,
        author_display_name=m.author.display_name,
        author_avatar_url=m.author.avatar_url,
        channel_id=m.channel_id,
        image_url=m.image_url,
        file_url=m.file_url,
        file_name=m.file_name,
        file_size=m.file_size,
        pinned_at=_as_utc(m.pinned_at) if m.pinned_at else None,
        edited_at=_as_utc(m.edited_at) if m.edited_at else None,
        reply_to=_reply_of(db, m),
        reactions=_reactions_of(db, m),
    )


@router.get("/{channel_id}/messages", response_model=list[MessageOut])
def channel_history(channel_id: int, db: DbSession, user: CurrentUser, limit: int = 50):
    rows = db.scalars(
        select(Message)
        .options(joinedload(Message.author))  # evita N+1 al leer author.username
        .where(Message.channel_id == channel_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))  # cronológico (más viejo arriba)
    return [_to_out(db, m) for m in rows]


@router.get("/{channel_id}/pins", response_model=list[MessageOut])
def channel_pins(channel_id: int, db: DbSession, user: CurrentUser):
    """Mensajes fijados del canal, del más reciente al más antiguo."""
    rows = db.scalars(
        select(Message)
        .options(joinedload(Message.author))
        .where(Message.channel_id == channel_id, Message.pinned_at.is_not(None))
        .order_by(Message.pinned_at.desc())
    ).all()
    return [_to_out(db, m) for m in rows]


@router.get("/{channel_id}/search", response_model=list[MessageOut])
def channel_search(channel_id: int, q: str, db: DbSession, user: CurrentUser, limit: int = 30):
    """Busca en los mensajes del canal por texto (case-insensitive)."""
    term = q.strip()
    if not term:
        return []
    rows = db.scalars(
        select(Message)
        .options(joinedload(Message.author))
        .where(Message.channel_id == channel_id, Message.content.ilike(f"%{term}%"))
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return [_to_out(db, m) for m in rows]
