<script>
  import Avatar from "./Avatar.svelte";
  import { voiceState } from "../lib/voice.js";
  import { jpLabels, channelKanji } from "../lib/appearance.js";

  export let channels = [];
  export let dms = [];
  export let currentChannelId = null;
  export let currentDmUserId = null;
  export let unread = {};
  export let voiceMembers = {}; // channel_id (texto) -> [{id, display_name, avatar_url}]
  export let isAdmin = false;
  export let onSelectChannel = () => {};   // canal de TEXTO -> abre chat
  export let onSelectVoice = () => {};     // canal de VOZ -> se une a la voz
  export let onSelectDm = () => {};
  export let onCreate = () => {};          // (name, kind)
  export let onDeleteChannel = () => {};
  export let onReorder = () => {};         // (orderedIds)

  let newName = "";
  let newKind = "text"; // "text" | "voice"

  // Separamos por tipo. El canal de música (is_music) cuenta como texto.
  $: textChannels = channels.filter((c) => c.kind !== "voice");
  $: voiceChannels = channels.filter((c) => c.kind === "voice");

  function create() {
    const name = newName.trim();
    if (!name) return;
    onCreate(name, newKind);
    newName = "";
  }

  function confirmDelete(c, e) {
    e.stopPropagation();
    if (confirm(`¿Borrar el canal ${c.kind === "voice" ? "🔊" : "#"}${c.name} y todos sus mensajes?`)) {
      onDeleteChannel(c.id);
    }
  }

  let menu = null; // { channel, x, y }
  function openMenu(e, c) {
    if (!isAdmin) return; // por ahora la única acción del menú es borrar (admin)
    e.preventDefault();
    menu = { channel: c, x: e.clientX, y: e.clientY };
  }
  function delFromMenu() {
    const c = menu.channel;
    menu = null;
    if (confirm(`¿Borrar el canal ${c.kind === "voice" ? "🔊" : "#"}${c.name} y todos sus mensajes?`)) onDeleteChannel(c.id);
  }
  $: menuLeft = menu ? Math.min(menu.x, window.innerWidth - 210) : 0;
  $: menuTop = menu ? Math.min(menu.y, window.innerHeight - 110) : 0;

  // --- Arrastrar para reordenar (dentro de su misma sección) ---
  let dragId = null;
  let overId = null;
  function onDragStart(e, c) {
    dragId = c.id;
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", String(c.id)); } catch {}
  }
  function onDragOver(e, c) {
    if (dragId == null || dragId === c.id) return;
    e.preventDefault();
    overId = c.id;
  }
  function onDrop(e, target, list) {
    e.preventDefault();
    overId = null;
    if (dragId == null || dragId === target.id) { dragId = null; return; }
    const ids = list.map((c) => c.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(target.id);
    if (from === -1 || to === -1) { dragId = null; return; }
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    dragId = null;
    // Orden global = orden de texto seguido del de voz, con esta sección movida.
    const textIds = list === textChannels ? ids : textChannels.map((c) => c.id);
    const voiceIds = list === voiceChannels ? ids : voiceChannels.map((c) => c.id);
    onReorder([...textIds, ...voiceIds]);
  }
  function onDragEnd() { dragId = null; overId = null; }

  // Peers en la voz actual (para el punto de "en directo" en el canal activo).
  $: activeVoiceId = $voiceState.active ? $voiceState.channelId : null;
</script>

<aside class="col">
  <header>
    <div class="brand">
      <span class="seal serif">刃</span>
      <div>
        <div class="display title name">Kurug</div>
        <div class="sub serif">クルグ</div>
      </div>
    </div>
  </header>

  <div class="body">
    <!-- Canales de texto -->
    <div class="lbl">Texto{#if $jpLabels}<span class="lk">テキスト</span>{/if}</div>
    {#each textChannels as c (c.id)}
      <div
        class="row"
        class:on={c.id === currentChannelId}
        class:dragover={overId === c.id}
        class:dragging={dragId === c.id}
        role="presentation"
        draggable="true"
        on:dragstart={(e) => onDragStart(e, c)}
        on:dragover={(e) => onDragOver(e, c)}
        on:drop={(e) => onDrop(e, c, textChannels)}
        on:dragend={onDragEnd}
        on:contextmenu={(e) => openMenu(e, c)}
      >
        <button class="ch" class:unread={unread[c.id] > 0} on:click={() => onSelectChannel(c.id)}>
          <span class="hash">{c.is_music ? "♪" : "#"}</span>{c.name}
          {#if $jpLabels && channelKanji(c.name)}<span class="rd">{channelKanji(c.name)}</span>{/if}
          {#if c.id === currentChannelId}
            <svg class="brush" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true"><path d="M3 5 C25 2 45 7 65 4 S100 6 117 4 L117 7 C95 9 55 5 33 7 S8 6 3 7 Z" fill="currentColor"/></svg>
          {/if}
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
    {#if textChannels.length === 0}
      <p class="empty">Crea el primer canal abajo.</p>
    {/if}

    <!-- Separador de tinta entre secciones -->
    <div class="ink"><svg viewBox="0 0 200 6" preserveAspectRatio="none" aria-hidden="true"><path d="M2 3 C40 1 70 5 110 3 S180 4 198 2" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg></div>

    <!-- Canales de voz -->
    <div class="lbl">Voz{#if $jpLabels}<span class="lk">ボイス</span>{/if}</div>
    {#each voiceChannels as c (c.id)}
      <div class="vwrap">
        <div
          class="row voice"
          class:on={c.id === activeVoiceId}
          class:dragover={overId === c.id}
          class:dragging={dragId === c.id}
          role="presentation"
          draggable="true"
          on:dragstart={(e) => onDragStart(e, c)}
          on:dragover={(e) => onDragOver(e, c)}
          on:drop={(e) => onDrop(e, c, voiceChannels)}
          on:dragend={onDragEnd}
          on:contextmenu={(e) => openMenu(e, c)}
        >
          <button class="ch" on:click={() => onSelectVoice(c.id)}>
            <span class="hash"><i class="ti ti-volume"></i></span>{c.name}
            {#if $jpLabels && channelKanji(c.name)}<span class="rd">{channelKanji(c.name)}</span>{/if}
            {#if (voiceMembers[c.id] || []).length}
              <span class="count">{(voiceMembers[c.id] || []).length}</span>
            {/if}
            {#if c.id === activeVoiceId}<span class="livedot" title="Estás aquí"></span>{/if}
            {#if c.id === activeVoiceId}
              <svg class="brush" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true"><path d="M3 5 C25 2 45 7 65 4 S100 6 117 4 L117 7 C95 9 55 5 33 7 S8 6 3 7 Z" fill="currentColor"/></svg>
            {/if}
          </button>
          {#if isAdmin}
            <button class="x" title="Borrar canal" aria-label="Borrar canal" on:click={(e) => confirmDelete(c, e)}>
              <i class="ti ti-trash"></i>
            </button>
          {/if}
        </div>
        {#if (voiceMembers[c.id] || []).length}
          <div class="vmembers">
            {#each voiceMembers[c.id] as m (m.id)}
              <span class="vm" title={m.display_name}>
                <Avatar name={m.display_name} url={m.avatar_url} size={20} />
                <span class="vm-name">{m.display_name}</span>
              </span>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
    {#if voiceChannels.length === 0}
      <p class="empty">Sin canales de voz. Crea uno abajo (tipo Voz).</p>
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
      <div class="kindpick" role="group" aria-label="Tipo de canal">
        <button class="kb" class:on={newKind === "text"} on:click={() => (newKind = "text")}>
          <i class="ti ti-hash"></i> Texto
        </button>
        <button class="kb" class:on={newKind === "voice"} on:click={() => (newKind = "voice")}>
          <i class="ti ti-volume"></i> Voz
        </button>
      </div>
      <div class="newrow">
        <input
          placeholder={newKind === "voice" ? "nuevo canal de voz" : "nuevo canal"}
          bind:value={newName}
          on:keydown={(e) => e.key === "Enter" && create()}
        />
        <button class="add" on:click={create} aria-label="Crear canal">
          <i class="ti ti-plus"></i>
        </button>
      </div>
    </div>
  </div>

  <!-- Ambientación sumi-e: torii + sol naciente al pie de la columna. -->
  <svg class="amb" viewBox="0 0 200 130" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
    <circle cx="100" cy="92" r="36" fill="currentColor" />
    <path d="M40 78 H160 M46 87 H154 M60 87 V130 M140 87 V130" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" />
    <path d="M52 78 Q100 65 148 78" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" />
  </svg>
</aside>

{#if menu}
  <div class="cm-backdrop" on:click={() => (menu = null)} on:contextmenu|preventDefault={() => (menu = null)} role="presentation"></div>
  <div class="cmenu" style="left:{menuLeft}px; top:{menuTop}px" role="menu">
    <div class="cm-head">{menu.channel.kind === "voice" ? "🔊" : "#"} {menu.channel.name}</div>
    <button class="cm-item danger" on:click={delFromMenu} role="menuitem">
      <i class="ti ti-trash"></i> Borrar canal
    </button>
  </div>
{/if}

<style>
  .col {
    width: 256px;
    background: var(--pan);
    border-right: 1px solid var(--bd);
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
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
    padding: 18px 18px 15px;
    border-bottom: 1px solid var(--bd);
    position: relative;
    z-index: 1;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 11px;
  }
  .seal {
    width: 38px;
    height: 38px;
    flex: none;
    border-radius: 12px;
    background: var(--shu);
    color: #160d0a;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 21px;
    line-height: 1;
  }
  .name {
    font-size: 21px;
    font-weight: 600;
    letter-spacing: 0.02em;
    line-height: 1.1;
  }
  .sub {
    font-size: 11.5px;
    color: var(--mut);
    letter-spacing: 0.08em;
    margin-top: 1px;
  }
  .body {
    padding: 12px;
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
  }
  .lbl {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--mut);
    padding: 0 8px;
    margin: 16px 0 7px;
    display: flex;
    align-items: baseline;
    gap: 7px;
  }
  .lbl .lk {
    font-size: 10px;
    letter-spacing: 0;
    color: var(--fnt);
    text-transform: none;
  }
  .ink {
    color: var(--bd2);
    padding: 4px 10px 2px;
    height: 10px;
  }
  .ink svg {
    width: 100%;
    height: 6px;
    display: block;
  }
  .amb {
    position: absolute;
    left: 0;
    right: 0;
    bottom: -6px;
    height: 150px;
    color: var(--tx);
    opacity: 0.08;
    pointer-events: none;
    z-index: 0;
  }
  :global(:root[data-theme="light"]) .amb { opacity: 0.13; }
  .row {
    display: flex;
    align-items: center;
    border-radius: 11px;
  }
  .row.on {
    background: rgba(var(--shu-rgb), 0.09);
  }
  .row:hover {
    background: var(--hover);
  }
  .rd {
    font-size: 11px;
    color: var(--fnt);
    margin-left: 6px;
  }
  .brush {
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 3px;
    height: 6px;
    color: var(--shu);
    pointer-events: none;
  }
  .row.dragging {
    opacity: 0.4;
  }
  .row.dragover {
    box-shadow: inset 0 2px 0 var(--shu);
  }
  .ch {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    text-align: left;
    background: none;
    border: none;
    padding: 11px 12px;
    border-radius: 11px;
    color: var(--mut);
    font-size: 14.5px;
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
    display: inline-flex;
    align-items: center;
    font-size: 13px;
  }
  .row.on .hash {
    color: var(--shu);
  }
  .row.voice .ch:hover .hash {
    color: var(--shu);
  }
  .count {
    flex: none;
    min-width: 16px;
    height: 16px;
    padding: 0 5px;
    border-radius: 999px;
    background: var(--field);
    border: 1px solid var(--bd2);
    color: var(--mut);
    font-size: 10.5px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
    margin-left: auto;
  }
  .vmembers {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 2px 8px 4px 24px;
  }
  .vm {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--mut);
    min-width: 0;
  }
  .vm-name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .livedot {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: 50%;
    background: var(--on, #6bbf59);
    box-shadow: 0 0 0 3px rgba(107, 191, 89, 0.25);
  }
  /* Si no hay contador (canal vacío) pero estás dentro, empuja el punto al final. */
  .count + .livedot {
    margin-left: 4px;
  }
  .ch > .livedot:not(.count + .livedot) {
    margin-left: auto;
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
    flex-direction: column;
    gap: 7px;
  }
  /* Selector de tipo: segmentado a ancho completo, en su propia fila. */
  .kindpick {
    display: flex;
    border: 1px solid var(--bd2);
    border-radius: 9px;
    overflow: hidden;
  }
  .kb {
    flex: 1;
    height: 32px;
    border: none;
    background: transparent;
    color: var(--mut);
    font-size: 12.5px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
  }
  .kb + .kb {
    border-left: 1px solid var(--bd2);
  }
  .kb.on {
    background: rgba(var(--shu-rgb), 0.16);
    color: var(--shu);
  }
  .newrow {
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
