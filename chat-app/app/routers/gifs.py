"""
Buscador de GIFs vía Giphy.

La API key vive en el servidor (config), nunca se expone al navegador: el
frontend pega contra estos endpoints y nosotros llamamos a Giphy. Los GIF se
envían luego como `image_url` apuntando a media*.giphy.com (hotlink, sin guardar
nada en el server).

- GET /gifs/featured            -> GIFs en tendencia (vista por defecto)
- GET /gifs/search?q=...        -> búsqueda

Si no hay GIPHY_API_KEY configurada, devuelven 503 (el frontend lo trata como
"buscador no disponible" sin romper el resto del chat).

Conseguir la key: developers.giphy.com -> Create an App -> "API" (instantáneo,
sin Google Cloud ni tarjeta).
"""
import httpx
from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..deps import CurrentUser
from ..schemas import GifOut

router = APIRouter(prefix="/gifs", tags=["gifs"])

GIPHY_BASE = "https://api.giphy.com/v1/gifs"
LIMIT = 30
MAX_OFFSET = 4000  # Giphy corta sobre 5000; dejamos margen


def _require_key() -> str:
    if not settings.giphy_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="El buscador de GIFs no está configurado (falta GIPHY_API_KEY).",
        )
    return settings.giphy_api_key


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _parse(payload: dict) -> list[GifOut]:
    out: list[GifOut] = []
    for r in payload.get("data", []):
        images = r.get("images", {})
        # Para enviar: downsized (cap ~2MB) y si no, el original.
        sendable = images.get("downsized") or images.get("original") or {}
        # Para el grid: una versión pequeña.
        preview = (
            images.get("fixed_width_small")
            or images.get("preview_gif")
            or images.get("fixed_width")
            or sendable
        )
        url = sendable.get("url")
        if not url:
            continue
        out.append(GifOut(
            id=str(r.get("id", url)),
            url=url,
            preview=preview.get("url", url),
            width=_int(sendable.get("width")),
            height=_int(sendable.get("height")),
            description=r.get("title", ""),
        ))
    return out


async def _giphy(path: str, params: dict, offset: int = 0) -> list[GifOut]:
    params = {
        **params,
        "api_key": _require_key(),
        "limit": LIMIT,
        "offset": max(0, min(MAX_OFFSET, offset)),
        "rating": "pg-13",
        "bundle": "messaging_non_clips",
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{GIPHY_BASE}/{path}", params=params)
            resp.raise_for_status()
            return _parse(resp.json())
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="No se pudo contactar con Giphy.")


@router.get("/featured", response_model=list[GifOut])
async def featured(user: CurrentUser, offset: int = Query(0, ge=0, le=MAX_OFFSET)):
    return await _giphy("trending", {}, offset=offset)


@router.get("/search", response_model=list[GifOut])
async def search(
    user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=100),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
):
    return await _giphy("search", {"q": q.strip()}, offset=offset)
