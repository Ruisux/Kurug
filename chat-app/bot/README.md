# Kurug — bot de música

Proceso aparte que se une como **un participante más** a la voz de **general**
(sala LiveKit `channel-{id}`) y publica ahí la música. El control se hace desde
el chat de música; el sonido sale en la voz de general.

Cómo funciona:
- El servidor manda la cola/estado por el WS de control (`/ws/music-bot`):
  qué suena, play/pausa, siguiente, loop, aleatorio.
- El bot resuelve el audio de YouTube con `yt-dlp` (sin descargar: saca la URL
  directa) y lo decodifica con `ffmpeg` a PCM, que empuja a un `AudioSource` de
  **LiveKit** (este lo codifica a Opus y lo reparte a los oyentes).
- Spotify/Apple Music: el servidor saca el título y lo busca en YouTube.
- Va marcado como bot (`metadata.bot`), así la UI lo oculta de la lista de gente.
- Tiene un supervisor: si se cae una conexión, reintenta solo.

## Requisitos
- `ffmpeg` en el PATH (`brew install ffmpeg` / `apt install ffmpeg`).
- Un servidor **LiveKit** corriendo (en dev: `livekit-server --dev --node-ip 127.0.0.1`).
- Entorno del bot:
  ```bash
  cd chat-app/bot
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
  ```

## Ejecutar (desarrollo)
El backend y LiveKit deben estar corriendo.
```bash
cd chat-app/bot
SECRET_KEY="<el mismo del servidor>" ./.venv/bin/python bot.py
```

Variables de entorno:
- `KURUG_URL` (def. `http://localhost:8000`)
- `BOT_USERNAME` (def. `kurug-bot`)
- `MUSIC_CHANNEL_ID` (si no, descubre el canal `is_music`)
- `VOICE_CHANNEL_ID` (si no, usa el canal `general`)
- `LIVEKIT_URL` (def. `ws://localhost:7880`), `LIVEKIT_API_KEY` (def. `devkey`),
  `LIVEKIT_API_SECRET` (def. `secret`). En producción el bot habla con LiveKit
  por loopback (`ws://127.0.0.1:7880`), ver `deploy/kurug-bot.service`.

## Uso
1. Únete a la voz de **#general** (botón Voz, o "Unirse para escuchar" en música).
2. En la pestaña **música**, pega un link de YouTube/Spotify/Apple Music o
   escribe una canción.
3. Controla con play/pausa, siguiente, anterior, aleatorio, loop y la cola.

## Notas
- Reproducir audio de YouTube desde el server va contra sus ToS; uso personal,
  tu decisión.
- Si el bot no arranca por SSL (certificados), `pip install certifi` en su venv
  (ya está en requirements).
