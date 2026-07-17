// Estado de música GLOBAL: la conexión de control vive a nivel de app (Shell),
// así el estado (qué suena, cola…) está disponible en toda la app — para el
// reproductor completo y para la mini-barra — aunque navegues entre canales.

import { writable, get } from "svelte/store";
import { token } from "./stores.js";
import { reconnectingSocket, wsURL } from "./realtime.js";

export const musicState = writable({
  queue: [],
  current: null,
  playing: false,
  loop: "off",
  shuffle: false,
  position: 0,
  error: null,   // se auto-limpia a los segundos
  info: null,    // avisos transitorios ("añadiendo N canciones…")
  busy: false,   // buscando/resolviendo lo recién pedido
  botOnline: true, // el bot está conectado al servidor
});
export const musicChannelId = writable(null);

let sock = null;
let errTimer = 0;
let infoTimer = 0;

function flash(key, message, ms) {
  // Muestra un error/aviso y lo limpia solo (antes se quedaban para siempre).
  const timer = key === "error" ? errTimer : infoTimer;
  clearTimeout(timer);
  musicState.update((s) => ({ ...s, [key]: message }));
  const t = setTimeout(() => musicState.update((s) => ({ ...s, [key]: null })), ms);
  if (key === "error") errTimer = t;
  else infoTimer = t;
}

export function connectMusic(channelId) {
  if (sock) sock.close();
  musicChannelId.set(channelId);
  sock = reconnectingSocket({
    url: () => wsURL(`/ws/music/${channelId}?token=${get(token)}`),
    onMessage: (m) => {
      if (m.type === "state") {
        musicState.update((s) => ({
          ...s,
          queue: m.queue,
          current: m.current,
          playing: m.playing,
          loop: m.loop,
          shuffle: m.shuffle,
          position: m.position,
          botOnline: m.bot_online !== false,
          busy: false, // llegó estado nuevo: lo pedido ya está (o falló con error)
        }));
      } else if (m.type === "adding") {
        musicState.update((s) => ({ ...s, busy: true }));
      } else if (m.type === "info") {
        flash("info", m.message, 5000);
      } else if (m.type === "error") {
        musicState.update((s) => ({ ...s, busy: false }));
        flash("error", m.message, 6000);
      }
    },
  });
}

export function disconnectMusic() {
  if (sock) {
    sock.close();
    sock = null;
  }
}

function send(obj) {
  if (sock) sock.send(obj);
}

// Comandos (con actualización optimista donde se nota la latencia).
export const music = {
  add: (query) => send({ type: "add", query }),
  toggle() {
    musicState.update((s) => ({ ...s, playing: !s.playing }));
    send({ type: "toggle" });
  },
  skip: () => send({ type: "skip" }),
  prev: () => send({ type: "prev" }),
  jump: (i) => send({ type: "jump", index: i }),
  remove: (id) => send({ type: "remove", id }),
  shuffle() {
    let on;
    musicState.update((s) => ((on = !s.shuffle), { ...s, shuffle: on }));
    send({ type: "shuffle", on });
  },
  loop() {
    let next;
    musicState.update((s) => ((next = { off: "all", all: "one", one: "off" }[s.loop]), { ...s, loop: next }));
    send({ type: "loop", mode: next });
  },
};
