<script>
  // Apariencia: tema (Sumi / Washi / Amoled), color de acento (paleta japonesa
  // + personalizado) y el interruptor de lecturas japonesas. El acento se guarda
  // en el perfil (accent_color); el tema y el japonés, en local.
  import { theme, THEMES, setTheme } from "../lib/theme.js";
  import {
    jpLabels, toggleJpLabels, decorations, toggleDecorations, ACCENTS, uiScale, UI_SCALES,
  } from "../lib/appearance.js";
  import { me } from "../lib/stores.js";
  import { api } from "../lib/api.js";

  export let onClose = () => {};
  export let onSaved = () => {};

  let accent = $me.accent_color || "#e2553b";

  // Colores de muestra por preset (para la vista previa, independientes del tema
  // activo).
  const PREVIEW = {
    dark: { bg: "#1c1714", tx: "#ece5db", bd: "rgba(194,163,91,0.3)" },
    light: { bg: "#f1ead9", tx: "#2a231b", bd: "rgba(120,92,40,0.34)" },
    amoled: { bg: "#000000", tx: "#ece5db", bd: "rgba(194,163,91,0.28)" },
  };

  async function setAccent(hex) {
    accent = hex;
    me.update((u) => ({ ...u, accent_color: hex })); // vista previa inmediata
    try {
      const updated = await api.updateMe({ accent_color: hex });
      me.set(updated);
      onSaved();
    } catch {}
  }
</script>

<button class="backdrop" on:click={onClose} aria-label="Cerrar"></button>
<div class="modal" role="dialog" aria-label="Apariencia">
  <header>
    <span class="display title">Apariencia</span>
    <button class="x" on:click={onClose} aria-label="Cerrar"><i class="ti ti-x"></i></button>
  </header>

  <div class="body">
    <div class="sec">Tema</div>
    <div class="themes">
      {#each THEMES as t (t.key)}
        <button class="theme" class:on={$theme === t.key} on:click={() => setTheme(t.key)}>
          <span class="prev" style="background:{PREVIEW[t.key].bg}; border-color:{PREVIEW[t.key].bd}">
            <span class="pbar" style="background:{PREVIEW[t.key].tx}; opacity:.5"></span>
            <span class="pbar short" style="background:{accent}"></span>
          </span>
          <span class="tname">{t.label}<span class="jp">{t.jp}</span></span>
          <span class="thint">{t.hint}</span>
        </button>
      {/each}
    </div>

    <div class="sec">Color de acento</div>
    <div class="accents">
      {#each ACCENTS as a (a.key)}
        <button
          class="dot"
          class:on={accent.toLowerCase() === a.hex.toLowerCase()}
          style="background:{a.hex}"
          title={a.label}
          aria-label={a.label}
          on:click={() => setAccent(a.hex)}
        ></button>
      {/each}
      <label class="custom" title="Color personalizado">
        <input type="color" bind:value={accent} on:change={() => setAccent(accent)} />
        <i class="ti ti-plus"></i>
      </label>
      <code class="hex">{accent}</code>
    </div>

    <div class="sec">Tamaño de la interfaz</div>
    <div class="scales">
      {#each UI_SCALES as s (s.key)}
        <button class="scale" class:on={$uiScale === s.key} on:click={() => uiScale.set(s.key)}>
          {s.label}
        </button>
      {/each}
    </div>
    <div class="rs" style="margin-top:6px">En "Auto" crece solo en pantallas grandes (24"+). Tu color de acento también pinta tu nombre en los chats.</div>

    <div class="sec">Toques japoneses</div>
    <label class="row">
      <div class="rt">
        <div class="rl">Lecturas japonesas</div>
        <div class="rs">Muestra el kanji junto a canales y secciones (general 一般)</div>
      </div>
      <button class="sw" class:on={$jpLabels} on:click={toggleJpLabels} role="switch" aria-checked={$jpLabels} aria-label="Lecturas japonesas">
        <span class="knob"></span>
      </button>
    </label>
    <label class="row">
      <div class="rt">
        <div class="rl">Decoraciones laterales</div>
        <div class="rs">La rama de sakura y el torii de los lados (el kanji del chat se queda)</div>
      </div>
      <button class="sw" class:on={$decorations} on:click={toggleDecorations} role="switch" aria-checked={$decorations} aria-label="Decoraciones">
        <span class="knob"></span>
      </button>
    </label>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); border: none; z-index: 90;
  }
  .modal {
    position: fixed; z-index: 91; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: min(520px, calc(94 * var(--vw))); max-height: calc(86 * var(--vh)); display: flex; flex-direction: column;
    background: var(--pan); border: 1px solid var(--bd2); border-radius: 16px;
    box-shadow: 0 24px 60px var(--shadow);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 15px 18px; border-bottom: 1px solid var(--bd);
  }
  .title { font-size: 16px; }
  .x { background: none; border: none; color: var(--mut); font-size: 18px; }
  .x:hover { color: var(--shu); }
  .body { padding: 14px 18px 20px; overflow-y: auto; }
  .sec {
    font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--mut); margin: 16px 2px 10px;
  }
  .sec:first-child { margin-top: 4px; }
  .themes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .theme {
    display: flex; flex-direction: column; align-items: flex-start; gap: 7px;
    padding: 10px; border-radius: 12px; border: 1px solid var(--bd2);
    background: var(--field); cursor: pointer; text-align: left;
  }
  .theme:hover { border-color: var(--shu); }
  .theme.on { border-color: var(--shu); box-shadow: 0 0 0 2px rgba(var(--shu-rgb), 0.3); }
  .prev {
    width: 100%; height: 46px; border-radius: 8px; border: 1px solid;
    display: flex; flex-direction: column; justify-content: center; gap: 5px; padding: 0 10px;
  }
  .pbar { height: 5px; width: 70%; border-radius: 3px; }
  .pbar.short { width: 40%; opacity: 1; }
  .tname { font-size: 13.5px; font-weight: 500; color: var(--tx); display: flex; align-items: baseline; gap: 6px; }
  .tname .jp { font-size: 11px; color: var(--mut); }
  .thint { font-size: 11px; color: var(--fnt); }
  .accents { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .dot {
    width: 26px; height: 26px; border-radius: 50%; border: 2px solid transparent; cursor: pointer;
  }
  .dot.on { border-color: var(--tx); box-shadow: 0 0 0 2px var(--pan) inset; }
  .custom {
    position: relative; width: 26px; height: 26px; border-radius: 50%;
    border: 1px dashed var(--bd2); display: flex; align-items: center; justify-content: center;
    color: var(--mut); cursor: pointer; overflow: hidden;
  }
  .custom input { position: absolute; inset: -4px; opacity: 0; cursor: pointer; }
  .hex { font-size: 12px; color: var(--mut); font-family: ui-monospace, monospace; }
  .scales { display: flex; gap: 8px; flex-wrap: wrap; }
  .scale {
    padding: 7px 13px; border-radius: 999px; border: 1px solid var(--bd2);
    background: var(--field); color: var(--tx); font-size: 12.5px; cursor: pointer;
  }
  .scale:hover { border-color: var(--shu); }
  .scale.on { border-color: var(--shu); background: rgba(var(--shu-rgb), 0.14); color: var(--shu); }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .rl { font-size: 13.5px; color: var(--tx); }
  .rs { font-size: 11.5px; color: var(--mut); margin-top: 2px; }
  .sw {
    flex: none; width: 42px; height: 24px; border-radius: 999px; border: 1px solid var(--bd2);
    background: var(--field); position: relative; cursor: pointer; transition: background 0.15s;
  }
  .sw.on { background: var(--shu); border-color: var(--shu); }
  .knob {
    position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
    background: var(--mut); transition: transform 0.15s, background 0.15s;
  }
  .sw.on .knob { transform: translateX(18px); background: #1a0f0b; }
</style>
