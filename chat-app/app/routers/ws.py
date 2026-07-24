"""
Endpoint WebSocket: el corazón del chat en tiempo real.

El cliente se conecta a:  ws://servidor/ws/{channel_id}?token=JWT

Flujo:
1. Validamos el token (los navegadores no mandan cabeceras en WebSocket
   fácilmente, así que el token va como query param).
2. Verificamos que el usuario y el canal existen.
3. Cada mensaje que llega: se guarda en la BD y se reenvía a todos los
   conectados al mismo canal.
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select, func, delete

from ..database import SessionLocal
from ..models import User, Channel, Message, DirectMessage, Reaction, DMReaction
from ..security import decode_token
from ..ws_manager import manager
from ..presence import presence, VALID_STATUSES


async def _dm_notify(pair, event) -> None:
    """Envía un evento a ambos participantes de un DM (sin duplicar)."""
    if not pair or event is None:
        return
    for uid in set(pair):
        await presence.send_to(uid, event)


def _dm_reactions_for(db, dm_id):
    rows = db.scalars(select(DMReaction).where(DMReaction.dm_id == dm_id)).all()
    groups: dict[str, list[int]] = {}
    for r in rows:
        groups.setdefault(r.emoji, []).append(r.user_id)
    return [{"emoji": e, "count": len(u), "users": u} for e, u in groups.items()]

_MENTION_RE = re.compile(r"@(\w+)")
_EVERYONE_RE = re.compile(r"@(everyone|todos)\b", re.IGNORECASE)


def _parse_mentions(db, content):
    """Devuelve (lista de user_ids mencionados, bool @everyone)."""
    everyone = bool(_EVERYONE_RE.search(content or ""))
    names = {m.lower() for m in _MENTION_RE.findall(content or "")}
    names -= {"everyone", "todos"}
    ids = []
    if names:
        rows = db.scalars(
            select(User).where(func.lower(User.username).in_(names))
        ).all()
        ids = [u.id for u in rows]
    return ids, everyone


def _utc_iso(dt):
    """SQLite devuelve naive (UTC): lo marcamos explícito para el cliente."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _reply_preview(db, reply_to_id):
    """Vista mínima del mensaje de canal citado (autor + contenido), o None."""
    if not reply_to_id:
        return None
    target = db.get(Message, reply_to_id)
    if target is None:
        return None
    return {
        "id": target.id,
        "author_display_name": target.author.display_name,
        "content": target.content,
    }


def _dm_reply_preview(db, reply_to_id):
    """Vista mínima del DM citado, o None."""
    if not reply_to_id:
        return None
    target = db.get(DirectMessage, reply_to_id)
    if target is None:
        return None
    return {
        "id": target.id,
        "author_display_name": target.sender.display_name,
        "content": target.content,
    }


def _clean_image_url(value):
    """Imágenes que subimos nosotros (/static/uploads) o GIFs de Giphy/Tenor."""
    if not isinstance(value, str):
        return None
    if value.startswith("/static/uploads/"):
        return value[:512]
    # GIFs externos: solo dominios conocidos de Giphy/Tenor por HTTPS.
    if value.startswith("https://"):
        host = value[len("https://"):].split("/", 1)[0].lower()
        if host.endswith(".giphy.com") or host.endswith(".tenor.com"):
            return value[:512]
    return None


def _clean_file(data):
    """Adjunto de archivo: {url,name,size} validado, o (None, None, None)."""
    f = data.get("file")
    if not isinstance(f, dict):
        return None, None, None
    url = f.get("url")
    if not (isinstance(url, str) and url.startswith("/static/uploads/files/")):
        return None, None, None
    name = (f.get("name") or "archivo")
    name = name[:255] if isinstance(name, str) else "archivo"
    size = f.get("size")
    size = size if isinstance(size, int) and size >= 0 else None
    return url[:255], name, size


# XP por tiempo en voz: cuándo entró cada quien a una sala (uid -> datetime).
# Al salir (o desconectar) se convierten los minutos en XP. En memoria: si el
# server se reinicia con gente en voz, se pierde ese tramo (aceptable).
_voice_since: dict[int, datetime] = {}
VOICE_XP_PER_MIN = 3
VOICE_XP_CAP = 240  # tope por sesión (~80 min), evita farmear dejando la voz abierta


async def _award_voice_time(uid: int) -> None:
    started = _voice_since.pop(uid, None)
    if started is None:
        return
    mins = (datetime.now(timezone.utc) - started).total_seconds() / 60
    gained = min(VOICE_XP_CAP, int(mins) * VOICE_XP_PER_MIN)
    if gained <= 0:
        return
    from ..gamify import level_from_xp
    with SessionLocal() as db:
        u = db.get(User, uid)
        if u is None:
            return
        before = level_from_xp(u.xp)["level"]
        u.xp = (u.xp or 0) + gained
        db.commit()
        db.refresh(u)
        if level_from_xp(u.xp)["level"] > before:
            await presence.update_profile(u)


def _reactions_for(db, message_id):
    """Reacciones de un mensaje agrupadas por emoji: [{emoji,count,users}]."""
    rows = db.scalars(
        select(Reaction).where(Reaction.message_id == message_id)
    ).all()
    groups: dict[str, list[int]] = {}
    for r in rows:
        groups.setdefault(r.emoji, []).append(r.user_id)
    return [{"emoji": e, "count": len(u), "users": u} for e, u in groups.items()]

router = APIRouter()

# Tope de longitud de un mensaje, para no persistir payloads abusivos.
MAX_MESSAGE_LENGTH = 4000


@router.websocket("/ws/presence")
async def presence_ws(websocket: WebSocket, token: str = Query(...)):
    """
    Gateway de presencia: el cliente lo abre UNA vez tras hacer login y lo
    mantiene abierto. Recibe el snapshot inicial y luego eventos en vivo
    (entró / salió / cambió de estado). Puede mandar {"type":"set_status",
    "status":"dnd"} para cambiar su disponibilidad.
    """
    username = decode_token(token)
    if username is None:
        await websocket.close(code=1008)
        return

    # Sesión CORTA solo para validar y registrar presencia. NO se mantiene una
    # sesión abierta mientras esperamos mensajes (eso agotaba el pool con varias
    # personas). Las operaciones abren su propia sesión breve.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            await websocket.close(code=1008)
            return
        uid = user.id
    await presence.connect(user, websocket)  # user separado, pero sus columnas siguen disponibles

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            kind = data.get("type")

            if kind == "set_status":
                status = data.get("status")
                if status not in VALID_STATUSES:
                    continue
                with SessionLocal() as db:
                    u = db.get(User, uid)
                    if u is not None:
                        u.status = status
                        db.commit()
                await presence.set_status(uid, status)

            elif kind == "sync_profile":
                # El perfil cambió por REST (otra sesión): recargar y difundir.
                with SessionLocal() as db:
                    u = db.get(User, uid)
                if u is not None:
                    await presence.update_profile(u)

            elif kind == "voice_join":
                # El cliente entró a la sala de voz de un canal: lo registramos
                # para mostrar "quién está en voz" a todos.
                cid = data.get("channel_id")
                if isinstance(cid, int):
                    await presence.set_voice(uid, cid)
                    _voice_since.setdefault(uid, datetime.now(timezone.utc))

            elif kind == "voice_leave":
                await presence.set_voice(uid, None)
                await _award_voice_time(uid)  # XP por el rato en voz

            elif kind == "voice_state":
                # Micro/auriculares/compartiendo/ping, para la lista de ocupantes.
                rtt = data.get("rtt")
                await presence.set_voice_state(
                    uid,
                    bool(data.get("muted")),
                    bool(data.get("deafened")),
                    bool(data.get("sharing")),
                    int(rtt) if isinstance(rtt, (int, float)) and 0 <= rtt < 10_000 else None,
                )

            elif kind == "set_activity":
                # Actividad automática ("jugando X"/"escuchando Y") de la app
                # de escritorio. null = limpiar. Vive solo en memoria.
                act_kind = data.get("kind")
                text = (data.get("text") or "").strip()[:128]
                if act_kind in ("game", "music") and text:
                    act = {"kind": act_kind, "text": text}
                    # Enriquecimiento de la música (Spotify): título, artista,
                    # álbum, carátula y progreso. Todo opcional y acotado; la
                    # carátula viaja como data URI (se limita el tamaño para no
                    # inflar el broadcast de presencia en memoria).
                    if act_kind == "music":
                        for f in ("title", "artist", "album"):
                            v = data.get(f)
                            if isinstance(v, str) and v.strip():
                                act[f] = v.strip()[:128]
                        art = data.get("art")
                        if isinstance(art, str) and art.startswith(("data:image/", "https://")) and len(art) <= 300_000:
                            act["art"] = art
                        for f in ("duration_ms", "position_ms"):
                            v = data.get(f)
                            if isinstance(v, (int, float)) and 0 <= v <= 4_320_000_000:  # ≤ 50 días en ms
                                act[f] = int(v)
                        # `at` es una marca de tiempo epoch en ms (~1.7e12), no
                        # una duración: su tope es mucho mayor (año ~2100).
                        at = data.get("at")
                        if isinstance(at, (int, float)) and 0 <= at <= 4_200_000_000_000:
                            act["at"] = int(at)
                        if isinstance(data.get("playing"), bool):
                            act["playing"] = data["playing"]
                    await presence.set_activity(uid, act)
                    # Insignia de melómano: escuchar música por primera vez.
                    if act_kind == "music":
                        from ..gamify import grant_badge
                        with SessionLocal() as db:
                            u = db.get(User, uid)
                            if u is not None and grant_badge(u, "melomano"):
                                db.commit()
                                db.refresh(u)
                                await presence.update_profile(u)
                else:
                    await presence.set_activity(uid, None)

            elif kind == "typing_dm":
                # "Está escribiendo…" en un DM: efímero, directo al destinatario.
                to = data.get("to")
                if isinstance(to, int):
                    info = presence.info.get(uid) or {}
                    await presence.send_to(to, {
                        "type": "dm_typing",
                        "from": uid,
                        "display_name": info.get("display_name") or username,
                    })

            elif kind == "dm":
                to = data.get("to")
                content = (data.get("content") or "").strip()
                image_url = _clean_image_url(data.get("image_url"))
                file_url, file_name, file_size = _clean_file(data)
                if not isinstance(to, int) or (not content and not image_url and not file_url):
                    continue
                content = content[:MAX_MESSAGE_LENGTH]
                reply_to = data.get("reply_to")
                reply_id = reply_to if isinstance(reply_to, int) else None
                payload = None
                with SessionLocal() as db:
                    recipient = db.get(User, to)
                    u = db.get(User, uid)
                    if recipient is None or u is None:
                        continue
                    dm = DirectMessage(
                        content=content, sender_id=uid, recipient_id=to,
                        image_url=image_url, file_url=file_url, file_name=file_name,
                        file_size=file_size, reply_to_id=reply_id,
                    )
                    db.add(dm)
                    db.commit()
                    db.refresh(dm)
                    payload = {
                        "type": "dm",
                        "message": {
                            "id": dm.id,
                            "content": dm.content,
                            "created_at": _utc_iso(dm.created_at),
                            "sender_id": uid,
                            "recipient_id": to,
                            "sender_username": u.username,
                            "sender_display_name": u.display_name,
                            "sender_avatar_url": u.avatar_url,
                            "image_url": dm.image_url,
                            "file_url": dm.file_url,
                            "file_name": dm.file_name,
                            "file_size": dm.file_size,
                            "edited_at": None,
                            "pinned_at": None,
                            "reply_to": _dm_reply_preview(db, reply_id),
                            "reactions": [],
                        },
                    }
                if payload:
                    await presence.send_to(to, payload)
                    if to != uid:
                        await presence.send_to(uid, payload)

            elif kind == "dm_delete":
                mid = data.get("id")
                if not isinstance(mid, int):
                    continue
                pair = None
                with SessionLocal() as db:
                    dm = db.get(DirectMessage, mid)
                    if dm is None or dm.sender_id != uid:  # solo el autor borra
                        continue
                    pair = (dm.sender_id, dm.recipient_id)
                    db.execute(delete(DMReaction).where(DMReaction.dm_id == mid))
                    db.delete(dm)
                    db.commit()
                await _dm_notify(pair, {"type": "dm_deleted", "id": mid})

            elif kind == "dm_edit":
                mid = data.get("id")
                new = (data.get("content") or "").strip()
                if not isinstance(mid, int) or not new:
                    continue
                pair = None
                event = None
                with SessionLocal() as db:
                    dm = db.get(DirectMessage, mid)
                    if dm is None or dm.sender_id != uid:
                        continue
                    dm.content = new[:MAX_MESSAGE_LENGTH]
                    dm.edited_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(dm)
                    pair = (dm.sender_id, dm.recipient_id)
                    event = {
                        "type": "dm_edited", "id": mid,
                        "content": dm.content, "edited_at": _utc_iso(dm.edited_at),
                    }
                await _dm_notify(pair, event)

            elif kind == "dm_react":
                mid = data.get("id")
                emoji = (data.get("emoji") or "")[:16]
                if not isinstance(mid, int) or not emoji:
                    continue
                pair = None
                reactions = None
                with SessionLocal() as db:
                    dm = db.get(DirectMessage, mid)
                    if dm is None or uid not in (dm.sender_id, dm.recipient_id):
                        continue
                    pair = (dm.sender_id, dm.recipient_id)
                    existing = db.scalar(
                        select(DMReaction).where(
                            DMReaction.dm_id == mid,
                            DMReaction.user_id == uid,
                            DMReaction.emoji == emoji,
                        )
                    )
                    if existing:
                        db.delete(existing)
                    else:
                        db.add(DMReaction(dm_id=mid, user_id=uid, emoji=emoji))
                    db.commit()
                    reactions = _dm_reactions_for(db, mid)
                await _dm_notify(pair, {"type": "dm_reactions", "id": mid, "reactions": reactions})

            elif kind == "dm_pin":
                mid = data.get("id")
                if not isinstance(mid, int):
                    continue
                pair = None
                event = None
                with SessionLocal() as db:
                    dm = db.get(DirectMessage, mid)
                    if dm is None or uid not in (dm.sender_id, dm.recipient_id):
                        continue
                    dm.pinned_at = None if dm.pinned_at else datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(dm)
                    pair = (dm.sender_id, dm.recipient_id)
                    event = {
                        "type": "dm_pinned", "id": mid,
                        "pinned_at": _utc_iso(dm.pinned_at) if dm.pinned_at else None,
                    }
                await _dm_notify(pair, event)
    except WebSocketDisconnect:
        pass
    finally:
        await _award_voice_time(uid)  # se fue sin "voice_leave": cerrar el tramo
        await presence.disconnect(uid, websocket)


@router.websocket("/ws/{channel_id}")
async def chat_ws(websocket: WebSocket, channel_id: int, token: str = Query(...)):
    username = decode_token(token)
    if username is None:
        await websocket.close(code=1008)  # 1008 = política violada (no autorizado)
        return

    # Validación con sesión corta (capturamos lo necesario del usuario).
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        channel = db.get(Channel, channel_id)
        if user is None or channel is None:
            await websocket.close(code=1008)
            return
        uid = user.id
        is_admin = user.is_admin
        display_name = user.display_name

    await manager.connect(channel_id, websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                # JSON malformado u otro payload no válido: ignorar y seguir.
                continue

            if not isinstance(data, dict):
                continue

            kind = data.get("type")

            # "Está escribiendo…": efímero, sin BD; solo a quienes miran este
            # canal (el WS de chat se abre por canal, así que el broadcast ya
            # llega únicamente a ellos).
            if kind == "typing":
                await manager.broadcast(channel_id, {
                    "type": "typing", "user_id": uid, "display_name": display_name,
                })
                continue

            # Borrar un mensaje: solo el autor o un admin.
            if kind == "delete":
                mid = data.get("id")
                if not isinstance(mid, int):
                    continue
                deleted = False
                with SessionLocal() as db:
                    target = db.get(Message, mid)
                    if target is None or target.channel_id != channel_id:
                        continue
                    if target.author_id != uid and not is_admin:
                        continue
                    db.delete(target)
                    db.commit()
                    deleted = True
                if deleted:
                    await manager.broadcast(channel_id, {"type": "deleted", "id": mid})
                continue

            # Reaccionar (toggle) con un emoji.
            if kind == "react":
                mid = data.get("id")
                emoji = (data.get("emoji") or "")[:16]
                if not isinstance(mid, int) or not emoji:
                    continue
                reactions = None
                with SessionLocal() as db:
                    target = db.get(Message, mid)
                    if target is None or target.channel_id != channel_id:
                        continue
                    existing = db.scalar(
                        select(Reaction).where(
                            Reaction.message_id == mid,
                            Reaction.user_id == uid,
                            Reaction.emoji == emoji,
                        )
                    )
                    if existing:
                        db.delete(existing)
                    else:
                        db.add(Reaction(message_id=mid, user_id=uid, emoji=emoji))
                    db.commit()
                    reactions = _reactions_for(db, mid)
                await manager.broadcast(channel_id, {
                    "type": "reactions", "id": mid, "reactions": reactions,
                })
                continue

            # Editar un mensaje: solo el autor.
            if kind == "edit":
                mid = data.get("id")
                new = (data.get("content") or "").strip()
                if not isinstance(mid, int) or not new:
                    continue
                edited = None
                with SessionLocal() as db:
                    target = db.get(Message, mid)
                    if target is None or target.channel_id != channel_id:
                        continue
                    if target.author_id != uid:
                        continue
                    target.content = new[:MAX_MESSAGE_LENGTH]
                    target.edited_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(target)
                    edited = {
                        "type": "edited",
                        "id": target.id,
                        "content": target.content,
                        "edited_at": _utc_iso(target.edited_at),
                    }
                await manager.broadcast(channel_id, edited)
                continue

            # Fijar / desfijar un mensaje (toggle): autor o admin.
            if kind == "pin":
                mid = data.get("id")
                if not isinstance(mid, int):
                    continue
                event = None
                with SessionLocal() as db:
                    target = db.get(Message, mid)
                    if target is None or target.channel_id != channel_id:
                        continue
                    if target.author_id != uid and not is_admin:
                        continue
                    if target.pinned_at is None:
                        target.pinned_at = datetime.now(timezone.utc)
                    else:
                        target.pinned_at = None
                    db.commit()
                    db.refresh(target)
                    event = {
                        "type": "pinned",
                        "id": target.id,
                        "pinned_at": _utc_iso(target.pinned_at) if target.pinned_at else None,
                    }
                await manager.broadcast(channel_id, event)
                continue

            content = (data.get("content") or "").strip()
            image_url = _clean_image_url(data.get("image_url"))
            file_url, file_name, file_size = _clean_file(data)
            # Un mensaje necesita texto, imagen o archivo.
            if not content and not image_url and not file_url:
                continue
            content = content[:MAX_MESSAGE_LENGTH]

            reply_to = data.get("reply_to")
            reply_id = reply_to if isinstance(reply_to, int) else None

            payload = None
            author_name = ""
            mention_ids, mention_all = [], False
            with SessionLocal() as db:
                u = db.get(User, uid)
                if u is None:
                    continue
                author_name = u.display_name
                mention_ids, mention_all = _parse_mentions(db, content)
                msg = Message(
                    content=content, author_id=uid, channel_id=channel_id,
                    image_url=image_url, file_url=file_url, file_name=file_name,
                    file_size=file_size, reply_to_id=reply_id,
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)
                payload = {
                    "type": "message",
                    "id": msg.id,
                    "content": msg.content,
                    "author_id": uid,
                    "author_username": u.username,
                    "author_display_name": u.display_name,
                    "author_avatar_url": u.avatar_url,
                    "channel_id": channel_id,
                    "image_url": msg.image_url,
                    "file_url": msg.file_url,
                    "file_name": msg.file_name,
                    "file_size": msg.file_size,
                    "pinned_at": None,
                    "created_at": _utc_iso(msg.created_at),
                    "edited_at": None,
                    "reply_to": _reply_preview(db, reply_id),
                    "reactions": [],
                    "mentions": mention_ids,
                    "mention_everyone": mention_all,
                }
                mid = msg.id

                # --- XP e insignias por participar ---
                # XP con enfriamiento de 60 s (no premia enviar mil mensajes
                # seguidos). Insignias: noctámbulo (madrugada) y charlatán (1000).
                refresh_presence = False
                from ..gamify import level_from_xp, grant_badge
                now = datetime.now(timezone.utc)
                last = u.xp_updated_at
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if last is None or (now - last).total_seconds() >= 60:
                    before = level_from_xp(u.xp)["level"]
                    u.xp = (u.xp or 0) + 8
                    u.xp_updated_at = now
                    if level_from_xp(u.xp)["level"] > before:
                        refresh_presence = True
                if datetime.now().hour < 5 and grant_badge(u, "noctambulo"):
                    refresh_presence = True
                total_msgs = db.scalar(
                    select(func.count()).select_from(Message).where(Message.author_id == uid)
                ) or 0
                if total_msgs >= 1000 and grant_badge(u, "charlatan"):
                    refresh_presence = True
                db.commit()

            await manager.broadcast(channel_id, payload)
            # Si subió de nivel o ganó una insignia, refrescar su presencia para
            # que las mini-tarjetas y el nombre se actualicen en vivo.
            if refresh_presence:
                with SessionLocal() as db2:
                    fresh = db2.get(User, uid)
                    if fresh is not None:
                        await presence.update_profile(fresh)
            # Aviso GLOBAL (por presencia): no leídos + menciones + notificación.
            await presence.broadcast_all({
                "type": "channel_activity",
                "channel_id": channel_id,
                "message_id": mid,
                "author_id": uid,
                "author_display_name": author_name,
                "content": (content or ("📷 Imagen" if image_url else "📎 Archivo"))[:140],
                "mentions": mention_ids,
                "mention_everyone": mention_all,
            })
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(channel_id, websocket)
