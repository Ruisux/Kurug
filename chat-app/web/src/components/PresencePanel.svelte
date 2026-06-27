<script>
  import Avatar from "./Avatar.svelte";
  import UserMenu from "./UserMenu.svelte";
  import { STATUSES } from "../lib/ui.js";
  import { me } from "../lib/stores.js";

  export let online = [];
  export let onSelectUser = () => {};

  let menu = null; // { user, x, y }
  function openMenu(e, u) {
    if (u.id === $me.id) return;
    e.preventDefault();
    menu = { user: u, x: e.clientX, y: e.clientY };
  }

  // Agrupar por estado, en el orden online -> away -> dnd (invisible no se ve).
  const ORDER = ["online", "away", "dnd"];
  $: groups = ORDER.map((key) => ({
    meta: STATUSES.find((s) => s.key === key),
    users: online.filter((u) => u.status === key),
  })).filter((g) => g.users.length > 0);

  $: total = online.length;
</script>

<aside class="col">
  <header>
    <i class="ti ti-circle-dot" style="color:var(--on)"></i>
    Conectados — {total}
  </header>

  <div class="body">
    {#each groups as g (g.meta.key)}
      <div class="lbl">{g.meta.label} — {g.users.length}</div>
      {#each g.users as u (u.id)}
        <button
          class="pr"
          class:dim={g.meta.key !== "online"}
          disabled={u.id === $me.id}
          title={u.id === $me.id ? "Eres tú" : `Mensaje a ${u.display_name} · clic derecho para más`}
          on:click={() => onSelectUser(u)}
          on:contextmenu={(e) => openMenu(e, u)}
        >
          <Avatar name={u.display_name} url={u.avatar_url} size={30} />
          <div class="info">
            <div class="nm">{u.display_name}</div>
            {#if u.custom_status}
              <div class="cs">{u.custom_status}</div>
            {/if}
          </div>
          <span class="dot" style="background:{g.meta.color}"></span>
        </button>
      {/each}
    {/each}

    {#if total === 0}
      <p class="empty">Nadie conectado todavía.</p>
    {/if}
  </div>
</aside>

{#if menu}
  <UserMenu user={menu.user} x={menu.x} y={menu.y} onClose={() => (menu = null)} />
{/if}

<style>
  .col {
    width: 200px;
    background: var(--pan);
    border-left: 1px solid var(--bd);
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 15px 14px 12px;
    border-bottom: 1px solid var(--bd);
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .body {
    padding: 8px 7px;
    flex: 1;
    overflow-y: auto;
  }
  .lbl {
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--fnt);
    padding: 0 8px;
    margin: 12px 0 5px;
  }
  .pr {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 5px 8px;
    border-radius: 8px;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .pr:hover:not(:disabled) {
    background: var(--hover);
  }
  .pr:disabled {
    cursor: default;
  }
  .pr.dim {
    opacity: 0.72;
  }
  .info {
    flex: 1;
    min-width: 0;
  }
  .nm {
    font-size: 12.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cs {
    font-size: 11px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
  }
  .empty {
    font-size: 12px;
    color: var(--fnt);
    padding: 8px;
  }
</style>
