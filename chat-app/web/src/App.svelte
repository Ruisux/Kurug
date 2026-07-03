<script>
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import { token, me } from "./lib/stores.js";
  import { api } from "./lib/api.js";
  import { preloadKrisp } from "./lib/voice.js";
  import Login from "./components/Login.svelte";
  import Shell from "./components/Shell.svelte";

  let booting = true;

  onMount(async () => {
    preloadKrisp(); // descarga el WASM de Krisp en segundo plano (no bloquea)
    if (get(token)) {
      try {
        me.set(await api.me());
      } catch {
        token.set(null);
      }
    }
    booting = false;
  });

  // Personalización: el acento del usuario tiñe TODO lo que usa el acento
  // (botones, resaltados, tintes) sin tocar los colores base del tema.
  function applyAccent(hex) {
    const m = /^#?([0-9a-fA-F]{6})$/.exec(hex || "");
    if (!m) return;
    const n = parseInt(m[1], 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    const root = document.documentElement.style;
    root.setProperty("--shu", `#${m[1]}`);
    root.setProperty("--shu-rgb", `${r}, ${g}, ${b}`);
    const d = 0.86; // ~14% más oscuro para el hover
    root.setProperty(
      "--shu-deep",
      `rgb(${Math.round(r * d)}, ${Math.round(g * d)}, ${Math.round(b * d)})`,
    );
  }
  $: if ($me?.accent_color) applyAccent($me.accent_color);
</script>

{#if booting}
  <div class="boot serif">刃</div>
{:else if $token && $me}
  <Shell />
{:else}
  <Login />
{/if}

<style>
  .boot {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 64px;
    color: var(--shu);
    opacity: 0.5;
  }
</style>
