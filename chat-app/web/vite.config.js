import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// El backend FastAPI corre en :8000. En desarrollo proxyeamos las rutas de la
// API (y el WebSocket) hacia él, así el frontend usa rutas relativas y no hay
// problemas de CORS. En producción la SPA se sirve desde el mismo origen.
const target = "http://localhost:8000";

// HTTPS local opcional (mkcert): si existen los certs en web/.certs/, Vite
// sirve por HTTPS. Necesario para getUserMedia/getDisplayMedia fuera de
// localhost (p. ej. probar voz entre dos dispositivos de la LAN).
const dir = path.dirname(fileURLToPath(import.meta.url));
const keyPath = path.join(dir, ".certs", "key.pem");
const certPath = path.join(dir, ".certs", "cert.pem");
const https =
  fs.existsSync(keyPath) && fs.existsSync(certPath)
    ? { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
    : undefined;

export default defineConfig(({ mode }) => {
  // Hosts extra permitidos (IP de LAN, hostname .local…) son ESPECÍFICOS de cada
  // máquina, así que no se hornean aquí: se leen de `KURUG_ALLOWED_HOSTS` (lista
  // separada por comas) en un `.env.local` que git ignora. Ejemplo:
  //   KURUG_ALLOWED_HOSTS=192.168.1.22,macbook-pro-rui.local
  const env = loadEnv(mode, dir, "KURUG_");
  const extraHosts = (env.KURUG_ALLOWED_HOSTS || "")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);

  return {
  plugins: [svelte()],
  server: {
    host: true, // escucha en 0.0.0.0 para que otros equipos de la LAN entren
    port: 5173,
    https,
    // localhost siempre; el resto (IP LAN / .local) desde KURUG_ALLOWED_HOSTS.
    allowedHosts: ["localhost", ...extraHosts],
    proxy: {
      "/auth": target,
      "/users": target,
      "/channels": target,
      "/presence": target,
      "/dms": target,
      "/voice": target,
      "/uploads": target,
      "/gifs": target,
      "/static": target,
      "/ws": { target: "ws://localhost:8000", ws: true },
      // Señalización de LiveKit por el MISMO origen (wss) -> sin "mixed content"
      // al probar entre dispositivos de la LAN sobre HTTPS.
      "/rtc": { target: "ws://localhost:7880", ws: true },
      "/twirp": "http://localhost:7880",
    },
  },
  };
});
