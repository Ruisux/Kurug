// Conexiones WebSocket con auto-reconexión (chat por canal y presencia global).
//
// reconnectingSocket reabre la conexión con backoff exponencial si se cae la red,
// así no hay que recargar la app. `url` es una función para releer el token fresco
// en cada reintento. Devuelve { send, close } — send acepta un objeto (lo serializa).
import { wsBase } from "./server.js";

function reconnectingSocket({ url, onMessage, onOpen }) {
  let ws = null;
  let closed = false;
  let attempt = 0;
  let timer = null;

  function connect() {
    ws = new WebSocket(url());
    ws.onopen = () => {
      attempt = 0;
      if (onOpen) onOpen();
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch {}
    };
    ws.onclose = () => {
      if (closed) return;
      const delay = Math.min(1000 * 2 ** attempt, 15000); // 1s,2s,4s… máx 15s
      attempt += 1;
      timer = setTimeout(connect, delay);
    };
    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
  }

  connect();

  return {
    send(obj) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    },
    close() {
      closed = true;
      clearTimeout(timer);
      try { ws && ws.close(); } catch {}
    },
  };
}

function wsURL(path) {
  return `${wsBase()}${path}`;
}

export function chatSocket(channelId, tok, onMessage) {
  return reconnectingSocket({
    url: () => wsURL(`/ws/${channelId}?token=${tok}`),
    onMessage,
  });
}

export function presenceSocket(tok, onMessage, onOpen) {
  return reconnectingSocket({
    url: () => wsURL(`/ws/presence?token=${tok}`),
    onMessage,
    onOpen,
  });
}

export { reconnectingSocket, wsURL };
