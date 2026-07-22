<script>
  // Tarjeta de perfil (clic IZQUIERDO en un usuario): avatar grande, estado,
  // bio, actividad y botón para abrir el chat privado. El clic derecho sigue
  // abriendo el menú de voz (UserMenu).
  import { onMount } from "svelte";
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

    {#if activity}
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
