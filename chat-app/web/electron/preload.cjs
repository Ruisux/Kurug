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

  // Selector de pantalla propio: el main pide elegir fuente (onRequest) y el
  // renderer responde con la elección (respond) o {} para cancelar.
  screen: {
    onRequest: (cb) => {
      const listener = (_e, sources) => cb(sources);
      ipcRenderer.on("screen:request", listener);
      return () => ipcRenderer.removeListener("screen:request", listener);
    },
    respond: (choice) => ipcRenderer.send("screen:choice", choice || {}),
  },
});
