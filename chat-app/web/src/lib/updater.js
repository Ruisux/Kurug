// Auto-actualización (solo en la app de escritorio / Tauri).
// Comprueba si hay versión nueva publicada en GitHub Releases; si la hay,
// expone un store para mostrar un botón "Actualizar y reiniciar".
import { writable } from "svelte/store";

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

// { available, version, notes, downloading, progress(0..1), error } | null mientras carga
export const updateState = writable({
  available: false,
  version: "",
  notes: "",
  downloading: false,
  progress: 0,
  error: "",
});

let pending = null; // objeto Update de Tauri

export async function checkForUpdates() {
  if (!isTauri) return;
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const update = await check();
    if (update) {
      pending = update;
      updateState.update((s) => ({
        ...s,
        available: true,
        version: update.version,
        notes: update.body || "",
      }));
    }
  } catch (e) {
    console.warn("checkForUpdates:", e);
  }
}

export async function installUpdate() {
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
    // Reiniciar la app para aplicar la actualización.
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch (e) {
    updateState.update((s) => ({ ...s, downloading: false, error: String(e) }));
  }
}
