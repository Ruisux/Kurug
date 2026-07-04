import { writable } from "svelte/store";

const KEY = "kurug-theme";

// Presets de tema (el valor va a [data-theme] en <html>).
export const THEMES = [
  { key: "dark", label: "Sumi", jp: "標準", hint: "oscuro cálido" },
  { key: "light", label: "Washi", jp: "和紙", hint: "claro" },
  { key: "amoled", label: "Amoled", jp: "漆黒", hint: "negro puro" },
];
const VALID = new Set(THEMES.map((t) => t.key));

const saved = localStorage.getItem(KEY);
const initial = VALID.has(saved) ? saved : "dark";

export const theme = writable(initial);

theme.subscribe((t) => {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(KEY, t);
});

export function setTheme(t) {
  if (VALID.has(t)) theme.set(t);
}

// Toggle rápido (Rail): alterna claro/oscuro sin pasar por amoled.
export function toggleTheme() {
  theme.update((t) => (t === "light" ? "dark" : "light"));
}
