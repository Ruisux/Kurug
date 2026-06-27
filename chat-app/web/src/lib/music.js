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
  error: null,
});
export const musicChannelId = writable(null);

let sock = null;

export function connectMusic(channelId) {
  if (sock) sock.close();
  musicChannelId.set(channelId);
  sock = reconnectingSocket({
    url: () => wsURL(`/ws/music/${channelId}?token=${get(token)}`),
    onMessage: (m) => {
      if (m.type === "state") musicState.set({ ...m, error: null });
      else if (m.type === "error") musicState.update((s) => ({ ...s, error: m.message }));
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
