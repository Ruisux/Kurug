<script>
  // Picker de GIFs (Tenor). Muestra tendencias al abrir; busca con debounce.
  // Al elegir, devuelve la URL del GIF (se envía como image_url).
  import { onMount, tick } from "svelte";
  import { api } from "../lib/api.js";

  export let onPick = () => {};
  export let onClose = () => {};

  let q = "";
  let results = [];
  let loading = true;
  let error = "";
  let timer = null;
  let inputEl;

  async function load(promise) {
    loading = true;
    error = "";
    try {
      results = await promise;
    } catch (e) {
      results = [];
      error = e?.status === 503
        ? "El buscador de GIFs no está configurado en el servidor."
        : "No se pudieron cargar los GIFs.";
    } finally {
      loading = false;
    }
  }

  function onInput() {
    clearTimeout(timer);
    const term = q.trim();
    timer = setTimeout(() => {
      load(term ? api.gifsSearch(term) : api.gifsFeatured());
    }, 300);
  }

  onMount(() => {
    load(api.gifsFeatured());
    tick().then(() => inputEl?.focus());
  });
</script>

<div class="gifp">
  <div class="top">
    <i class="ti ti-search"></i>
    <input
      bind:this={inputEl}
      bind:value={q}
      on:input={onInput}
      on:keydown={(e) => e.key === "Escape" && onClose()}
      placeholder="Buscar GIFs en Giphy…"
    />
    <button class="x" on:click={onClose} aria-label="Cerrar"><i class="ti ti-x"></i></button>
  </div>

  <div class="grid">
    {#if loading}
      <p class="info"><i class="ti ti-loader-2 spin"></i> Cargando…</p>
    {:else if error}
      <p class="info err">{error}</p>
    {:else if results.length === 0}
      <p class="info">Sin resultados.</p>
    {:else}
      {#each results as g (g.id)}
        <button class="cell" on:click={() => onPick(g.url)} title={g.description}>
          <img src={g.preview} alt={g.description || "gif"} loading="lazy" />
        </button>
      {/each}
    {/if}
  </div>
  <div class="attr">Vía Giphy</div>
</div>

<style>
  .gifp {
    width: 320px;
    max-width: 86vw;
    height: 380px;
    display: flex;
    flex-direction: column;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 14px;
    box-shadow: 0 18px 44px var(--shadow);
    overflow: hidden;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 9px 11px;
    border-bottom: 1px solid var(--bd);
    color: var(--mut);
  }
  .top input {
    flex: 1;
    min-width: 0;
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 13px;
    color: var(--tx);
    outline: none;
  }
  .top input:focus {
    border-color: var(--shu);
  }
  .top .x {
    background: none;
    border: none;
    color: var(--mut);
    font-size: 16px;
  }
  .top .x:hover {
    color: var(--shu);
  }
  /* Mosaico tipo Giphy: 2 columnas, cada GIF conserva su proporción. */
  .grid {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 8px;
    column-count: 2;
    column-gap: 6px;
  }
  .cell {
    display: block;
    width: 100%;
    margin: 0 0 6px;
    break-inside: avoid;
    padding: 0;
    border: 1px solid var(--bd2);
    border-radius: 9px;
    overflow: hidden;
    background: var(--art-bg);
    cursor: pointer;
    line-height: 0;
  }
  .cell:hover {
    border-color: var(--shu);
  }
  .cell img {
    width: 100%;
    height: auto;
    display: block;
  }
  .info {
    column-span: all;
    text-align: center;
    color: var(--mut);
    font-size: 13px;
    padding: 24px 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
  }
  .info.err {
    color: #c0593b;
  }
  .attr {
    text-align: right;
    font-size: 10px;
    color: var(--fnt);
    padding: 3px 10px;
    border-top: 1px solid var(--bd);
  }
  .spin {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
