import { writable } from "svelte/store";

function persisted(key, init) {
  const existing = localStorage.getItem(key);
  const store = writable(existing ?? init);
  store.subscribe((val) => {
    if (val == null) localStorage.removeItem(key);
    else localStorage.setItem(key, val);
  });
  return store;
}

// JWT del usuario autenticado (persistido entre recargas).
export const token = persisted("kurug-token", null);

// Perfil del usuario actual (en memoria; se recarga al iniciar).
export const me = writable(null);
