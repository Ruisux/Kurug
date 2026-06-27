import { writable } from "svelte/store";

const KEY = "kurug-theme";
const initial = localStorage.getItem(KEY) || "dark";

export const theme = writable(initial);

theme.subscribe((t) => {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(KEY, t);
});

export function toggleTheme() {
  theme.update((t) => (t === "dark" ? "light" : "dark"));
}
