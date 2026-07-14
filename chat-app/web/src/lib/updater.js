// Auto-actualización de la app de escritorio (Electron: electron-updater).
// Expone un store para el aviso de "hay versión nueva" y "Actualizar y reiniciar".
import { writable } from "svelte/store";
import { isElectron, updater as desktopUpdater } from "./desktop.js";

// { available, version, notes, downloading, installing, progress(0..1), error }
export const updateState = writable({
  available: false,
  version: "",
  notes: "",
  downloading: false,
  installing: false, // descargado: instalando en silencio y reiniciando
  progress: 0,
  error: "",
});

let wired = false;
function wire() {
  if (wired) return;
  wired = true;
  desktopUpdater.on("available", (info) =>
    updateState.update((s) => ({ ...s, available: true, version: info.version, notes: info.notes || "" })),
  );
  desktopUpdater.on("progress", (p) =>
    updateState.update((s) => ({ ...s, downloading: true, progress: p || 0 })),
  );
  desktopUpdater.on("error", (e) =>
    updateState.update((s) => ({ ...s, downloading: false, installing: false, error: String(e) })),
  );
  // Descargado: el proceso principal instala en silencio y reinicia solo.
  desktopUpdater.on("downloaded", () =>
    updateState.update((s) => ({ ...s, downloading: false, installing: true })),
  );
}

export async function checkForUpdates() {
  if (!isElectron) return;
  wire();
  try { await desktopUpdater.check(); } catch (e) { console.warn("checkForUpdates:", e); }
}

export async function installUpdate() {
  if (!isElectron) return;
  updateState.update((s) => ({ ...s, downloading: true, error: "" }));
  try { await desktopUpdater.install(); } catch (e) {
    updateState.update((s) => ({ ...s, downloading: false, error: String(e) }));
  }
}
