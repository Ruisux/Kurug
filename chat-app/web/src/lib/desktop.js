// Capa de abstracción del "escritorio" (Electron) frente a la web.
//
// Los componentes (Titlebar, atajos, notificaciones, updater, selector de
// pantalla) hablan con ESTA capa, no con Electron directamente.

const w = typeof window !== "undefined" ? window : {};

export const isElectron = !!(w.kurug && w.kurug.isElectron);
export const isDesktop = isElectron;

// Plataforma normalizada ("windows" | "mac" | "linux" | "web").
export function platform() {
  if (isElectron) {
    const p = w.kurug.platform;
    return p === "win32" ? "windows" : p === "darwin" ? "mac" : "linux";
  }
  if (typeof navigator !== "undefined" && /mac/i.test(navigator.platform || "")) return "mac";
  if (typeof navigator !== "undefined" && /win/i.test(navigator.platform || "")) return "windows";
  return "web";
}

// --- Auto-update (electron-updater vía IPC) ---
export const updater = {
  supported: isElectron,
  check() { if (isElectron && w.kurug.updater) return w.kurug.updater.check(); },
  install() { if (isElectron && w.kurug.updater) return w.kurug.updater.install(); },
  on(event, cb) {
    if (isElectron && w.kurug.updater) return w.kurug.updater.on(event, cb);
    return () => {};
  },
};

// --- Atajos globales (globalShortcut vía IPC) ---
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

// --- Selector de pantalla (Electron; en web usa el del navegador) ---
export const screenPicker = {
  supported: isElectron,
  async getSources() {
    if (isElectron && w.kurug.screen) return w.kurug.screen.getSources();
    return [];
  },
  setChoice(choice) {
    if (isElectron && w.kurug.screen) w.kurug.screen.setChoice(choice);
  },
};

// --- Controles de ventana (barra de título propia) ---
export const windowControls = {
  minimize() { if (isElectron) return w.kurug.window.minimize(); },
  toggleMaximize() { if (isElectron) return w.kurug.window.toggleMaximize(); },
  close() { if (isElectron) return w.kurug.window.close(); },
};
