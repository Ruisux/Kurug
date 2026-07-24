// Catálogo de rangos e insignias (espejo de app/gamify.py). La BD guarda solo
// CLAVES; aquí resolvemos etiqueta, color e icono para pintarlas. Si añades una
// insignia/rango, tócalo en los DOS sitios.

// Rango -> { label, color }. Sin rango = no se pinta sello y el nombre usa el
// color de acento normal.
export const RANKS = {
  fundador: { label: "Fundador", color: "#e2b33b" },
  moderador: { label: "Moderador", color: "#5a76c4" },
  veterano: { label: "Veterano", color: "#9a6cc0" },
  artista: { label: "Artista", color: "#dd8bab" },
};

// Insignia -> { label, icon (tabler, sin ti-), color }.
export const BADGES = {
  fundador: { label: "Fundador", icon: "seal", color: "#c0392b" },
  melomano: { label: "Melómano", icon: "music", color: "#1ed760" },
  noctambulo: { label: "Noctámbulo", icon: "moon", color: "#9a6cc0" },
  pizarra: { label: "Artista de pizarra", icon: "pencil", color: "#5a76c4" },
  charlatan: { label: "Charlatán (1000 mensajes)", icon: "message-2", color: "#e2553b" },
  racha: { label: "Racha de fuego", icon: "flame", color: "#e2553b" },
  mvp: { label: "MVP", icon: "star", color: "#e2b33b" },
  corazon: { label: "Alma del grupo", icon: "heart", color: "#dd8bab" },
};

export function rankInfo(key) {
  return key && RANKS[key] ? RANKS[key] : null;
}
export function badgeInfo(key) {
  return BADGES[key] || null;
}
// Color del nombre: el del rango si tiene, si no el acento del usuario.
export function nameColorFor(user) {
  const r = rankInfo(user?.rank);
  return r ? r.color : user?.accent_color || null;
}
