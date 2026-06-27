"""
Subida de foto de perfil (avatar).

- POST /users/me/avatar  (multipart, campo `file`)

La imagen se valida y se redimensiona con Pillow (máx. 256x256) y se guarda en
`static/avatars/` con un nombre único, de modo que se sirve como estático en
`/static/avatars/...`. Guardar en el filesystem es lo más simple y eficiente
para un server casero; si algún día se escala, se cambia por object storage.
"""
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image, UnidentifiedImageError

from ..deps import DbSession, CurrentUser
from ..schemas import UserOut

router = APIRouter(prefix="/users/me/avatar", tags=["users"])

# static/avatars relativo a la raíz del proyecto (donde corre uvicorn).
AVATAR_DIR = Path("static") / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_SIZE = (256, 256)


@router.post("", response_model=UserOut)
async def upload_avatar(db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="La imagen supera los 5 MB")

    # Validar y normalizar con Pillow (rechaza cualquier cosa que no sea imagen).
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Archivo de imagen inválido")

    img.thumbnail(AVATAR_SIZE)

    filename = f"{user.id}_{uuid.uuid4().hex}.png"
    img.save(AVATAR_DIR / filename, format="PNG")

    # Borrar el avatar anterior si era uno gestionado por nosotros.
    _delete_previous_avatar(user.avatar_url)

    user.avatar_url = f"/static/avatars/{filename}"
    db.commit()
    db.refresh(user)
    return user


def _delete_previous_avatar(avatar_url: str | None) -> None:
    if not avatar_url or not avatar_url.startswith("/static/avatars/"):
        return
    old = AVATAR_DIR / Path(avatar_url).name
    try:
        old.unlink(missing_ok=True)
    except OSError:
        pass  # si no se puede borrar, no es crítico
