"""
Fuente de audio PCM para el bot (LiveKit).

ffmpeg lee la URL directa del audio (resuelta por yt-dlp) y la decodifica a PCM
s16le 48 kHz estéreo. El bot lee bloques de 20 ms y los empuja a un
`rtc.AudioSource` de LiveKit, que se encarga del ritmo y la codificación Opus.

Cuando no hay nada sonando se devuelve silencio, así la pista publicada nunca
se cae al cambiar de canción (solo intercambiamos el subproceso de ffmpeg).
"""
import os
import subprocess

# Ejecutable de ffmpeg. Por defecto se busca en el PATH ("ffmpeg"); como servicio
# de Windows (LocalSystem) el PATH del sistema no siempre lo tiene, asi que se
# puede fijar la ruta absoluta con la variable de entorno FFMPEG_BIN.
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")

SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLES = 960  # 20 ms a 48 kHz (muestras por canal)
FRAME_BYTES = SAMPLES * CHANNELS * 2  # s16 = 2 bytes
SILENCE = b"\x00" * FRAME_BYTES


def _ffmpeg(url: str, start: float = 0.0) -> subprocess.Popen:
    cmd = [FFMPEG, "-nostdin"]
    if start > 0:
        cmd += ["-ss", str(start)]
    cmd += [
        # Arranque rápido: menos análisis y sin buffer de entrada.
        "-probesize", "32k", "-analyzeduration", "0", "-fflags", "nobuffer",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", url,
        # -vn: si el formato resuelto viniera con vídeo (fallback "best"), no
        # gastar CPU decodificándolo — solo interesa el audio.
        "-vn",
        "-f", "s16le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
        "-loglevel", "quiet", "pipe:1",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


class PcmSource:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._paused = False
        self._url: str | None = None
        self._samples = 0  # muestras emitidas del tema actual (para progreso)
        self._resume_at = 0.0

    # ---- control desde el bot ----
    def play(self, url: str, start: float = 0.0) -> None:
        self._url = url
        self._paused = False
        self._open(start)

    def _open(self, start: float) -> None:
        self._kill()
        self._proc = _ffmpeg(self._url, start)
        self._samples = int(start * SAMPLE_RATE)

    def pause(self) -> None:
        # Matamos ffmpeg y recordamos la posición; al reanudar reabrimos ahí.
        if self._paused or self._proc is None:
            return
        self._resume_at = self.position()
        self._paused = True
        self._kill()

    def resume(self) -> None:
        if not self._paused:
            return
        self._paused = False
        if self._url is not None:
            self._open(self._resume_at)

    def stop_playback(self) -> None:
        self._url = None
        self._kill()

    def position(self) -> float:
        return self._samples / SAMPLE_RATE

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

    # ---- lectura de un frame de 20 ms (llamar en executor: bloquea) ----
    def read_frame(self) -> tuple[bytes, bool]:
        """Devuelve (pcm_20ms, ended). ended=True cuando el tema termina."""
        if self._proc is None or self._paused:
            return SILENCE, False
        chunk = self._proc.stdout.read(FRAME_BYTES)
        if not chunk or len(chunk) < FRAME_BYTES:
            self._kill()
            return SILENCE, True
        self._samples += SAMPLES
        return chunk, False
