<script>
  // Picker de GIFs (Giphy). Tendencias al abrir, categorías rápidas, búsqueda
  // con debounce, FAVORITOS (localStorage) y scroll infinito ("muchos más").
  // Al elegir, devuelve la URL del GIF (se envía como image_url).
  import { onMount, tick } from "svelte";
  import { api } from "../lib/api.js";

  export let onPick = () => {};
  export let onClose = () => {};

  // Categorías rápidas: cada chip lanza una búsqueda con ese término.
  const CATEGORIES = [
    { label: "Reacciones", q: "reaction" },
    { label: "Risa", q: "laugh" },
    { label: "Amor", q: "love" },
    { label: "Saludo", q: "hello" },
    { label: "Baile", q: "dance" },
    { label: "Meme", q: "meme" },
    { label: "Anime", q: "anime" },
    { label: "Sí", q: "yes" },
    { label: "No", q: "no" },
    { label: "Aplausos", q: "applause" },
    { label: "Llorar", q: "crying" },
    { label: "Ok", q: "okay" },
  ];
  const FAV_KEY = "kurug-gif-favs";

  let q = "";
  let results = [];
  let loading = true;
  let loadingMore = false;
  let error = "";
  let timer = null;
  let inputEl;
  let gridEl;
  let offset = 0;
  let hasMore = true;
  let mode = "trending"; // "trending" | "search" | "favorites"
  let favs = loadFavs();

  function loadFavs() {
    try { return JSON.parse(localStorage.getItem(FAV_KEY)) || []; }
    catch { return []; }
  }
  function saveFavs() {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(favs.slice(0, 200))); } catch {}
  }
  function isFav(g) {
    return favs.some((f) => f.id === g.id);
  }
  function toggleFav(g) {
    if (isFav(g)) favs = favs.filter((f) => f.id !== g.id);
    else favs = [{ id: g.id, url: g.url, preview: g.preview, description: g.description }, ...favs];
    saveFavs();
  }

  function pageFor(off) {
    const term = q.trim();
    return term ? api.gifsSearch(term, off) : api.gifsFeatured(off);
  }

  // Carga la primera página del modo/búsqueda actual (reemplaza la lista).
  async function reload() {
    if (mode === "favorites") { loading = false; error = ""; return; }
    loading = true;
    error = "";
    offset = 0;
    hasMore = true;
    try {
      results = await pageFor(0);
      offset = results.length;
      hasMore = results.length >= 30;
      if (gridEl) gridEl.scrollTop = 0;
    } catch (e) {
      results = [];
      error = e?.status === 503
        ? "El buscador de GIFs no está configurado en el servidor."
        : "No se pudieron cargar los GIFs.";
    } finally {
      loading = false;
    }
  }

  // Página siguiente (scroll infinito): añade sin borrar.
  async function loadMore() {
    if (loadingMore || !hasMore || loading || mode === "favorites") return;
    loadingMore = true;
    try {
      const more = await pageFor(offset);
      // Evita duplicados por si Giphy repite en el borde de páginas.
      const seen = new Set(results.map((r) => r.id));
      const fresh = more.filter((m) => !seen.has(m.id));
      results = [...results, ...fresh];
      offset += more.length;
      hasMore = more.length >= 30;
    } catch {
      hasMore = false;
    } finally {
      loadingMore = false;
    }
  }

  function onScroll() {
    if (!gridEl || mode === "favorites") return;
    const nearBottom = gridEl.scrollHeight - gridEl.scrollTop - gridEl.clientHeight < 300;
    if (nearBottom) loadMore();
  }

  function onInput() {
    clearTimeout(timer);
    mode = q.trim() ? "search" : "trending";
    timer = setTimeout(reload, 300);
  }
  function pickCategory(c) {
    q = c.q;
    mode = "search";
    reload();
    inputEl?.focus();
  }
  function showFavorites() {
    mode = "favorites";
    q = "";
    error = "";
    loading = false;
  }
  function showTrending() {
    mode = "trending";
    q = "";
    reload();
  }

  $: shown = mode === "favorites" ? favs : results;

  onMount(() => {
    reload();
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

  <!-- Chips: Tendencias / Favoritos + categorías rápidas. -->
  <div class="chips">
    <button class="chip" class:on={mode === "trending"} on:click={showTrending}>
      <i class="ti ti-flame"></i> Tendencias
    </button>
    <button class="chip fav" class:on={mode === "favorites"} on:click={showFavorites}>
      <i class="ti ti-star"></i> Favoritos{#if favs.length} · {favs.length}{/if}
    </button>
    {#each CATEGORIES as c (c.q)}
      <button class="chip" class:on={mode === "search" && q.trim() === c.q} on:click={() => pickCategory(c)}>{c.label}</button>
    {/each}
  </div>

  <div class="grid" bind:this={gridEl} on:scroll={onScroll}>
    {#if loading}
      <p class="info"><i class="ti ti-loader-2 spin"></i> Cargando…</p>
    {:else if error}
      <p class="info err">{error}</p>
    {:else if mode === "favorites" && favs.length === 0}
      <p class="info">Marca GIFs con la ⭐ para guardarlos aquí.</p>
    {:else if shown.length === 0}
      <p class="info">Sin resultados.</p>
    {:else}
      {#each shown as g (g.id)}
        <div class="cell">
          <button class="pick" on:click={() => onPick(g.url)} title={g.description || "gif"}>
            <img src={g.preview} alt={g.description || "gif"} loading="lazy" />
          </button>
          <button
            class="star"
            class:on={isFav(g)}
            title={isFav(g) ? "Quitar de favoritos" : "Guardar en favoritos"}
            aria-label="Favorito"
            on:click|stopPropagation={() => toggleFav(g)}
          ><i class="ti {isFav(g) ? 'ti-star-filled' : 'ti-star'}"></i></button>
        </div>
      {/each}
      {#if loadingMore}
        <p class="info more"><i class="ti ti-loader-2 spin"></i></p>
      {/if}
    {/if}
  </div>
  <div class="attr">Vía Giphy</div>
</div>

<style>
  .gifp {
    width: 320px;
    max-width: calc(86 * var(--vw));
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
  /* Chips de categorías / tendencias / favoritos (scroll horizontal). */
  .chips {
    display: flex;
    gap: 6px;
    padding: 8px 10px;
    overflow-x: auto;
    border-bottom: 1px solid var(--bd);
    scrollbar-width: none;
  }
  .chips::-webkit-scrollbar { display: none; }
  .chip {
    flex: none;
    padding: 5px 11px;
    border-radius: 999px;
    border: 1px solid var(--bd2);
    background: var(--field);
    color: var(--mut);
    font-size: 12px;
    white-space: nowrap;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .chip:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .chip.on {
    background: rgba(var(--shu-rgb), 0.16);
    color: var(--shu);
    border-color: var(--shu);
  }
  .chip.fav.on {
    background: rgba(226, 179, 59, 0.18);
    color: #e2b33b;
    border-color: #e2b33b;
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
    position: relative;
    width: 100%;
    margin: 0 0 6px;
    break-inside: avoid;
    border-radius: 9px;
    overflow: hidden;
    background: var(--art-bg);
    line-height: 0;
    border: 1px solid var(--bd2);
  }
  .cell:hover {
    border-color: var(--shu);
  }
  .pick {
    display: block;
    width: 100%;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    line-height: 0;
  }
  .pick img {
    width: 100%;
    height: auto;
    display: block;
  }
  /* Estrella de favorito, arriba a la derecha de cada GIF. */
  .star {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.5);
    color: #fff;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .cell:hover .star,
  .star.on {
    opacity: 1;
  }
  .star.on {
    color: #e2b33b;
  }
  .star:hover {
    background: rgba(0, 0, 0, 0.72);
  }
  .info.more {
    padding: 10px;
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
