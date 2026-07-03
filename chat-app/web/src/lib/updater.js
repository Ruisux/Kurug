// Auto-actualización de la app de escritorio. Soporta Electron (electron-updater)
// y, mientras dure la migración, Tauri. Expone un store para el aviso de "hay
// versión nueva" y un botón "Actualizar y reiniciar".
import { writable } from "svelte/store";
import { isElectron, isTauri, updater as desktopUpdater } from "./desktop.js";

// { available, version, notes, downloading, progress(0..1), error }
export const updateState = writable({
  available: false,
  version: "",
  notes: "",
  downloading: false,
  progress: 0,
  error: "",
});

let pending = null; // objeto Update de Tauri
let electronWired = false;

function wireElectron() {
  if (electronWired) return;
  electronWired = true;
  desktopUpdater.on("available", (info) =>
    updateState.update((s) => ({ ...s, available: true, version: info.version, notes: info.notes || "" })),
  );
  desktopUpdater.on("progress", (p) =>
    updateState.update((s) => ({ ...s, downloading: true, progress: p || 0 })),
  );
  desktopUpdater.on("error", (e) =>
    updateState.update((s) => ({ ...s, downloading: false, error: String(e) })),
  );
  // "update-downloaded" reinicia solo (quitAndInstall en el main).
}

export async function checkForUpdates() {
  if (isElectron) {
    wireElectron();
    try { await desktopUpdater.check(); } catch (e) { console.warn("checkForUpdates:", e); }
    return;
  }
  if (!isTauri) return;
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const update = await check();
    if (update) {
      pending = update;
      updateState.update((s) => ({ ...s, available: true, version: update.version, notes: update.body || "" }));
    }
  } catch (e) {
    console.warn("checkForUpdates:", e);
  }
}

export async function installUpdate() {
  if (isElectron) {
    updateState.update((s) => ({ ...s, downloading: true, error: "" }));
    try { await desktopUpdater.install(); } catch (e) {
      updateState.update((s) => ({ ...s, downloading: false, error: String(e) }));
    }
    return;
  }
  if (!isTauri || !pending) return;
  try {
    updateState.update((s) => ({ ...s, downloading: true, error: "" }));
    let total = 0;
    let got = 0;
    await pending.downloadAndInstall((ev) => {
      if (ev.event === "Started") total = ev.data.contentLength || 0;
      else if (ev.event === "Progress") {
        got += ev.data.chunkLength || 0;
        if (total) updateState.update((s) => ({ ...s, progress: got / total }));
      }
    });
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch (e) {
    updateState.update((s) => ({ ...s, downloading: false, error: String(e) }));
  }
}
