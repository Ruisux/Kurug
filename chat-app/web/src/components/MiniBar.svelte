<script>
  // Mini-reproductor flotante: visible cuando ESTÁS escuchando (conectado a la
  // voz donde suena la música = general) y hay algo sonando, pero estás en otro
  // canal. Si te sales de la llamada deja de aparecer.
  import { musicState, music } from "../lib/music.js";
  import { voiceState, setBotVolume } from "../lib/voice.js";
  import { prefs } from "../lib/prefs.js";

  export let onOpen = () => {};
  // Solo referencia externa (Shell la pasa); la visibilidad ya no depende de
  // un canal concreto: la música suena en TU voz, sea cual sea.
  export const voiceChannelId = null;
  export let voiceView = false; // en la vista de recuadros se recoloca (ver CSS)

  let hidden = false; // ocultar el mini-reproductor (se puede volver a mostrar)

  $: st = $musicState;
  $: track = st.current != null ? st.queue[st.current] : null;
  // La música suena en TU canal de voz: el mini-reproductor aparece si estás en
  // cualquier voz (no solo en la de "general").
  $: listening = $voiceState.active;
</script>

{#if track && listening && hidden}
  <!-- Botón compacto para volver a mostrar el mini-reproductor. -->
  <button class="mini-show" class:vv={voiceView} on:click={() => (hidden = false)} title="Mostrar reproductor">
    <i class="ti ti-disc"></i>
    {#if st.playing}<span class="dot"></span>{/if}
  </button>
{/if}

{#if track && listening && !hidden}
  <div class="mini" class:vv={voiceView}>
    <button class="open" on:click={onOpen} title="Abrir sala de música">
      <div class="art">{#if track.thumbnail}<img src={track.thumbnail} alt="" />{:else}<i class="ti ti-disc"></i>{/if}</div>
      <div class="meta">
        <div class="t">{track.title}</div>
        <div class="s">{st.playing ? "reproduciendo" : "en pausa"} · {track.added_by}</div>
      </div>
    </button>

    <div class="ctrls">
      <button class="ctrl" on:click={music.prev} aria-label="Anterior"><i class="ti ti-player-skip-back"></i></button>
      <button class="ctrl play" on:click={music.toggle} aria-label="Play/Pausa">
        <i class="ti {st.playing ? 'ti-player-pause' : 'ti-player-play'}"></i>
      </button>
      <button class="ctrl" on:click={music.skip} aria-label="Siguiente"><i class="ti ti-player-skip-forward"></i></button>
    </div>

    <div class="vol" title="Tu volumen de la música ({$prefs.botVolume}%)">
      <i class="ti {$prefs.botVolume === 0 ? 'ti-volume-3' : 'ti-volume'}"></i>
      <input type="range" min="0" max="200" step="1" list="minibar-vol-ticks" value={$prefs.botVolume}
        on:input={(e) => setBotVolume(+e.target.value)} aria-label="Volumen de la música" />
      <datalist id="minibar-vol-ticks"><option value="100"></option></datalist>
    </div>

    <button class="ctrl hide" on:click={() => (hidden = true)} title="Ocultar reproductor" aria-label="Ocultar">
      <i class="ti ti-chevron-down"></i>
    </button>
  </div>
{/if}

<style>
  .mini {
    position: fixed;
    bottom: 78px; /* por encima del compositor para no taparlo */
    left: 50%;
    transform: translateX(-50%);
    z-index: 40;
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: min(92vw, 480px);
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 14px;
    padding: 7px 11px 7px 7px;
    box-shadow: 0 14px 36px var(--shadow);
  }
  .open {
    display: flex;
    align-items: center;
    gap: 10px;
    background: none;
    border: none;
    text-align: left;
    color: var(--tx);
    min-width: 0;
    flex: 1;
    padding: 0;
  }
  .art {
    width: 38px;
    height: 38px;
    flex: none;
    border-radius: 9px;
    background: var(--art-bg);
    border: 1px solid var(--bd2);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--shu);
    font-size: 18px;
    overflow: hidden;
  }
  .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .meta {
    min-width: 0;
  }
  .t {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .s {
    font-size: 11px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ctrls {
    display: flex;
    align-items: center;
    gap: 5px;
    flex: none;
  }
  .ctrl {
    width: 32px;
    height: 32px;
    flex: none;
    border-radius: 9px;
    border: 1px solid var(--bd2);
    background: transparent;
    color: var(--mut);
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .ctrl:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .ctrl.play {
    background: var(--shu);
    color: #1a0f0b;
    border-color: var(--shu);
  }
  .ctrl.play:hover {
    background: var(--shu-deep);
    color: #1a0f0b;
  }
  .vol {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
    color: var(--mut);
    font-size: 15px;
  }
  .vol input[type="range"] {
    width: 70px;
    accent-color: var(--shu);
  }
  .hide {
    margin-left: 2px;
  }
  /* Botón compacto para volver a mostrar el reproductor oculto. */
  .mini-show {
    position: fixed;
    bottom: 78px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 40;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--shu);
    font-size: 19px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 10px 28px var(--shadow);
  }
  .mini-show:hover {
    border-color: var(--shu);
  }
  .mini-show .dot {
    position: absolute;
    top: 7px;
    right: 7px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--on);
    border: 1.5px solid var(--pan);
  }
  /* En la vista de recuadros (llamada): el centro real del área central está
     desplazado por las columnas laterales (izquierda 76+256px, panel de
     miembros 248px -> (332-248)/2 = 42px), y la barra de controles es más
     alta; sin esto quedaba descentrado y pisando la línea de los controles. */
  .mini.vv,
  .mini-show.vv {
    left: calc(50% + 42px);
    bottom: 98px;
  }
  .mini.vv {
    /* El mínimo evita que en ventanas estrechas el cálculo se vuelva negativo
       y la barra "desaparezca" aplastada. */
    max-width: clamp(220px, 92vw - 580px, 480px);
  }

  /* En móvil ahorramos espacio: ocultamos el slider (queda en la sala). */
  @media (max-width: 640px) {
    .vol {
      display: none;
    }
    /* Sin columnas laterales: vuelve al centro de la ventana. */
    .mini.vv,
    .mini-show.vv {
      left: 50%;
      bottom: 78px;
    }
    .mini.vv {
      max-width: min(92vw, 480px);
    }
  }
</style>
