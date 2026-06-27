// Atajos de teclado para silenciar/ensordecer.
// - Escritorio (Tauri): atajos GLOBALES vía plugin-global-shortcut (funcionan
//   aunque la app no tenga el foco, como Discord).
// - Web: listener de teclado en la ventana (solo con foco y sin estar escribiendo).
import { get } from "svelte/store";
import { prefs } from "./prefs.js";
import { toggleMute, toggleDeafen } from "./voice.js";

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const isMac =
  typeof navigator !== "undefined" && /mac/i.test(navigator.platform || "");

let gs = null;            // módulo plugin-global-shortcut (lazy)
let registered = [];      // aceleradores registrados globalmente
let webHandler = null;

function actionFor(kind) {
  return kind === "mute" ? toggleMute : toggleDeafen;
}

// Construye un acelerador a partir de un evento de teclado, o null si solo es
// una tecla modificadora.
export function comboFromEvent(e) {
  const k = e.key;
  if (["Control", "Shift", "Alt", "Meta", "OS"].includes(k)) return null;
  const parts = [];
  if (e.metaKey || e.ctrlKey) parts.push("CommandOrControl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey) parts.push("Shift");
  let key;
  if (k === " ") key = "Space";
  else if (k.length === 1) key = k.toUpperCase();
  else key = k; // F1, ArrowUp, etc.
  parts.push(key);
  return parts.join("+");
}

// Texto legible para mostrar el atajo.
export function prettyCombo(combo) {
  if (!combo) return "Sin asignar";
  return combo
    .replace("CommandOrControl", isMac ? "⌘" : "Ctrl")
    .replace("Alt", isMac ? "⌥" : "Alt")
    .replace("Shift", isMac ? "⇧" : "Shift")
    .split("+")
    .join(" + ");
}

function parseAccel(accel) {
  const parts = accel.split("+");
  return {
    cmdctrl: parts.includes("CommandOrControl"),
    alt: parts.includes("Alt"),
    shift: parts.includes("Shift"),
    key: parts[parts.length - 1],
  };
}

function matches(e, a) {
  if (a.cmdctrl !== (e.metaKey || e.ctrlKey)) return false;
  if (a.alt !== e.altKey) return false;
  if (a.shift !== e.shiftKey) return false;
  let ek;
  if (e.key === " ") ek = "Space";
  else ek = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return ek === a.key;
}

async function applyTauri(p) {
  if (!gs) gs = await import("@tauri-apps/plugin-global-shortcut");
  for (const a of registered) {
    try { await gs.unregister(a); } catch {}
  }
  registered = [];
  for (const [kind, accel] of [["mute", p.muteShortcut], ["deafen", p.deafenShortcut]]) {
    if (!accel) continue;
    try {
      await gs.register(accel, (ev) => {
        // Versiones nuevas pasan {state}: actuar solo al pulsar (no al soltar).
        if (!ev || ev.state === undefined || ev.state === "Pressed") actionFor(kind)();
      });
      registered.push(accel);
    } catch (e) {
      console.warn("No se pudo registrar el atajo", accel, e);
    }
  }
}

function applyWeb(p) {
  if (webHandler) window.removeEventListener("keydown", webHandler);
  const combos = [["mute", p.muteShortcut], ["deafen", p.deafenShortcut]]
    .filter(([, a]) => a)
    .map(([k, a]) => [k, parseAccel(a)]);
  if (!combos.length) { webHandler = null; return; }
  webHandler = (e) => {
    const el = document.activeElement;
    if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
    for (const [kind, a] of combos) {
      if (matches(e, a)) { e.preventDefault(); actionFor(kind)(); break; }
    }
  };
  window.addEventListener("keydown", webHandler);
}

// (Re)aplica los atajos según las preferencias actuales.
export function applyShortcuts() {
  const p = get(prefs);
  try {
    if (isTauri) applyTauri(p);
    else applyWeb(p);
  } catch (e) {
    console.warn("applyShortcuts:", e);
  }
}
