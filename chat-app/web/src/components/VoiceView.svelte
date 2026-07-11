<script>
  // Vista de canal de voz (pantalla completa del área central), estilo Discord
  // pero con la personalidad sumi-e de Kurug: recuadros de participantes con
  // aro de tinta al hablar, cámaras y pantallas compartidas, y una barra de
  // controles gorda (micro, ensordecer, cámara, compartir, salir).
  import Avatar from "./Avatar.svelte";
  import { me } from "../lib/stores.js";
  import {
    voiceState,
    toggleMute,
    toggleDeafen,
    toggleCamera,
    toggleShare,
    leaveVoice,
    localCameraStream,
    localShareStream,
  } from "../lib/voice.js";

  export let channelName = "voz";
  export let onBack = () => {};

  // Solo reasigna si el stream de verdad cambió: re-poner el mismo srcObject
  // reinicia el <video> y provoca parpadeos en cada re-render.
  function srcObject(node, stream) {
    node.srcObject = stream || null;
    return {
      update(s) { if (node.srcObject !== (s || null)) node.srcObject = s || null; },
      destroy() { node.srcObject = null; },
    };
  }
  function fs(e) {
    e.currentTarget.closest(".tile")?.querySelector("video")?.requestFullscreen?.();
  }

  $: st = $voiceState;
  $: peers = Object.values(st.peers);
  // Pantallas compartidas (grandes): la mía + las de los demás.
  $: shares = [
    ...(st.sharing ? [{ id: "me-screen", name: "Tú", stream: localShareStream(), me: true }] : []),
    ...peers.filter((p) => p.hasScreen).map((p) => ({ id: p.id + "-s", name: p.name, stream: p.screen })),
  ];
  // Participantes (yo + peers) para los recuadros de personas.
  $: people = [
    {
      id: "me", name: $me.display_name, avatar: $me.avatar_url, self: true,
      camera: st.cameraOn ? localCameraStream() : null, hasCamera: st.cameraOn,
      speaking: st.meSpeaking && !st.muted, micMuted: st.muted,
    },
    ...peers.map((p) => ({
      id: p.id, name: p.name, avatar: p.avatar, self: false,
      camera: p.camera, hasCamera: p.hasCamera, speaking: p.speaking, micMuted: p.micMuted,
    })),
  ];
</script>

<section class="vv">
  <header>
    <button class="back" on:click={onBack} aria-label="Volver"><i class="ti ti-chevron-left"></i></button>
    <span class="mk"><i class="ti ti-volume"></i></span>
    <span class="display title">{channelName}</span>
    <span class="count">{people.length} en la sala</span>
  </header>

  <div class="stage">
    {#if st.error}<div class="err">{st.error}</div>{/if}

    {#if shares.length}
      <div class="shares">
        {#each shares as s (s.id)}
          <div class="tile screen">
            <video use:srcObject={s.stream} autoplay playsinline muted></video>
            <span class="lbl"><i class="ti ti-screen-share"></i> {s.name}</span>
            <button class="fsbtn" on:click={fs} title="Pantalla completa" aria-label="Pantalla completa"><i class="ti ti-maximize"></i></button>
          </div>
        {/each}
      </div>
    {/if}

    <div class="grid">
      {#each people as p (p.id)}
        <div class="tile" class:speaking={p.speaking}>
          {#if p.hasCamera && p.camera}
            <video use:srcObject={p.camera} autoplay playsinline muted={p.self}></video>
          {:else}
            <div class="mid"><Avatar name={p.name} url={p.avatar} size={82} /></div>
          {/if}
          <span class="lbl">
            {p.name}{#if p.self}&nbsp;(tú){/if}
            {#if p.micMuted}<i class="ti ti-microphone-off mo"></i>{/if}
          </span>
        </div>
      {/each}
    </div>
  </div>

  <div class="bar">
    <button class="cb" class:on={st.muted} on:click={toggleMute} title="Silenciar" aria-label="Silenciar micrófono">
      <i class="ti {st.muted ? 'ti-microphone-off' : 'ti-microphone'}"></i>
    </button>
    <button class="cb" class:on={st.deafened} on:click={toggleDeafen} title="Ensordecer" aria-label="Ensordecer">
      <i class="ti {st.deafened ? 'ti-headphones-off' : 'ti-headphones'}"></i>
    </button>
    <button class="cb" class:act={st.cameraOn} on:click={toggleCamera} title="Cámara" aria-label="Cámara">
      <i class="ti {st.cameraOn ? 'ti-video' : 'ti-video-off'}"></i>
    </button>
    <button class="cb" class:act={st.sharing} on:click={toggleShare} title="Compartir pantalla" aria-label="Compartir pantalla">
      <i class="ti ti-screen-share"></i>
    </button>
    <button class="cb leave" on:click={leaveVoice} title="Salir de la voz" aria-label="Salir de la voz">
      <i class="ti ti-phone-off"></i>
    </button>
  </div>
</section>

<style>
  .vv {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    background: var(--ink);
  }
  header {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--bd);
  }
  .back {
    display: none;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 20px;
  }
  .mk { color: var(--shu); font-size: 18px; display: flex; }
  .title { font-size: 16px; }
  .count { margin-left: auto; font-size: 12px; color: var(--mut); }
  .stage { flex: 1; min-height: 0; overflow-y: auto; padding: 16px; }
  .err {
    background: rgba(var(--shu-rgb), 0.14);
    border: 1px solid var(--shu);
    color: var(--tx);
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    margin-bottom: 14px;
  }
  .shares {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 12px;
    margin-bottom: 14px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 12px;
  }
  .tile {
    position: relative;
    aspect-ratio: 16 / 10;
    background: #0c0a08;
    border: 1px solid var(--bd2);
    border-radius: 16px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 20px var(--shadow);
  }
  .tile.screen { aspect-ratio: 16 / 9; }
  .tile video { width: 100%; height: 100%; object-fit: cover; }
  .tile.screen video { object-fit: contain; background: #000; }
  /* Aro de tinta al hablar. */
  .tile.speaking {
    border-color: var(--on, #6bbf59);
    box-shadow: 0 0 0 3px rgba(107, 191, 89, 0.4);
  }
  .mid { display: flex; align-items: center; justify-content: center; }
  .lbl {
    position: absolute;
    left: 12px;
    bottom: 11px;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    font-weight: 500;
    color: #f3ece2;
    background: rgba(18, 12, 9, 0.72);
    backdrop-filter: blur(6px);
    padding: 4px 11px;
    border-radius: 999px;
    border: 1px solid rgba(var(--shu-rgb), 0.35);
  }
  .lbl .mo { color: var(--shu); font-size: 13px; }
  .fsbtn {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 32px;
    height: 32px;
    border-radius: 9px;
    border: none;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .tile:hover .fsbtn { opacity: 1; }
  .fsbtn:hover { background: var(--shu); color: #160d0a; }
  /* Barra de controles gorda. */
  .bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 14px;
    border-top: 1px solid var(--bd);
    background: var(--pan);
  }
  .cb {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    border: 1px solid var(--bd2);
    background: var(--field);
    color: var(--tx);
    font-size: 21px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.1s, background 0.12s, border-color 0.12s;
  }
  .cb:hover { transform: translateY(-2px); border-color: var(--shu); }
  .cb.on { background: rgba(var(--shu-rgb), 0.16); color: var(--shu); border-color: var(--shu); }
  .cb.act { background: rgba(107, 191, 89, 0.16); color: var(--on, #6bbf59); border-color: var(--on, #6bbf59); }
  .cb.leave { background: var(--shu); color: #160d0a; border-color: var(--shu); }
  .cb.leave:hover { background: var(--shu-deep); }
  @media (max-width: 640px) {
    .back { display: flex; }
  }
</style>
