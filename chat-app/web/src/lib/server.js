// Base del servidor.
//
// - Web / desarrollo: vacío -> rutas relativas al mismo origen (Vite proxya en
//   dev; en prod la SPA se sirve desde el mismo dominio).
// - App de escritorio (Tauri): se hornea en compilación con VITE_KURUG_SERVER
//   (p. ej. https://kurug.tu-tailnet.ts.net), porque el binario no tiene proxy
//   y las rutas relativas no llegarían al servidor.
const RAW = (import.meta.env.VITE_KURUG_SERVER || "").replace(/\/+$/, "");

export const SERVER = RAW; // "" o "https://host"

// URL HTTP(S) para una ruta de API/estáticos.
export function apiUrl(path) {
  return SERVER + path;
}

// Base WebSocket (ws/wss) para chat, presencia y señalización de LiveKit.
export function wsBase() {
  if (SERVER) return SERVER.replace(/^http/, "ws"); // https->wss, http->ws
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
}

// URL de un recurso multimedia (avatar, imagen, archivo). Prefija las rutas
// locales (/static, /uploads) con la base del servidor en la app de escritorio;
// deja intactas las externas (GIFs de Giphy/Tenor) y data:/blob:.
export function mediaUrl(u) {
  if (!u) return u;
  if (/^(https?:|data:|blob:)/.test(u)) return u;
  if (SERVER && u.startsWith("/")) return SERVER + u;
  return u;
}
