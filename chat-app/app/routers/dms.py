"""
Mensajes directos (DMs) 1-a-1.

- GET /dms/conversations   -> lista de personas con las que has hablado.
- GET /dms/{user_id}       -> historial con esa persona.

El ENVÍO y la entrega en vivo NO van por aquí: se hacen por el WebSocket de
presencia (mensaje {"type":"dm", ...}), que ya tiene una conexión por usuario.
"""
from datetime import timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import joinedload

from ..deps import DbSession, CurrentUser
from ..models import User, DirectMessage, DMReaction
from ..schemas import DirectMessageOut, DMConversation, UserOut, ReplyPreview, ReactionGroup

router = APIRouter(prefix="/dms", tags=["dms"])


def _as_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/conversations", response_model=list[DMConversation])
def conversations(db: DbSession, user: CurrentUser):
    rows = db.scalars(
        select(DirectMessage)
        .where(or_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user.id))
        .order_by(DirectMessage.id.desc())
    ).all()

    seen: dict[int, DirectMessage] = {}
    for dm in rows:
        other = dm.recipient_id if dm.sender_id == user.id else dm.sender_id
        if other not in seen:
            seen[other] = dm  # la primera (más reciente) por ser orden desc

    out = []
    for other_id, dm in seen.items():
        partner = db.get(User, other_id)
        if partner is not None:
            out.append(DMConversation(user=UserOut.model_validate(partner), last_at=_as_utc(dm.created_at)))
    out.sort(key=lambda c: c.last_at, reverse=True)
    return out


@router.get("/{user_id}", response_model=list[DirectMessageOut])
def history(user_id: int, db: DbSession, user: CurrentUser, limit: int = 50):
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    rows = db.scalars(
        select(DirectMessage)
        .options(joinedload(DirectMessage.sender))
        .where(
            or_(
                and_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user_id),
                and_(DirectMessage.sender_id == user_id, DirectMessage.recipient_id == user.id),
            )
        )
        .order_by(DirectMessage.id.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))
    return [_dm_to_out(db, m) for m in rows]


def _dm_reply_of(db, m):
    if not m.reply_to_id:
        return None
    t = db.get(DirectMessage, m.reply_to_id)
    if t is None:
        return None
    return ReplyPreview(id=t.id, author_display_name=t.sender.display_name, content=t.content)


def _dm_reactions_of(db, m):
    rows = db.scalars(select(DMReaction).where(DMReaction.dm_id == m.id)).all()
    groups: dict[str, list[int]] = {}
    for r in rows:
        groups.setdefault(r.emoji, []).append(r.user_id)
    return [ReactionGroup(emoji=e, count=len(u), users=u) for e, u in groups.items()]


def _dm_to_out(db, m):
    return DirectMessageOut(
        id=m.id,
        content=m.content,
        created_at=_as_utc(m.created_at),
        sender_id=m.sender_id,
        recipient_id=m.recipient_id,
        sender_username=m.sender.username,
        sender_display_name=m.sender.display_name,
        sender_avatar_url=m.sender.avatar_url,
        image_url=m.image_url,
        file_url=m.file_url,
        file_name=m.file_name,
        file_size=m.file_size,
        edited_at=_as_utc(m.edited_at) if m.edited_at else None,
        pinned_at=_as_utc(m.pinned_at) if m.pinned_at else None,
        reply_to=_dm_reply_of(db, m),
        reactions=_dm_reactions_of(db, m),
    )


@router.get("/{user_id}/pins", response_model=list[DirectMessageOut])
def dm_pins(user_id: int, db: DbSession, user: CurrentUser):
    """Mensajes fijados de la conversación con `user_id`."""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    rows = db.scalars(
        select(DirectMessage)
        .options(joinedload(DirectMessage.sender))
        .where(
            or_(
                and_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user_id),
                and_(DirectMessage.sender_id == user_id, DirectMessage.recipient_id == user.id),
            ),
            DirectMessage.pinned_at.is_not(None),
        )
        .order_by(DirectMessage.pinned_at.desc())
    ).all()
    return [_dm_to_out(db, m) for m in rows]


@router.get("/{user_id}/search", response_model=list[DirectMessageOut])
def dm_search(user_id: int, q: str, db: DbSession, user: CurrentUser, limit: int = 30):
    """Busca en la conversación directa con `user_id` por texto."""
    term = q.strip()
    if not term:
        return []
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    rows = db.scalars(
        select(DirectMessage)
        .options(joinedload(DirectMessage.sender))
        .where(
            or_(
                and_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user_id),
                and_(DirectMessage.sender_id == user_id, DirectMessage.recipient_id == user.id),
            ),
            DirectMessage.content.ilike(f"%{term}%"),
        )
        .order_by(DirectMessage.id.desc())
        .limit(limit)
    ).all()
    return [_dm_to_out(db, m) for m in rows]
