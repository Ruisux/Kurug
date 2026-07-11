// Cliente de voz/pantalla sobre LiveKit (SFU).
//
// Sustituye a la antigua malla P2P hecha a mano. Cada quien sube UN stream al
// servidor LiveKit y este lo reparte; así escala a 10+ personas. El backend
// (app/routers/voice.py) firma el token de acceso a la sala `channel-{id}`.
//
// Mantenemos el MISMO `voiceState` y las mismas funciones que usaba la UI para
// no tocar VoicePanel/UserMenu más de lo necesario. El audio se reproduce con
// LiveKit (webAudioMix) y el volumen por persona (0-200%) usa su GainNode.

import { writable, get } from "svelte/store";
import { Room, RoomEvent, Track } from "livekit-client";
import { api } from "./api.js";
import { prefs, setPref } from "./prefs.js";
import { playSound } from "./sounds.js";
import { wsBase } from "./server.js";
import { screenPicker } from "./desktop.js";
import { pickScreen } from "./screenshare.js";
import { createNoiseProcessor, preloadNoiseModel, isNoiseSupported } from "./noise.js";

// Presets de calidad al compartir pantalla. Más opciones que solo fluido/nítido.
// VP9 comprime mejor el texto/código que el VP8 por defecto. "res:null" = sin
// reescalar (resolución nativa de tu pantalla). El techo real con 10 personas es
// la SUBIDA del servidor (1 que comparte -> N que miran).
export const SCREEN_PRESETS = {
  fluido:      { label: "Fluido · 1080p 60fps",  hint: "motion", w: 1920, h: 1080, fps: 60, bitrate: 8_000_000 },
  equilibrado: { label: "Equilibrado · 1080p 30fps", hint: "motion", w: 1920, h: 1080, fps: 30, bitrate: 5_000_000 },
  nitido:      { label: "Nítido · 1440p 30fps (texto/código)", hint: "detail", w: 2560, h: 1440, fps: 30, bitrate: 12_000_000 },
  maximo:      { label: "Máximo · 4K 60fps (mucha subida)", hint: "detail", w: 3840, h: 2160, fps: 60, bitrate: 18_000_000 },
};
const SCREEN_CODEC = "vp9"; // mejor que vp8 para pantalla (texto nítido)

// Estado reactivo para la UI (misma forma que la versión mesh).
export const voiceState = writable({
  active: false,
  channelId: null,
  muted: false,
  deafened: false,
  sharing: false,
  cameraOn: false, // mi cámara encendida
  meSpeaking: false, // ilumina mi propio chip cuando hablo
  quality: get(prefs).screenQuality, // clave de SCREEN_PRESETS
  peers: {}, // identity -> { id, name, avatar, stream, hasVideo, volume, localMuted, speaking }
  error: null,
});

let room = null;
let peers = {}; // identity -> peer interno
let audioBin = null; // contenedor oculto para los <audio> de LiveKit

function ensureAudioBin() {
  if (!audioBin) {
    audioBin = document.createElement("div");
    audioBin.style.display = "none";
    document.body.appendChild(audioBin);
  }
  return audioBin;
}

function parseMeta(s) {
  try {
    return JSON.parse(s || "{}") || {};
  } catch {
    return {};
  }
}

function publish() {
  const view = {};
  for (const p of Object.values(peers)) {
    if (p.hidden) continue; // el bot de música no aparece como persona
    view[p.id] = {
      id: p.id,
      name: p.info.display_name,
      avatar: p.info.avatar_url,
      camera: p.camera || null,
      screen: p.screen || null,
      hasCamera: !!p.camera,
      hasScreen: !!p.screen,
      // Compat con la barra de voz antigua (usa stream/hasVideo = pantalla).
      stream: p.screen || null,
      hasVideo: !!p.screen,
      volume: p.volume,
      localMuted: p.localMuted,
      micMuted: !!p.micMuted,
      speaking: !!p.speaking,
    };
  }
  voiceState.update((s) => ({ ...s, peers: view }));
}

function peerFor(participant) {
  let p = peers[participant.identity];
  if (!p) {
    const meta = parseMeta(participant.metadata);
    p = {
      id: participant.identity,
      info: {
        display_name: participant.name || meta.display_name || "…",
        avatar_url: meta.avatar_url || null,
      },
      camera: null, // MediaStream de su cámara
      screen: null, // MediaStream de su pantalla compartida
      audioTrack: null,
      audioEl: null,
      micMuted: false, // si tiene el micro silenciado
      // El bot de música usa el volumen local guardado; las personas, 100%.
      volume: meta.bot ? get(prefs).botVolume : 100,
      localMuted: false,
      hidden: !!meta.bot,
      isBot: !!meta.bot,
    };
    peers[participant.identity] = p;
  }
  return p;
}

function applyVol(p) {
  if (!p.audioTrack) return;
  const deaf = get(voiceState).deafened;
  const v = deaf || p.localMuted ? 0 : p.volume / 100;
  try {
    p.audioTrack.setVolume(v);
  } catch {}
}

function onSubscribed(track, _pub, participant) {
  const p = peerFor(participant);
  if (track.kind === Track.Kind.Audio) {
    p.audioTrack = track;
    p.audioEl = track.attach(); // reproduce (vía webAudioMix)
    ensureAudioBin().appendChild(p.audioEl);
    applyVol(p);
  } else if (track.kind === Track.Kind.Video) {
    const isScreen = (_pub?.source || track.source) === Track.Source.ScreenShare;
    const stream = new MediaStream([track.mediaStreamTrack]);
    if (isScreen) {
      p.screen = stream;
      playSound("shareStart"); // alguien empezó a compartir su pantalla
    } else {
      p.camera = stream; // encendió su cámara
    }
    publish();
  }
}

function onUnsubscribed(track, _pub, participant) {
  const p = peers[participant.identity];
  if (!p) return;
  if (track.kind === Track.Kind.Audio) {
    try { track.detach(); } catch {}
    p.audioTrack = null;
    p.audioEl = null;
  } else if (track.kind === Track.Kind.Video) {
    const isScreen = (_pub?.source || track.source) === Track.Source.ScreenShare;
    if (isScreen) {
      p.screen = null;
      playSound("shareStop"); // alguien dejó de compartir
    } else {
      p.camera = null;
    }
    publish();
  }
}

export async function joinVoice(channelId) {
  if (get(voiceState).active) await leaveVoice();

  let token;
  try {
    ({ token } = await api.voiceToken(channelId));
  } catch (e) {
    voiceState.update((s) => ({ ...s, error: "No se pudo obtener el acceso a la sala." }));
    return;
  }
  // Señalización de LiveKit por la base del servidor (mismo origen en web; la
  // URL horneada en la app de escritorio). El proxy (vite/Caddy) la enruta al
  // servidor LiveKit, así una página HTTPS usa wss:// sin "mixed content".
  const url = wsBase();

  const pr = get(prefs);
  room = new Room({
    adaptiveStream: true,
    dynacast: true,
    webAudioMix: true,
    audioCaptureDefaults: micAudioConstraints(),
  });

  room
    .on(RoomEvent.ParticipantConnected, (pt) => {
      const p = peerFor(pt);
      if (!p.isBot) playSound("join"); // suena al entrar alguien (no el bot)
      publish();
    })
    .on(RoomEvent.ParticipantDisconnected, (pt) => {
      const p = peers[pt.identity];
      if (p && !p.isBot) playSound("leave");
      if (p?.audioEl) try { p.audioTrack?.detach(); } catch {}
      delete peers[pt.identity];
      publish();
    })
    .on(RoomEvent.TrackSubscribed, onSubscribed)
    .on(RoomEvent.TrackUnsubscribed, onUnsubscribed)
    .on(RoomEvent.ParticipantMetadataChanged, (_m, pt) => {
      const p = peers[pt.identity];
      if (!p) return;
      const meta = parseMeta(pt.metadata);
      p.info.avatar_url = meta.avatar_url || p.info.avatar_url;
      p.hidden = !!meta.bot;
      publish();
    })
    .on(RoomEvent.TrackMuted, (pub, pt) => {
      const p = peers[pt.identity];
      if (p && pub.kind === Track.Kind.Audio) { p.micMuted = true; publish(); }
    })
    .on(RoomEvent.TrackUnmuted, (pub, pt) => {
      const p = peers[pt.identity];
      if (p && pub.kind === Track.Kind.Audio) { p.micMuted = false; publish(); }
    })
    .on(RoomEvent.Disconnected, () => { if (get(voiceState).active) leaveVoice(); });

  try {
    await room.connect(url, token);
  } catch (e) {
    voiceState.update((s) => ({ ...s, error: "No se pudo conectar a la voz." }));
    try { room.disconnect(); } catch {}
    room = null;
    return;
  }
  // El micro es opcional: si falla o lo deniegan, entras igual (solo escuchas).
  let micOk = true;
  try {
    await room.localParticipant.setMicrophoneEnabled(true);
  } catch {
    micOk = false;
  }
  try { await room.startAudio(); } catch {}
  // Salida de audio elegida (auriculares/altavoz), si la hay.
  if (pr.outputDeviceId) {
    try { await room.switchActiveDevice("audiooutput", pr.outputDeviceId); } catch {}
  }
  // Participantes ya presentes (sus tracks llegan por TrackSubscribed).
  room.remoteParticipants.forEach((pt) => peerFor(pt));

  voiceState.update((s) => ({
    ...s,
    active: true,
    channelId,
    muted: !micOk,
    deafened: false,
    sharing: false,
    cameraOn: false,
    meSpeaking: false,
    peers: {},
    error: micOk ? null : "Sin micrófono: estás solo escuchando.",
  }));
  playSound("join"); // sonido al ENTRAR tú a la voz
  publish();
  startLevelMonitor(); // aro verde instantáneo (medición local, no del servidor)

  // Supresión de ruido avanzada (Krisp): se aplica DESPUÉS de mostrar la UI,
  // pero esperando de verdad a que la pista esté lista, para que quede activa al
  // entrar (antes a veces "parecía activa" y no lo estaba hasta re-togglearla).
  if (micOk) await applyKrisp();
}

// --- Detección LOCAL de quién habla (sin el retardo del servidor) ---
// El evento ActiveSpeakersChanged de LiveKit se calcula en el servidor y llega
// con ~300 ms de retraso y umbral lento: el aro verde iba "a destiempo". Aquí
// medimos el volumen de cada pista de audio EN el cliente cada 40 ms con un
// AnalyserNode: se enciende con el primer golpe de sonido, sin lag.
let lvlCtx = null;   // AudioContext propio del medidor
let lvlTimer = 0;    // fallback con setInterval si no hay ScriptProcessor
let lvlPump = null;  // nodo que dispara el tick desde el hilo de AUDIO (sin
                     // throttling: setInterval se frena a 1/s con la ventana
                     // oculta/minimizada y el aro se congelaría)
let lvlNodes = new WeakMap(); // MediaStreamTrack -> AnalyserNode
let lvlLast = {};    // id -> timestamp del último pico (para el "hold")

const SPEAK_RMS = 0.02;      // volumen mínimo (RMS) que cuenta como sonido
const SPEAK_HOLD_MS = 220;   // el aro se mantiene un instante tras el último pico
const LVL_TICK_MS = 40;      // 25 mediciones por segundo

function lvlAnalyser(mst) {
  let an = lvlNodes.get(mst);
  if (!an) {
    try {
      const src = lvlCtx.createMediaStreamSource(new MediaStream([mst]));
      an = lvlCtx.createAnalyser();
      an.fftSize = 512; // ~10 ms de ventana: respuesta inmediata
      src.connect(an);  // solo mide; no suena (no va a destination)
      lvlNodes.set(mst, an);
    } catch { return null; }
  }
  return an;
}

function lvlSpeaking(id, mst, now, buf) {
  if (mst && mst.readyState === "live") {
    const an = lvlAnalyser(mst);
    if (an) {
      an.getFloatTimeDomainData(buf);
      let e = 0;
      for (let i = 0; i < buf.length; i++) e += buf[i] * buf[i];
      if (Math.sqrt(e / buf.length) >= SPEAK_RMS) lvlLast[id] = now;
    }
  }
  return now - (lvlLast[id] || 0) < SPEAK_HOLD_MS;
}

function startLevelMonitor() {
  stopLevelMonitor();
  try {
    lvlCtx = new AudioContext();
    if (lvlCtx.state === "suspended") lvlCtx.resume().catch(() => {});
  } catch { return; }
  const buf = new Float32Array(512);
  const tick = () => {
    if (!room) return;
    const now = performance.now();
    let changed = false;

    // Yo: se mide la pista del micro PUBLICADA (si está muteada no cuenta).
    const meTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    const meMst = meTrack && !meTrack.isMuted ? meTrack.mediaStreamTrack : null;
    const meSp = lvlSpeaking("me", meMst, now, buf);
    if (meSp !== get(voiceState).meSpeaking) {
      voiceState.update((s) => ({ ...s, meSpeaking: meSp }));
      changed = true;
    }

    // Los demás: su pista de audio suscrita (el bot no lleva aro: hidden).
    for (const p of Object.values(peers)) {
      const sp = lvlSpeaking(p.id, p.micMuted ? null : p.audioTrack?.mediaStreamTrack, now, buf);
      if (sp !== !!p.speaking) { p.speaking = sp; changed = true; }
    }
    if (changed) publish();
  };

  // Reloj en el hilo de audio: un ScriptProcessor de 2048 muestras dispara
  // cada ~43 ms a 48 kHz pase lo que pase con la ventana. Si no existiera,
  // caemos a setInterval (con ventana visible funciona igual de bien).
  if (lvlCtx.createScriptProcessor) {
    lvlPump = lvlCtx.createScriptProcessor(2048, 1, 1);
    lvlPump.onaudioprocess = tick;
    const mute = lvlCtx.createGain();
    mute.gain.value = 0; // el pump no debe sonar: solo marca el ritmo
    lvlPump.connect(mute);
    mute.connect(lvlCtx.destination);
  } else {
    lvlTimer = setInterval(tick, LVL_TICK_MS);
  }
}

function stopLevelMonitor() {
  clearInterval(lvlTimer);
  lvlTimer = 0;
  if (lvlPump) {
    try { lvlPump.onaudioprocess = null; lvlPump.disconnect(); } catch {}
    lvlPump = null;
  }
  lvlLast = {};
  lvlNodes = new WeakMap();
  try { lvlCtx?.close(); } catch {}
  lvlCtx = null;
}

export async function leaveVoice() {
  if (get(voiceState).active) playSound("leave"); // sonido al SALIR tú de la voz
  stopLevelMonitor();
  if (room) {
    try { await room.disconnect(); } catch {}
    room = null;
  }
  peers = {};
  // El procesador de Krisp queda atado a la pista/sala de esta sesión; lo
  // descartamos para que el próximo join cree uno limpio (evita fallos al
  // reaplicarlo sobre una sala ya cerrada).
  krispProcessor = null;
  if (audioBin) { audioBin.remove(); audioBin = null; }
  voiceState.set({
    active: false,
    channelId: null,
    muted: false,
    deafened: false,
    sharing: false,
    cameraOn: false,
    meSpeaking: false,
    quality: get(voiceState).quality,
    peers: {},
    error: null,
  });
}

export async function toggleMute() {
  if (!room) return;
  const enabled = room.localParticipant.isMicrophoneEnabled;
  playSound(enabled ? "mute" : "unmute");
  // Desmutear también deja de ensordecer (como en Discord).
  voiceState.update((s) => ({ ...s, muted: enabled, deafened: enabled ? s.deafened : false }));
  await room.localParticipant.setMicrophoneEnabled(!enabled);
  // Al DESMUTEAR se re-publica el micro: reaplicar Krisp para que no se caiga.
  if (enabled === false) {
    restoreDeafen();
    await applyKrisp();
  }
}

function restoreDeafen() {
  for (const p of Object.values(peers)) applyVol(p);
}

export async function toggleDeafen() {
  const st = get(voiceState);
  if (!st.deafened) {
    voiceState.update((s) => ({ ...s, deafened: true, muted: true }));
    playSound("deafen");
    if (room) await room.localParticipant.setMicrophoneEnabled(false);
  } else {
    voiceState.update((s) => ({ ...s, deafened: false, muted: false }));
    playSound("undeafen");
    if (room) {
      await room.localParticipant.setMicrophoneEnabled(true);
      await applyKrisp(); // re-publicar el micro: reaplicar el filtro
    }
  }
  for (const p of Object.values(peers)) applyVol(p);
}

export function setPeerVolume(id, vol) {
  const p = peers[id];
  if (!p) return;
  p.volume = Math.max(0, Math.min(200, Math.round(vol)));
  applyVol(p);
  publish();
}

export function setPeerMuted(id, on) {
  const p = peers[id];
  if (!p) return;
  p.localMuted = !!on;
  applyVol(p);
  publish();
}

export async function kickPeer(id) {
  const { channelId } = get(voiceState);
  if (channelId == null) return;
  try { await api.kickVoice(channelId, id); } catch {}
}

function screenOpts(wantAudio = true) {
  const p = SCREEN_PRESETS[get(voiceState).quality] || SCREEN_PRESETS.equilibrado;
  const capture = {
    audio: !!wantAudio, // audio de lo presentado (sistema); en Electron = loopback
    contentHint: p.hint,
    // El navegador da min(pantalla, este tope): en 1080p sale 1080p, etc.
    resolution: { width: p.w, height: p.h, frameRate: p.fps },
  };
  const publishOpts = {
    videoCodec: SCREEN_CODEC,
    screenShareEncoding: { maxBitrate: p.bitrate, maxFramerate: p.fps },
  };
  return { capture, publishOpts };
}

// Publica la pantalla con la calidad y el audio elegidos (reintenta sin audio
// del sistema si falla, para que compartir NUNCA se quede a medias).
async function startShare(wantAudio, choice) {
  try {
    const { capture, publishOpts } = screenOpts(wantAudio);
    await room.localParticipant.setScreenShareEnabled(true, capture, publishOpts);
    voiceState.update((s) => ({ ...s, sharing: true, error: null }));
    playSound("shareStart");
    publish();
    return true;
  } catch (e) {
    // Si falló CON audio del sistema (Electron), reintentar solo vídeo.
    if (wantAudio && choice && !choice.native) {
      screenPicker.setChoice({ id: choice.id, audio: false });
      try {
        const { capture, publishOpts } = screenOpts(false);
        await room.localParticipant.setScreenShareEnabled(true, capture, publishOpts);
        voiceState.update((s) => ({
          ...s, sharing: true,
          error: "No se pudo capturar el audio del sistema; se comparte solo vídeo.",
        }));
        playSound("shareStart");
        publish();
        return true;
      } catch {}
    }
    return false; // el usuario canceló o no se pudo
  }
}

export async function toggleShare() {
  if (!room) return;
  const sharing = room.localParticipant.isScreenShareEnabled;
  if (sharing) {
    await room.localParticipant.setScreenShareEnabled(false);
    voiceState.update((s) => ({ ...s, sharing: false }));
    playSound("shareStop");
    publish();
    return;
  }

  // Selector: en Electron es NUESTRO modal (fuente + calidad + audio); en
  // web/Tauri se usa el selector del navegador.
  const choice = await pickScreen();
  if (choice == null) return; // cancelado en el selector propio

  let wantAudio = true;
  if (!choice.native) {
    if (choice.quality) setQuality(choice.quality); // aplica la calidad elegida
    wantAudio = !!choice.audio;
    screenPicker.setChoice({ id: choice.id, audio: wantAudio });
  }
  await startShare(wantAudio, choice);
}

export async function setQuality(q) {
  if (!SCREEN_PRESETS[q]) return;
  setPref("screenQuality", q); // recordar la elección
  voiceState.update((s) => ({ ...s, quality: q }));
  // Si ya se está compartiendo, re-publicar con la nueva preferencia.
  if (room && room.localParticipant.isScreenShareEnabled) {
    try {
      await room.localParticipant.setScreenShareEnabled(false);
      const { capture, publishOpts } = screenOpts();
      await room.localParticipant.setScreenShareEnabled(true, capture, publishOpts);
    } catch {}
  }
}

// Streams locales para previsualizar en mi propia UI. CACHEADOS: si cada
// llamada devolviera un `new MediaStream(...)`, cada re-render de Svelte
// reasignaría un srcObject "nuevo" al <video> y este se reiniciaría -> el
// parpadeo constante al compartir/ver. Con la caché, mientras la pista sea la
// misma se devuelve SIEMPRE el mismo objeto y el vídeo ni se entera.
let shareCache = { track: null, stream: null };
let cameraCache = { track: null, stream: null };

function cachedStream(cache, source) {
  if (!room) return null;
  const t = room.localParticipant.getTrackPublication(source)?.track;
  if (!t) { cache.track = cache.stream = null; return null; }
  const mst = t.mediaStreamTrack;
  if (cache.track !== mst) {
    cache.track = mst;
    cache.stream = new MediaStream([mst]);
  }
  return cache.stream;
}

// Stream local de pantalla, para previsualizarlo en mi propia UI.
export function localShareStream() {
  return cachedStream(shareCache, Track.Source.ScreenShare);
}

// --- Cámara ---
export async function toggleCamera() {
  if (!room) return;
  const on = room.localParticipant.isCameraEnabled;
  try {
    await room.localParticipant.setCameraEnabled(!on, {
      deviceId: get(prefs).cameraDeviceId || undefined,
    });
    voiceState.update((s) => ({ ...s, cameraOn: !on }));
    publish();
  } catch (e) {
    voiceState.update((s) => ({ ...s, error: "No se pudo acceder a la cámara." }));
  }
}

// Stream local de la cámara, para verme a mí mismo (cacheado, ver arriba).
export function localCameraStream() {
  return cachedStream(cameraCache, Track.Source.Camera);
}

// --- Volumen del bot de música (local, por persona) ---
export function setBotVolume(vol) {
  const v = Math.max(0, Math.min(200, Math.round(vol)));
  setPref("botVolume", v);
  for (const p of Object.values(peers)) {
    if (p.isBot) {
      p.volume = v;
      applyVol(p);
    }
  }
}

// --- Dispositivos de audio y supresión de ruido ---
export async function listAudioDevices() {
  // Pedimos permiso primero para que los nombres de los dispositivos aparezcan.
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
  } catch {}
  const devs = await navigator.mediaDevices.enumerateDevices();
  return {
    inputs: devs.filter((d) => d.kind === "audioinput"),
    outputs: devs.filter((d) => d.kind === "audiooutput"),
  };
}

export async function setInputDevice(deviceId) {
  setPref("inputDeviceId", deviceId);
  if (room) {
    try { await room.switchActiveDevice("audioinput", deviceId || "default"); } catch {}
    await applyKrisp(); // el cambio de micro reinicia la pista: reaplicar
  }
}

export async function setOutputDevice(deviceId) {
  setPref("outputDeviceId", deviceId);
  if (room) {
    try { await room.switchActiveDevice("audiooutput", deviceId || "default"); } catch {}
  }
}

// Constraints de captura del micro. La supresión del NAVEGADOR va SIEMPRE
// apagada: la única supresión de ruido es la nuestra (RNNoise, ver noise.js);
// dos filtros en cadena degradaban la voz. El eco y el AGC sí se mantienen.
function micAudioConstraints() {
  const pr = get(prefs);
  return {
    deviceId: pr.inputDeviceId || undefined,
    noiseSuppression: false,
    echoCancellation: pr.echoCancellation,
    autoGainControl: pr.autoGainControl,
  };
}

// Reaplica las constraints del micro (eco, AGC) en vivo.
export async function refreshMicConstraints() {
  if (!room || !room.localParticipant.isMicrophoneEnabled) return;
  try {
    await room.localParticipant.setMicrophoneEnabled(true, micAudioConstraints());
  } catch {}
  await applyKrisp(); // re-publicar el micro descarta el procesador: reaplicarlo
}

// --- Supresión de ruido (RNNoise, la tecnología del Discord clásico) ---
// El paquete de Krisp de LiveKit exigía licencia de LiveKit Cloud y en nuestro
// servidor auto-hospedado NO suprimía nada. Detalles en lib/noise.js.
let krispProcessor = null; // procesador RNNoise activo en la pista del micro
export let krispSupported = true;

// Precarga el WASM de RNNoise en segundo plano (al abrir la app), para que al
// entrar a la voz el filtro se aplique YA, sin la demora de la descarga.
export function preloadKrisp() {
  if (isNoiseSupported()) preloadNoiseModel().catch(() => {});
}

// Espera a que la pista del micro esté publicada (tras setMicrophoneEnabled la
// publicación puede tardar un instante en aparecer). Reintenta unas veces.
async function micTrack(tries = 10) {
  for (let i = 0; i < tries; i++) {
    const t = room?.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    if (t) return t;
    await new Promise((r) => setTimeout(r, 60));
  }
  return null;
}

// Aplica o quita el filtro RNNoise en la pista del micro según la preferencia.
// BLINDAJE: siempre quita el procesador anterior (lo destruye) y, si se quiere
// supresión, crea uno NUEVO. Reutilizar la instancia entre reinicios del micro
// (mutear/reconectar) deja un procesador "muerto" que saca silencio.
async function applyKrisp() {
  if (!room) return false;
  const track = await micTrack();
  if (!track) return false;

  // 1) Quitar SIEMPRE el procesador que hubiera (LiveKit lo destruye).
  try { await track.stopProcessor(); } catch {}
  krispProcessor = null;

  if (!get(prefs).krisp) return false; // supresión apagada: micro limpio.

  // 2) Crear uno nuevo y aplicarlo.
  try {
    krispSupported = isNoiseSupported();
    if (!krispSupported) return false;
    const proc = createNoiseProcessor();
    await track.setProcessor(proc);
    krispProcessor = proc;
    return true;
  } catch (e) {
    // Si algo falla, dejamos el micro SIN filtro (mejor voz cruda que silencio).
    krispSupported = false;
    krispProcessor = null;
    try { await track.stopProcessor(); } catch {}
    console.warn("Supresión de ruido:", e);
    return false;
  }
}

export async function setKrisp(on) {
  setPref("krisp", on);
  if (!room) return;
  await applyKrisp(); // aplica/quita el filtro en vivo, sin re-capturar el micro
}
