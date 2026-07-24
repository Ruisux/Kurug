"""
Endpoints de perfil de usuario.

- GET   /users/me           -> mi perfil completo.
- PATCH /users/me           -> editar mi perfil (nickname, bio, color, estado…).
- GET   /users/{id}         -> perfil público de otro usuario.

Todos requieren estar autenticado. La subida de avatar vive en avatars.py.
El cambio de `status` aquí actualiza la preferencia persistida; la difusión en
tiempo real a los demás clientes la hace el sistema de presencia (ver ws.py).
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..config import settings
from ..deps import DbSession, CurrentUser
from ..gamify import RANKS, BADGES, grant_badge, revoke_badge
from ..models import User
from ..presence import presence
from ..schemas import UserOut, MeOut, UserUpdate, RankUpdate, BadgeUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _: CurrentUser):
    """Todos los usuarios (menos el bot). Para autocompletar menciones."""
    users = db.scalars(
        select(User).where(User.username != settings.bot_username).order_by(User.username)
    ).all()
    return users


@router.get("/me", response_model=MeOut)
def get_me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(data: UserUpdate, db: DbSession, user: CurrentUser):
    # Solo aplicamos los campos enviados (PATCH parcial).
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DbSession, _: CurrentUser):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


# --- Gestión de rango e insignias (solo admin) ---
def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede hacer esto")


@router.post("/{user_id}/rank", response_model=UserOut)
async def set_rank(user_id: int, data: RankUpdate, db: DbSession, me: CurrentUser):
    _require_admin(me)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if data.rank is not None and data.rank not in RANKS:
        raise HTTPException(status_code=422, detail="Rango desconocido")
    target.rank = data.rank
    db.commit()
    db.refresh(target)
    await presence.update_profile(target)  # difunde el nuevo rango en vivo
    return target


@router.post("/{user_id}/badges", response_model=UserOut)
async def set_badge(user_id: int, data: BadgeUpdate, db: DbSession, me: CurrentUser):
    _require_admin(me)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if data.key not in BADGES:
        raise HTTPException(status_code=422, detail="Insignia desconocida")
    changed = grant_badge(target, data.key) if data.action == "add" else revoke_badge(target, data.key)
    if changed:
        db.commit()
        db.refresh(target)
        await presence.update_profile(target)
    return target
