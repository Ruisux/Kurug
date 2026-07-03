// Controlador del selector de pantalla (Electron).
//
// voice.js llama a pickScreen() al iniciar el compartir; esto abre el modal
// ScreenPicker (vía pickerStore) y resuelve con la elección del usuario:
//   { id, audio, quality }  o  null si canceló.
// En web/Tauri no hay selector propio: devuelve { native: true } y se usa el
// picker del navegador como siempre.
import { writable } from "svelte/store";
import { screenPicker } from "./desktop.js";

export const pickerStore = writable(null); // { sources } cuando está abierto
let resolver = null;

export async function pickScreen() {
  if (!screenPicker.supported) return { native: true };
  let sources = [];
  try {
    sources = await screenPicker.getSources();
  } catch {
    sources = [];
  }
  return new Promise((resolve) => {
    resolver = resolve;
    pickerStore.set({ sources });
  });
}

// La llama ScreenPicker al elegir (choice) o cancelar (null).
export function resolvePick(choice) {
  pickerStore.set(null);
  if (resolver) {
    resolver(choice);
    resolver = null;
  }
}
