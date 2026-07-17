"""
Bot de música de Kurug (LiveKit).

Proceso aparte que:
- obedece a la sala de música del servidor (play/pausa/siguiente…) por el WS
  de control `/ws/music-bot/{music_channel_id}` (sin cambios respecto a antes),
- se une como UN participante más a la VOZ del canal "general" (sala LiveKit
  `channel-{general_id}`) y publica ahí el audio. Quien esté en esa voz lo oye.
- resuelve el audio de YouTube con yt-dlp y lo transmite con ffmpeg (sin descargar).

El control se hace desde el chat de música; el sonido sale en la voz de general.

Config por variables de entorno:
  KURUG_URL          base del servidor (def. http://localhost:8000)
  SECRET_KEY         el mismo del servidor (para el token del WS de control)  [obligatorio]
  BOT_USERNAME       usuario del bot (def. kurug-bot)
  MUSIC_CHANNEL_ID   opcional; si no, se descubre el canal is_music
  VOICE_CHANNEL_ID   opcional; si no, se usa "general" (o el primer canal no-música)
  LIVEKIT_URL        ws del servidor LiveKit (def. ws://localhost:7880)
  LIVEKIT_API_KEY    (def. devkey)
  LIVEKIT_API_SECRET (def. secret)

Ejecutar:
  cd chat-app/bot && SECRET_KEY=... ./.venv/bin/python bot.py
"""
import asyncio
import datetime as dt
import json
import os
import time
import urllib.request

import jwt
import websockets
from yt_dlp import YoutubeDL
from livekit import rtc, api

from audio_track import PcmSource, SAMPLE_RATE, CHANNELS, SAMPLES, FRAME_BYTES, SILENCE

BASE = os.environ.get("KURUG_URL", "http://localhost:8000").rstrip("/")
WS_BASE = BASE.replace("http", "ws", 1)
SECRET = os.environ["SECRET_KEY"]
BOT_USER = os.environ.get("BOT_USERNAME", "kurug-bot")

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")


def mint_token() -> str:
    """JWT de la app (para el WS de control de música)."""
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)
    return jwt.encode({"sub": BOT_USER, "exp": exp}, SECRET, algorithm="HS256")


def _channels(token: str):
    req = urllib.request.Request(BASE + "/channels", headers={"Authorization": f"Bearer {token}"})
    return json.load(urllib.request.urlopen(req))


def discover_music_channel(token: str) -> int:
    env = os.environ.get("MUSIC_CHANNEL_ID")
    if env:
        return int(env)
    for c in _channels(token):
        if c.get("is_music"):
            return c["id"]
    raise SystemExit("No hay canal de música (is_music). Arranca el servidor primero.")


def discover_voice_channel(token: str) -> int:
    """Canal cuya VOZ usará el bot: 'general' por defecto (o el primero no-música)."""
    env = os.environ.get("VOICE_CHANNEL_ID")
    if env:
        return int(env)
    chans = _channels(token)
    for c in chans:
        if not c.get("is_music") and c.get("name") == "general":
            return c["id"]
    for c in chans:
        if not c.get("is_music"):
            return c["id"]
    raise SystemExit("No hay un canal de voz para el bot.")


def livekit_token(room: str) -> str:
    """Token LiveKit del bot: solo publica, marcado como bot en metadata."""
    grants = api.VideoGrants(
        room_join=True, room=room, can_publish=True, can_subscribe=False,
    )
    metadata = json.dumps({"bot": True, "display_name": "Kurug DJ"})
    return (
        api.AccessToken(LIVEKIT_KEY, LIVEKIT_SECRET)
        .with_identity(BOT_USER)
        .with_name("Kurug DJ")
        .with_metadata(metadata)
        .with_grants(grants)
        .to_jwt()
    )


def resolve_audio(video_id: str):
    """URL directa del mejor audio + duración (yt-dlp, sin descargar)."""
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "format": "bestaudio/best",
        # Sin esto, una petición colgada dejaba el "play" atascado minutos.
        "socket_timeout": 10,
        "retries": 2,
        "noplaylist": True,  # aquí siempre es UN vídeo
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    url = info.get("url")
    if not url:  # algunos formatos DASH ponen la url dentro de 'requested_formats'
        for f in info.get("requested_formats") or []:
            if f.get("acodec") != "none":
                url = f.get("url")
                break
    return url, info.get("duration")


# Caché de URLs ya resueltas (las de googlevideo viven varias horas). Hace que
# "anterior" y volver a una canción reciente sean instantáneos, y permite
# pre-resolver la siguiente mientras suena la actual.
_URL_CACHE: dict[str, tuple] = {}
_CACHE_TTL = 3 * 3600  # 3 horas


def resolve_cached(video_id: str):
    hit = _URL_CACHE.get(video_id)
    now = time.time()
    if hit and now - hit[2] < _CACHE_TTL:
        return hit[0], hit[1]
    url, dur = resolve_audio(video_id)
    if url:
        _URL_CACHE[video_id] = (url, dur, now)
    return url, dur


class MusicBot:
    def __init__(self, token: str, music_cid: int, voice_cid: int) -> None:
        self.token = token
        self.music_cid = music_cid
        self.voice_cid = voice_cid
        self.room_name = f"channel-{voice_cid}"
        self.pcm = PcmSource()
        self.control_ws = None
        self.room: rtc.Room | None = None
        self.source: rtc.AudioSource | None = None
        self.loop = asyncio.get_event_loop()
        # Protege el cambio de sala (self.room/self.source) frente al bucle de audio.
        self.voice_lock = asyncio.Lock()
        # Número de orden de reproducción: si llegan varios "play" seguidos
        # (skip skip skip), solo el ÚLTIMO puede arrancar el audio. Sin esto,
        # una canción vieja que tardara más en resolver "ganaba" a la nueva.
        self._play_seq = 0
        self.current_dur: float | None = None  # duración del tema actual (si se sabe)

    # ---------- control (sala de música) ----------
    async def control(self):
        url = f"{WS_BASE}/ws/music-bot/{self.music_cid}?token={self.token}"
        async with websockets.connect(url) as ws:
            self.control_ws = ws
            print("[bot] conectado al control de música")
            async for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "play":
                    await self._play(msg["video_id"], msg.get("position", 0))
                elif t == "pause":
                    self.pcm.pause()
                    self._flush()  # vacía el buffer ya enviado -> pausa instantánea
                elif t == "resume":
                    self.pcm.resume()
                elif t == "stop":
                    self.pcm.stop_playback()
                    self._flush()
                elif t == "prefetch":
                    vid = msg.get("video_id")
                    if vid:
                        asyncio.create_task(self._prefetch(vid))
                elif t == "room":
                    # El servidor indica en qué sala de voz debe sonar la música
                    # (la de quien pidió la canción). Reconectar si cambió.
                    await self._switch_room(msg.get("voice_cid"))
                elif t == "seek":
                    pass  # (futuro) reabrir ffmpeg con -ss

    def _flush(self):
        """Descarta el audio ya encolado en LiveKit (para cortar/cambiar al instante)."""
        if self.source is not None:
            try:
                self.source.clear_queue()
            except Exception:
                pass

    async def _play(self, video_id: str, position: float):
        self._play_seq += 1
        seq = self._play_seq
        # Cortar el audio ACTUAL al instante (antes de resolver el nuevo, que
        # tarda): así siguiente/anterior se sienten inmediatos aunque el tema
        # nuevo tarde una fracción en arrancar.
        self.pcm.stop_playback()
        self._flush()
        url, dur = await self.loop.run_in_executor(None, resolve_cached, video_id)
        if seq != self._play_seq:
            return  # mientras resolvíamos pidieron OTRA canción: no pisarla
        if not url:
            print(f"[bot] no pude resolver audio de {video_id}")
            self._on_ended()  # pasa al siguiente
            return
        self._flush()
        self.current_dur = dur
        self.pcm.play(url, position)
        print(f"[bot] reproduciendo {video_id}")

    async def _prefetch(self, video_id: str):
        """Pre-resuelve (y cachea) una canción para que el cambio sea instantáneo."""
        try:
            await self.loop.run_in_executor(None, resolve_cached, video_id)
        except Exception:
            pass

    def _on_ended(self):
        if self.control_ws is not None:
            asyncio.create_task(self.control_ws.send(json.dumps({"type": "ended"})))

    async def progress_loop(self):
        # Además de la posición se manda la DURACIÓN real (yt-dlp la sabe): las
        # entradas de playlist llegan sin duración y la barra no avanzaba.
        while True:
            await asyncio.sleep(2)
            if self.control_ws is not None and self.pcm.position() > 0:
                try:
                    await self.control_ws.send(json.dumps({
                        "type": "progress",
                        "position": self.pcm.position(),
                        "duration": self.current_dur,
                    }))
                except Exception:
                    pass

    # ---------- voz (LiveKit, solo publica) ----------
    async def _connect_voice(self, voice_cid: int):
        """(Re)conecta a la sala de voz indicada y publica la pista de música."""
        async with self.voice_lock:
            self.source = None  # el bucle deja de capturar mientras cambiamos
            old = self.room
        if old is not None:
            try:
                await old.disconnect()
            except Exception:
                pass
        room_name = f"channel-{voice_cid}"
        room = rtc.Room()
        await room.connect(LIVEKIT_URL, livekit_token(room_name))
        # Buffer de 1 s: absorbe los tirones de red al leer de googlevideo sin
        # cortes. La inmediatez de pausar/saltar NO se pierde: clear_queue()
        # vacía este buffer al instante en pausa/stop/cambio.
        source = rtc.AudioSource(SAMPLE_RATE, CHANNELS, queue_size_ms=1000)
        track = rtc.LocalAudioTrack.create_audio_track("music", source)
        opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        # MÚSICA, no voz: sin estas opciones LiveKit codifica con el perfil de
        # micrófono (Opus a bitrate bajo + DTX que corta los pasajes suaves) y
        # la música sonaba "rara"/apagada. 128 kbps estéreo y DTX/RED fuera.
        opts.dtx = False
        opts.red = False
        opts.audio_encoding.max_bitrate = 128_000
        await room.local_participant.publish_track(track, opts)
        async with self.voice_lock:
            self.room = room
            self.source = source
            self.voice_cid = voice_cid
            self.room_name = room_name
        print(f"[bot] publicando en la voz (sala {room_name})")

    async def _switch_room(self, voice_cid):
        if not isinstance(voice_cid, int) or voice_cid == self.voice_cid:
            return
        try:
            await self._connect_voice(voice_cid)
        except Exception as e:
            print(f"[bot] no pude cambiar a la sala {voice_cid}: {e}")

    async def voice(self):
        await self._connect_voice(self.voice_cid)

        # Bucle de audio: empuja un frame de 20 ms; AudioSource marca el ritmo.
        # Durante un cambio de sala self.source es None: se descarta el frame.
        while True:
            data, ended = await self.loop.run_in_executor(None, self.pcm.read_frame)
            if ended:
                self._on_ended()
            async with self.voice_lock:
                src = self.source
            if src is None:
                continue
            frame = rtc.AudioFrame(data, SAMPLE_RATE, CHANNELS, SAMPLES)
            try:
                await src.capture_frame(frame)
            except Exception:
                pass

    async def run(self):
        await asyncio.gather(self.control(), self.voice(), self.progress_loop())

    async def cleanup(self):
        self.pcm.stop_playback()
        if self.room is not None:
            try:
                await self.room.disconnect()
            except Exception:
                pass
            self.room = None


async def main():
    token = mint_token()
    # Supervisor: si el backend aún no está, o todavía no existe el canal de voz
    # (general), o se cae la conexión, ESPERAMOS y reintentamos en vez de morir.
    # Así el orden de arranque (bot antes que el server/canales) da igual.
    while True:
        try:
            music_cid = discover_music_channel(token)
            voice_cid = discover_voice_channel(token)
        except SystemExit as e:
            print(f"[bot] esperando a que exista el canal de voz… ({e})")
            await asyncio.sleep(5)
            continue
        except Exception as e:
            print(f"[bot] esperando al backend… ({e!r})")
            await asyncio.sleep(5)
            continue

        print(f"[bot] control en canal música: {music_cid} | audio en voz de: {voice_cid}")
        bot = MusicBot(token, music_cid, voice_cid)
        try:
            await bot.run()
        except Exception as e:
            print(f"[bot] caída ({e!r}); reintentando en 3s…")
        finally:
            await bot.cleanup()
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
