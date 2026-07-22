// Helpers de presentación compartidos.

const AVATAR_COLORS = [
  "#6FBF8E",
  "#E2553B",
  "#C2A35B",
  "#C98B6B",
  "#8FA6C9",
  "#B58BC9",
  "#7FB2A8",
];

export function avatarColor(name) {
  let h = 0;
  for (const c of name || "?") h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function initials(name) {
  const parts = (name || "?").trim().split(/\s+/);
  return ((parts[0]?.[0] || "?") + (parts[1]?.[0] || "")).toUpperCase();
}

export const STATUSES = [
  { key: "online", label: "En línea", color: "var(--on)" },
  { key: "away", label: "Ausente", color: "var(--away)" },
  { key: "dnd", label: "No molestar", color: "var(--dnd)" },
  { key: "invisible", label: "Invisible", color: "var(--off)" },
];

export function statusColor(s) {
  return (STATUSES.find((x) => x.key === s) || { color: "var(--off)" }).color;
}

export function statusLabel(s) {
  return (STATUSES.find((x) => x.key === s) || { label: "Desconectado" }).label;
}

export function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString("es", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

// --- Paneles flotantes y escala de la interfaz ---
//
// La interfaz entera se agranda con `zoom` en <body> (--ui-zoom, app.css).
// OJO: un `position: fixed` DENTRO de esa caja escalada resuelve su left/top
// en las unidades YA escaladas — con zoom 1.35, `left: 1000px` aterriza en el
// píxel 1350 de la pantalla. Los eventos (clientX/clientY) y
// getBoundingClientRect(), en cambio, hablan siempre en píxeles reales de
// viewport. Sin traducir entre ambos mundos, los menús y tarjetas se van fuera
// de la pantalla en cuanto la interfaz no está en tamaño "Normal".
export function uiZoom() {
  try {
    const z = parseFloat(getComputedStyle(document.body).zoom);
    if (z > 0) return z;
  } catch {}
  return 1;
}

// Coloca un panel de w×h junto a (x, y) —coordenadas de viewport, tal cual
// llegan de un evento— sin que se salga de la pantalla. Devuelve {left, top}
// en las unidades que el CSS del elemento entiende.
export function anchorFixed(x, y, w, h, margin = 8) {
  const z = uiZoom();
  const vw = window.innerWidth / z;
  const vh = window.innerHeight / z;
  return {
    left: Math.max(margin, Math.min(x / z, vw - w - margin)),
    top: Math.max(margin, Math.min(y / z, vh - h - margin)),
  };
}

// Color del badge de ping: verde fluido, ámbar regular, rojo malo, gris sin
// dato. Si LiveKit reporta calidad "poor"/"lost" se fuerza el rojo aunque el
// último ping publicado fuera bueno (cubre "se le cayó la red hace un momento").
export function pingColor(rtt, quality = null) {
  if (quality === "poor" || quality === "lost") return "#d43d2a";
  if (rtt == null) return "var(--fnt)";
  if (rtt < 80) return "var(--on, #6bbf59)";
  if (rtt < 180) return "#d9a53b";
  return "#d43d2a";
}
