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
from ..models import User
from ..schemas import UserOut, MeOut, UserUpdate

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
