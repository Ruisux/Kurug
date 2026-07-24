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

  export let user;
  export let x = 0;
  export let y = 0;
  export let activity = null; // {kind:"game"|"music", text} de la presencia
  export let onClose = () => {};
  export let onMessage = () => {};

  const W = 300;
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
  $: info = { ...(full || {}), ...user };

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
</script>

<div class="backdrop" on:click={onClose} on:contextmenu|preventDefault={onClose} role="presentation"></div>
<div
  class="card"
  bind:clientHeight={cardH}
  style="left:{pos.left}px; top:{pos.top}px"
  role="dialog"
  aria-label="Perfil de {info.display_name}"
>
  <div class="head" style={info.accent_color ? `--card-accent: ${info.accent_color}` : ""}>
    <div class="stripe"></div>
    <Avatar name={info.display_name} url={info.avatar_url} size={64} status={info.status} />
    <div class="names">
      <div class="display dn">{info.display_name}</div>
      {#if info.username}<div class="un">@{info.username}</div>{/if}
    </div>
  </div>

  <div class="body">
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
    width: 300px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 18px 48px var(--shadow);
  }
  .head {
    position: relative;
    padding: 26px 16px 10px;
    display: flex;
    align-items: flex-end;
    gap: 12px;
  }
  .stripe {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 42px;
    background: var(--card-accent, var(--shu));
    opacity: 0.85;
  }
  .head :global(.avatar) {
    position: relative;
  }
  .names {
    position: relative;
    min-width: 0;
    padding-bottom: 2px;
  }
  .dn {
    font-size: 17px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .un {
    font-size: 12px;
    color: var(--mut);
  }
  .body {
    padding: 10px 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 9px;
  }
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
