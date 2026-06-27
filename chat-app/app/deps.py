"""
Dependencias reutilizables de FastAPI.

- `get_db`: abre una sesión de BD por petición y la cierra al terminar.
- `get_current_user`: lee el token "Authorization: Bearer ..." y devuelve
  el usuario autenticado, o lanza 401 si el token no sirve.

Los `Annotated[...]` de abajo son atajos para no repetir Depends(...) en
cada endpoint.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    username = decode_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
