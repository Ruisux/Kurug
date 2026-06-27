# Kurug — frontend (Svelte + Vite)

SPA del chat Kurug. Mismo backend FastAPI, pensada para servir en web y, más
adelante, empaquetarse con **Tauri** como app de escritorio (una sola base de
código, dos targets).

## Diseño

Estética **sumi-e** (tinta japonesa): minimalista, mucho vacío, un único acento
bermellón (朱). Dos temas conmutables y persistentes:

- **Oscuro "sumi"** (por defecto) — fondo tinta cálido.
- **Claro "washi"** — papel cálido, no blanco nieve.

Tipografías: Shippori Mincho (serif, títulos/kanji) + Zen Kaku Gothic (UI).
Iconos: Tabler. Todo el color sale de variables CSS en `src/app.css`.

## Correr en desarrollo

Necesitas el backend corriendo en `:8000` (ver `../README.md`). Vite proxyea
`/auth`, `/users`, `/channels`, `/presence`, `/dms`, `/voice`, `/uploads`,
`/static` y el WebSocket `/ws` hacia él, así que no hay problemas de CORS.

```bash
npm install
npm run dev      # http://localhost:5173
```

## Build de producción

```bash
npm run build    # genera dist/
```

`dist/` se puede servir como estático desde el propio FastAPI o empaquetar con
Tauri.

## Probar voz/pantalla en la LAN (HTTPS con mkcert)

`getUserMedia`/`getDisplayMedia` solo funcionan en **contexto seguro**. En
`localhost` y en la ventana de Tauri es automático; para abrir desde **otro
dispositivo** de la red hace falta HTTPS. Ya está configurado con **mkcert**:

- El certificado vive en `web/.certs/` (cubre `localhost`, la IP de LAN y el
  hostname `.local`). Está en `.gitignore`.
- Si existen esos certs, `npm run dev` arranca Vite por **HTTPS** y escuchando
  en `0.0.0.0` (toda la LAN). Si no existen, arranca por HTTP normal.

Pasos:

1. (Una vez, en este Mac) confía en la CA local:
   ```bash
   mkcert -install      # pide tu contraseña de macOS
   ```
2. Arranca backend y frontend (en dos terminales):
   ```bash
   cd chat-app && uvicorn app.main:app          # :8000
   cd chat-app/web && npm run dev               # https://0.0.0.0:5173
   ```
3. En este Mac: `https://localhost:5173`.
   En otro dispositivo de la **misma Wi-Fi**, usa el **hostname** (estable aunque
   cambie la IP por DHCP): `https://macbook-pro-rui.local:5173`. La IP también
   sirve (mira la actual con `ipconfig getifaddr en0`), pero cambia con DHCP, y
   habría que regenerar el cert y `allowedHosts` con la nueva.
   Acepta el aviso de seguridad → "Avanzado / Continuar" (sigue siendo contexto
   seguro; el micro funciona).
4. Entra con **dos usuarios distintos**, abre el **mismo canal**, pulsa **Voz**
   en ambos y permite el micrófono. Para compartir pantalla, el icono de
   pantalla.

Notas:
- Ambos equipos deben estar en la misma red. macOS puede pedir permitir
  conexiones entrantes para `node` → permitir.
- Si la IP de LAN cambia, regenera el cert con la nueva IP y actualízala en
  `vite.config.js` (`allowedHosts`). Alternativa sin estos pasos: **Tailscale**
  (te da HTTPS válido automático, sin avisos).

## App de escritorio (Tauri)

El shell de Tauri vive en `src-tauri/`. Requiere el toolchain de Rust
(`rustup`) ya instalado. Comandos:

```bash
npm run desktop         # tauri dev: abre la ventana nativa (arranca Vite solo)
npm run desktop:build   # tauri build: genera el binario/instalador
```

`tauri dev` levanta su propio Vite en `:5173`, así que ese puerto debe estar
libre. Necesita el backend FastAPI corriendo en `:8000` igual que la web.

Pendiente (Fase 2, distribución): en el binario de producción no hay proxy de
Vite, así que el cliente tendrá que apuntar a la URL real del backend
(p. ej. la dirección de Tailscale del server casero) en vez de rutas relativas.
Hoy en `tauri dev` funciona porque usa el Vite con proxy.

## Estructura

```
src/
  main.js              monta la app
  app.css              tema (tokens oscuro + claro)
  App.svelte           login vs shell según sesión
  lib/
    api.js             cliente REST
    realtime.js        sockets de chat y presencia
    stores.js          token + perfil (token persistido)
    theme.js           tema persistente + toggle
    ui.js              helpers (avatar, estados, formato)
  components/
    Login.svelte       registro / login (con katana y marca de agua 道)
    Shell.svelte       orquesta rail + canales + chat + presencia
    Rail.svelte        barra de servidores + tu avatar
    ChannelList.svelte lista y creación de canales
    ChatView.svelte    mensajes en vivo + compositor
    PresencePanel.svelte  conectados agrupados por estado
    ProfileModal.svelte   editar nickname, bio, avatar, color, estado
    Avatar.svelte / Katana.svelte / ThemeToggle.svelte
```
