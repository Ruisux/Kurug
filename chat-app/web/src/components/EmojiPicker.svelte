<script>
  import { tick } from "svelte";
  import { GROUPS, FREQUENT, searchEmojis } from "../lib/emoji.js";

  export let onPick = () => {};
  export let onClose = () => {};

  let query = "";
  let activeGroup = GROUPS[0].id;
  let scroller;
  let searchInput;

  $: results = query.trim() ? searchEmojis(query) : null;

  function pick(e) {
    onPick(e);
  }

  async function goTo(id) {
    activeGroup = id;
    query = "";
    await tick();
    const el = scroller?.querySelector(`[data-group="${id}"]`);
    if (el) el.scrollIntoView({ block: "start" });
  }

  // Marca la pestaña activa según lo que esté visible al hacer scroll.
  function onScroll() {
    if (results) return;
    const secs = scroller.querySelectorAll("[data-group]");
    const top = scroller.scrollTop;
    for (const s of secs) {
      if (s.offsetTop - scroller.offsetTop <= top + 8) activeGroup = s.dataset.group;
    }
  }

  // Autofoco en la búsqueda al abrir.
  $: if (searchInput) searchInput.focus();
</script>

<div class="picker" role="dialog" aria-label="Elegir emoji">
  <div class="search">
    <i class="ti ti-search"></i>
    <input
      bind:this={searchInput}
      bind:value={query}
      placeholder="Buscar emoji…"
      on:keydown={(e) => e.key === "Escape" && onClose()}
    />
  </div>

  {#if !results}
    <div class="tabs">
      {#each GROUPS as g (g.id)}
        <button
          class="tab"
          class:active={activeGroup === g.id}
          title={g.label}
          on:click={() => goTo(g.id)}
        >
          <i class="ti {g.icon}"></i>
        </button>
      {/each}
    </div>
  {/if}

  <div class="grid" bind:this={scroller} on:scroll={onScroll}>
    {#if results}
      {#if results.length}
        <div class="rows">
          {#each results as e}
            <button class="emoji" on:click={() => pick(e)}>{e}</button>
          {/each}
        </div>
      {:else}
        <p class="none">Sin resultados para “{query}”.</p>
      {/if}
    {:else}
      <section data-group="frequent">
        <h4>Frecuentes</h4>
        <div class="rows">
          {#each FREQUENT as e}
            <button class="emoji" on:click={() => pick(e)}>{e}</button>
          {/each}
        </div>
      </section>
      {#each GROUPS as g (g.id)}
        <section data-group={g.id}>
          <h4>{g.label}</h4>
          <div class="rows">
            {#each g.emojis as e}
              <button class="emoji" on:click={() => pick(e)}>{e}</button>
            {/each}
          </div>
        </section>
      {/each}
    {/if}
  </div>
</div>

<style>
  .picker {
    width: 296px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 12px;
    box-shadow: 0 14px 38px var(--shadow);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .search {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--bd);
    color: var(--fnt);
  }
  .search input {
    flex: 1;
    min-width: 0;
    background: none;
    border: none;
    outline: none;
    color: var(--tx);
    font-size: 13px;
  }
  .tabs {
    display: flex;
    gap: 1px;
    padding: 4px 6px;
    border-bottom: 1px solid var(--bd);
    overflow-x: auto;
  }
  .tab {
    flex: none;
    background: none;
    border: none;
    color: var(--fnt);
    width: 30px;
    height: 28px;
    border-radius: 7px;
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .tab:hover {
    color: var(--tx);
    background: var(--hover);
  }
  .tab.active {
    color: var(--shu);
    background: rgba(var(--shu-rgb), 0.12);
  }
  .grid {
    max-height: 248px;
    overflow-y: auto;
    padding: 4px 8px 8px;
  }
  section h4 {
    position: sticky;
    top: 0;
    margin: 0;
    padding: 7px 2px 4px;
    font-size: 11px;
    font-weight: 500;
    color: var(--fnt);
    background: var(--pan);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .rows {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 1px;
  }
  .emoji {
    background: none;
    border: none;
    font-size: 20px;
    line-height: 1;
    padding: 5px 0;
    border-radius: 7px;
    cursor: pointer;
  }
  .emoji:hover {
    background: var(--hover);
  }
  .none {
    text-align: center;
    color: var(--fnt);
    font-size: 12.5px;
    padding: 18px 0;
  }
</style>
