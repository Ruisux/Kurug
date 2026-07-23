// Cliente de voz/pantalla sobre LiveKit (SFU).
//
// Sustituye a la antigua malla P2P hecha a mano. Cada quien sube UN stream al
// servidor LiveKit y este lo reparte; así escala a 10+ personas. El backend
// (app/routers/voice.py) firma el token de acceso a la sala `channel-{id}`.
//
// Mantenemos el MISMO `voiceState` y las mismas funciones que usaba la UI para
// no tocar VoicePanel/UserMenu más de lo necesario. El audio se reproduce con
// los <audio> que adjunta LiveKit y el volumen por persona (0-100%) se aplica
// sobre ellos. OJO: NO usar `webAudioMix` — en livekit-client 2.x tiene una
// carrera: si la pista se adjunta antes de que exista su AudioContext, el
// <audio> queda sonando a tope SIN mutear en paralelo al GainNode (el volumen
// dejaba de responder: el bot al 1% seguía fuerte). Con una sola ruta de audio
// el control es determinista.

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
  connecting: false, // entre "clic en el canal" y "conectado" (feedback inmediato)
  channelId: null,
  muted: false,
  deafened: false,
  sharing: false,
  cameraOn: false, // mi cámara encendida
  meSpeaking: false, // ilumina mi propio chip cuando hablo
  quality: get(prefs).screenQuality, // clave de SCREEN_PRESETS
  myRtt: null, // MI latencia (ms) al servidor de voz; se difunde por presencia
  peers: {}, // identity -> { id, name, avatar, stream, hasVideo, volume, localMuted, speaking }
  error: null,
});

let room = null;
let peers = {}; // identity -> peer interno
let audioBin = null; // contenedor oculto para los <audio> de LiveKit
let outCtx = null;   // salida de audio: fuente → GainNode → altavoces

function ensureAudioBin() {
  if (!audioBin) {
    audioBin = document.createElement("div");
    audioBin.style.display = "none";
    document.body.appendChild(audioBin);
  }
  return audioBin;
}

// AudioContext de SALIDA (uno por sesión de voz). Permite subir el volumen por
// persona hasta el 200% (un <audio> a pelo se queda en 1.0). Se crea al entrar
// a la voz (gesto del usuario → autoplay OK) y se cierra al salir.
function ensureOutCtx() {
  if (outCtx && outCtx.state !== "closed") return outCtx;
  outCtx = new AudioContext();
  // Si el SO lo suspende (cambio de dispositivo…), reanudarlo solo.
  outCtx.onstatechange = () => {
    if (outCtx && outCtx.state === "suspended") outCtx.resume().catch(() => {});
  };
  const dev = get(prefs).outputDeviceId;
  if (dev && outCtx.setSinkId) outCtx.setSinkId(dev).catch(() => {});
  return outCtx;
}

function closeOutCtx() {
  if (outCtx) { try { outCtx.onstatechange = null; } catch {} }
  try { outCtx?.close(); } catch {}
  outCtx = null;
}

// Monta la cadena de reproducción de UNA pista de audio remota.
// El <audio> MUTEADO debe existir igualmente: sin un elemento consumiendo la
// pista, Chrome no entrega samples a WebAudio (bug conocido de tracks remotos).
// Elemento y cadena se crean en la MISMA pasada síncrona: no existe la ventana
// en la que el <audio> sonara a tope en paralelo (la carrera del viejo
// webAudioMix de LiveKit que nos obligó a quitarlo).
// El <audio> es solo un GRIFO para que Chrome entregue samples a WebAudio: no
// debe sonar nunca, porque quien suena es la cadena con ganancia.
//
// OJO, ESTO ES LA CAUSA DEL "SE ESCUCHA DOBLE": livekit-client desmutea esos
// elementos POR SU CUENTA. `Room.startAudio()` recorre las pistas remotas y
// hace `e.muted = false` sobre todas, y `attachToElement()` repite lo mismo en
// cada attach. Al pasar eso, la persona se oye por DOS caminos a la vez (el
// elemento + la cadena) con unos milisegundos de desfase: el "sonido raro".
// Como `startAudio()` se dispara sola (al entrar, al conceder el micro, al
// volver a la pestaña…), no basta con silenciar una vez: hay que reafirmarlo.
// Silenciamos por partida doble —`muted` Y `volume`, porque LiveKit solo toca
// `muted`— y marcamos el elemento para poder barrerlos después.
function silenceEl(el) {
  if (!el) return;
  el.muted = true;
  el.volume = 0;
  el.dataset.kurugSilenced = "1";
}

// Red de seguridad: vuelve a callar los grifos que LiveKit haya desmuteado.
// Es barato (un par de asignaciones por pista) y da igual POR QUÉ ruta se
// desmutaron: en el siguiente barrido vuelven a estar callados. Los elementos
// SIN marca son los del modo de emergencia (sin WebAudio) y no se tocan: esos
// sí tienen que sonar.
function resilence() {
  if (!audioBin) return;
  for (const el of audioBin.querySelectorAll('audio[data-kurug-silenced="1"]')) {
    if (!el.muted || el.volume !== 0) {
      el.muted = true;
      el.volume = 0;
    }
  }
}

function buildChain(track) {
  const el = track.attach();
  silenceEl(el);
  ensureAudioBin().appendChild(el);
  try {
    const ctx = ensureOutCtx();
    const src = ctx.createMediaStreamSource(new MediaStream([track.mediaStreamTrack]));
    const gain = ctx.createGain();
    src.connect(gain);
    gain.connect(ctx.destination);
    return { el, src, gain };
  } catch {
    // Si WebAudio fallara, que al menos se oiga por el elemento (sin boost).
    // Se le quita la marca: este SÍ debe sonar y el barrido no debe callarlo.
    delete el.dataset.kurugSilenced;
    el.muted = false;
    el.volume = 1;
    return { el, src: null, gain: null };
  }
}

function dropChain(chain, track) {
  if (!chain) return;
  try { chain.src?.disconnect(); } catch {}
  try { chain.gain?.disconnect(); } catch {}
  // Desengancha SOLO su propio elemento: si esta pista ya tiene una cadena
  // nueva montada (re-suscripción), un detach() a secas la dejaría muda.
  try { chain.el ? track?.detach(chain.el) : track?.detach(); } catch {}
  try { chain.el?.pause?.(); } catch {}
  try { if (chain.el) chain.el.srcObject = null; } catch {}
  try { chain.el?.remove(); } catch {}
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
      quality: p.quality || null, // señal de LiveKit (excellent/good/poor/lost)
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
      audioTrack: null,  // su micro
      screenAudio: null, // el audio de su pantalla compartida (pista aparte)
      audioChain: null,  // {el, src, gain} del micro (cadena WebAudio)
      screenChain: null, // ídem del audio de su pantalla
      audioEl: null,
      micMuted: false, // si tiene el micro silenciado
      // El bot de música usa el volumen local guardado; las personas, 100%.
      volume: meta.bot ? clampVol(get(prefs).botVolume) : 100,
      localMuted: false,
      hidden: !!meta.bot,
      isBot: !!meta.bot,
    };
    peers[participant.identity] = p;
  }
  return p;
}

// El volumen va de 0 a 200: por encima de 100 la cadena WebAudio AMPLIFICA
// (GainNode >1), para la gente que se oye baja incluso al máximo.
function clampVol(v) {
  return Math.max(0, Math.min(200, Math.round(+v || 0)));
}

function applyVol(p) {
  const deaf = get(voiceState).deafened;
  const lin = deaf || p.localMuted ? 0 : clampVol(p.volume) / 100; // 0..2
  // Curva perceptual (cuadrática): el oído es logarítmico; con volumen lineal
  // el 50% del slider sonaba casi igual que el 100% y el tramo bajo no hacía
  // nada. 100% = ganancia 1 (sin tocar); 200% = ganancia 4 (~+12 dB).
  const v = lin * lin;
  for (const c of [p.audioChain, p.screenChain]) {
    if (!c) continue;
    if (c.gain) c.gain.gain.value = v;
    else if (c.el) { try { c.el.volume = Math.min(1, v); } catch {} } // fallback sin WebAudio
  }
}

function onSubscribed(track, _pub, participant) {
  const p = peerFor(participant);
  if (track.kind === Track.Kind.Audio) {
    // El audio de una pantalla compartida es una pista APARTE del micro; si se
    // mezclaban, el slider de volumen dejaba de controlar la voz al compartir.
    const isShareAudio = (_pub?.source || track.source) === Track.Source.ScreenShareAudio;
    // OJO: LiveKit reemite TrackSubscribed de una pista que YA estaba sonando
    // cuando se re-suscribe (bache de red, reconexión, adaptiveStream). Si no
    // se suelta antes la cadena anterior, quedan DOS caminos del MISMO audio
    // conectados a la salida y la persona se oye DOBLE, con unos milisegundos
    // de desfase (el "eco raro"). Por eso se libera siempre la ranura primero.
    if (isShareAudio) {
      dropChain(p.screenChain, p.screenAudio);
      p.screenAudio = track;
      p.screenChain = buildChain(track); // <audio> muteado + WebAudio con ganancia
    } else {
      dropChain(p.audioChain, p.audioTrack);
      p.audioTrack = track;
      p.audioChain = buildChain(track);
      p.audioEl = p.audioChain.el;
    }
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
    if (p.screenAudio === track) {
      dropChain(p.screenChain, track);
      p.screenAudio = null;
      p.screenChain = null;
    }
    if (p.audioTrack === track) {
      dropChain(p.audioChain, track);
      p.audioTrack = null;
      p.audioChain = null;
      p.audioEl = null;
    }
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

// Número de intento de conexión: si el usuario se sale (o entra a otro canal)
// mientras un join sigue en vuelo, el join viejo se da cuenta y no pisa nada.
let joinSeq = 0;

export async function joinVoice(channelId) {
  if (get(voiceState).active || room) await leaveVoice();
  const seq = ++joinSeq;

  // Feedback INMEDIATO: la vista de voz muestra "conectando…" desde el clic.
  // Antes todo (token + conexión + primer arranque del micro) pasaba ANTES de
  // actualizar la UI y la primera vez tras abrir la app parecía colgada.
  voiceState.update((s) => ({ ...s, connecting: true, channelId, error: null }));

  let token;
  try {
    ({ token } = await api.voiceToken(channelId));
  } catch (e) {
    if (seq === joinSeq)
      voiceState.update((s) => ({ ...s, connecting: false, error: "No se pudo obtener el acceso a la sala." }));
    return;
  }
  if (seq !== joinSeq) return; // el usuario ya se fue a otra cosa
  // Señalización de LiveKit por la base del servidor (mismo origen en web; la
  // URL horneada en la app de escritorio). El proxy (vite/Caddy) la enruta al
  // servidor LiveKit, así una página HTTPS usa wss:// sin "mixed content".
  const url = wsBase();

  const pr = get(prefs);
  room = new Room({
    adaptiveStream: true,
    dynacast: true,
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
      if (p) {
        dropChain(p.audioChain, p.audioTrack);
        dropChain(p.screenChain, p.screenAudio);
      }
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
      if (p && pub.source === Track.Source.Microphone) { p.micMuted = true; publish(); }
    })
    .on(RoomEvent.TrackUnmuted, (pub, pt) => {
      const p = peers[pt.identity];
      if (p && pub.source === Track.Source.Microphone) { p.micMuted = false; publish(); }
    })
    .on(RoomEvent.ConnectionQualityChanged, (q, pt) => {
      // Señal de calidad por participante (la calcula LiveKit). Complementa al
      // ping numérico: si alguien está "poor/lost", su badge se fuerza a rojo.
      const p = peers[pt.identity];
      if (p) { p.quality = q; publish(); }
    })
    .on(RoomEvent.AudioPlaybackStatusChanged, resilence) // startAudio() acaba de correr
    .on(RoomEvent.Reconnected, resilence) // tras reconectar re-engancha pistas
    .on(RoomEvent.Disconnected, () => { if (get(voiceState).active) leaveVoice(); });

  const r = room;
  try {
    await r.connect(url, token);
  } catch (e) {
    if (seq === joinSeq) {
      voiceState.update((s) => ({ ...s, connecting: false, error: "No se pudo conectar a la voz." }));
      room = null;
    }
    try { r.disconnect(); } catch {}
    return;
  }
  if (seq !== joinSeq) { try { r.disconnect(); } catch {} return; }

  // Contexto de salida listo ANTES de que lleguen las pistas (TrackSubscribed).
  ensureOutCtx();
  // Participantes ya presentes (sus tracks llegan por TrackSubscribed).
  r.remoteParticipants.forEach((pt) => peerFor(pt));

  // Conectado: la UI queda operativa YA. El micro se enciende en segundo plano
  // (la PRIMERA captura tras abrir la app puede tardar segundos en Windows
  // mientras arranca el subsistema de audio; no tiene por qué congelar la
  // entrada a la sala: mientras tanto ya oyes a los demás).
  voiceState.update((s) => ({
    ...s,
    active: true,
    connecting: false,
    channelId,
    muted: false,
    deafened: false,
    sharing: false,
    cameraOn: false,
    meSpeaking: false,
    peers: {},
    error: null,
  }));
  playSound("join"); // sonido al ENTRAR tú a la voz
  publish();
  startLevelMonitor(); // aro verde instantáneo (medición local, no del servidor)
  startRttMonitor();   // mi ping al SFU cada 5 s (se difunde por presencia)

  (async () => {
    // `startAudio()` desmutea TODOS los grifos ya enganchados (los de quien ya
    // estaba en la sala cuando entraste): re-silenciar justo después es lo que
    // evita oírles doble. Es también el motivo de que "a alguien le pasaba
    // siempre": quien ya estaba dentro caía en esta ventana.
    try { await r.startAudio(); } catch {}
    resilence();
    try { await ensureOutCtx().resume(); } catch {}
    // Salida de audio elegida (auriculares/altavoz), si la hay.
    if (pr.outputDeviceId) {
      try { await r.switchActiveDevice("audiooutput", pr.outputDeviceId); } catch {}
    }
    // El micro es opcional: si falla o lo deniegan, entras igual (solo escuchas).
    let micOk = true;
    try {
      await r.localParticipant.setMicrophoneEnabled(true);
    } catch {
      micOk = false;
    }
    resilence(); // conceder el micro emite AudioStreamAcquired -> startAudio()
    if (seq !== joinSeq) return; // ya salimos de la sala mientras tanto
    if (!micOk) {
      voiceState.update((s) => ({ ...s, muted: true, error: "Sin micrófono: estás solo escuchando." }));
      return;
    }
    // Supresión de ruido avanzada: se aplica DESPUÉS de publicar el micro,
    // esperando de verdad a que la pista esté lista, para que quede activa al
    // entrar (antes a veces "parecía activa" y no lo estaba hasta re-togglearla).
    await applyKrisp();
  })();
}

// --- Latencia: MI RTT al servidor de voz (candidate-pair de WebRTC) ---
// OJO: el ping de un REMOTO no se puede medir desde aquí (solo su tramo lo
// conoce él). Cada cliente mide el suyo y lo difunde por presencia
// (voice_state en Shell): así todos ven el ping real de todos.
let rttTimer = 0;

async function measureRtt() {
  if (!room) return;
  try {
    const local = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    let report = local ? await local.getRTCStatsReport?.() : null;
    if (!report) {
      // Sin micro publicado (entré solo a escuchar): la PeerConnection de
      // bajada va al mismo SFU, su RTT sirve igual.
      const anyPeer = Object.values(peers).find((p) => p.audioTrack);
      report = anyPeer ? await anyPeer.audioTrack.getRTCStatsReport?.() : null;
    }
    if (!report) return;
    let rtt = null;
    report.forEach((s) => {
      if (
        s.type === "candidate-pair" &&
        s.state === "succeeded" &&
        (s.nominated || s.selected) &&
        s.currentRoundTripTime != null
      ) {
        rtt = Math.max(1, Math.round((s.currentRoundTripTime * 1000) / 10) * 10);
      }
    });
    if (rtt != null && rtt !== get(voiceState).myRtt) {
      voiceState.update((s) => ({ ...s, myRtt: rtt }));
    }
  } catch {}
}

function startRttMonitor() {
  clearInterval(rttTimer);
  measureRtt();
  rttTimer = setInterval(() => {
    measureRtt();
    // Barrido de seguridad del audio doble: si alguna ruta de LiveKit que no
    // controlamos vuelve a desmutear un grifo, aquí se corrige sola en ≤5 s
    // en vez de quedarse toda la llamada sonando doble.
    resilence();
  }, 5000);
}

function stopRttMonitor() {
  clearInterval(rttTimer);
  rttTimer = 0;
}

// --- Detección LOCAL de quién habla (sin el retardo del servidor) ---
// El evento ActiveSpeakersChanged de LiveKit se calcula en el servidor y llega
// con ~300 ms de retraso y umbral lento: el aro verde iba "a destiempo". Aquí
// medimos el volumen de cada pista de audio EN el cliente cada 40 ms con un
// AnalyserNode: se enciende con el primer golpe de sonido, sin lag.
let lvlCtx = null;   // AudioContext propio del medidor
let lvlTimer = 0;    // setInterval (corre SIEMPRE, por si el pump no dispara)
let lvlPump = null;  // nodo que dispara el tick desde el hilo de AUDIO (sin
                     // throttling: setInterval se frena a 1/s con la ventana
                     // oculta/minimizada y el aro se congelaría)
let lvlNodes = new WeakMap(); // MediaStreamTrack -> AnalyserNode
let lvlState = {};   // id -> { floor, last } (piso de ruido + último pico de voz)
let lvlLastTick = 0; // dedupe entre el pump y el setInterval

const SPEAK_HOLD_MS = 300;   // el aro se mantiene un instante tras el último pico
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

// ¿Está hablando `id`? Un umbral FIJO fallaba en ambos sentidos: con ruido de
// fondo constante (ventilador, estática) el aro se encendía solo, y una voz
// suave nunca lo alcanzaba ("se ilumina cuando quiere"). Ahora cada persona
// lleva su PISO de ruido (baja al instante, sube muy despacio) y cuenta como
// voz lo que sobresale claramente de ese piso, con histéresis para no titilar.
function lvlSpeaking(id, mst, now, buf) {
  const st = lvlState[id] || (lvlState[id] = { floor: 0.003, last: 0 });
  if (mst && mst.readyState === "live") {
    const an = lvlAnalyser(mst);
    if (an) {
      an.getFloatTimeDomainData(buf);
      let e = 0;
      for (let i = 0; i < buf.length; i++) e += buf[i] * buf[i];
      const rms = Math.sqrt(e / buf.length);
      st.floor = rms < st.floor ? rms : Math.min(st.floor * 1.002, 0.05);
      const held = now - st.last < SPEAK_HOLD_MS;
      // Encender exige sobresalir 3x del piso; mantener, solo 2x (histéresis).
      // Suelo bajo (0.006): había voces MUY flojas que se oían pero no
      // encendían el aro; con la puerta de ruido activa el fondo ya llega
      // silenciado, así que bajar el suelo no enciende con ruido.
      const thresh = Math.max(0.006, st.floor * (held ? 2 : 3));
      if (rms >= thresh) st.last = now;
    }
  }
  return now - st.last < SPEAK_HOLD_MS;
}

function startLevelMonitor() {
  stopLevelMonitor();
  try {
    lvlCtx = new AudioContext();
    if (lvlCtx.state === "suspended") lvlCtx.resume().catch(() => {});
    // Si el SO suspende el contexto (cambio de dispositivo…), reanudarlo solo.
    lvlCtx.onstatechange = () => {
      if (lvlCtx?.state === "suspended") lvlCtx.resume().catch(() => {});
    };
  } catch { return; }
  const buf = new Float32Array(512);
  const tick = () => {
    if (!room) return;
    const now = performance.now();
    if (now - lvlLastTick < LVL_TICK_MS - 8) return; // ya midió el otro reloj
    lvlLastTick = now;
    let changed = false;

    // Yo: se mide la pista del micro que se PUBLICA de verdad — la procesada
    // por la supresión de ruido si está activa. Antes se medía la cruda y el
    // aro se encendía con ruido que los demás ni oían.
    const meTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    const meMst = meTrack && !meTrack.isMuted
      ? (krispProcessor?.processedTrack || meTrack.mediaStreamTrack)
      : null;
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

  // Dos relojes a la vez (con dedupe): el ScriptProcessor dispara desde el
  // hilo de audio aunque la ventana esté oculta/minimizada, y el setInterval
  // cubre el caso de que el contexto de audio no arranque o se pause.
  if (lvlCtx.createScriptProcessor) {
    lvlPump = lvlCtx.createScriptProcessor(2048, 1, 1);
    lvlPump.onaudioprocess = tick;
    const mute = lvlCtx.createGain();
    mute.gain.value = 0; // el pump no debe sonar: solo marca el ritmo
    lvlPump.connect(mute);
    mute.connect(lvlCtx.destination);
  }
  lvlTimer = setInterval(tick, LVL_TICK_MS);
}

function stopLevelMonitor() {
  clearInterval(lvlTimer);
  lvlTimer = 0;
  if (lvlPump) {
    try { lvlPump.onaudioprocess = null; lvlPump.disconnect(); } catch {}
    lvlPump = null;
  }
  lvlState = {};
  lvlLastTick = 0;
  lvlNodes = new WeakMap();
  if (lvlCtx) { try { lvlCtx.onstatechange = null; } catch {} }
  try { lvlCtx?.close(); } catch {}
  lvlCtx = null;
}

export async function leaveVoice() {
  joinSeq++; // cancela cualquier join que siga en vuelo
  if (get(voiceState).active) playSound("leave"); // sonido al SALIR tú de la voz
  stopLevelMonitor();
  stopRttMonitor();
  if (room) {
    try { await room.disconnect(); } catch {}
    room = null;
  }
  // Desmontar las cadenas de audio de todos y cerrar el contexto de salida.
  for (const p of Object.values(peers)) {
    dropChain(p.audioChain, p.audioTrack);
    dropChain(p.screenChain, p.screenAudio);
  }
  closeOutCtx();
  dropClone(shareCache);
  dropClone(cameraCache);
  shareCache.track = shareCache.stream = null;
  cameraCache.track = cameraCache.stream = null;
  peers = {};
  // El procesador de Krisp queda atado a la pista/sala de esta sesión; lo
  // descartamos para que el próximo join cree uno limpio (evita fallos al
  // reaplicarlo sobre una sala ya cerrada).
  krispProcessor = null;
  if (audioBin) { audioBin.remove(); audioBin = null; }
  voiceState.set({
    active: false,
    connecting: false,
    channelId: null,
    muted: false,
    deafened: false,
    sharing: false,
    cameraOn: false,
    meSpeaking: false,
    quality: get(voiceState).quality,
    myRtt: null,
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
  p.volume = clampVol(vol);
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
let shareCache = { track: null, stream: null, clone: null };
let cameraCache = { track: null, stream: null, clone: null };

function dropClone(cache) {
  if (cache.clone) { try { cache.clone.stop(); } catch {} }
  cache.clone = null;
}

function cachedStream(cache, source, clone = false) {
  if (!room) return null;
  const t = room.localParticipant.getTrackPublication(source)?.track;
  if (!t) {
    dropClone(cache);
    cache.track = cache.stream = null;
    return null;
  }
  const mst = t.mediaStreamTrack;
  if (cache.track !== mst) {
    dropClone(cache);
    cache.track = mst;
    // clone: la preview usa un CLON del track. Renderizar el MISMO track que
    // se está codificando dispara un bug de color de Chromium (tinte verde)
    // al ponerlo en pantalla completa.
    const use = clone ? (cache.clone = mst.clone()) : mst;
    cache.stream = new MediaStream([use]);
  }
  return cache.stream;
}

// Stream local de pantalla, para previsualizarlo en mi propia UI.
export function localShareStream() {
  return cachedStream(shareCache, Track.Source.ScreenShare, true);
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
  const v = clampVol(vol);
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
  // La reproducción real va por el AudioContext de salida: cambiar SU sink.
  if (outCtx && outCtx.setSinkId) {
    try { await outCtx.setSinkId(deviceId || ""); } catch {}
  }
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
    // La voz es MONO. Algunos micros (interfaces/USB) capturan estéreo y la
    // cadena de supresión procesaba solo el canal izquierdo: a esa persona se
    // le oía por un solo oído. Mono de origen lo elimina de raíz.
    channelCount: 1,
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

  // 2) Crear uno nuevo y aplicarlo (con el nivel de puerta de ruido elegido).
  try {
    krispSupported = isNoiseSupported();
    if (!krispSupported) return false;
    const proc = createNoiseProcessor(get(prefs).noiseGate);
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

// Cambia la intensidad de la puerta de ruido (off/suave/medio/fuerte) en vivo.
// Recrea el procesador porque el nivel se fija al construir la cadena de audio.
export async function setNoiseGate(level) {
  setPref("noiseGate", level);
  if (!room) return;
  if (get(prefs).krisp) await applyKrisp();
}
