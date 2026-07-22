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
  import { screenPicker } from "../lib/desktop.js";
  import { pingColor } from "../lib/ui.js";

  export let online = []; // presencia viva: el punto de estado de cada chip

  const presetEntries = Object.entries(SCREEN_PRESETS);

  // Quien está en la voz está conectado: a falta de dato vivo, "online".
  $: statusById = new Map(online.map((u) => [u.id, u.status || "online"]));
  // En Electron la calidad se elige en el selector de pantalla propio; aquí solo
  // se muestra para el picker del navegador (web/Tauri).
  const showQualityBar = !screenPicker.supported;

  let minimized = false;

  // Acción para asignar un MediaStream a <audio>/<video> (no se puede con bind).
  // Solo reasigna si cambió: re-poner el mismo srcObject reinicia el vídeo
  // (parpadeo en cada re-render).
  function srcObject(node, stream) {
    node.srcObject = stream || null;
    return {
      update(s) {
        if (node.srcObject !== (s || null)) node.srcObject = s || null;
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
    // El contenedor, no el <video>: evita el tinte verde del share propio en
    // pantalla completa (bug de render de Chromium con el track codificándose).
    e.currentTarget.closest(".tile")?.requestFullscreen?.();
  }
  async function pip(e) {
    const v = videoOf(e);
    if (!v) return;
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await v.requestPictureInPicture?.();
    } catch {}
  }

  // Ver la transmisión de otros es OPCIONAL (como Discord): mostramos quién
  // comparte y tú eliges verla. Solo se renderiza el <video> de los peers que
  // decides ver; el resto de pistas LiveKit las pausa (adaptiveStream) => sin
  // gasto de ancho de banda por transmisiones que no miras.
  let watching = new Set();
  function toggleWatch(id) {
    watching.has(id) ? watching.delete(id) : watching.add(id);
    watching = watching; // fuerza reactividad
  }

  $: peers = Object.values($voiceState.peers);
  $: videoPeers = peers.filter((p) => p.hasVideo);
  // Poda ids de quien dejó de compartir para no dejar recuadros fantasma.
  $: if (videoPeers) {
    const live = new Set(videoPeers.map((p) => p.id));
    let changed = false;
    for (const id of watching) if (!live.has(id)) { watching.delete(id); changed = true; }
    if (changed) watching = watching;
  }
  $: watchedPeers = videoPeers.filter((p) => watching.has(p.id));
  $: hasTiles = watchedPeers.length || $voiceState.sharing;
</script>

{#if $voiceState.active}
  <div class="voice">
    <div class="bar">
      <span class="live"><i class="ti ti-broadcast"></i> En voz · {peers.length + 1}</span>
      {#if $voiceState.myRtt != null}
        <span class="myping" style="color:{pingColor($voiceState.myRtt)}" title="Tu latencia con el servidor de voz">
          <i class="ti ti-wifi"></i> {$voiceState.myRtt} ms
        </span>
      {/if}

      <div class="chips">
        <span class="chip" class:muted={$voiceState.muted} class:speaking={$voiceState.meSpeaking && !$voiceState.muted}>
          <Avatar name={$me.display_name} url={$me.avatar_url} size={22} status={$me.status || "online"} />
          tú
          {#if $voiceState.sharing}<span class="live-badge">EN DIRECTO</span>{/if}
          {#if $voiceState.deafened}<i class="ti ti-headphones-off"></i>
          {:else if $voiceState.muted}<i class="ti ti-microphone-off"></i>{/if}
        </span>
        {#each peers as p (p.id)}
          <span class="chip" class:speaking={p.speaking}>
            <Avatar name={p.name} url={p.avatar} size={22} status={statusById.get(p.id) || "online"} />
            {p.name}
            {#if p.hasVideo}<span class="live-badge">EN DIRECTO</span>{/if}
          </span>
        {/each}
      </div>

      <div class="ctrls">
        {#if $voiceState.sharing && showQualityBar}
          <select
            class="quality"
            value={$voiceState.quality}
            on:change={(e) => setQuality(e.target.value)}
            title="Calidad de TU pantalla compartida"
          >
            {#each presetEntries as [key, p] (key)}
              <option value={key}>{p.label}</option>
            {/each}
          </select>
        {/if}
        {#if hasTiles}
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

    {#if videoPeers.length}
      <div class="shares">
        {#each videoPeers as p (p.id)}
          <button class="share-item" class:on={watching.has(p.id)} on:click={() => toggleWatch(p.id)}>
            <Avatar name={p.name} url={p.avatar} size={20} />
            <span class="share-name">{p.name}</span>
            <span class="share-tag"><i class="ti ti-device-desktop"></i> comparte</span>
            <span class="share-act">
              <i class="ti {watching.has(p.id) ? 'ti-eye-off' : 'ti-eye'}"></i>
              {watching.has(p.id) ? "Ocultar" : "Ver"}
            </span>
          </button>
        {/each}
      </div>
    {/if}

    {#if hasTiles && !minimized}
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
        {#each watchedPeers as p (p.id)}
          <div class="tile">
            <!-- muted a propósito: el audio de la pantalla llega por una pista
                 de audio separada de LiveKit; si no, se oiría doble. -->
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
  .myping {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11.5px;
    font-variant-numeric: tabular-nums;
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
  .live-badge {
    flex: none;
    font-size: 8.5px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: #fff;
    background: #d43d2a;
    border-radius: 4px;
    padding: 1.5px 5px;
    line-height: 1.3;
  }
  /* Ilumina el chip de quien está hablando (activo en el micro). */
  .chip.speaking {
    border-color: var(--on, #6bbf59);
    box-shadow: 0 0 0 2px rgba(107, 191, 89, 0.45);
    transition: box-shadow 0.1s, border-color 0.1s;
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
  .shares {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 16px 10px;
  }
  .share-item {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 999px;
    padding: 4px 6px 4px 4px;
    color: var(--tx);
    font-size: 12px;
  }
  .share-item:hover {
    border-color: var(--shu);
  }
  .share-item.on {
    background: rgba(var(--shu-rgb), 0.14);
    border-color: var(--shu);
  }
  .share-name {
    font-weight: 500;
  }
  .share-tag {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--mut);
    font-size: 11px;
  }
  .share-act {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--shu);
    font-weight: 500;
    padding-left: 4px;
    border-left: 1px solid var(--bd);
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
