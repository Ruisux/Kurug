<script>
  import Avatar from "./Avatar.svelte";

  export let channels = [];
  export let dms = [];
  export let currentChannelId = null;
  export let currentDmUserId = null;
  export let unread = {};
  export let isAdmin = false;
  export let onSelectChannel = () => {};
  export let onSelectDm = () => {};
  export let onCreate = () => {};
  export let onDeleteChannel = () => {};

  let newName = "";

  function create() {
    const name = newName.trim();
    if (!name) return;
    onCreate(name);
    newName = "";
  }

  function confirmDelete(c, e) {
    e.stopPropagation();
    if (confirm(`¿Borrar el canal #${c.name} y todos sus mensajes?`)) {
      onDeleteChannel(c.id);
    }
  }

  let menu = null; // { channel, x, y }
  function openMenu(e, c) {
    if (!isAdmin) return; // por ahora la única acción es borrar (admin)
    e.preventDefault();
    menu = { channel: c, x: e.clientX, y: e.clientY };
  }
  function delFromMenu() {
    const c = menu.channel;
    menu = null;
    if (confirm(`¿Borrar el canal #${c.name} y todos sus mensajes?`)) onDeleteChannel(c.id);
  }
  $: menuLeft = menu ? Math.min(menu.x, window.innerWidth - 210) : 0;
  $: menuTop = menu ? Math.min(menu.y, window.innerHeight - 110) : 0;
</script>

<aside class="col">
  <header><div class="display title name">Kurug</div></header>

  <div class="body">
    <div class="lbl">Canales</div>
    {#each channels as c (c.id)}
      <div class="row" class:on={c.id === currentChannelId} on:contextmenu={(e) => openMenu(e, c)} role="presentation">
        <button class="ch" class:unread={unread[c.id] > 0} on:click={() => onSelectChannel(c.id)}>
          <span class="hash">#</span>{c.name}
        </button>
        {#if unread[c.id] > 0}
          <span class="badge">{unread[c.id] > 99 ? "99+" : unread[c.id]}</span>
        {/if}
        {#if isAdmin}
          <button class="x" title="Borrar canal" aria-label="Borrar canal" on:click={(e) => confirmDelete(c, e)}>
            <i class="ti ti-trash"></i>
          </button>
        {/if}
      </div>
    {/each}
    {#if channels.length === 0}
      <p class="empty">Crea el primer canal abajo.</p>
    {/if}

    {#if dms.length}
      <div class="lbl">Directos</div>
      {#each dms as d (d.user.id)}
        <button
          class="ch dm"
          class:on={d.user.id === currentDmUserId}
          on:click={() => onSelectDm(d.user)}
        >
          <Avatar name={d.user.display_name} url={d.user.avatar_url} size={20} status={d.user.status} />
          <span class="dmname">{d.user.display_name}</span>
        </button>
      {/each}
    {/if}

    <div class="new">
      <input
        placeholder="nuevo canal"
        bind:value={newName}
        on:keydown={(e) => e.key === "Enter" && create()}
      />
      <button class="add" on:click={create} aria-label="Crear canal">
        <i class="ti ti-plus"></i>
      </button>
    </div>
  </div>
</aside>

{#if menu}
  <div class="cm-backdrop" on:click={() => (menu = null)} on:contextmenu|preventDefault={() => (menu = null)} role="presentation"></div>
  <div class="cmenu" style="left:{menuLeft}px; top:{menuTop}px" role="menu">
    <div class="cm-head"># {menu.channel.name}</div>
    <button class="cm-item danger" on:click={delFromMenu} role="menuitem">
      <i class="ti ti-trash"></i> Borrar canal
    </button>
  </div>
{/if}

<style>
  .col {
    width: 196px;
    background: var(--pan);
    border-right: 1px solid var(--bd);
    display: flex;
    flex-direction: column;
  }
  @media (max-width: 640px) {
    /* En móvil la lista llena el ancho disponible junto al rail. */
    .col {
      width: auto;
      flex: 1;
      min-width: 0;
    }
  }
  header {
    padding: 15px 14px 12px;
    border-bottom: 1px solid var(--bd);
  }
  .name {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .body {
    padding: 8px;
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .lbl {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--mut);
    padding: 0 8px;
    margin: 14px 0 6px;
  }
  .row {
    display: flex;
    align-items: center;
    border-radius: 8px;
  }
  .row.on,
  .ch.on {
    background: rgba(var(--shu-rgb), 0.13);
  }
  .row:hover {
    background: var(--hover);
  }
  .ch {
    display: flex;
    align-items: center;
    gap: 7px;
    flex: 1;
    min-width: 0;
    text-align: left;
    background: none;
    border: none;
    padding: 7px 9px;
    border-radius: 8px;
    color: var(--mut);
    font-size: 13.5px;
  }
  .ch:hover {
    color: var(--tx);
  }
  .row.on .ch,
  .ch.on {
    color: var(--tx);
  }
  .hash {
    color: var(--fnt);
  }
  .row.on .hash {
    color: var(--shu);
  }
  .ch.unread {
    color: var(--tx);
    font-weight: 600;
  }
  .badge {
    flex: none;
    min-width: 18px;
    height: 18px;
    padding: 0 6px;
    margin-right: 6px;
    border-radius: 999px;
    background: var(--shu);
    color: #1a0f0b;
    font-size: 11px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }
  .ch.dm {
    flex: 0 0 auto; /* en la columna de Directos no debe crecer en vertical */
  }
  .dmname {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .x {
    background: none;
    border: none;
    color: var(--fnt);
    width: 28px;
    height: 28px;
    border-radius: 7px;
    display: none;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }
  .row:hover .x {
    display: flex;
  }
  .x:hover {
    color: var(--shu);
  }
  .empty {
    font-size: 12px;
    color: var(--fnt);
    padding: 0 9px;
  }
  .new {
    margin-top: auto;
    padding-top: 10px;
    display: flex;
    gap: 6px;
  }
  .new input {
    flex: 1;
    min-width: 0;
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 9px;
    padding: 8px 10px;
    font-size: 13px;
    outline: none;
  }
  .new input:focus {
    border-color: var(--shu);
  }
  .add {
    width: 34px;
    border: 1px solid var(--bd2);
    background: transparent;
    color: var(--shu);
    border-radius: 9px;
    font-size: 17px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .add:hover {
    border-color: var(--shu);
    color: var(--tx);
  }
  .cm-backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
  }
  .cmenu {
    position: fixed;
    z-index: 61;
    width: 196px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 11px;
    padding: 6px;
    box-shadow: 0 16px 40px var(--shadow);
  }
  .cm-head {
    padding: 7px 9px 8px;
    font-size: 13px;
    color: var(--mut);
    border-bottom: 1px solid var(--bd);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cm-item {
    display: flex;
    align-items: center;
    gap: 9px;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    color: var(--tx);
    font-size: 13px;
    padding: 8px 9px;
    border-radius: 8px;
  }
  .cm-item:hover {
    background: var(--hover);
  }
  .cm-item.danger {
    color: var(--shu);
  }
  .cm-item.danger:hover {
    background: rgba(var(--shu-rgb), 0.12);
  }
</style>
