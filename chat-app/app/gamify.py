"""
Personalización de perfiles: rangos, insignias y niveles (XP).

Todo lo "de catálogo" (qué rangos y qué insignias existen, con su etiqueta,
color e icono) vive aquí y se refleja en el cliente (web/src/lib/gamify.js).
La BD solo guarda CLAVES; el aspecto se resuelve en el cliente. Así añadir una
insignia nueva es tocar el catálogo en dos sitios, sin migración.

Niveles: la XP se acumula (mensajes con enfriamiento + tiempo en voz). El nivel
sale de una curva creciente: cada nivel cuesta un poco más que el anterior.
"""
import json

# --- Rangos (los asigna un admin; tiñen el nombre y ponen un sello) ---
# clave -> {label, color}. El "miembro" (sin rango) no pinta sello.
RANKS: dict[str, dict] = {
    "fundador": {"label": "Fundador", "color": "#e2b33b"},   # oro
    "moderador": {"label": "Moderador", "color": "#5a76c4"},  # azul
    "veterano": {"label": "Veterano", "color": "#9a6cc0"},    # púrpura
    "artista": {"label": "Artista", "color": "#dd8bab"},      # sakura
}

# --- Insignias ---
# clave -> {label, icon (nombre tabler sin el prefijo ti-), color, auto}.
# `auto` = la concede el sistema por un hito; las demás las da un admin.
BADGES: dict[str, dict] = {
    "fundador":   {"label": "Fundador", "icon": "seal", "color": "#c0392b", "auto": True},
    "melomano":   {"label": "Melómano", "icon": "music", "color": "#1ed760", "auto": True},
    "noctambulo": {"label": "Noctámbulo", "icon": "moon", "color": "#9a6cc0", "auto": True},
    "pizarra":    {"label": "Artista de pizarra", "icon": "pencil", "color": "#5a76c4", "auto": True},
    "charlatan":  {"label": "Charlatán (1000 mensajes)", "icon": "message-2", "color": "#e2553b", "auto": True},
    "racha":      {"label": "Racha de fuego", "icon": "flame", "color": "#e2553b", "auto": False},
    "mvp":        {"label": "MVP", "icon": "star", "color": "#e2b33b", "auto": False},
    "corazon":    {"label": "Alma del grupo", "icon": "heart", "color": "#dd8bab", "auto": False},
}

# --- Curva de niveles ---
# XP para pasar del nivel L al L+1. Crece de forma lineal: nivel barato al
# principio, más caro después (nivel 12 ≈ 1600 XP acumulados hasta ahí).
def xp_for_level(level: int) -> int:
    """XP necesaria para subir DESDE `level` (>=1) al siguiente."""
    return 100 + (level - 1) * 90


def level_from_xp(xp: int) -> dict:
    """Descompone la XP total en {level, into, span}: nivel actual, XP dentro de
    ese nivel y XP total que ese nivel necesita para completarse."""
    xp = max(0, int(xp or 0))
    level = 1
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
    return {"level": level, "into": xp, "span": xp_for_level(level)}


# --- Helpers de insignias (la BD guarda un JSON de claves) ---
def parse_badges(raw) -> list[str]:
    try:
        val = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return [b for b in val if isinstance(b, str) and b in BADGES]
    except (ValueError, TypeError):
        return []


def dump_badges(keys) -> str:
    seen = []
    for k in keys:
        if k in BADGES and k not in seen:
            seen.append(k)
    return json.dumps(seen)


def grant_badge(user, key: str) -> bool:
    """Concede una insignia si es válida y no la tenía. True si es nueva."""
    if key not in BADGES:
        return False
    have = parse_badges(user.badges)
    if key in have:
        return False
    have.append(key)
    user.badges = dump_badges(have)
    return True


def revoke_badge(user, key: str) -> bool:
    have = parse_badges(user.badges)
    if key not in have:
        return False
    user.badges = dump_badges([b for b in have if b != key])
    return True
