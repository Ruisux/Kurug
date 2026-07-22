<script>
  // Selector de pantalla PROPIO (solo Electron). Lo abre voice.js al compartir.
  // Deja elegir la fuente, la CALIDAD y (para pantallas completas) el audio del
  // sistema. Sustituye al selector de Chrome y evita la barra de "compartiendo".
  import { pickerStore, resolvePick } from "../lib/screenshare.js";
  import { platform } from "../lib/desktop.js";
  import { SCREEN_PRESETS, voiceState } from "../lib/voice.js";
  import { get } from "svelte/store";

  const presetEntries = Object.entries(SCREEN_PRESETS);
  const isWindows = platform() === "windows";

  let sources = [];
  let selectedId = null;
  let systemAudio = false;
  let quality = "equilibrado";

  $: open = $pickerStore != null;
  $: if ($pickerStore) {
    sources = $pickerStore.sources || [];
    selectedId = sources[0]?.id ?? null;
    systemAudio = false;
    quality = get(voiceState).quality || "equilibrado";
  }

  $: screens = sources.filter((s) => s.type === "screen");
  $: windows = sources.filter((s) => s.type === "window");
  $: selected = sources.find((s) => s.id === selectedId) || null;
  // El audio del sistema solo es fiable capturando una PANTALLA completa.
  $: audioAllowed = isWindows && selected?.type === "screen";
  $: if (!audioAllowed) systemAudio = false;

  function share() {
    if (!selectedId) return cancel();
    resolvePick({ id: selectedId, audio: systemAudio && audioAllowed, quality });
  }
  function cancel() {
    resolvePick(null);
  }
</script>

{#if open}
  <button class="backdrop" on:click={cancel} aria-label="Cancelar"></button>
  <div class="modal" role="dialog" aria-label="Elegir qué compartir">
    <header>
      <span class="display title">Compartir pantalla</span>
      <button class="x" on:click={cancel} aria-label="Cerrar"><i class="ti ti-x"></i></button>
    </header>

    <div class="body">
      {#if screens.length}
        <div class="lbl">Pantallas</div>
        <div class="grid">
          {#each screens as s (s.id)}
            <button class="src" class:on={selectedId === s.id} on:click={() => (selectedId = s.id)}>
              {#if s.thumbnail}<img src={s.thumbnail} alt="" />{:else}<div class="ph"><i class="ti ti-device-desktop"></i></div>{/if}
              <span class="nm">{s.name}</span>
            </button>
          {/each}
        </div>
      {/if}

      {#if windows.length}
        <div class="lbl">Ventanas</div>
        <div class="grid">
          {#each windows as s (s.id)}
            <button class="src" class:on={selectedId === s.id} on:click={() => (selectedId = s.id)}>
              {#if s.thumbnail}<img src={s.thumbnail} alt="" />{:else}<div class="ph"><i class="ti ti-app-window"></i></div>{/if}
              <span class="nm">{#if s.appIcon}<img class="ic" src={s.appIcon} alt="" />{/if}{s.name}</span>
            </button>
          {/each}
        </div>
      {/if}

      {#if !sources.length}
        <p class="empty">No hay fuentes disponibles.</p>
      {/if}
    </div>

    <footer>
      <div class="opts">
        <label class="opt">
          <span class="opt-lbl">Calidad</span>
          <select bind:value={quality}>
            {#each presetEntries as [key, p] (key)}
              <option value={key}>{p.label}</option>
            {/each}
          </select>
        </label>
        <label class="audio" class:dim={!audioAllowed}>
          <input type="checkbox" bind:checked={systemAudio} disabled={!audioAllowed} />
          <span>Audio del sistema{#if !audioAllowed}<small>{isWindows ? "solo con pantalla completa" : "solo en Windows"}</small>{/if}</span>
        </label>
      </div>
      <div class="actions">
        <button class="btn ghost" on:click={cancel}>Cancelar</button>
        <button class="btn go" on:click={share} disabled={!selectedId}>
          <i class="ti ti-screen-share"></i> Compartir
        </button>
      </div>
    </footer>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    border: none;
    z-index: 90;
  }
  .modal {
    position: fixed;
    z-index: 91;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(660px, calc(94 * var(--vw)));
    max-height: calc(86 * var(--vh));
    display: flex;
    flex-direction: column;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 16px;
    box-shadow: 0 24px 60px var(--shadow);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 15px 18px;
    border-bottom: 1px solid var(--bd);
  }
  .title { font-size: 16px; }
  .x { background: none; border: none; color: var(--mut); font-size: 18px; }
  .x:hover { color: var(--shu); }
  .body { padding: 12px 16px; overflow-y: auto; }
  .lbl {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--mut);
    margin: 8px 2px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }
  .src {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px;
    background: var(--ink);
    border: 1px solid var(--bd2);
    border-radius: 10px;
    cursor: pointer;
    overflow: hidden;
  }
  .src:hover { border-color: var(--shu); }
  .src.on {
    border-color: var(--shu);
    box-shadow: 0 0 0 2px rgba(var(--shu-rgb), 0.35);
  }
  .src img {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 6px;
    background: #0c0a08;
  }
  .ph {
    width: 100%;
    aspect-ratio: 16 / 9;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0c0a08;
    border-radius: 6px;
    color: var(--mut);
    font-size: 24px;
  }
  .nm {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: var(--tx);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .nm .ic { width: 14px; height: 14px; border-radius: 3px; }
  .empty { color: var(--fnt); font-size: 13px; padding: 12px; }
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 16px;
    border-top: 1px solid var(--bd);
    flex-wrap: wrap;
  }
  .opts { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .opt { display: flex; align-items: center; gap: 8px; }
  .opt-lbl { font-size: 12px; color: var(--mut); }
  .opt select {
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 12.5px;
    color: var(--tx);
    outline: none;
  }
  .opt select:focus { border-color: var(--shu); }
  .audio {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--tx);
    cursor: pointer;
  }
  .audio.dim { opacity: 0.6; cursor: default; }
  .audio input { accent-color: var(--shu); width: 16px; height: 16px; }
  .audio small { color: var(--fnt); font-size: 11px; margin-left: 6px; }
  .actions { display: flex; gap: 8px; margin-left: auto; }
  .btn {
    height: 36px;
    padding: 0 16px;
    border-radius: 9px;
    font-size: 13px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  .btn.ghost {
    background: transparent;
    border: 1px solid var(--bd2);
    color: var(--mut);
  }
  .btn.ghost:hover { color: var(--tx); border-color: var(--shu); }
  .btn.go {
    background: var(--shu);
    border: 1px solid var(--shu);
    color: #1a0f0b;
    font-weight: 500;
  }
  .btn.go:hover { background: var(--shu-deep); }
  .btn.go:disabled { opacity: 0.5; cursor: default; }
</style>
