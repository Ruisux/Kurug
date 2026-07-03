// Preload: expone una API mínima y segura al renderer (contextIsolation).
// El renderer accede a esto como `window.kurug` (ver src/lib/desktop.js).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kurug", {
  isElectron: true,
  platform: process.platform, // "win32" | "darwin" | "linux"

  // Controles de la ventana (barra de título propia).
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("window:toggleMaximize"),
    close: () => ipcRenderer.invoke("window:close"),
  },
});
