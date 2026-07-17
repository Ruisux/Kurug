"""
Resolución de lo que pide el usuario → pista(s) de YouTube.

- Enlace de YouTube (vídeo o playlist) → yt-dlp directo (playlists en plano y
  con tope, así una lista de 500 no cuelga nada).
- Enlace de Spotify (canción/álbum/playlist) → página EMBED de Spotify
  (`open.spotify.com/embed/...`), que sirve un JSON (__NEXT_DATA__) con TODAS
  las pistas (título, artistas y duración) sin API key. Cada pista se busca
  luego en YouTube.
- Enlace de Apple Music (canción/álbum/playlist) → JSON-LD (schema.org) de la
  página + el JSON interno `serialized-server-data` para el artista por pista.
- Texto libre → búsqueda en YouTube.

Diseño en dos fases para que las playlists no bloqueen:
  plan(query)   -> {"kind":"tracks", ...}   pistas YA resueltas (YouTube), o
                   {"kind":"queries", ...}  búsquedas pendientes (Spotify/Apple)
  search_youtube(q, ...) -> resuelve UNA búsqueda a una pista de YouTube
El router añade la primera al instante y el resto en segundo plano.

Todo aquí es BLOQUEANTE (red): llamar siempre desde un executor.
"""
import json
import re
import ssl
import urllib.request

from yt_dlp import YoutubeDL

# CAs de certifi si está disponible: el Python de macOS (y algunos Windows) no
# encuentra las CAs del sistema y CUALQUIER https con urllib falla en silencio.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

MAX_PLAYLIST = 100  # tope de pistas por enlace (playlists gigantes/mixes)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",  # playlists en plano: id/título sin abrir cada vídeo
    "noplaylist": False,
    "playlist_items": f"1:{MAX_PLAYLIST}",
    "socket_timeout": 10,
    "retries": 2,
}

_BAD_TITLES = {"[Private video]", "[Deleted video]"}


def _thumb(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _fetch(url: str, timeout: float = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX).read().decode("utf-8", "ignore")


def _is_url(q: str) -> bool:
    return bool(re.match(r"https?://", q, re.I))


# Un item pendiente de buscar en YouTube: la query, el título "bonito" para la
# cola (título — artista, sin los "(Official Video)" de YouTube) y la duración
# real que reporta Spotify/Apple.
def _pending(title: str, artists: str, duration_s) -> dict:
    title = (title or "").strip()
    artists = (artists or "").strip()
    return {
        "q": f"{title} {artists}".strip(),
        "title": f"{title} — {artists}" if artists else title,
        "duration": duration_s,
    }


# ---------------- Spotify (vía página embed, sin API key) ----------------

_SP_RE = re.compile(r"open\.spotify\.com/(?:intl-[a-z-]+/)?(track|album|playlist)/([A-Za-z0-9]+)")
_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)


def _spotify_items(url: str) -> list[dict] | None:
    m = _SP_RE.search(url)
    if not m:
        return None
    kind, sid = m.groups()
    try:
        html = _fetch(f"https://open.spotify.com/embed/{kind}/{sid}")
        nd = _NEXT_RE.search(html)
        entity = json.loads(nd.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception:
        return None

    def ms(v):  # Spotify da milisegundos
        return round(v / 1000) if isinstance(v, (int, float)) and v > 0 else None

    tl = entity.get("trackList")
    if tl:  # álbum o playlist: lista completa
        return [
            _pending(t.get("title"), t.get("subtitle"), ms(t.get("duration")))
            for t in tl[:MAX_PLAYLIST]
            if t.get("title")
        ]
    # canción suelta
    name = entity.get("name") or entity.get("title")
    if not name:
        return None
    artists = ", ".join(a.get("name", "") for a in entity.get("artists", []) if a.get("name"))
    return [_pending(name, artists, ms(entity.get("duration")))]


# ---------------- Apple Music (JSON-LD + datos serializados) ----------------

_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_AM_SONG_RE = re.compile(r"music\.apple\.com/.*(/song/|[?&]i=)")
_OG_TITLE_RE = re.compile(r'og:title"\s+content="([^"]+)"')
_AM_OG_RE = re.compile(r"^(.*) by (.*?) on Apple Music$")


def _iso_dur(s) -> int | None:
    """Duración ISO-8601 (PT4M18S) → segundos."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", s or "")
    if not m:
        return None
    h, mn, sec = (int(x or 0) for x in m.groups())
    total = h * 3600 + mn * 60 + sec
    return total or None


def _apple_artist_map(html: str) -> dict[str, str]:
    """título → artista, del JSON interno de la página (el JSON-LD no lo trae)."""
    m = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}

    def walk(o):
        if isinstance(o, dict):
            t, a = o.get("title") or o.get("name"), o.get("artistName")
            if isinstance(t, str) and isinstance(a, str) and t not in out:
                out[t] = a
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    try:
        walk(json.loads(m.group(1)))
    except Exception:
        return {}
    return out


def _apple_items(url: str) -> list[dict] | None:
    try:
        html = _fetch(url)
    except Exception:
        return None

    # Canción suelta (/song/... o álbum con ?i=...): og:title es lo fiable.
    if _AM_SONG_RE.search(url):
        og = _OG_TITLE_RE.search(html)
        if not og:
            return None
        # OJO: Apple escribe "on Apple\xa0Music" con espacio duro.
        title = og.group(1).replace("\xa0", " ").strip()
        m = _AM_OG_RE.match(title)
        if m:
            return [_pending(m.group(1), m.group(2), None)]
        return [_pending(title, "", None)]

    # Álbum o playlist: el JSON-LD es la LISTA autoritativa de pistas; el JSON
    # interno aporta el artista por pista (y el byArtist del álbum, de respaldo).
    artist_of = _apple_artist_map(html)
    for ld in _LD_RE.findall(html):
        try:
            data = json.loads(ld)
        except Exception:
            continue
        for it in data if isinstance(data, list) else [data]:
            # Según la variante de la página, la lista viene como "tracks" o
            # como "track" (el nombre estándar de schema.org).
            tracks = it.get("tracks") or it.get("track")
            if not isinstance(tracks, list) or not tracks:
                continue
            by = it.get("byArtist")
            album_artist = ""
            if isinstance(by, list) and by:
                album_artist = by[0].get("name", "")
            elif isinstance(by, dict):
                album_artist = by.get("name", "")
            out = []
            for t in tracks[:MAX_PLAYLIST]:
                name = t.get("name")
                if not name:
                    continue
                out.append(_pending(name, artist_of.get(name, album_artist), _iso_dur(t.get("duration"))))
            if out:
                return out
    # Sin lista de pistas: último recurso, el og:title (título del álbum).
    og = _OG_TITLE_RE.search(html)
    return [_pending(og.group(1).replace("\xa0", " "), "", None)] if og else None


# ---------------- YouTube ----------------

def _track(info: dict, source: str) -> dict | None:
    vid = info.get("id")
    title = info.get("title") or "(sin título)"
    if not vid or title in _BAD_TITLES:
        return None
    return {
        "video_id": vid,
        "title": title,
        "thumbnail": info.get("thumbnail") or _thumb(vid),
        "duration": info.get("duration"),
        "source": source,
    }


def _yt_extract(q: str) -> dict | None:
    try:
        with YoutubeDL(_YDL_OPTS) as ydl:
            return ydl.extract_info(q, download=False)
    except Exception:
        return None


def search_youtube(query: str, source: str = "youtube", title: str | None = None, duration=None) -> dict | None:
    """Busca UNA canción en YouTube. `title`/`duration` (de Spotify/Apple) tienen
    prioridad para que la cola muestre lo pedido, no el título del vídeo."""
    info = _yt_extract(f"ytsearch1:{query}")
    entries = (info or {}).get("entries") or []
    t = _track(entries[0], source) if entries else None
    if t:
        if title:
            t["title"] = title
        if duration and not t.get("duration"):
            t["duration"] = duration
    return t


def plan(query: str) -> dict:
    """Primera fase: decide qué es lo pedido.

    → {"kind": "tracks",  "tracks": [...]}                 listo para encolar
    → {"kind": "queries", "items": [...], "source": ...}   falta buscar en YouTube
    """
    q = (query or "").strip()
    if not q:
        return {"kind": "tracks", "tracks": []}

    if "open.spotify.com" in q:
        return {"kind": "queries", "source": "spotify", "items": _spotify_items(q) or []}
    if "music.apple.com" in q:
        return {"kind": "queries", "source": "apple", "items": _apple_items(q) or []}

    info = _yt_extract(q if _is_url(q) else f"ytsearch1:{q}")
    if not info:
        return {"kind": "tracks", "tracks": []}

    if info.get("entries") is not None:
        # Playlist real O resultado de búsqueda (ytsearch también envuelve).
        entries = [e for e in (info.get("entries") or []) if e]
        n = 1 if not _is_url(q) else MAX_PLAYLIST  # búsqueda: solo el primero
        tracks = [t for e in entries[:n] if (t := _track(e, "youtube"))]
        return {"kind": "tracks", "tracks": tracks}

    t = _track(info, "youtube")
    return {"kind": "tracks", "tracks": [t] if t else []}


def resolve(query: str) -> list[dict]:
    """Resolución completa en un paso (compatibilidad). Puede tardar MUCHO con
    playlists de Spotify/Apple: el router usa plan() + search_youtube()."""
    p = plan(query)
    if p["kind"] == "tracks":
        return p["tracks"]
    out = []
    for it in p["items"]:
        t = search_youtube(it["q"], p["source"], it["title"], it.get("duration"))
        if t:
            out.append(t)
    return out
