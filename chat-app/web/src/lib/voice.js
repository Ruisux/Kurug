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
      stream: p.video || null,
      hasVideo: !!p.video,
      volume: p.volume,
      localMuted: p.localMuted,
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
      video: null,
      audioTrack: null,
      audioEl: null,
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
    p.video = new MediaStream([track.mediaStreamTrack]);
    playSound("shareStart"); // alguien empezó a compartir su pantalla
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
    p.video = null;
    playSound("shareStop"); // alguien dejó de compartir
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
    audioCaptureDefaults: {
      deviceId: pr.inputDeviceId || undefined,
      noiseSuppression: pr.noiseSuppression,
      echoCancellation: pr.echoCancellation,
      autoGainControl: pr.autoGainControl,
    },
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
    .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      // LiveKit avisa quién habla (voz por encima del umbral). Iluminamos su
      // avatar en la barra de voz para saber de dónde vienen los sonidos.
      const ids = new Set(speakers.map((s) => s.identity));
      const localId = room?.localParticipant?.identity;
      for (const p of Object.values(peers)) p.speaking = ids.has(p.id);
      voiceState.update((s) => ({ ...s, meSpeaking: localId ? ids.has(localId) : false }));
      publish();
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
    meSpeaking: false,
    peers: {},
    error: micOk ? null : "Sin micrófono: estás solo escuchando.",
  }));
  playSound("join"); // sonido al ENTRAR tú a la voz
  publish();

  // Supresión de ruido avanzada (Krisp): se aplica DESPUÉS de mostrar la UI,
  // pero esperando de verdad a que la pista esté lista, para que quede activa al
  // entrar (antes a veces "parecía activa" y no lo estaba hasta re-togglearla).
  if (micOk) await applyKrisp();
}

export async function leaveVoice() {
  if (get(voiceState).active) playSound("leave"); // sonido al SALIR tú de la voz
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
    meSpeaking: false,
    quality: get(voiceState).quality,
    peers: {},
    error: null,
  });
}

export function toggleMute() {
  if (!room) return;
  const enabled = room.localParticipant.isMicrophoneEnabled;
  room.localParticipant.setMicrophoneEnabled(!enabled);
  playSound(enabled ? "mute" : "unmute");
  // Desmutear también deja de ensordecer (como en Discord).
  voiceState.update((s) => ({ ...s, muted: enabled, deafened: enabled ? s.deafened : false }));
  if (enabled === false) restoreDeafen();
}

function restoreDeafen() {
  for (const p of Object.values(peers)) applyVol(p);
}

export function toggleDeafen() {
  const st = get(voiceState);
  if (!st.deafened) {
    if (room) room.localParticipant.setMicrophoneEnabled(false);
    voiceState.update((s) => ({ ...s, deafened: true, muted: true }));
    playSound("deafen");
  } else {
    if (room) room.localParticipant.setMicrophoneEnabled(true);
    voiceState.update((s) => ({ ...s, deafened: false, muted: false }));
    playSound("undeafen");
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

function screenOpts() {
  const p = SCREEN_PRESETS[get(voiceState).quality] || SCREEN_PRESETS.equilibrado;
  const capture = {
    audio: true, // audio de lo presentado (depende del SO/origen)
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
  try {
    const { capture, publishOpts } = screenOpts();
    await room.localParticipant.setScreenShareEnabled(true, capture, publishOpts);
    voiceState.update((s) => ({ ...s, sharing: true }));
    playSound("shareStart");
    publish();
  } catch (e) {
    /* el usuario canceló el diálogo */
  }
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

// Stream local de pantalla, para previsualizarlo en mi propia UI.
export function localShareStream() {
  if (!room) return null;
  const pub = room.localParticipant.getTrackPublication(Track.Source.ScreenShare);
  const t = pub?.track;
  return t ? new MediaStream([t.mediaStreamTrack]) : null;
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

// Reaplica las constraints del micro (supresión de ruido, eco, AGC) en vivo.
export async function refreshMicConstraints() {
  if (!room || !room.localParticipant.isMicrophoneEnabled) return;
  const pr = get(prefs);
  try {
    await room.localParticipant.setMicrophoneEnabled(true, {
      deviceId: pr.inputDeviceId || undefined,
      noiseSuppression: pr.noiseSuppression,
      echoCancellation: pr.echoCancellation,
      autoGainControl: pr.autoGainControl,
    });
  } catch {}
  await applyKrisp(); // re-publicar el micro descarta el procesador: reaplicarlo
}

// --- Supresión de ruido avanzada (Krisp, modelo de LiveKit) ---
let krispMod = null;       // módulo cargado bajo demanda (trae WASM, ~MB)
let krispProcessor = null; // instancia reutilizable
export let krispSupported = true;

export async function loadKrisp() {
  if (!krispMod) krispMod = await import("@livekit/krisp-noise-filter");
  return krispMod;
}

// Precarga el WASM de Krisp en segundo plano (al abrir la app), para que al
// entrar a la voz el filtro se pueda aplicar YA, sin la demora de la descarga
// que hacía que "pareciera activo pero no lo estuviera" hasta re-togglearlo.
export function preloadKrisp() {
  loadKrisp().catch(() => {});
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

// Aplica o quita el filtro Krisp en la pista del micro según la preferencia.
// Devuelve true si quedó aplicado. Es robusto ante reintentos y procesadores
// obsoletos: si `setProcessor` falla, recrea el procesador y vuelve a intentar.
async function applyKrisp() {
  if (!room) return false;
  const want = get(prefs).krisp;
  const track = await micTrack();
  if (!track) return false;
  try {
    const mod = await loadKrisp();
    krispSupported = !mod.isKrispNoiseFilterSupported || mod.isKrispNoiseFilterSupported();
    if (want && krispSupported) {
      if (!krispProcessor) krispProcessor = mod.KrispNoiseFilter();
      try {
        await track.setProcessor(krispProcessor);
      } catch {
        // El procesador puede haber quedado atado a una sala/pista anterior;
        // recrearlo desde cero y reintentar una vez.
        try { krispProcessor = mod.KrispNoiseFilter(); await track.setProcessor(krispProcessor); }
        catch { return false; }
      }
      return true;
    } else {
      try { await track.stopProcessor(); } catch {}
      return false;
    }
  } catch {
    krispSupported = false;
    return false;
  }
}

export async function setKrisp(on) {
  setPref("krisp", on);
  await applyKrisp();
}
