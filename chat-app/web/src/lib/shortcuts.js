// Atajos de teclado para silenciar/ensordecer.
//
// Formato de combo (nuevo): tokens de `KeyboardEvent.code` unidos por "+", en
// orden canónico (modificadores primero). Permite combos SOLO de modificadores
// (p. ej. "AltLeft+ControlLeft", como el push-to-mute de Discord) y distingue
// izquierda/derecha. Ejemplos: "ControlLeft+ShiftLeft+KeyM", "AltLeft+ControlLeft".
//
// - Escritorio (Tauri): si el combo es "simple" (modificadores + UNA tecla
//   normal) se registra como atajo GLOBAL (funciona sin foco). Los combos que el
//   plugin no soporta (solo modificadores, o específicos de izq/der) caen al
//   listener de ventana enfocada.
// - Web: siempre por listener de ventana (solo con foco y sin estar escribiendo).
import { get } from "svelte/store";
import { prefs } from "./prefs.js";
import { toggleMute, toggleDeafen } from "./voice.js";
import { isElectron, isTauri, globalShortcuts } from "./desktop.js";

const isMac =
  typeof navigator !== "undefined" && /mac/i.test(navigator.platform || "");

let gs = null;            // módulo plugin-global-shortcut (lazy)
let registered = [];      // aceleradores registrados globalmente
let webCombos = [];       // combos gestionados por el listener de ventana
let pressed = new Set();  // e.code actualmente pulsados (para combos con foco)
let firedCode = null;     // combo que ya disparó (evita repetición por auto-repeat)
let keydownH = null, keyupH = null, blurH = null;

function actionFor(kind) {
  return kind === "mute" ? toggleMute : toggleDeafen;
}

// --- Modelo de combos por code ---
const MOD_CODES = new Set([
  "ControlLeft", "ControlRight", "AltLeft", "AltRight",
  "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight",
]);
const MOD_ORDER = ["Control", "Alt", "Shift", "Meta"];

function isMod(code) { return MOD_CODES.has(code); }

// Ordena los codes de forma canónica: modificadores (Ctrl, Alt, Shift, Meta) y
// luego la tecla normal. Así "Shift+Ctrl+M" y "Ctrl+Shift+M" son el mismo combo.
function canonCodes(codes) {
  const uniq = [...new Set(codes)];
  const mods = uniq.filter(isMod).sort((a, b) => {
    const pa = MOD_ORDER.findIndex((m) => a.startsWith(m));
    const pb = MOD_ORDER.findIndex((m) => b.startsWith(m));
    return pa - pb || a.localeCompare(b);
  });
  const keys = uniq.filter((c) => !isMod(c)).sort();
  return [...mods, ...keys];
}

// Construye la cadena de combo a partir de un conjunto de codes.
export function codeCombo(codes) {
  return canonCodes(codes).join("+");
}

// Etiqueta legible de un code para mostrar el atajo.
function labelForCode(code) {
  const side = code.endsWith("Left") ? (isMac ? " izq" : " I") :
               code.endsWith("Right") ? (isMac ? " der" : " D") : "";
  if (code.startsWith("Control")) return (isMac ? "⌃" : "Ctrl") + side;
  if (code.startsWith("Alt")) return (isMac ? "⌥" : "Alt") + side;
  if (code.startsWith("Shift")) return (isMac ? "⇧" : "Shift") + side;
  if (code.startsWith("Meta")) return (isMac ? "⌘" : "Win") + side;
  if (code.startsWith("Key")) return code.slice(3);          // KeyM -> M
  if (code.startsWith("Digit")) return code.slice(5);        // Digit1 -> 1
  if (code.startsWith("Numpad")) return "Num " + code.slice(6);
  if (code === "Space") return "Espacio";
  if (code.startsWith("Arrow")) return "↑↓←→"["UDLR".indexOf(code.slice(5)[0])] || code;
  return code; // F1, Enter, Tab, etc.
}

export function prettyCombo(combo) {
  if (!combo) return "Sin asignar";
  return combo.split("+").map(labelForCode).join(" + ");
}

// --- Compatibilidad con el formato antiguo (acelerador de Tauri) ---
// Antes se guardaba p. ej. "CommandOrControl+Shift+M". Lo convertimos a codes.
function isLegacy(combo) {
  return /CommandOrControl/.test(combo) ||
    (!/Left|Right|Key|Digit|Numpad|Space|Arrow|^F\d/.test(combo) &&
     /Alt|Shift|Ctrl|Command/.test(combo));
}
export function legacyToCombo(accel) {
  const codes = [];
  for (const part of accel.split("+")) {
    if (part === "CommandOrControl" || part === "Command" || part === "Ctrl")
      codes.push(isMac ? "MetaLeft" : "ControlLeft");
    else if (part === "Alt") codes.push("AltLeft");
    else if (part === "Shift") codes.push("ShiftLeft");
    else if (part === "Space") codes.push("Space");
    else if (/^[A-Z0-9]$/.test(part)) codes.push(/[0-9]/.test(part) ? "Digit" + part : "Key" + part);
    else codes.push(part);
  }
  return codeCombo(codes);
}
function normalize(combo) {
  return combo && isLegacy(combo) ? legacyToCombo(combo) : combo;
}

// --- Acelerador global de Tauri (solo para combos "simples") ---
// Devuelve la cadena de acelerador si el combo tiene EXACTAMENTE una tecla
// normal (el plugin no admite solo-modificadores), o null si no aplica.
function toAccel(combo) {
  const codes = combo.split("+");
  const mods = codes.filter(isMod);
  const keys = codes.filter((c) => !isMod(c));
  if (keys.length !== 1) return null; // 0 teclas normales -> no registrable global
  const parts = [];
  if (mods.some((m) => m.startsWith("Control") || m.startsWith("Meta"))) parts.push("CommandOrControl");
  if (mods.some((m) => m.startsWith("Alt"))) parts.push("Alt");
  if (mods.some((m) => m.startsWith("Shift"))) parts.push("Shift");
  const k = keys[0];
  if (k.startsWith("Key")) parts.push(k.slice(3));
  else if (k.startsWith("Digit")) parts.push(k.slice(5));
  else if (k === "Space") parts.push("Space");
  else parts.push(k); // F1, ArrowUp, etc.
  return parts.join("+");
}

async function applyTauri(entries) {
  if (!gs) gs = await import("@tauri-apps/plugin-global-shortcut");
  for (const a of registered) { try { await gs.unregister(a); } catch {} }
  registered = [];
  const focusOnly = [];
  for (const [kind, combo] of entries) {
    const accel = toAccel(combo);
    if (accel) {
      try {
        await gs.register(accel, (ev) => {
          if (!ev || ev.state === undefined || ev.state === "Pressed") actionFor(kind)();
        });
        registered.push(accel);
        continue; // registrado global; no lo dupliques en el listener con foco
      } catch (e) {
        console.warn("No se pudo registrar el atajo global", accel, e);
      }
    }
    focusOnly.push([kind, combo]); // solo-modificadores o falló el global
  }
  return focusOnly;
}

// --- Listener de ventana (combos con foco: web y fallback de escritorio) ---
function detachWeb() {
  if (keydownH) window.removeEventListener("keydown", keydownH);
  if (keyupH) window.removeEventListener("keyup", keyupH);
  if (blurH) window.removeEventListener("blur", blurH);
  keydownH = keyupH = blurH = null;
  pressed.clear();
  firedCode = null;
}

function attachWeb(entries) {
  detachWeb();
  webCombos = entries.map(([kind, combo]) => [kind, new Set(combo.split("+"))]);
  if (!webCombos.length) return;

  const typing = () => {
    const el = document.activeElement;
    return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
  };
  // ¿El conjunto de teclas pulsadas coincide EXACTAMENTE con el combo?
  const exact = (set) => set.size === pressed.size && [...set].every((c) => pressed.has(c));

  keydownH = (e) => {
    if (isMod(e.code)) pressed.add(e.code);
    else if (!typing()) pressed.add(e.code); // teclas normales solo fuera de campos
    if (e.repeat) return;
    for (const [kind, set] of webCombos) {
      if (exact(set) && firedCode !== kind) {
        // Si el combo lleva tecla normal y estás escribiendo, no interceptes.
        if ([...set].some((c) => !isMod(c)) && typing()) continue;
        e.preventDefault();
        firedCode = kind;
        actionFor(kind)();
        break;
      }
    }
  };
  keyupH = (e) => {
    pressed.delete(e.code);
    if (firedCode) firedCode = null; // al soltar cualquier tecla, rearmamos
  };
  blurH = () => { pressed.clear(); firedCode = null; };
  window.addEventListener("keydown", keydownH);
  window.addEventListener("keyup", keyupH);
  window.addEventListener("blur", blurH);
}

// --- Atajos globales en Electron (globalShortcut vía IPC) ---
let electronTriggerWired = false;
async function applyElectron(entries) {
  const toReg = [];
  for (const [kind, combo] of entries) {
    const accel = toAccel(combo);
    if (accel) toReg.push({ id: kind, accel });
  }
  let ok = [];
  try { ok = await globalShortcuts.register(toReg); } catch {}
  if (!electronTriggerWired) {
    electronTriggerWired = true;
    globalShortcuts.onTrigger((id) => actionFor(id)());
  }
  const okKinds = new Set(toReg.filter((r) => ok.includes(r.accel)).map((r) => r.id));
  // Los combos que el global no cubre (solo modificadores, izq/der) van al foco.
  return entries.filter(([kind]) => !okKinds.has(kind));
}

// (Re)aplica los atajos según las preferencias actuales.
export async function applyShortcuts() {
  const p = get(prefs);
  const entries = [["mute", normalize(p.muteShortcut)], ["deafen", normalize(p.deafenShortcut)]]
    .filter(([, c]) => c);
  try {
    if (isElectron) {
      const focusOnly = await applyElectron(entries);
      attachWeb(focusOnly);
    } else if (isTauri) {
      const focusOnly = await applyTauri(entries);
      attachWeb(focusOnly); // fallback con foco para lo que el global no cubre
    } else {
      attachWeb(entries);
    }
  } catch (e) {
    console.warn("applyShortcuts:", e);
  }
}
