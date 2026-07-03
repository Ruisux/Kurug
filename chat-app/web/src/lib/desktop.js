// Capa de abstracción del "escritorio": unifica Electron, Tauri y web.
//
// Durante la migración de Tauri -> Electron conviven ambos. Los componentes
// (Titlebar, atajos, notificaciones, updater) hablan con ESTA capa y no con una
// tecnología concreta, así el resto del código no cambia.

const w = typeof window !== "undefined" ? window : {};

export const isElectron = !!(w.kurug && w.kurug.isElectron);
export const isTauri = "__TAURI_INTERNALS__" in w;
export const isDesktop = isElectron || isTauri;

// Plataforma normalizada ("windows" | "mac" | "linux" | "web").
export function platform() {
  if (isElectron) {
    const p = w.kurug.platform;
    return p === "win32" ? "windows" : p === "darwin" ? "mac" : "linux";
  }
  if (typeof navigator !== "undefined" && /mac/i.test(navigator.platform || "")) return "mac";
  if (typeof navigator !== "undefined" && /win/i.test(navigator.platform || "")) return "windows";
  return isTauri ? "linux" : "web";
}

// --- Auto-update (Electron: electron-updater vía IPC) ---
export const updater = {
  supported: isElectron,
  check() { if (isElectron && w.kurug.updater) return w.kurug.updater.check(); },
  install() { if (isElectron && w.kurug.updater) return w.kurug.updater.install(); },
  on(event, cb) {
    if (isElectron && w.kurug.updater) return w.kurug.updater.on(event, cb);
    return () => {};
  },
};

// --- Atajos globales (Electron: globalShortcut vía IPC) ---
export const globalShortcuts = {
  supported: isElectron,
  async register(list) {
    if (isElectron && w.kurug.shortcuts) return w.kurug.shortcuts.register(list);
    return [];
  },
  onTrigger(cb) {
    if (isElectron && w.kurug.shortcuts) return w.kurug.shortcuts.onTrigger(cb);
    return () => {};
  },
};

// --- Controles de ventana (barra de título propia) ---
let tauriWin = null;
async function getTauriWindow() {
  if (!tauriWin) {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    tauriWin = getCurrentWindow();
  }
  return tauriWin;
}

// --- Selector de pantalla (solo Electron; en web/Tauri usa el del navegador) ---
export const screenPicker = {
  supported: isElectron,
  // Lista de pantallas/ventanas para elegir. [] fuera de Electron.
  async getSources() {
    if (isElectron && w.kurug.screen) return w.kurug.screen.getSources();
    return [];
  },
  // Deja la elección que usará getDisplayMedia al compartir.
  setChoice(choice) {
    if (isElectron && w.kurug.screen) w.kurug.screen.setChoice(choice);
  },
};

export const windowControls = {
  async minimize() {
    if (isElectron) return w.kurug.window.minimize();
    if (isTauri) return (await getTauriWindow()).minimize();
  },
  async toggleMaximize() {
    if (isElectron) return w.kurug.window.toggleMaximize();
    if (isTauri) return (await getTauriWindow()).toggleMaximize();
  },
  async close() {
    if (isElectron) return w.kurug.window.close();
    if (isTauri) return (await getTauriWindow()).close();
  },
};
