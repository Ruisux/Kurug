// Preferencias de apariencia local (además del tema y el acento del perfil).
import { writable } from "svelte/store";

const KEY = "kurug-jp-labels";

// Mostrar las lecturas japonesas (kanji) junto a canales/secciones. Discreto y
// opcional: por defecto DESACTIVADO (solo se ven los toques sutiles siempre).
const initial = localStorage.getItem(KEY) === "1";
export const jpLabels = writable(initial);
jpLabels.subscribe((v) => {
  try { localStorage.setItem(KEY, v ? "1" : "0"); } catch {}
});
export function toggleJpLabels() {
  jpLabels.update((v) => !v);
}

// Tamaño de la interfaz. "auto" escala según el ancho de la pantalla (14" vs
// 24"+); el resto fija el zoom a mano. Se aplica como data-uiscale en <html>
// y el CSS de app.css lo convierte en --ui-zoom.
const SCALE_KEY = "kurug-ui-scale";
export const UI_SCALES = [
  { key: "auto", label: "Auto (según pantalla)" },
  { key: "1", label: "Normal" },
  { key: "1.1", label: "Grande" },
  { key: "1.2", label: "Muy grande" },
  { key: "1.35", label: "Enorme" },
];
export const uiScale = writable(localStorage.getItem(SCALE_KEY) || "auto");
uiScale.subscribe((v) => {
  try { localStorage.setItem(SCALE_KEY, v); } catch {}
  const el = document.documentElement;
  if (v === "auto") delete el.dataset.uiscale;
  else el.dataset.uiscale = v;
});

// Paleta de acentos sugeridos (nombre japonés + hex). El usuario también puede
// elegir un color personalizado. Tiñe TODO lo del acento vía --shu.
export const ACCENTS = [
  { key: "shu", label: "朱 bermellón", hex: "#e2553b" },
  { key: "ai", label: "藍 índigo", hex: "#5a76c4" },
  { key: "matcha", label: "抹茶 matcha", hex: "#6f9e5a" },
  { key: "sakura", label: "桜 sakura", hex: "#dd8bab" },
  { key: "kin", label: "金 oro", hex: "#c2a35b" },
  { key: "murasaki", label: "紫 púrpura", hex: "#9a6cc0" },
];

// Lectura kanji para canales conocidos (solo se muestra si jpLabels está ON).
// Para nombres sin correspondencia no se muestra nada: discreto y seguro.
const CHANNEL_KANJI = {
  general: "一般",
  aportes: "寄稿",
  "música": "音楽",
  musica: "音楽",
  principal: "主",
  random: "雑談",
  memes: "戯画",
  ayuda: "助力",
  bienvenida: "歓迎",
  reglas: "規則",
  anuncios: "告知",
};
export function channelKanji(name) {
  return CHANNEL_KANJI[(name || "").trim().toLowerCase()] || "";
}
