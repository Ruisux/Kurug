// Notificaciones con la Web Notifications API (funciona igual en el navegador y
// en Electron, que usa Chromium). Una sola interfaz.

let ready = false;

async function ensurePermission() {
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
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
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
