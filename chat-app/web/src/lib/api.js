import { get } from "svelte/store";
import { token } from "./stores.js";
import { apiUrl } from "./server.js";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function authHeaders() {
  const t = get(token);
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req(method, path, { json, body } = {}) {
  const headers = { ...authHeaders() };
  if (json) headers["Content-Type"] = "application/json";
  const opts = { method, headers };
  if (json) opts.body = JSON.stringify(json);
  if (body) opts.body = body;

  const r = await fetch(apiUrl(path), opts);
  if (!r.ok) {
    let detail;
    try {
      detail = (await r.json()).detail;
    } catch {
      detail = r.statusText;
    }
    // Un 422 de validación trae una LISTA de errores, no un texto: sacarle el
    // mensaje al primero (antes se mostraba "[object Object]").
    if (Array.isArray(detail)) detail = detail[0]?.msg || "Datos no válidos.";
    else if (detail && typeof detail !== "string") detail = "Datos no válidos.";
    throw new ApiError(r.status, detail || "Error");
  }
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const api = {
  register: (email, username, password) =>
    req("POST", "/auth/register", { json: { email, username, password } }),
  verifyCode: (email, code) =>
    req("POST", "/auth/verify", { json: { email, code } }),
  resendCode: (email) =>
    req("POST", "/auth/resend", { json: { email } }),
  forgotPassword: (email) =>
    req("POST", "/auth/forgot", { json: { email } }),
  resetPassword: (email, code, password) =>
    req("POST", "/auth/reset", { json: { email, code, password } }),

  async login(identifier, password) {
    // OAuth2 espera form-urlencoded; "username" admite usuario O correo.
    const body = new URLSearchParams({ username: identifier, password });
    const r = await fetch(apiUrl("/auth/login"), { method: "POST", body });
    if (!r.ok) {
      let detail = "Credenciales inválidas";
      try { detail = (await r.json()).detail || detail; } catch {}
      throw new ApiError(r.status, detail);
    }
    return r.json();
  },

  me: () => req("GET", "/users/me"),
  updateMe: (data) => req("PATCH", "/users/me", { json: data }),
  uploadAvatar: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("POST", "/users/me/avatar", { body: fd });
  },
  user: (id) => req("GET", `/users/${id}`),
  users: () => req("GET", "/users"),
  uploadImage: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("POST", "/uploads/image", { body: fd });
  },
  // Subida de archivo genérico con progreso (XHR: fetch no expone progreso de
  // subida). onProgress recibe un 0..1. Resuelve a {url, name, size}.
  uploadFile(file, onProgress) {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      fd.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl("/uploads/file"));
      const t = get(token);
      if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { resolve(null); }
        } else {
          let detail = "No se pudo subir el archivo";
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch {}
          reject(new ApiError(xhr.status, detail));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Error de red al subir"));
      xhr.send(fd);
    });
  },

  gifsFeatured: (offset = 0) => req("GET", `/gifs/featured?offset=${offset}`),
  gifsSearch: (q, offset = 0) => req("GET", `/gifs/search?q=${encodeURIComponent(q)}&offset=${offset}`),

  channels: () => req("GET", "/channels"),
  createChannel: (name, kind = "text") => req("POST", "/channels", { json: { name, kind } }),
  reorderChannels: (order) => req("PATCH", "/channels/reorder", { json: { order } }),
  deleteChannel: (id) => req("DELETE", `/channels/${id}`),
  messages: (channelId, limit = 50) =>
    req("GET", `/channels/${channelId}/messages?limit=${limit}`),
  searchChannel: (channelId, q) =>
    req("GET", `/channels/${channelId}/search?q=${encodeURIComponent(q)}`),
  channelPins: (channelId) => req("GET", `/channels/${channelId}/pins`),
  searchDm: (userId, q) =>
    req("GET", `/dms/${userId}/search?q=${encodeURIComponent(q)}`),
  dmPins: (userId) => req("GET", `/dms/${userId}/pins`),

  unreadCounts: (lastRead) =>
    req("POST", "/channels/unread", { json: { last_read: lastRead } }),

  presence: () => req("GET", "/presence"),

  dms: (userId, limit = 50) => req("GET", `/dms/${userId}?limit=${limit}`),
  dmConversations: () => req("GET", "/dms/conversations"),
  dmUnreadCounts: (lastRead) =>
    req("POST", "/dms/unread", { json: { last_read: lastRead } }),

  voiceToken: (channelId) => req("POST", `/voice/token/${channelId}`),
  kickVoice: (channelId, identity) =>
    req("POST", `/voice/kick/${channelId}/${identity}`),
};
