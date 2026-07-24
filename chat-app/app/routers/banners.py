"""
Banner de la tarjeta de perfil.

- POST   /users/me/banner  (multipart, campo `file`) -> sube y recorta a 4:1.
- DELETE /users/me/banner                            -> lo quita.

Mismo enfoque que el avatar (Pillow + filesystem en static/banners/). Si no hay
banner, la tarjeta usa un degradado con el color de acento (lo decide el cliente).
"""
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image, UnidentifiedImageError, ImageOps

from ..deps import DbSession, CurrentUser
from ..schemas import UserOut

router = APIRouter(prefix="/users/me/banner", tags=["users"])

BANNER_DIR = Path("static") / "banners"
BANNER_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
BANNER_W, BANNER_H = 1000, 250      # 4:1


def _delete_previous(url: str | None) -> None:
    if not url or not url.startswith("/static/banners/"):
        return
    try:
        (Path("static") / "banners" / Path(url).name).unlink(missing_ok=True)
    except OSError:
        pass


@router.post("", response_model=UserOut)
async def upload_banner(db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="La imagen supera los 8 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Archivo de imagen inválido")

    # Recorte centrado a 4:1 (rellena el banner sin deformar).
    img = ImageOps.fit(img, (BANNER_W, BANNER_H), Image.LANCZOS)

    filename = f"{user.id}_{uuid.uuid4().hex}.jpg"
    img.save(BANNER_DIR / filename, format="JPEG", quality=85)
    _delete_previous(user.banner_url)

    user.banner_url = f"/static/banners/{filename}"
    db.commit()
    db.refresh(user)
    return user


@router.delete("", response_model=UserOut)
def remove_banner(db: DbSession, user: CurrentUser):
    _delete_previous(user.banner_url)
    user.banner_url = None
    db.commit()
    db.refresh(user)
    return user
