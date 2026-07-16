<script>
  import { voiceState, setPeerVolume, setPeerMuted, kickPeer } from "../lib/voice.js";
  import { me } from "../lib/stores.js";

  export let user;
  export let x = 0;
  export let y = 0;
  export let onClose = () => {};

  // Datos de voz del usuario (si está en la sala de voz conmigo).
  $: peer = $voiceState.peers[user.id];
  $: inVoice = !!peer;

  // Posición acotada a la ventana.
  $: left = Math.min(x, window.innerWidth - 240);
  $: top = Math.min(y, window.innerHeight - 200);

  function toggleMute() {
    if (peer) setPeerMuted(user.id, !peer.localMuted);
  }
  function onVol(e) {
    setPeerVolume(user.id, +e.target.value);
  }
  async function disconnect() {
    await kickPeer(String(user.id));
    onClose();
  }
</script>

<div class="backdrop" on:click={onClose} on:contextmenu|preventDefault={onClose} role="presentation"></div>
<div class="menu" style="left:{left}px; top:{top}px" role="menu">
  <div class="head">
    <span class="display">{user.display_name}</span>
  </div>

  {#if inVoice}
    <button class="item" on:click={toggleMute} role="menuitem">
      <i class="ti {peer.localMuted ? 'ti-volume-3' : 'ti-volume'}"></i>
      {peer.localMuted ? "Quitar silencio" : "Silenciar para mí"}
    </button>

    <div class="vol">
      <div class="vlabel"><span>Volumen</span><span class="vval">{peer.volume}%</span></div>
      <input type="range" min="0" max="100" step="1" value={peer.volume} on:input={onVol} />
    </div>
  {:else}
    <div class="empty">No está en la voz</div>
  {/if}

  {#if $me.is_admin && user.id !== $me.id}
    <div class="sep"></div>
    <button class="item danger" on:click={disconnect} role="menuitem">
      <i class="ti ti-phone-off"></i> Desconectar de la voz
    </button>
  {/if}
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
  }
  .menu {
    position: fixed;
    z-index: 61;
    width: 224px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 11px;
    padding: 6px;
    box-shadow: 0 16px 40px var(--shadow);
  }
  .head {
    padding: 7px 9px 8px;
    font-size: 13px;
    border-bottom: 1px solid var(--bd);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .item {
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
  .item:hover {
    background: var(--hover);
  }
  .item.danger {
    color: var(--shu);
  }
  .item.danger:hover {
    background: rgba(var(--shu-rgb), 0.12);
  }
  .vol {
    padding: 7px 9px 9px;
  }
  .vlabel {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--mut);
    margin-bottom: 6px;
  }
  .vval {
    color: var(--tx);
  }
  .vol input[type="range"] {
    width: 100%;
    accent-color: var(--shu);
  }
  .empty {
    padding: 7px 9px;
    font-size: 12px;
    color: var(--fnt);
  }
  .sep {
    height: 1px;
    background: var(--bd);
    margin: 4px 0;
  }
</style>
