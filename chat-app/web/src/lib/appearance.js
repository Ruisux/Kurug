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
