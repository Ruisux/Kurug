// Preferencias de audio del usuario, persistidas en localStorage.
// Las usan voice.js (dispositivos, supresión de ruido, volumen del bot) y
// sounds.js (activar/desactivar efectos).
import { writable } from "svelte/store";

const KEY = "kurug-audio-prefs";

const defaults = {
  inputDeviceId: "",        // "" = dispositivo por defecto del sistema
  outputDeviceId: "",
  noiseSuppression: true,
  echoCancellation: true,
  autoGainControl: true,
  krisp: true,              // supresión de ruido avanzada (modelo Krisp de LiveKit)
  soundsEnabled: true,      // efectos de UI (mute, entrar, salir…)
  notificationSound: true,  // sonido al recibir mensajes/menciones
  botVolume: 100,           // volumen local de la música (0-200)
  screenQuality: "equilibrado", // preset de calidad al compartir pantalla
  // Atajos de teclado (formato por `code`, p. ej. "ControlLeft+ShiftLeft+KeyM").
  // Permite combos solo de modificadores (Alt+Ctrl izq) y distingue izq/der.
  // En escritorio los combos "simples" son GLOBALES; el resto funciona con foco.
  muteShortcut: "ControlLeft+ShiftLeft+KeyM",
  deafenShortcut: "ControlLeft+ShiftLeft+KeyD",
};

// Convierte los atajos del formato antiguo (acelerador de Tauri, p. ej.
// "CommandOrControl+Shift+M") al nuevo formato por `code`. Solo para migrar
// valores ya guardados en localStorage; a futuro todo se guarda ya migrado.
function migrateShortcut(v) {
  if (typeof v !== "string" || !v) return v;
  if (/Left|Right|Key|Digit|Numpad/.test(v)) return v; // ya está en el nuevo formato
  const mac = /mac/i.test((typeof navigator !== "undefined" && navigator.platform) || "");
  return v.split("+").map((part) => {
    if (part === "CommandOrControl" || part === "Command" || part === "Ctrl") return mac ? "MetaLeft" : "ControlLeft";
    if (part === "Alt") return "AltLeft";
    if (part === "Shift") return "ShiftLeft";
    if (part === "Space") return "Space";
    if (/^[A-Z]$/.test(part)) return "Key" + part;
    if (/^[0-9]$/.test(part)) return "Digit" + part;
    return part;
  }).join("+");
}

function load() {
  try {
    const saved = { ...defaults, ...(JSON.parse(localStorage.getItem(KEY)) || {}) };
    saved.muteShortcut = migrateShortcut(saved.muteShortcut);
    saved.deafenShortcut = migrateShortcut(saved.deafenShortcut);
    return saved;
  } catch {
    return { ...defaults };
  }
}

export const prefs = writable(load());

prefs.subscribe((v) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(v));
  } catch {}
});

export function setPref(key, value) {
  prefs.update((p) => ({ ...p, [key]: value }));
}
