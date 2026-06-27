"""
Resolución de lo que pide el usuario → pista(s) de YouTube.

- Enlace de YouTube (vídeo o playlist) → se usa tal cual.
- Enlace de Spotify / Apple Music → sacamos solo el título (og:title) y lo
  BUSCAMOS en YouTube (no nos conectamos a reproducir en esos servicios).
- Texto libre → búsqueda en YouTube.

Devuelve metadatos para la cola/UI. El audio lo resuelve y reproduce el bot.
yt-dlp puede tardar unos segundos: llamar desde un executor (no bloquear el loop).
"""
import re
import urllib.request

from yt_dlp import YoutubeDL

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "noplaylist": False,
    "default_search": "ytsearch1",
}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _thumb(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _og_title(url: str) -> str | None:
    """Título de una página (Spotify/Apple) vía og:title, para buscar en YouTube."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "ignore")
    except Exception:
        return None
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    title = m.group(1) if m else None
    if not title:
        return None
    # og:description suele traer el artista ("Song · Artist · ...").
    md = re.search(r'<meta property="og:description" content="([^"]+)"', html)
    artist = ""
    if md:
        parts = [p.strip() for p in md.group(1).split("·")]
        if len(parts) >= 2:
            artist = parts[1]
    return f"{title} {artist}".strip()


def _track(info: dict, source: str) -> dict:
    vid = info.get("id")
    return {
        "video_id": vid,
        "title": info.get("title") or "(sin título)",
        "thumbnail": info.get("thumbnail") or (_thumb(vid) if vid else None),
        "duration": info.get("duration"),  # segundos o None (en playlists planas)
        "source": source,
    }


def resolve(query: str) -> list[dict]:
    """Devuelve una lista de pistas (1 para vídeo/canción; varias para playlist)."""
    q = (query or "").strip()
    if not q:
        return []

    source = "youtube"
    if "spotify.com" in q or "music.apple.com" in q:
        source = "spotify" if "spotify" in q else "apple"
        title = _og_title(q)
        if not title:
            return []
        q = title  # a partir de aquí, búsqueda en YouTube

    try:
        with YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(q, download=False)
    except Exception:
        return []

    if not info:
        return []

    # Resultado de búsqueda: viene envuelto en entries → tomamos el primero.
    if info.get("_type") == "playlist" and "ytsearch" in q:
        entries = info.get("entries") or []
        return [_track(entries[0], source)] if entries else []

    # Playlist real → todas las entradas.
    if info.get("entries"):
        return [_track(e, source) for e in info["entries"] if e]

    return [_track(info, source)]
