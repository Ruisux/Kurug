<script>
  import Avatar from "./Avatar.svelte";
  import UserMenu from "./UserMenu.svelte";
  import ProfileCard from "./ProfileCard.svelte";
  import { statusColor, statusLabel } from "../lib/ui.js";
  import { me } from "../lib/stores.js";
  import { decorations } from "../lib/appearance.js";

  export let online = [];        // usuarios conectados (info en vivo)
  export let allUsers = [];      // todos los miembros (conectados y no)
  export let userVoice = {};     // id -> nombre del canal de voz donde está
  export let onSelectUser = () => {};

  let menu = null; // { user, x, y }
  function openMenu(e, u) {
    if (u.id === $me.id) return;
    e.preventDefault();
    menu = { user: u, x: e.clientX, y: e.clientY };
  }

  // Clic IZQUIERDO: tarjeta de perfil (antes abría el DM directamente; el
  // botón "Enviar mensaje" de la tarjeta sigue haciendo eso).
  let profile = null; // { user, x, y }
  function openProfile(e, u) {
    if (u.id === $me.id) return;
    // El perfil guardado trae un `status` de preferencia; si NO está conectado,
    // la tarjeta debe decir "Desconectado" (no ese estado guardado).
    profile = {
      user: u.connected ? u : { ...u, status: "offline" },
      x: e.clientX,
      y: e.clientY,
    };
  }

  // Mezclamos: para los conectados usamos la info EN VIVO (estado/custom/avatar);
  // para el resto, su perfil base. Así el panel muestra a TODO el grupo.
  $: onlineById = new Map(online.map((u) => [u.id, u]));
  $: members = allUsers.map((u) =>
    onlineById.has(u.id)
      ? { ...u, ...onlineById.get(u.id), connected: true }
      : { ...u, connected: false },
  );
  const byName = (a, b) => (a.display_name || "").localeCompare(b.display_name || "");
  $: connected = members.filter((m) => m.connected).sort(byName);
  $: offline = members.filter((m) => !m.connected).sort(byName);

  // Línea secundaria de la tarjeta: voz > estado personalizado > etiqueta de estado.
  function subtitle(u) {
    if (userVoice[u.id]) return null; // la voz se muestra como chip aparte
    if (u.connected && u.custom_status) return u.custom_status;
    return u.connected ? statusLabel(u.status) : "Desconectado";
  }
</script>

<aside class="col">
  <header>
    <i class="ti ti-users"></i>
    <span>Miembros</span>
    <span class="hcount">{connected.length}/{members.length}</span>
  </header>

  <div class="body">
    <div class="lbl">En línea — {connected.length}</div>
    {#each connected as u (u.id)}
      <button
        class="card"
        style="--ac:{u.accent_color || 'var(--shu)'}"
        disabled={u.id === $me.id}
        title={u.id === $me.id ? "Eres tú" : `Perfil de ${u.display_name} · clic derecho para opciones de voz`}
        on:click={(e) => openProfile(e, u)}
        on:contextmenu={(e) => openMenu(e, u)}
      >
        <span class="av"><Avatar name={u.display_name} url={u.avatar_url} size={42} status={u.status} /></span>
        <span class="info">
          <span class="nm">{u.display_name}{#if u.is_admin}<span class="hanko serif" title="Admin">主</span>{/if}</span>
          {#if userVoice[u.id]}
            <span class="voice"><i class="ti ti-volume"></i>{userVoice[u.id]}</span>
          {:else if u.activity}
            <span class="act" title={u.activity.text}>
              <i class="ti {u.activity.kind === 'game' ? 'ti-device-gamepad-2' : 'ti-music'}"></i>
              {u.activity.kind === "game" ? "Jugando a" : "Escuchando"} {u.activity.text}
            </span>
          {:else}
            <span class="cs">{subtitle(u)}</span>
          {/if}
        </span>
      </button>
    {/each}
    {#if connected.length === 0}
      <p class="empty">Nadie conectado.</p>
    {/if}

    {#if offline.length}
      <div class="lbl">Desconectados — {offline.length}</div>
      {#each offline as u (u.id)}
        <button
          class="card off"
          disabled={u.id === $me.id}
          title={u.id === $me.id ? "Eres tú" : `Perfil de ${u.display_name} · clic derecho para opciones de voz`}
          on:click={(e) => openProfile(e, u)}
          on:contextmenu={(e) => openMenu(e, u)}
        >
          <span class="av"><Avatar name={u.display_name} url={u.avatar_url} size={42} /></span>
          <span class="info">
            <span class="nm">{u.display_name}{#if u.is_admin}<span class="hanko serif" title="Admin">主</span>{/if}</span>
            <span class="cs">Desconectado</span>
          </span>
        </button>
      {/each}
    {/if}
  </div>

  <!-- Ambientación sumi-e: rama de sakura ANCLADA a la esquina inferior
       derecha (xMaxYMax): antes se centraba y en columnas anchas quedaba
       "flotando" separada del borde. -->
  {#if $decorations}
  <svg class="amb" viewBox="0 0 180 130" preserveAspectRatio="xMaxYMax meet" aria-hidden="true">
    <path d="M14 130 C60 104 100 86 158 34" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" />
    <path d="M96 66 C110 55 124 58 130 44" stroke="currentColor" stroke-width="2.2" fill="none" />
    <path d="M64 92 C74 84 86 86 92 74" stroke="currentColor" stroke-width="2.2" fill="none" />
    <g fill="currentColor">
      <circle cx="158" cy="34" r="6" /><circle cx="146" cy="46" r="5" /><circle cx="130" cy="44" r="5" />
      <circle cx="120" cy="30" r="4.5" /><circle cx="140" cy="28" r="4" /><circle cx="92" cy="74" r="5" /><circle cx="80" cy="82" r="4.5" />
    </g>
  </svg>
  {/if}
</aside>

{#if menu}
  <UserMenu user={menu.user} x={menu.x} y={menu.y} onClose={() => (menu = null)} />
{/if}

{#if profile}
  <ProfileCard
    user={profile.user}
    x={profile.x}
    y={profile.y}
    activity={profile.user.activity || null}
    onMessage={onSelectUser}
    onClose={() => (profile = null)}
  />
{/if}

<style>
  .col {
    width: 300px;
    background: var(--pan);
    border-left: 1px solid var(--bd);
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
  }
  header {
    box-sizing: border-box;
    min-height: var(--header-h); /* alineada con las demás columnas */
    padding: 0 16px;
    border-bottom: 1px solid var(--bd);
    font-size: 13.5px;
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
    z-index: 1;
  }
  header i {
    color: var(--shu);
  }
  .hcount {
    margin-left: auto;
    font-size: 11px;
    color: var(--mut);
    font-variant-numeric: tabular-nums;
  }
  .body {
    padding: 10px 10px 12px;
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    position: relative;
    z-index: 1;
  }
  .amb {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0; /* pegada al borde: con xMaxYMax la rama toca la esquina */
    height: 210px;
    color: var(--tx);
    opacity: 0.12;
    pointer-events: none;
    z-index: 0;
  }
  :global(:root[data-theme="light"]) .amb { opacity: 0.17; }
  .hanko {
    font-size: 10px;
    width: 18px;
    height: 18px;
    flex: none;
    border-radius: 4px;
    border: 1.5px solid #c0392b;
    color: #c0392b;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }
  .lbl {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--fnt);
    padding: 0 6px;
    margin: 12px 0 4px;
  }
  /* Tarjeta grande con barra de acento por usuario (personalidad propia). */
  .card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 12px 11px 15px;
    border-radius: 14px;
    width: 100%;
    text-align: left;
    background: var(--ink);
    border: 1px solid var(--bd);
    color: inherit;
    font: inherit;
    cursor: pointer;
    overflow: hidden;
    transition: border-color 0.12s, transform 0.12s, background 0.12s;
  }
  /* Barra de acento a la izquierda, con el color del usuario. */
  .card::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--ac, var(--shu));
    opacity: 0.9;
  }
  .card:hover:not(:disabled) {
    border-color: var(--ac, var(--shu));
    transform: translateX(-1px);
    background: var(--hover);
  }
  .card:disabled {
    cursor: default;
  }
  .card.off {
    background: transparent;
    opacity: 0.6;
  }
  .card.off::before {
    background: var(--off);
    opacity: 0.5;
  }
  .av {
    flex: none;
    display: flex;
  }
  .info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .nm {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 14.5px;
    font-weight: 500;
    color: var(--tx);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .adm {
    color: var(--shu);
    font-size: 13px;
  }
  .cs {
    font-size: 12.5px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* Actividad: "Jugando a X" / "Escuchando Y" bajo el nombre. */
  .act {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    max-width: 100%;
    font-size: 11px;
    color: var(--shu);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .act i {
    flex: none;
    font-size: 12px;
  }
  .voice {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    align-self: flex-start;
    max-width: 100%;
    font-size: 11px;
    font-weight: 500;
    color: var(--on, #6bbf59);
    background: rgba(107, 191, 89, 0.12);
    border: 1px solid rgba(107, 191, 89, 0.35);
    border-radius: 999px;
    padding: 1px 8px 1px 6px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .empty {
    font-size: 12px;
    color: var(--fnt);
    padding: 8px;
  }
</style>
