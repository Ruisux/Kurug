// Cliente de la pizarra colaborativa (WS /ws/board/{channel_id}).
//
// El estado local es un Map id -> elemento (mismo orden de llegada que el
// server). El que dibuja pinta LOCAL al instante y el server difunde a los
// demás (a él lo excluye); al reconectar, el snapshot REEMPLAZA todo.
import { writable, get } from "svelte/store";
import { token } from "./stores.js";
import { reconnectingSocket, wsURL } from "./realtime.js";

export const boardState = writable({ elements: [] });

let els = new Map();
let sock = null;

function pub() {
  boardState.set({ elements: [...els.values()] });
}

export function connectBoard(channelId) {
  disconnectBoard();
  els = new Map();
  pub();
  sock = reconnectingSocket({
    url: () => wsURL(`/ws/board/${channelId}?token=${get(token)}`),
    onMessage: (m) => {
      if (m.type === "snapshot") {
        els = new Map(m.elements.map((e) => [e.id, e]));
        pub();
      } else if (m.type === "added") {
        els.set(m.el.id, m.el);
        pub();
      } else if (m.type === "points") {
        const e = els.get(m.id);
        if (e) {
          e.points = e.points.concat(m.points);
          pub();
        }
      } else if (m.type === "updated") {
        const e = els.get(m.id);
        if (e) {
          Object.assign(e, m.patch);
          pub();
        }
      } else if (m.type === "removed") {
        els.delete(m.id);
        pub();
      } else if (m.type === "cleared") {
        els.clear();
        pub();
      }
    },
  });
}

export function disconnectBoard() {
  sock?.close();
  sock = null;
}

export function newElementId() {
  try {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  } catch {
    return Math.random().toString(16).slice(2, 10) + Date.now().toString(16);
  }
}

// Operaciones: aplican LOCAL primero (cero lag para quien dibuja) y avisan al
// server. `addPoints` no re-aplica local: el dibujante ya extendió su trazo.
export const boardOps = {
  add(el) {
    els.set(el.id, el);
    pub();
    sock?.send({ type: "add", el });
  },
  addPoints(id, points) {
    sock?.send({ type: "points", id, points });
  },
  touchLocal() {
    pub(); // el dibujante mutó su trazo en sitio: re-publicar la vista
  },
  update(id, patch) {
    const e = els.get(id);
    if (e) {
      Object.assign(e, patch);
      pub();
    }
    sock?.send({ type: "update", id, patch });
  },
  remove(id) {
    els.delete(id);
    pub();
    sock?.send({ type: "remove", id });
  },
  undo() {
    sock?.send({ type: "undo" }); // el server responde con "removed"
  },
  clear() {
    sock?.send({ type: "clear" }); // el server responde con "cleared"
  },
};
