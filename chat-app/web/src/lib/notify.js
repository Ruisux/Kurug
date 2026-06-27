// Notificaciones: usa el plugin nativo de Tauri en escritorio y la Web
// Notifications API en el navegador. Una sola interfaz para ambos.

const isTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

let tauri = null;
let ready = false;

async function ensurePermission() {
  if (isTauri) {
    tauri = await import("@tauri-apps/plugin-notification");
    let granted = await tauri.isPermissionGranted();
    if (!granted) granted = (await tauri.requestPermission()) === "granted";
    return granted;
  }
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission !== "denied") {
    return (await Notification.requestPermission()) === "granted";
  }
  return false;
}

export async function initNotifications() {
  try {
    ready = await ensurePermission();
  } catch {
    ready = false;
  }
}

export async function notify(title, body, opts = {}) {
  if (!ready) return;
  try {
    if (isTauri && tauri) tauri.sendNotification({ title, body });
    else if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      // Menciones: prioridad alta -> la notificación permanece hasta cerrarla y
      // se agrupa por etiqueta para no apilar duplicados.
      new Notification(title, {
        body,
        requireInteraction: !!opts.priority,
        tag: opts.tag,
        renotify: !!opts.tag,
      });
    }
  } catch {}
}

// Solo notificar si la ventana no tiene el foco (no molestar mientras chateas).
export function shouldNotify() {
  return typeof document !== "undefined" && !document.hasFocus();
}
