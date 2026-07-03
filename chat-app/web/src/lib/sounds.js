// Efectos de sonido de la UI (mute, ensordecer, entrar, salir…).
// Sintetizados con Web Audio: cero archivos, muy ligero y fiel al enfoque.
import { get } from "svelte/store";
import { prefs } from "./prefs.js";

let ctx = null;

// Multiplicador maestro: los tonos base eran demasiado suaves (0.05-0.08) y se
// escuchaban muy bajo. Subimos todo ~2.6x aquí en un solo sitio; si algún día se
// quiere un control de volumen de efectos en ajustes, basta con tocar este valor.
const MASTER = 2.6;

function ac() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

// Reproduce una secuencia corta de tonos (un "blip").
function blip(freqs, { dur = 0.13, gain = 0.05, type = "sine" } = {}) {
  const c = ac();
  const t0 = c.currentTime;
  const peak = Math.min(0.6, gain * MASTER); // techo por seguridad (evita clipping)
  freqs.forEach((f, i) => {
    const start = t0 + i * dur * 0.85;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = f;
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(peak, start + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
    o.connect(g).connect(c.destination);
    o.start(start);
    o.stop(start + dur);
  });
}

const SOUNDS = {
  mute: () => blip([460, 320]),
  unmute: () => blip([320, 520]),
  deafen: () => blip([420, 300, 220]),
  undeafen: () => blip([220, 340, 500]),
  join: () => blip([523, 784], { gain: 0.06 }),   // dos notas ascendentes
  leave: () => blip([659, 392], { gain: 0.05 }),  // dos notas descendentes
  test: () => blip([440, 660], { gain: 0.07 }),
  // Compartir pantalla: empezar = sube; dejar de compartir = baja.
  shareStart: () => blip([494, 659, 988], { gain: 0.06, dur: 0.12 }),
  shareStop: () => blip([988, 659, 440], { gain: 0.055, dur: 0.12 }),
  // Notificaciones (gate aparte: notificationSound).
  notify: () => blip([880, 1175], { gain: 0.05, dur: 0.12 }),         // ding suave
  mention: () => blip([784, 1047, 1319], { gain: 0.08, dur: 0.13 }),  // 3 notas, más presente
};

// Sonidos que dependen de la preferencia de NOTIFICACIONES, no de los efectos UI.
const NOTIFY_KINDS = new Set(["notify", "mention"]);

export function playSound(kind) {
  try {
    const p = get(prefs);
    const enabled = NOTIFY_KINDS.has(kind) ? p.notificationSound : p.soundsEnabled;
    if (!enabled) return;
    (SOUNDS[kind] || (() => {}))();
  } catch {}
}
