// Proceso principal de Electron (shell de escritorio de Kurug).
//
// Reemplaza al shell de Tauri. Carga la MISMA SPA de Vite (web/dist) en una
// ventana SIN decoración nativa (usamos la barra de título propia de la app).
//
// Fase 1: ventana + controles de ventana (min/max/cerrar) por IPC.
// (El selector de pantalla propio y el audio del sistema llegan en la Fase 2;
//  el auto-update y los atajos globales, en la Fase 3.)
const { app, BrowserWindow, ipcMain, shell, protocol, net, session, desktopCapturer } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");

// Una sola instancia (evita abrir varias ventanas al reabrir).
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

let mainWindow = null;

const DIST = path.join(__dirname, "..", "dist");

// Esquema propio "app://": sirve el build de Vite desde la raíz (los assets con
// base "/" funcionan) y cuenta como CONTEXTO SEGURO, imprescindible para el
// micrófono y compartir pantalla. Debe declararse antes de "ready".
protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);

function registerAppProtocol() {
  protocol.handle("app", (request) => {
    const url = new URL(request.url);
    let rel = decodeURIComponent(url.pathname);
    if (rel === "/" || rel === "") rel = "/index.html";
    let filePath = path.join(DIST, rel);
    // Fallback SPA: si no es un archivo existente, servir index.html.
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST, "index.html");
    }
    return net.fetch(pathToFileURL(filePath).toString());
  });
}

// En dev cargamos el servidor de Vite (si se define ELECTRON_START_URL); en
// producción, la SPA empaquetada por el esquema app://.
function resolveStartUrl() {
  return process.env.ELECTRON_START_URL || "app://kurug/index.html";
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 760,
    minHeight: 520,
    center: true,
    resizable: true,
    frame: false, // sin marco nativo: usamos Titlebar.svelte
    backgroundColor: "#14100d",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: true, // menos CPU cuando la ventana está oculta
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // En desarrollo (no empaquetado) abrimos las DevTools para depurar.
  if (!app.isPackaged) mainWindow.webContents.openDevTools({ mode: "detach" });

  // Los enlaces externos se abren en el navegador del sistema, no en la app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.loadURL(resolveStartUrl());
}

// --- Compartir pantalla con SELECTOR PROPIO (sin el picker de Chrome ni la
//     barra de "estás compartiendo") + audio del sistema en Windows ---
//
// Flujo dirigido por el renderer: el renderer pide la lista de fuentes
// (screen:getSources), muestra NUESTRO selector, y antes de llamar a LiveKit
// deja la elección (screen:setChoice). Cuando LiveKit llama a getDisplayMedia,
// este handler devuelve directamente esa elección, SIN volver a preguntar.
let nextChoice = null; // { id, audio }

ipcMain.handle("screen:getSources", async () => {
  const sources = await desktopCapturer.getSources({
    types: ["screen", "window"],
    thumbnailSize: { width: 320, height: 180 },
    fetchWindowIcons: true,
  });
  return sources.map((s) => ({
    id: s.id,
    name: s.name,
    type: s.id.startsWith("screen:") ? "screen" : "window",
    thumbnail: s.thumbnail && !s.thumbnail.isEmpty() ? s.thumbnail.toDataURL() : null,
    appIcon: s.appIcon && !s.appIcon.isEmpty() ? s.appIcon.toDataURL() : null,
  }));
});

ipcMain.on("screen:setChoice", (_e, choice) => {
  nextChoice = choice && choice.id ? choice : null;
});

function setupDisplayMedia() {
  session.defaultSession.setDisplayMediaRequestHandler(
    async (_request, callback) => {
      try {
        if (!nextChoice) return callback(); // sin elección previa -> cancela
        const sources = await desktopCapturer.getSources({ types: ["screen", "window"] });
        const source = sources.find((s) => s.id === nextChoice.id);
        const withAudio = nextChoice.audio && process.platform === "win32";
        nextChoice = null;
        if (!source) return callback();
        // 'loopback' = audio del sistema (Windows). Se pide SOLO si el usuario lo
        // marcó, y el renderer solo lo ofrece para pantallas completas.
        callback(withAudio ? { video: source, audio: "loopback" } : { video: source });
      } catch {
        callback();
      }
    },
    { useSystemPicker: false },
  );
}

// --- Controles de ventana (los invoca la barra de título del renderer) ---
ipcMain.handle("window:minimize", () => mainWindow?.minimize());
ipcMain.handle("window:toggleMaximize", () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.handle("window:close", () => mainWindow?.close());

app.whenReady().then(() => {
  registerAppProtocol();
  setupDisplayMedia();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
