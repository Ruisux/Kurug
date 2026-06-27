# CLAUDE.md

Contexto del proyecto para Claude Code. Léelo antes de proponer cambios.

## Qué es esto

Mini Chat: un chat propio, liviano y auto-hospedado (alternativa local a
Discord). Meta final: añadir voz y compartir pantalla para un grupo pequeño,
corriendo en un PC con Ubuntu en casa. Prioridad: bajo consumo de recursos.

## Stack

- Python 3 + FastAPI
- SQLAlchemy 2.0 (sintaxis nueva: `Mapped`, `mapped_column`, `select(...)`)
- Pydantic v2
- WebSockets (chat en tiempo real)
- SQLite por defecto; PostgreSQL opcional (solo cambia `DATABASE_URL` en `.env`)

## Estructura

```
app/
  main.py          arranca la app y conecta routers (el esquema lo crea Alembic)
  config.py        configuración leída de .env (pydantic-settings); SECRET_KEY obligatoria
  database.py      engine + SessionLocal + Base
  models.py        tablas: User (con perfil), Channel, Message
  schemas.py       validación Pydantic (separada de models a propósito)
  security.py      hashing bcrypt + JWT
  deps.py          dependencias: get_db, get_current_user
  ws_manager.py    ConnectionManager (broadcast por canal, EN MEMORIA)
  presence.py      PresenceManager (presencia GLOBAL + estados, EN MEMORIA)
  routers/
    auth.py        /auth/register, /auth/login
    users.py       /users/me, /users/{id}  (perfil: nickname, bio, color, estado)
    avatars.py     /users/me/avatar  (subida de foto, Pillow -> static/avatars)
    presence.py    /presence  (REST: conectados; el vivo va por WS)
    channels.py    /channels, /channels/{id}/messages
    ws.py          /ws/{channel_id} (chat) y /ws/presence (presencia)  (WebSocket)
alembic/           migraciones (env.py usa Base.metadata + settings.database_url)
tests/             pytest (TestClient): auth, perfil, avatar, presencia, chat
web/               SPA Svelte + Vite (frontend "Kurug"); proxyea al backend
static/index.html  cliente de prueba viejo (la UI real es web/)
deploy/            systemd + guía de despliegue
```

## Frontend (web/)

SPA en **Svelte + Vite** con tema sumi-e (oscuro "sumi" / claro "washi"),
nombre de producto **Kurug**. En dev: backend en `:8000` y `npm run dev` en
`web/` (`:5173`, proxyea API y WebSocket). Detalles en `web/README.md`. El
acento bermellón se personaliza por usuario (`accent_color`).

## Cómo correr

Desarrollo (Mac):
```bash
source .venv/bin/activate
alembic upgrade head        # crea/actualiza el esquema antes de arrancar
uvicorn app.main:app --reload
```
Producción (Ubuntu): ver `deploy/DEPLOY.md` (servicio systemd, `--host 0.0.0.0`).

## Convenciones

- Comentarios y mensajes de error en español.
- Schemas de Pydantic SIEMPRE separados de los modelos de la BD. Nunca exponer
  `password_hash` al cliente.
- Un router por dominio en `app/routers/`. Endpoints autenticados dependen de
  `CurrentUser`; los que tocan la BD dependen de `DbSession` (ver `deps.py`).
- Usar `select(...)` de SQLAlchemy 2.0, no la API vieja `query(...)`.

## Restricciones importantes (NO romper sin avisar)

1. **Un solo worker de uvicorn.** El `ConnectionManager` vive en memoria, así
   que con `--workers >1` el broadcast se rompe (cada worker tiene su propia
   lista). Antes de escalar a varios workers/instancias hay que migrar el
   broadcast a Redis Pub/Sub. No sugerir multi-worker sin eso.
2. **Voz y compartir pantalla = LiveKit (SFU).** Cada quien sube UN stream al
   servidor LiveKit y este lo reparte (escala a 10+). El backend solo firma el
   token de acceso a la sala `channel-{id}` (`routers/voice.py`). NO implementar
   codecs ni transporte de media a mano (antes había una malla P2P propia, ya
   retirada). El servidor LiveKit corre aparte (Docker en prod, binario en dev).
3. **Screen share requiere HTTPS** (contexto seguro del navegador). `http://IP`
   local no sirve para capturar pantalla/micrófono; `localhost` sí. En LAN la
   salida simple es Tailscale (HTTPS automático) o `mkcert`.
4. **Seguridad de despliegue**: no exponer el puerto del router a internet.
   Acceso remoto vía Tailscale o Cloudflare Tunnel.
5. **Nunca commitear** `.env` ni archivos `*.db` (ya están en `.gitignore`).

## Roadmap (de más fácil a más difícil)

1. ✅ Migraciones con Alembic.
2. ✅ Presencia: PresenceManager GLOBAL + estados (online/away/dnd/invisible),
   por WS `/ws/presence` y REST `GET /presence`.
3. ✅ Perfiles: nickname, avatar, bio, color de acento, estado.
4. ✅ Cliente web: SPA en **Svelte** (`web/`) — chat, presencia en vivo, perfil,
   tema oscuro/claro.
5. ✅ Shell de **Tauri** (`web/src-tauri/`): la misma SPA abre en ventana nativa
   (`npm run desktop`). Falta la distribución pulida (iconos, instalador, firma)
   y apuntar el binario de producción a la URL real del backend (no hay proxy).
6. ✅ Mensajes directos (DMs): tabla `direct_messages`; REST `GET /dms/{id}` y
   `GET /dms/conversations`; envío/entrega en vivo por el WS de presencia.
7. ✅ Roles: `User.is_admin` (primer usuario = admin). Admin borra canales;
   autor o admin borra mensajes (en vivo por el WS de chat).
8. ✅ Notificaciones de escritorio (plugin Tauri) con fallback a la Web
   Notifications API; solo avisa si la ventana no tiene foco.
9. ✅ Voz y screen share con **LiveKit (SFU)**. El backend firma el token
   (`POST /voice/token/{channel_id}`, sala `channel-{id}`) y modera
   (`POST /voice/kick/...`). Cliente en `web/src/lib/voice.js` (`livekit-client`,
   `webAudioMix` para volumen 0-200%) + `VoicePanel.svelte`. El servidor LiveKit
   corre aparte (dev: `livekit-server --dev --node-ip 127.0.0.1`). En prod hay
   que configurar `node_ip` (IP pública/LAN) y abrir los puertos UDP, o LiveKit
   no establece media. Config en `app/config.py` (`livekit_*`).
10. ✅ Bot de música: proceso aparte (`bot/`, **livekit** + ffmpeg + yt-dlp) que
    se une como UN participante (oculto, `metadata.bot`) a la VOZ de **general**
    y publica el audio (sin descargar). Control por el chat de música (WS
    `/ws/music-bot`, sin cambios). Backend: `app/music.py` + `app/music_resolve.py`
    + `routers/music.py`. UI: `MusicRoom.svelte`. El lifespan de `main.py` crea el
    usuario `kurug-bot` y el canal música. Cómo correrlo: `bot/README.md`.
11. ✅ Adjuntos pesados: `POST /uploads/file` escribe a disco EN STREAMING (por
    trozos, no carga el archivo en memoria); límite `MAX_UPLOAD_MB` (def. 2048).
    Columnas `file_url/file_name/file_size` en Message y DirectMessage. El clip
    del compositor acepta cualquier archivo (imágenes -> inline, resto -> tarjeta
    de descarga) con barra de progreso (XHR). Caddy: subir `request_body.max_size`.
12. ✅ Pegar imágenes del portapapeles: handler `paste` en el compositor; sube por
    `/uploads/image` (los GIF se guardan sin recodificar para no perder animación).
13. ✅ Fijar mensajes: columna `pinned_at` en Message; comando WS `pin` (toggle,
    autor o admin) que difunde `pinned`; `GET /channels/{id}/pins`. UI: botón en la
    cabecera (panel de fijados) y en las acciones del mensaje.
14. ✅ GIFs (Giphy): `routers/gifs.py` proxyea Giphy con la key del server
    (`GIPHY_API_KEY`); sin key responde 503 y el picker lo indica. Los GIF se
    envían como `image_url` a media*.giphy.com (hotlink, sin guardar). La
    validación de `image_url` acepta `*.giphy.com` y `*.tenor.com` por HTTPS.
    UI: `GifPicker.svelte` (búsqueda + grid) desde el compositor.
15. ✅ Cuentas con correo + verificación: `User.email` (único), `email_verified`,
    `verification_code/_expires`. Registro en 2 pasos (`/auth/register` crea
    no-verificado y envía código por SMTP; `/auth/verify` confirma y devuelve
    token; `/auth/resend`). Login por usuario O correo, bloquea si no verificado.
    `username` es ahora un handle corto (para @menciones); el correo es privado
    (solo en `/users/me`). Correo por `app/mailer.py` (Gmail SMTP, ver `.env`).

Notas de WS: `/ws/presence` maneja `sync_profile` y `dm`. `/ws/{channel_id}`
maneja chat (`message`/`delete`/`edit`/`react`) y emite `channel_activity` global
para los no leídos. `/ws/music/{id}` (UI) y `/ws/music-bot/{id}` (bot) = música.
Los handlers WS usan **sesiones de BD cortas** (no retienen conexión mientras
esperan), clave para soportar ~10 personas sin agotar el pool.
La voz/pantalla NO usa WS propio: va por LiveKit (ver arriba).

## Decisiones de stack ya tomadas (no reabrir sin avisar)

- Frontend nuevo = **Svelte** (bundles pequeños, encaja con la prioridad de
  ligereza). El `static/index.html` actual es solo el cliente de prueba.
- Escritorio = **Tauri** (webview del sistema, binarios de pocos MB), NO Electron.
- Avatares en el **filesystem** del server (`static/avatars/`), no object storage.
- **Tipografía:** cuerpo/UI = **Poppins** (`.display` no); títulos/branding latinos =
  **Sora** (clase `.display`; `.display.title` = Bold 700, resto SemiBold 600);
  botones/CTA = Poppins Medium (500). Las marcas kanji (刃 道 音 間) siguen en
  **Shippori Mincho** (clase `.serif`) porque Sora/Poppins no tienen kanji.
- **Acento personalizable:** `accent_color` del perfil tiñe TODO lo que usa el
  acento vía `--shu` y `--shu-rgb` (tintes `rgba(var(--shu-rgb), …)`) y `--shu-deep`
  (hover), aplicados en `App.svelte`. Los colores base del tema (claro/oscuro) y
  los semánticos (estados) NO cambian.

## Al terminar una tarea

- Si tocaste `app/models.py`, generar y aplicar la migración Alembic.
- Correr los tests: `pytest -q` (todos en verde).
- Probar que el server arranca: `alembic upgrade head && uvicorn app.main:app`.
- Si tocaste el flujo de chat, verificar con dos clientes que el broadcast y la
  persistencia siguen funcionando.
