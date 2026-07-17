<script>
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { voiceState, setBotVolume } from "../lib/voice.js";
  import { musicState, music } from "../lib/music.js";
  import { prefs } from "../lib/prefs.js";
  import VoicePanel from "./VoicePanel.svelte";

  export let voiceChannelId = null; // voz donde suena la música (general)
  export let onBack = () => {};

  let query = "";
  let displayPos = 0;
  let ticker = null;

  $: st = $musicState;
  $: track = st.current != null ? st.queue[st.current] : null;
  $: listening = $voiceState.active && $voiceState.channelId === voiceChannelId;

  // Resincroniza la posición con cada estado del servidor; el ticker la avanza.
  // OJO: al empezar una canción el server manda playing=true con posición 0 al
  // INSTANTE, pero el bot tarda unos segundos en arrancar el audio de verdad.
  // Si el contador corriera ya, avanzaría en falso y se "reiniciaría" al llegar
  // el primer progreso real. Solo avanza cuando el bot reporta posición > 0.
  let started = false; // ¿el bot ya está emitiendo audio de esta reproducción?
  const unsub = musicState.subscribe((s) => {
    displayPos = s.position || 0;
    started = (s.position || 0) > 0;
  });

  function add() {
    const q = query.trim();
    if (!q) return;
    music.add(q);
    query = "";
  }
  function fmt(s) {
    if (s == null) return "–:––";
    s = Math.round(s);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  onMount(() => {
    ticker = setInterval(() => {
      if (get(musicState).playing && started) displayPos += 1;
    }, 1000);
  });
  onDestroy(() => {
    clearInterval(ticker);
    unsub();
  });
</script>

<section class="room">
  <header>
    <button class="back" on:click={onBack} aria-label="Volver"><i class="ti ti-chevron-left"></i></button>
    <span class="mark"><i class="ti ti-disc"></i></span>
    <span class="display title">sala de música</span>
    <span class="count">{st.queue.length} en cola</span>
    <span class="hint">La música suena en tu canal de voz</span>
  </header>

  {#if listening}<VoicePanel />{/if}

  {#if !st.botOnline}
    <div class="botwarn">
      <i class="ti ti-plug-connected-x"></i>
      El bot de música no está conectado: lo que añadas quedará en cola hasta que vuelva.
    </div>
  {/if}

  <div class="scroll">
    <div class="now">
      <div class="art">{#if track?.thumbnail}<img src={track.thumbnail} alt="" />{:else}<i class="ti ti-disc"></i>{/if}</div>
      <div class="info">
        <div class="state">{st.playing ? (started ? "REPRODUCIENDO" : "CARGANDO…") : track ? "EN PAUSA" : "NADA SONANDO"}</div>
        <div class="display name">{track ? track.title : "Pega un enlace para empezar"}</div>
        <div class="by">{track ? `añadido por ${track.added_by} · desde ${track.source}` : ""}</div>
        <div class="prog">
          <div class="bar"><div class="fill" style="width:{track?.duration ? Math.min(100, (displayPos / track.duration) * 100) : 0}%"></div></div>
          <div class="times"><span>{fmt(displayPos)}</span><span>{fmt(track?.duration)}</span></div>
        </div>
      </div>
    </div>

    <div class="controls">
      <button class:on={st.shuffle} on:click={music.shuffle} title="Aleatorio" aria-label="Aleatorio"><i class="ti ti-arrows-shuffle"></i></button>
      <button on:click={music.prev} title="Anterior" aria-label="Anterior"><i class="ti ti-player-skip-back"></i></button>
      <button class="play" on:click={music.toggle} disabled={!track} aria-label="Play/Pausa"><i class="ti {st.playing ? 'ti-player-pause' : 'ti-player-play'}"></i></button>
      <button on:click={music.skip} title="Siguiente" aria-label="Siguiente"><i class="ti ti-player-skip-forward"></i></button>
      <button class:on={st.loop !== "off"} on:click={music.loop} title="Repetir ({st.loop})" aria-label="Repetir">
        <i class="ti {st.loop === 'one' ? 'ti-repeat-once' : 'ti-repeat'}"></i>
      </button>
    </div>

    <!-- Volumen LOCAL de la música (cada quien el suyo). -->
    <div class="volrow" title="Tu volumen de la música (solo para ti)">
      <i class="ti {$prefs.botVolume === 0 ? 'ti-volume-3' : 'ti-volume'}"></i>
      <input type="range" min="0" max="100" step="1" value={$prefs.botVolume}
        on:input={(e) => setBotVolume(+e.target.value)} aria-label="Volumen de la música" />
      <span class="vval">{$prefs.botVolume}%</span>
    </div>

    <div class="queue">
      <div class="lbl">EN COLA</div>
      {#each st.queue as t, i (t.id)}
        <div class="qrow" class:on={i === st.current}>
          <button class="qmain" on:click={() => music.jump(i)}>
            <span class="idx">{#if i === st.current}<i class="ti ti-player-play"></i>{:else}{i + 1}{/if}</span>
            <div class="qart">{#if t.thumbnail}<img src={t.thumbnail} alt="" />{:else}<i class="ti ti-disc"></i>{/if}</div>
            <div class="qinfo"><div class="qt">{t.title}</div><div class="qby">{t.added_by} · {t.source}</div></div>
            <span class="qdur">{fmt(t.duration)}</span>
          </button>
          <button class="qx" on:click={() => music.remove(t.id)} aria-label="Quitar"><i class="ti ti-x"></i></button>
        </div>
      {/each}
      {#if st.queue.length === 0}
        <p class="empty">間 — la cola está vacía. Pega un enlace o escribe una canción.</p>
      {/if}
    </div>
  </div>

  {#if st.error}<div class="err">{st.error}</div>{/if}
  {#if st.info}<div class="infomsg"><i class="ti ti-playlist-add"></i> {st.info}</div>{/if}

  <div class="addbar">
    <input
      placeholder="Pega un link de YouTube/Spotify/Apple Music o escribe una canción…"
      bind:value={query}
      on:keydown={(e) => e.key === "Enter" && add()}
    />
    <button class="addbtn" on:click={add} disabled={st.busy} aria-label="Añadir">
      <i class="ti {st.busy ? 'ti-loader-2 spin' : 'ti-plus'}"></i>
    </button>
  </div>
</section>

<style>
  .room {
    flex: 1;
    min-width: 0;
    background: var(--ink);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 13px 16px;
    border-bottom: 1px solid var(--bd);
  }
  .back {
    display: none; /* solo en móvil */
    background: none;
    border: none;
    color: var(--mut);
    font-size: 22px;
    padding: 0;
    align-items: center;
  }
  .back:hover {
    color: var(--shu);
  }
  @media (max-width: 640px) {
    .back {
      display: flex;
    }
  }
  .mark {
    color: var(--shu);
    font-size: 18px;
  }
  .title {
    font-size: 15px;
  }
  .count {
    color: var(--mut);
    font-size: 12px;
  }
  .hint {
    margin-left: auto;
    font-size: 12px;
    color: var(--fnt);
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }
  .now {
    display: flex;
    gap: 16px;
    padding: 18px 16px;
  }
  .art {
    width: 108px;
    height: 108px;
    flex: none;
    border-radius: 12px;
    background: var(--art-bg);
    border: 1px solid var(--bd2);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--shu);
    font-size: 42px;
    overflow: hidden;
  }
  .art img,
  .qart img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .state {
    font-size: 11px;
    letter-spacing: 0.14em;
    color: var(--shu);
  }
  .name {
    font-size: 19px;
    margin: 3px 0 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .by {
    font-size: 12px;
    color: var(--mut);
  }
  .prog {
    margin-top: auto;
  }
  .bar {
    height: 5px;
    background: var(--pan);
    border-radius: 3px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--shu);
  }
  .times {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--fnt);
    margin-top: 4px;
  }
  .controls {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 14px;
    padding: 6px 16px 16px;
  }
  .controls button {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 1px solid var(--bd2);
    background: var(--pan);
    color: var(--mut);
    font-size: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .controls button:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .controls button.on {
    color: var(--shu);
    border-color: var(--shu);
  }
  .volrow {
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 360px;
    margin: 6px auto 2px;
    padding: 0 16px;
    color: var(--mut);
    font-size: 13px;
  }
  .volrow input[type="range"] {
    flex: 1;
    accent-color: var(--shu);
  }
  .volrow .vval {
    min-width: 38px;
    text-align: right;
    color: var(--tx);
    font-size: 12px;
  }
  .controls .play {
    width: 50px;
    height: 50px;
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    font-size: 21px;
  }
  .controls .play:hover {
    background: var(--shu-deep);
    color: #1a0f0b;
  }
  .controls .play:disabled {
    opacity: 0.5;
  }
  .queue {
    padding: 4px 10px 12px;
  }
  .lbl {
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--fnt);
    padding: 0 8px;
    margin: 6px 0;
  }
  .qrow {
    display: flex;
    align-items: center;
    border-radius: 9px;
  }
  .qrow.on,
  .qrow:hover {
    background: var(--hover);
  }
  .qrow.on {
    background: rgba(var(--shu-rgb), 0.1);
  }
  .qmain {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 11px;
    background: none;
    border: none;
    text-align: left;
    color: var(--tx);
    padding: 7px 8px;
  }
  .idx {
    width: 18px;
    text-align: center;
    color: var(--fnt);
    font-size: 12px;
    flex: none;
  }
  .qrow.on .idx {
    color: var(--shu);
  }
  .qart {
    width: 40px;
    height: 40px;
    flex: none;
    border-radius: 8px;
    background: var(--art-bg);
    border: 1px solid var(--bd);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--shu);
    font-size: 17px;
    overflow: hidden;
  }
  .qinfo {
    flex: 1;
    min-width: 0;
  }
  .qt {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .qby {
    font-size: 11px;
    color: var(--mut);
  }
  .qdur {
    font-size: 11px;
    color: var(--fnt);
    flex: none;
  }
  .qx {
    background: none;
    border: none;
    color: var(--fnt);
    width: 30px;
    height: 30px;
    border-radius: 7px;
    flex: none;
  }
  .qx:hover {
    color: var(--shu);
  }
  .empty {
    text-align: center;
    color: var(--fnt);
    font-size: 13px;
    padding: 20px;
  }
  .err {
    color: var(--shu);
    font-size: 12.5px;
    padding: 6px 16px;
  }
  .infomsg {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--mut);
    font-size: 12.5px;
    padding: 6px 16px;
  }
  .botwarn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    font-size: 12.5px;
    color: var(--tx);
    background: rgba(var(--shu-rgb), 0.10);
    border-bottom: 1px solid var(--bd);
  }
  .botwarn i {
    color: var(--shu);
    font-size: 15px;
  }
  .spin {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .addbtn:disabled {
    opacity: 0.7;
  }
  .addbar {
    display: flex;
    gap: 9px;
    align-items: center;
    padding: 11px 14px;
    border-top: 1px solid var(--bd);
  }
  .addbar input {
    flex: 1;
    min-width: 0;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 10px;
    padding: 11px 14px;
    font-size: 13.5px;
    outline: none;
  }
  .addbar input:focus {
    border-color: var(--shu);
  }
  .addbtn {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    font-size: 18px;
    flex: none;
  }
  .addbtn:hover {
    background: var(--shu-deep);
  }
</style>
