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
