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
  // Atajos de teclado (formato acelerador de Tauri, p. ej. "CommandOrControl+Shift+M").
  // En escritorio son GLOBALES (funcionan con la app en segundo plano); en web,
  // solo con la ventana enfocada y sin estar escribiendo.
  muteShortcut: "CommandOrControl+Shift+M",
  deafenShortcut: "CommandOrControl+Shift+D",
};

function load() {
  try {
    return { ...defaults, ...(JSON.parse(localStorage.getItem(KEY)) || {}) };
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
