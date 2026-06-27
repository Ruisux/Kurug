<script>
  import Avatar from "./Avatar.svelte";
  import { me } from "../lib/stores.js";
  import {
    voiceState,
    toggleMute,
    toggleDeafen,
    toggleShare,
    setQuality,
    leaveVoice,
    localShareStream,
    SCREEN_PRESETS,
  } from "../lib/voice.js";

  const presetEntries = Object.entries(SCREEN_PRESETS);

  let minimized = false;

  // Acción para asignar un MediaStream a <audio>/<video> (no se puede con bind).
  function srcObject(node, stream) {
    node.srcObject = stream || null;
    return {
      update(s) {
        node.srcObject = s || null;
      },
      destroy() {
        node.srcObject = null;
      },
    };
  }

  function videoOf(e) {
    return e.currentTarget.closest(".tile")?.querySelector("video");
  }
  function fullscreen(e) {
    videoOf(e)?.requestFullscreen?.();
  }
  async function pip(e) {
    const v = videoOf(e);
    if (!v) return;
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await v.requestPictureInPicture?.();
    } catch {}
  }

  $: peers = Object.values($voiceState.peers);
  $: videoPeers = peers.filter((p) => p.hasVideo);
  $: hasVideo = videoPeers.length || $voiceState.sharing;
</script>

{#if $voiceState.active}
  <div class="voice">
    <div class="bar">
      <span class="live"><i class="ti ti-broadcast"></i> En voz · {peers.length + 1}</span>

      <div class="chips">
        <span class="chip" class:muted={$voiceState.muted}>
          <Avatar name={$me.display_name} url={$me.avatar_url} size={22} />
          tú
          {#if $voiceState.deafened}<i class="ti ti-headphones-off"></i>
          {:else if $voiceState.muted}<i class="ti ti-microphone-off"></i>{/if}
        </span>
        {#each peers as p (p.id)}
          <span class="chip">
            <Avatar name={p.name} url={p.avatar} size={22} />
            {p.name}
            {#if p.hasVideo}<i class="ti ti-device-desktop"></i>{/if}
          </span>
        {/each}
      </div>

      <div class="ctrls">
        <select
          class="quality"
          value={$voiceState.quality}
          on:change={(e) => setQuality(e.target.value)}
          title="Calidad de la pantalla compartida (elígela antes o durante)"
        >
          {#each presetEntries as [key, p] (key)}
            <option value={key}>{p.label}</option>
          {/each}
        </select>
        {#if hasVideo}
          <button on:click={() => (minimized = !minimized)} title={minimized ? "Mostrar vídeo" : "Minimizar vídeo"} aria-label="Minimizar vídeo">
            <i class="ti {minimized ? 'ti-chevron-down' : 'ti-chevron-up'}"></i>
          </button>
        {/if}
        <button class:on={$voiceState.muted} on:click={toggleMute} title="Silenciar micrófono" aria-label="Silenciar micrófono">
          <i class="ti {$voiceState.muted ? 'ti-microphone-off' : 'ti-microphone'}"></i>
        </button>
        <button class:on={$voiceState.deafened} on:click={toggleDeafen} title="Ensordecer (no oír a nadie)" aria-label="Ensordecer">
          <i class="ti {$voiceState.deafened ? 'ti-headphones-off' : 'ti-headphones'}"></i>
        </button>
        <button class:on={$voiceState.sharing} on:click={toggleShare} title="Compartir pantalla" aria-label="Compartir pantalla">
          <i class="ti ti-screen-share"></i>
        </button>
        <button class="leave" on:click={leaveVoice} title="Salir de voz" aria-label="Salir de voz">
          <i class="ti ti-phone-off"></i>
        </button>
      </div>
    </div>

    {#if hasVideo && !minimized}
      <div class="grid">
        {#if $voiceState.sharing}
          <div class="tile">
            <video use:srcObject={localShareStream()} autoplay muted playsinline></video>
            <span class="lbl">tú (pantalla)</span>
            <div class="tilebtns">
              <button on:click={pip} title="Minimizar (PiP)" aria-label="Picture in picture"><i class="ti ti-picture-in-picture"></i></button>
              <button on:click={fullscreen} title="Pantalla completa" aria-label="Pantalla completa"><i class="ti ti-maximize"></i></button>
            </div>
          </div>
        {/if}
        {#each videoPeers as p (p.id)}
          <div class="tile">
            <video use:srcObject={p.stream} autoplay playsinline muted></video>
            <span class="lbl">{p.name}</span>
            <div class="tilebtns">
              <button on:click={pip} title="Minimizar (PiP)" aria-label="Picture in picture"><i class="ti ti-picture-in-picture"></i></button>
              <button on:click={fullscreen} title="Pantalla completa" aria-label="Pantalla completa"><i class="ti ti-maximize"></i></button>
            </div>
          </div>
        {/each}
      </div>
    {/if}

  </div>
{/if}

<style>
  .voice {
    border-bottom: 1px solid var(--bd);
    background: rgba(var(--shu-rgb), 0.06);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 10px 16px;
    flex-wrap: wrap;
  }
  .live {
    font-size: 12.5px;
    color: var(--shu);
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
  }
  .chips {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    flex-wrap: wrap;
    min-width: 0;
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--tx);
    background: var(--pan);
    border: 1px solid var(--bd);
    border-radius: 999px;
    padding: 3px 10px 3px 3px;
  }
  .chip.muted {
    opacity: 0.6;
  }
  .ctrls {
    display: flex;
    gap: 8px;
    flex: none;
    align-items: center;
  }
  .ctrls button {
    height: 34px;
    min-width: 34px;
    padding: 0 8px;
    border-radius: 9px;
    border: 1px solid var(--bd2);
    background: var(--pan);
    color: var(--mut);
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .ctrls button:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .ctrls button.on {
    background: rgba(var(--shu-rgb), 0.16);
    color: var(--shu);
    border-color: var(--shu);
  }
  .ctrls .quality {
    height: 34px;
    padding: 0 10px;
    border-radius: 9px;
    border: 1px solid var(--bd2);
    background: var(--pan);
    color: var(--shu);
    font-size: 12.5px;
    font-weight: 500;
    outline: none;
    cursor: pointer;
    max-width: 230px;
  }
  .ctrls .quality:hover {
    border-color: var(--shu);
  }
  .ctrls .leave {
    background: var(--shu);
    color: #1a0f0b;
    border-color: var(--shu);
  }
  .ctrls .leave:hover {
    background: var(--shu-deep);
    color: #1a0f0b;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 8px;
    padding: 10px 16px;
  }
  .tile {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #0c0a08;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--bd2);
    box-shadow: 0 6px 20px var(--shadow);
    transition: border-color 0.15s;
  }
  .tile:hover {
    border-color: var(--shu);
  }
  .tile video {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .tile .lbl {
    position: absolute;
    left: 9px;
    bottom: 9px;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11.5px;
    font-weight: 500;
    background: rgba(20, 14, 10, 0.7);
    backdrop-filter: blur(6px);
    color: #f3ece2;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid rgba(var(--shu-rgb), 0.4);
  }
  .tilebtns {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    gap: 6px;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .tile:hover .tilebtns {
    opacity: 1;
  }
  .tilebtns button {
    width: 30px;
    height: 30px;
    border-radius: 7px;
    border: none;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .tilebtns button:hover {
    background: var(--shu);
    color: #1a0f0b;
  }
</style>
