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

  // Selector de pantalla propio (flujo dirigido por el renderer):
  // getSources() -> lista de pantallas/ventanas; setChoice() deja la elección
  // que el handler de getDisplayMedia usará al compartir.
  screen: {
    getSources: () => ipcRenderer.invoke("screen:getSources"),
    setChoice: (choice) => ipcRenderer.send("screen:setChoice", choice || null),
  },

  // Auto-update: check/install y eventos (available/progress/error).
  updater: {
    check: () => ipcRenderer.invoke("updater:check"),
    install: () => ipcRenderer.invoke("updater:install"),
    on: (event, cb) => {
      const listener = (_e, data) => cb(data);
      ipcRenderer.on("updater:" + event, listener);
      return () => ipcRenderer.removeListener("updater:" + event, listener);
    },
  },

  // Atajos globales: register() devuelve los aceleradores registrados; onTrigger
  // avisa cuando se pulsa uno (con app en segundo plano).
  shortcuts: {
    register: (list) => ipcRenderer.invoke("shortcuts:register", list),
    onTrigger: (cb) => {
      const listener = (_e, id) => cb(id);
      ipcRenderer.on("shortcuts:trigger", listener);
      return () => ipcRenderer.removeListener("shortcuts:trigger", listener);
    },
  },
});
