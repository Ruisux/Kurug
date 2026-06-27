"""
Subida de adjuntos para mensajes (canales y DMs).

- POST /uploads/image  (multipart `file`)  -> {"url": "/static/uploads/..."}
    Imágenes: se validan con Pillow y se reescalan a WEBP. Los GIF se guardan
    tal cual (sin recodificar) para conservar la animación.
- POST /uploads/file   (multipart `file`)  -> {"url", "name", "size"}
    Cualquier archivo: se escribe a disco EN STREAMING (por trozos), así un
    archivo de 1-2 GB no se carga entero en memoria. Límite en config.

Mismo criterio que los avatares: filesystem del server, sin object storage.
El cliente sube primero por aquí y luego manda el mensaje (WS) con la URL.
"""
import io
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image, UnidentifiedImageError

from ..config import settings
from ..deps import CurrentUser

router = APIRouter(prefix="/uploads", tags=["uploads"])

# static/uploads relativo a la raíz del proyecto (donde corre uvicorn).
UPLOAD_DIR = Path("static") / "uploads"
FILE_DIR = UPLOAD_DIR / "files"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FILE_DIR.mkdir(parents=True, exist_ok=True)

# Las imágenes no necesitan ser enormes (se recodifican). Los archivos pesados
# van por /uploads/file. Tope generoso para GIF animados.
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 MB
CHUNK = 1024 * 1024  # 1 MB por trozo al escribir a disco

# Caracteres seguros para conservar parte del nombre original en disco.
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@router.post("/image")
async def upload_image(user: CurrentUser, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="La imagen supera los 50 MB")

    # Validar con Pillow (rechaza cualquier cosa que no sea imagen).
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Archivo de imagen inválido")

    # GIF: guardar el original sin tocar para conservar la animación.
    if (img.format or "").upper() == "GIF":
        filename = f"{user.id}_{uuid.uuid4().hex}.gif"
        (UPLOAD_DIR / filename).write_bytes(data)
        return {"url": f"/static/uploads/{filename}"}

    # WebP no admite paleta/transparencia en modo "P"; normalizamos a RGB(A).
    if img.mode in ("P", "LA"):
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # Reescalar si es enorme (preserva proporción).
    side = settings.image_max_side
    if max(img.size) > side:
        img.thumbnail((side, side))

    filename = f"{user.id}_{uuid.uuid4().hex}.webp"
    img.save(UPLOAD_DIR / filename, format="WEBP", quality=82, method=4)
    return {"url": f"/static/uploads/{filename}"}


@router.post("/file")
async def upload_file(user: CurrentUser, file: UploadFile = File(...)):
    """Sube cualquier archivo escribiéndolo a disco por trozos (streaming)."""
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Nombre en disco único; conservamos la extensión y un trozo legible del
    # nombre original para que la descarga tenga sentido.
    original = (file.filename or "archivo").strip()[:120]
    safe = _SAFE.sub("_", original).strip("._") or "archivo"
    stored = f"{user.id}_{uuid.uuid4().hex}_{safe}"
    dest = FILE_DIR / stored

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el máximo de {settings.max_upload_mb} MB",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="No se pudo guardar el archivo")

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Archivo vacío")

    return {"url": f"/static/uploads/files/{stored}", "name": original, "size": size}
