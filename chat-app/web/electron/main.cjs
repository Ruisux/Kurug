// Proceso principal de Electron (shell de escritorio de Kurug).
//
// Reemplaza al shell de Tauri. Carga la MISMA SPA de Vite (web/dist) en una
// ventana SIN decoración nativa (usamos la barra de título propia de la app).
//
// Fase 1: ventana + controles de ventana (min/max/cerrar) por IPC.
// (El selector de pantalla propio y el audio del sistema llegan en la Fase 2;
//  el auto-update y los atajos globales, en la Fase 3.)
const { app, BrowserWindow, ipcMain, shell, protocol, net, session, desktopCapturer, globalShortcut, Menu, clipboard, dialog } = require("electron");
const { autoUpdater } = require("electron-updater");
const path = require("node:path");
const fs = require("node:fs");
const { pathToFileURL } = require("node:url");
const { execFile } = require("node:child_process");

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

  attachContextMenu(mainWindow.webContents);
  mainWindow.loadURL(resolveStartUrl());
}

// --- Menú contextual nativo (clic derecho) ---
// En la app de escritorio el menú por defecto del navegador no aparece, así que
// al dar clic derecho no salían opciones. Aquí montamos uno propio: sobre una
// IMAGEN da "copiar imagen / copiar dirección / guardar imagen"; sobre texto,
// los básicos (copiar, cortar, pegar); y en un campo editable, pegar.
function attachContextMenu(wc) {
  wc.on("context-menu", (_e, params) => {
    const items = [];
    const isImg = params.mediaType === "image" && params.srcURL;
    if (isImg) {
      items.push(
        { label: "Copiar imagen", click: () => wc.copyImageAt(params.x, params.y) },
        { label: "Copiar dirección de la imagen", click: () => clipboard.writeText(params.srcURL) },
        {
          label: "Guardar imagen…",
          click: () => {
            // downloadURL dispara el flujo de descarga; el 'will-download' de
            // abajo abre el diálogo "Guardar como".
            try { wc.downloadURL(params.srcURL); } catch {}
          },
        },
      );
    }
    if (params.linkURL) {
      if (items.length) items.push({ type: "separator" });
      items.push(
        { label: "Copiar enlace", click: () => clipboard.writeText(params.linkURL) },
        { label: "Abrir en el navegador", click: () => shell.openExternal(params.linkURL) },
      );
    }
    // Texto seleccionado / campos editables.
    const canCopy = params.selectionText && params.selectionText.length > 0;
    if (canCopy || params.isEditable) {
      if (items.length) items.push({ type: "separator" });
      if (params.isEditable) items.push({ role: "cut" });
      if (canCopy || params.isEditable) items.push({ role: "copy" });
      if (params.isEditable) items.push({ role: "paste" });
      items.push({ type: "separator" }, { role: "selectAll" });
    }
    if (!items.length) return; // sin nada útil que ofrecer, no molestamos
    Menu.buildFromTemplate(items).popup({ window: mainWindow });
  });

  // "Guardar imagen…": diálogo nativo de destino para la descarga.
  wc.session.on("will-download", (_e, item) => {
    const name = item.getFilename() || "imagen";
    const dest = dialog.showSaveDialogSync(mainWindow, { defaultPath: name });
    if (dest) item.setSavePath(dest);
    else item.cancel();
  });
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

// --- Auto-update (electron-updater; lee la config de publish del builder) ---
// Log a archivo para poder diagnosticar updates fallidos en máquinas ajenas:
// %APPDATA%/kurug-web/updater.log (Windows) / ~/Library/Application Support (Mac).
function updLog(...parts) {
  try {
    const line = `[${new Date().toISOString()}] ${parts.join(" ")}\n`;
    fs.appendFileSync(path.join(app.getPath("userData"), "updater.log"), line);
  } catch {}
}

function setupUpdater() {
  autoUpdater.autoDownload = false; // descargar solo al pulsar "Actualizar"
  autoUpdater.autoInstallOnAppQuit = true;
  // Descarga SIEMPRE el instalador completo. El parche diferencial (blockmap)
  // falla a veces en silencio con GitHub Releases y deja el botón "muerto".
  autoUpdater.disableDifferentialDownload = true;
  autoUpdater.logger = {
    info: (m) => updLog("info:", m), warn: (m) => updLog("warn:", m),
    error: (m) => updLog("error:", m), debug: () => {},
  };
  const send = (ch, data) => mainWindow?.webContents.send(ch, data);
  autoUpdater.on("update-available", (info) =>
    send("updater:available", { version: info.version, notes: info.releaseNotes || "" }),
  );
  autoUpdater.on("error", (err) => { updLog("error:", err?.stack || err); send("updater:error", String(err)); });
  autoUpdater.on("download-progress", (p) => send("updater:progress", (p.percent || 0) / 100));
  autoUpdater.on("update-downloaded", () => {
    updLog("update-downloaded; instalando en silencio");
    send("updater:downloaded");
    // Instala SIN el asistente de NSIS (/S) y relanza la app sola. setImmediate
    // deja terminar el evento antes de cerrar (recomendación de electron-updater).
    setImmediate(() => autoUpdater.quitAndInstall(true, true));
  });
}
ipcMain.handle("updater:check", async () => {
  if (!app.isPackaged) return; // el auto-update solo aplica empaquetado
  try { await autoUpdater.checkForUpdates(); } catch {}
});
ipcMain.handle("updater:install", async () => {
  try { await autoUpdater.downloadUpdate(); } catch (e) {
    mainWindow?.webContents.send("updater:error", String(e));
  }
});

// --- Actividad (jugando X / escuchando Y) — solo Windows ---
// Sondeo cada 20 s de los procesos CON ventana vía PowerShell (sin dependencias
// nativas). Spotify: su título de ventana es "Artista - Canción" mientras suena
// y "Spotify"/"Spotify Free" en pausa. Juegos: lista curada de ejecutables.
// El renderer decide si publica esto en su presencia (toggle de privacidad).
const GAMES = {
  "valorant": "VALORANT", "valorant-win64-shipping": "VALORANT",
  "leagueclient": "League of Legends", "league of legends": "League of Legends",
  "cs2": "Counter-Strike 2", "dota2": "Dota 2",
  "fortniteclient-win64-shipping": "Fortnite",
  "rocketleague": "Rocket League",
  "minecraft.windows": "Minecraft", "minecraftlauncher": "Minecraft",
  "gta5": "Grand Theft Auto V", "gta5_enhanced": "Grand Theft Auto V",
  "r5apex": "Apex Legends", "r5apex_dx12": "Apex Legends",
  "overwatch": "Overwatch 2", "wow": "World of Warcraft",
  "hearthstone": "Hearthstone", "osu!": "osu!", "osulazer": "osu!",
  "eldenring": "Elden Ring", "nightreign": "Elden Ring Nightreign",
  "terraria": "Terraria", "stardew valley": "Stardew Valley",
  "stardewvalley": "Stardew Valley",
  "among us": "Among Us", "amongus": "Among Us",
  "rustclient": "Rust", "palworld": "Palworld",
  "helldivers2": "Helldivers 2", "bg3": "Baldur's Gate 3", "bg3_dx11": "Baldur's Gate 3",
  "cyberpunk2077": "Cyberpunk 2077", "witcher3": "The Witcher 3",
  "rdr2": "Red Dead Redemption 2", "warframe.x64": "Warframe", "warframe": "Warframe",
  "destiny2": "Destiny 2", "escapefromtarkov": "Escape from Tarkov",
  "deadbydaylight-win64-shipping": "Dead by Daylight",
  "rainbowsix": "Rainbow Six Siege", "rainbowsix_dx11": "Rainbow Six Siege",
  "robloxplayerbeta": "Roblox", "genshinimpact": "Genshin Impact",
  "sc2": "StarCraft II", "sc2_x64": "StarCraft II",
  "factorio": "Factorio", "factorygame-win64-shipping": "Satisfactory",
  "hollow_knight": "Hollow Knight", "silksong": "Hollow Knight: Silksong",
  "celeste": "Celeste", "lethal company": "Lethal Company",
  "lethalcompany": "Lethal Company", "valheim": "Valheim",
  "7daystodie": "7 Days to Die", "left4dead2": "Left 4 Dead 2",
  "tf_win64": "Team Fortress 2", "hl2": "Half-Life 2",
  "javaw": null, // demasiado genérico: nunca asumir que es un juego
};

let activityTimer = null;
let activityFails = 0;
let lastActivity = "";

// Script de PowerShell que devuelve, en UNA sola llamada:
//  - procs: procesos con ventana (para detectar juegos con el dict GAMES en JS)
//  - media: metadatos de Spotify vía GSMTC (los "controles de medios del
//    sistema" de Windows), con título, artista, álbum, CARÁTULA (base64) y
//    posición/duración. Todo el bloque de media va en try/catch: si WinRT
//    falla en esa máquina, `media` es null y se cae al método del título de
//    ventana (que sigue dando "Artista - Canción"), sin romper nada.
const ACTIVITY_PS = `
$ErrorActionPreference='SilentlyContinue'
$procs = Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name,MainWindowTitle
$media = $null
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $ext = [System.WindowsRuntimeSystemExtensions]
  $asTask = ($ext.GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation\`1' })[0]
  function Await($op,$t){ $m=$asTask.MakeGenericMethod($t); $tk=$m.Invoke($null,@($op)); [void]$tk.Wait(5000); $tk.Result }
  [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] > $null
  [Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime] > $null
  $mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
  $sess = $null
  foreach($x in $mgr.GetSessions()){ if($x.SourceAppUserModelId -match 'Spotify'){ $sess=$x; break } }
  if($sess){
    $p = Await ($sess.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    $tl = $sess.GetTimelineProperties()
    $pb = $sess.GetPlaybackInfo()
    $art = ''
    try {
      if($p.Thumbnail){
        $st = Await ($p.Thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        $sz = [uint32]$st.Size
        if($sz -gt 0 -and $sz -lt 400000){
          $rd = [Windows.Storage.Streams.DataReader]::new($st)
          [void](Await ($rd.LoadAsync($sz)) ([uint32]))
          $bytes = New-Object byte[] $sz
          $rd.ReadBytes($bytes)
          $art = 'data:image/jpeg;base64,'+[Convert]::ToBase64String($bytes)
        }
      }
    } catch {}
    $media = [pscustomobject]@{
      title=$p.Title; artist=$p.Artist; album=$p.AlbumTitle;
      durationMs=[int64]$tl.EndTime.TotalMilliseconds;
      positionMs=[int64]$tl.Position.TotalMilliseconds;
      playing=($pb.PlaybackStatus -eq [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionPlaybackStatus]::Playing);
      art=$art
    }
  }
} catch {}
[pscustomobject]@{ procs=@($procs); media=$media } | ConvertTo-Json -Compress -Depth 4
`;

function detectActivity() {
  // -EncodedCommand (base64 UTF-16LE) evita el infierno de comillas y funciona
  // desde el asar empaquetado (no hay que escribir un .ps1 a disco).
  const encoded = Buffer.from(ACTIVITY_PS, "utf16le").toString("base64");
  const args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded];
  execFile(
    "powershell.exe", args,
    { windowsHide: true, timeout: 12_000, maxBuffer: 8 * 1024 * 1024 },
    (err, stdout) => {
      if (err) {
        activityFails += 1;
        if (activityFails >= 5 && activityTimer) {
          clearInterval(activityTimer);
          activityTimer = null;
          updLog("actividad: desactivada tras fallos repetidos de PowerShell");
        }
        return;
      }
      activityFails = 0;
      let data;
      try {
        data = JSON.parse(stdout || "{}");
      } catch {
        return;
      }
      let procs = data?.procs || [];
      if (!Array.isArray(procs)) procs = [procs];
      const media = data?.media || null;

      // Juego: dict curado sobre el nombre del proceso.
      let game = null;
      let spotifyTitle = null; // respaldo por título de ventana
      for (const p of procs) {
        const name = String(p?.Name || "").toLowerCase();
        const title = String(p?.MainWindowTitle || "");
        if (GAMES[name]) game = { kind: "game", text: GAMES[name] };
        else if (name === "spotify" && title.includes(" - ")) spotifyTitle = title.slice(0, 120);
      }

      // Música: si GSMTC dio metadatos, actividad ENRIQUECIDA; si no, el título.
      let music = null;
      if (media && media.title) {
        const text = media.artist ? `${media.artist} - ${media.title}` : media.title;
        music = {
          kind: "music", text: text.slice(0, 128),
          title: media.title, artist: media.artist || "", album: media.album || "",
          art: typeof media.art === "string" && media.art.startsWith("data:image/") ? media.art : "",
          duration_ms: Number(media.durationMs) || 0,
          position_ms: Number(media.positionMs) || 0,
          playing: media.playing !== false,
          at: Date.now(), // instante en que se tomó la posición (el cliente interpola)
        };
      } else if (spotifyTitle) {
        music = { kind: "music", text: spotifyTitle };
      }

      const act = game || music || null; // como Discord: el juego manda
      // La clave de dedupe NO incluye la posición (solo emitimos por canción /
      // play-pause): el cliente avanza el reloj él solo.
      const key = act
        ? act.kind === "music"
          ? `music|${act.text}|${act.playing !== false}`
          : `game|${act.text}`
        : "";
      if (key !== lastActivity) {
        lastActivity = key;
        mainWindow?.webContents.send("activity:update", act);
      }
    },
  );
}

ipcMain.on("activity:setEnabled", (_e, on) => {
  if (activityTimer) clearInterval(activityTimer);
  activityTimer = null;
  activityFails = 0;
  lastActivity = "";
  if (on && process.platform === "win32") {
    detectActivity();
    activityTimer = setInterval(detectActivity, 20_000);
  }
});

// --- Atajos globales (funcionan con la app en segundo plano) ---
let registeredAccels = [];
ipcMain.handle("shortcuts:register", (_e, list) => {
  for (const a of registeredAccels) { try { globalShortcut.unregister(a); } catch {} }
  registeredAccels = [];
  const ok = [];
  for (const { id, accel } of list || []) {
    try {
      globalShortcut.register(accel, () => mainWindow?.webContents.send("shortcuts:trigger", id));
      registeredAccels.push(accel);
      ok.push(accel);
    } catch {}
  }
  return ok; // aceleradores que SÍ se registraron (el resto cae al foco)
});
app.on("will-quit", () => globalShortcut.unregisterAll());

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
  setupUpdater();
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
