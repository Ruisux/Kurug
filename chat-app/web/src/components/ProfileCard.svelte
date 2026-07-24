<script>
  // Tarjeta de perfil (clic IZQUIERDO en un usuario): avatar grande, estado,
  // bio, actividad y botón para abrir el chat privado. El clic derecho sigue
  // abriendo el menú de voz (UserMenu).
  import { onMount, onDestroy } from "svelte";
  import Avatar from "./Avatar.svelte";
  import { api } from "../lib/api.js";
  import { me } from "../lib/stores.js";
  import { statusColor, statusLabel, anchorFixed } from "../lib/ui.js";
  import { voiceState, setPeerVolume, setPeerMuted } from "../lib/voice.js";
  import { RANKS, BADGES, rankInfo, badgeInfo } from "../lib/gamify.js";
  import { mediaUrl } from "../lib/server.js";

  export let user;
  export let x = 0;
  export let y = 0;
  export let activity = null; // {kind:"game"|"music", text} de la presencia
  export let onClose = () => {};
  export let onMessage = () => {};

  const W = 322;
  // La altura real depende de lo que traiga el perfil (bio, actividad, control
  // de volumen): se MIDE en vez de suponerla, así la tarjeta nunca se sale por
  // abajo. `anchorFixed` traduce las coordenadas del clic a las unidades de la
  // interfaz escalada (ver --ui-zoom).
  let cardH = 330;
  $: pos = anchorFixed(x, y, W, cardH);

  $: self = user.id === $me.id;
  // Si está en MI sala de voz, la tarjeta incluye su volumen local.
  $: peer = $voiceState.peers[user.id];

  // El snapshot de presencia no siempre trae la bio (y desde el chat solo
  // llega {id, nombre, avatar}): completar del servidor. El perfil guardado
  // NO pisa lo vivo (estado/actividad): primero `full`, encima `user`.
  let full = null;
  onMount(async () => {
    try { full = await api.user(user.id); } catch {}
  });
  // Base: lo que llegó (presencia/chat). `full` (GET /users/{id}) manda para los
  // datos de PERFIL (rango, insignias, xp, banner, bio) — importante para que un
  // cambio del admin se vea al instante, sin que el `user` viejo lo tape. De lo
  // VIVO (estado, actividad, avatar) mandan los que trae `user`.
  $: live = {};
  $: {
    live = {};
    for (const k of ["status", "custom_status", "activity", "avatar_url"]) {
      if (user[k] !== undefined && user[k] !== null) live[k] = user[k];
    }
  }
  $: info = { ...user, ...(full || {}), ...live };

  // --- Progreso de Spotify (interpolado en el cliente) ---
  // El escritorio manda UNA foto por canción: posición (position_ms) tomada en
  // el instante `at`. Aquí avanzamos ese reloj localmente cada segundo mientras
  // la tarjeta está abierta, para ver "en qué minuto va" sin reenviar nada.
  $: music = activity && activity.kind === "music" && activity.title ? activity : null;
  let nowT = Date.now();
  let ticker = null;
  onMount(() => { ticker = setInterval(() => (nowT = Date.now()), 1000); });
  onDestroy(() => clearInterval(ticker));
  $: elapsed = music && music.position_ms != null
    ? Math.max(0, Math.min(
        music.duration_ms ?? Infinity,
        music.position_ms + (music.playing === false ? 0 : nowT - (music.at ?? nowT)),
      ))
    : null;
  $: progress = music && music.duration_ms ? Math.min(1, (elapsed ?? 0) / music.duration_ms) : 0;
  function mmss(ms) {
    if (ms == null || !isFinite(ms)) return "";
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  // --- Rango, nivel e insignias ---
  $: rank = rankInfo(info.rank);
  $: badges = (info.badges || [])
    .map((k) => ({ key: k, ...(badgeInfo(k) || {}) }))
    .filter((b) => b.label);
  $: level = info.level || 1;
  $: xpInto = info.xp_into ?? 0;
  $: xpSpan = info.xp_span || 100;
  $: xpPct = Math.min(100, Math.round((xpInto / Math.max(1, xpSpan)) * 100));

  // --- Gestión (solo admin, viendo a otro): asignar rango / dar insignias ---
  $: amAdmin = $me.is_admin && !self;
  let managing = false;
  async function chooseRank(key) {
    try { full = await api.setRank(user.id, key); } catch {}
  }
  async function toggleBadge(key) {
    const has = (info.badges || []).includes(key);
    try { full = await api.setBadge(user.id, key, has ? "remove" : "add"); } catch {}
  }
</script>

<div class="backdrop" on:click={onClose} on:contextmenu|preventDefault={onClose} role="presentation"></div>
<div
  class="card"
  bind:clientHeight={cardH}
  style="left:{pos.left}px; top:{pos.top}px"
  role="dialog"
  aria-label="Perfil de {info.display_name}"
>
  <!-- Banner: imagen propia o degradado con el color de acento. -->
  <div
    class="banner"
    style={info.banner_url
      ? `background-image:url(${mediaUrl(info.banner_url)})`
      : `--a:${info.accent_color || '#e2553b'}`}
    class:img={!!info.banner_url}
  >
    {#if !info.banner_url}
      <svg class="sakura" viewBox="0 0 150 120" aria-hidden="true">
        <path d="M8 118 C55 96 96 78 150 26" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round"/>
        <g fill="currentColor"><circle cx="150" cy="26" r="7"/><circle cx="136" cy="40" r="6"/><circle cx="120" cy="38" r="5.5"/><circle cx="130" cy="20" r="4.5"/></g>
      </svg>
    {/if}
  </div>

  <div class="head">
    <span class="av"><Avatar name={info.display_name} url={info.avatar_url} size={72} status={info.status} ring="var(--pan)" /></span>
    <div class="names">
      <div class="display dn" style={rank ? `color:${rank.color}` : ""}>{info.display_name}</div>
      {#if info.username}<div class="un">@{info.username}</div>{/if}
    </div>
    {#if rank}
      <span class="seal" style="--rc:{rank.color}"><i class="ti ti-seal"></i>{rank.label}</span>
    {/if}
  </div>

  <div class="body">
    <!-- Nivel y XP -->
    <div class="level">
      <div class="lrow">
        <span class="lv">Nivel <b>{level}</b></span>
        <span class="xp">{xpInto} / {xpSpan} XP</span>
      </div>
      <div class="lbar"><span style="width:{xpPct}%"></span></div>
    </div>

    <!-- Insignias -->
    {#if badges.length}
      <div class="badges">
        <div class="btitle">Insignias</div>
        <div class="brow">
          {#each badges as b (b.key)}
            <span class="badge" style="--bc:{b.color}" title={b.label}><i class="ti ti-{b.icon}"></i></span>
          {/each}
        </div>
      </div>
    {/if}

    <div class="strow">
      <span class="dot" style="background: {statusColor(info.status)}"></span>
      {statusLabel(info.status)}
      {#if info.custom_status}<span class="cst">· {info.custom_status}</span>{/if}
    </div>

    {#if music}
      <!-- Tarjeta de Spotify: carátula, canción, artista y progreso. -->
      <div class="spotify">
        <div class="cover">
          {#if music.art}
            <img src={music.art} alt="Carátula" />
          {:else}
            <i class="ti ti-music"></i>
          {/if}
        </div>
        <div class="sinfo">
          <div class="slabel"><i class="ti ti-brand-spotify"></i> Escuchando en Spotify</div>
          <div class="stitle" title={music.title}>{music.title}</div>
          {#if music.artist}<div class="sartist" title={music.artist}>{music.artist}</div>{/if}
          {#if music.album}<div class="salbum" title={music.album}>{music.album}</div>{/if}
          {#if music.duration_ms}
            <div class="sbar"><span style="width:{progress * 100}%"></span></div>
            <div class="stime"><span>{mmss(elapsed)}</span><span>{mmss(music.duration_ms)}</span></div>
          {/if}
        </div>
      </div>
    {:else if activity}
      <div class="act">
        <i class="ti {activity.kind === 'game' ? 'ti-device-gamepad-2' : 'ti-music'}"></i>
        <span>{activity.kind === "game" ? "Jugando a" : "Escuchando"} <b>{activity.text}</b></span>
      </div>
    {/if}

    {#if info.bio}
      <div class="bio">{info.bio}</div>
    {/if}

    {#if peer && !self}
      <div class="voice">
        <div class="vlabel"><i class="ti ti-volume"></i> Volumen <span class="vval">{peer.volume}%</span></div>
        <input
          type="range" min="0" max="200" step="1" list="card-vol-ticks" value={peer.volume}
          on:input={(e) => setPeerVolume(user.id, +e.target.value)}
        />
        <datalist id="card-vol-ticks"><option value="100"></option></datalist>
        <button class="mutebtn" on:click={() => setPeerMuted(user.id, !peer.localMuted)}>
          <i class="ti {peer.localMuted ? 'ti-volume-3' : 'ti-volume'}"></i>
          {peer.localMuted ? "Quitar silencio" : "Silenciar para mí"}
        </button>
      </div>
    {/if}

    {#if !self}
      <button class="msg" on:click={() => { onMessage(user); onClose(); }}>
        <i class="ti ti-message-circle"></i> Enviar mensaje
      </button>
    {/if}

    {#if amAdmin}
      <button class="manage-toggle" on:click={() => (managing = !managing)}>
        <i class="ti ti-adjustments"></i> {managing ? "Ocultar gestión" : "Gestionar rango e insignias"}
      </button>
      {#if managing}
        <div class="manage">
          <div class="mlabel">Rango</div>
          <div class="mgrid">
            <button class="rchip" class:on={!info.rank} on:click={() => chooseRank(null)}>Ninguno</button>
            {#each Object.entries(RANKS) as [key, r] (key)}
              <button class="rchip" class:on={info.rank === key} style="--rc:{r.color}" on:click={() => chooseRank(key)}>{r.label}</button>
            {/each}
          </div>
          <div class="mlabel">Insignias</div>
          <div class="mgrid">
            {#each Object.entries(BADGES) as [key, b] (key)}
              <button
                class="bchip"
                class:on={(info.badges || []).includes(key)}
                style="--bc:{b.color}"
                title={b.label}
                on:click={() => toggleBadge(key)}
              ><i class="ti ti-{b.icon}"></i> {b.label}</button>
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
  }
  .card {
    position: fixed;
    z-index: 61;
    width: 322px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 18px 48px var(--shadow);
  }
  /* Banner: imagen 4:1 o degradado con el color de acento. */
  .banner {
    height: 96px;
    background-size: cover;
    background-position: center;
    position: relative;
  }
  .banner:not(.img) {
    background:
      radial-gradient(130% 150% at 82% -20%, color-mix(in srgb, var(--a) 65%, transparent), transparent 62%),
      linear-gradient(135deg, #3a2016, #241812 72%);
    color: #f0d9c8;
  }
  .sakura {
    position: absolute;
    right: -6px;
    top: -4px;
    width: 150px;
    height: 118px;
    opacity: 0.18;
  }
  .head {
    position: relative;
    padding: 0 16px 6px;
    margin-top: -34px;
    display: flex;
    align-items: flex-end;
    gap: 12px;
  }
  .head .av { flex: none; }
  .names {
    position: relative;
    min-width: 0;
    padding-bottom: 3px;
  }
  .dn {
    font-size: 18px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .un {
    font-size: 12px;
    color: var(--mut);
  }
  /* Sello de rango junto al nombre. */
  .seal {
    margin-left: auto;
    align-self: flex-start;
    margin-top: 40px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    color: var(--rc);
    border: 1.5px solid var(--rc);
    background: color-mix(in srgb, var(--rc) 12%, transparent);
    white-space: nowrap;
  }
  .body {
    padding: 8px 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 11px;
  }
  /* Nivel y XP. */
  .level .lrow {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 12px;
  }
  .level .lv { color: var(--tx); font-weight: 600; }
  .level .lv b { color: var(--shu); }
  .level .xp { color: var(--fnt); font-variant-numeric: tabular-nums; }
  .lbar {
    height: 7px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.09);
    margin-top: 6px;
    overflow: hidden;
  }
  :global(:root[data-theme="light"]) .lbar { background: rgba(0, 0, 0, 0.08); }
  .lbar span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--shu), #e2b33b);
    transition: width 0.4s ease;
  }
  /* Insignias. */
  .btitle {
    font-size: 10.5px;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--fnt);
    margin-bottom: 7px;
  }
  .brow { display: flex; gap: 8px; flex-wrap: wrap; }
  .badge {
    width: 36px;
    height: 36px;
    border-radius: 11px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 17px;
    color: var(--bc);
    border: 1px solid color-mix(in srgb, var(--bc) 45%, transparent);
    background: color-mix(in srgb, var(--bc) 12%, transparent);
  }
  /* Panel de gestión del admin. */
  .manage-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    background: none;
    border: 1px solid var(--bd2);
    border-radius: 10px;
    color: var(--mut);
    font-size: 12.5px;
    padding: 8px;
    cursor: pointer;
  }
  .manage-toggle:hover { border-color: var(--shu); color: var(--tx); }
  .manage {
    display: flex;
    flex-direction: column;
    gap: 7px;
    border-top: 1px solid var(--bd);
    padding-top: 10px;
  }
  .mlabel {
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--fnt);
  }
  .mgrid { display: flex; flex-wrap: wrap; gap: 6px; }
  .rchip, .bchip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 9px;
    border-radius: 999px;
    border: 1px solid var(--bd2);
    background: var(--field);
    color: var(--mut);
    font-size: 11.5px;
    cursor: pointer;
  }
  .rchip.on { color: var(--rc, var(--shu)); border-color: var(--rc, var(--shu)); background: color-mix(in srgb, var(--rc, var(--shu)) 14%, transparent); }
  .bchip.on { color: var(--bc); border-color: var(--bc); background: color-mix(in srgb, var(--bc) 14%, transparent); }
  .rchip:hover, .bchip:hover { color: var(--tx); }
  .strow {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12.5px;
    color: var(--tx);
  }
  .strow .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: none;
  }
  .cst {
    color: var(--mut);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .act {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    color: var(--tx);
    background: rgba(var(--shu-rgb), 0.08);
    border: 1px solid var(--bd);
    border-radius: 9px;
    padding: 7px 10px;
  }
  .act i {
    color: var(--shu);
    font-size: 15px;
    flex: none;
  }
  .act span {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  /* Tarjeta de Spotify: carátula + info + barra de progreso. */
  .spotify {
    display: flex;
    gap: 11px;
    background: rgba(30, 215, 96, 0.09);
    border: 1px solid rgba(30, 215, 96, 0.28);
    border-radius: 11px;
    padding: 10px;
  }
  .cover {
    width: 62px;
    height: 62px;
    flex: none;
    border-radius: 8px;
    overflow: hidden;
    background: rgba(30, 215, 96, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #1ed760;
    font-size: 26px;
  }
  .cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .sinfo {
    min-width: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .slabel {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #1ed760;
    text-transform: uppercase;
  }
  .stitle {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--tx);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sartist,
  .salbum {
    font-size: 11.5px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .salbum {
    color: var(--fnt);
    font-size: 10.5px;
  }
  .sbar {
    margin-top: 5px;
    height: 4px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.14);
    overflow: hidden;
  }
  .sbar span {
    display: block;
    height: 100%;
    background: #1ed760;
    border-radius: 999px;
    transition: width 0.9s linear;
  }
  .stime {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: var(--fnt);
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
  }
  .bio {
    font-size: 12.5px;
    color: var(--mut);
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 90px;
    overflow-y: auto;
  }
  .voice {
    border-top: 1px solid var(--bd);
    padding-top: 9px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .vlabel {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--mut);
  }
  .vlabel .vval {
    margin-left: auto;
    color: var(--tx);
    font-variant-numeric: tabular-nums;
  }
  .voice input[type="range"] {
    width: 100%;
    accent-color: var(--shu);
  }
  .mutebtn {
    display: flex;
    align-items: center;
    gap: 7px;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 12.5px;
    padding: 3px 0;
    cursor: pointer;
  }
  .mutebtn:hover {
    color: var(--shu);
  }
  .msg {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    border-radius: 10px;
    padding: 9px;
    font-size: 13px;
    font-weight: 500;
  }
  .msg:hover {
    background: var(--shu-deep);
  }
</style>
