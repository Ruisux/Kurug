<script>
  // Vista de canal de voz (pantalla completa del área central), estilo Discord
  // pero con la personalidad sumi-e de Kurug: recuadros de participantes con
  // aro de tinta al hablar, cámaras y pantallas compartidas, y una barra de
  // controles gorda (micro, ensordecer, cámara, compartir, salir).
  import { onDestroy } from "svelte";
  import Avatar from "./Avatar.svelte";
  import Whiteboard from "./Whiteboard.svelte";
  import UserMenu from "./UserMenu.svelte";
  import { me } from "../lib/stores.js";
  import { pingColor } from "../lib/ui.js";
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
  export let channelId = null; // para la pizarra compartida del canal
  export let voiceFlags = {}; // user_id -> { muted, deafened, rtt } (por presencia)
  export let onBack = () => {};

  // --- Menú de usuario (clic derecho) + resaltado de "auditando" ---
  // Igual que en la lista izquierda: clic derecho sobre un recuadro abre las
  // opciones de voz (volumen / silenciar / desconectar) y ese usuario se ilumina
  // con el color de acento para saber a quién se está tocando.
  let menu = null; // { user, x, y }
  function openMenu(e, p) {
    if (p.self) return; // sobre ti mismo no hay opciones de voz
    e.preventDefault();
    e.stopPropagation();
    menu = { user: { id: p.id, display_name: p.name }, x: e.clientX, y: e.clientY };
  }
  $: auditId = menu ? menu.user.id : null;

  // --- Foco: agrandar el recuadro de un usuario ---
  // Un clic sobre un recuadro lo pone en GRANDE (útil sobre todo cuando alguien
  // enciende la cámara); otro clic lo devuelve al mosaico.
  let focusId = null;
  function toggleFocus(p) {
    focusId = focusId === p.id ? null : p.id;
  }
  // Si el usuario enfocado se va de la sala, salir del foco.
  $: if (focusId && !people.some((p) => p.id === focusId)) focusId = null;

  let boardOpen = false;
  // Al cambiar de canal, la pizarra abierta era la del canal anterior.
  $: if (channelId != null) boardOpen = false;

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
    // Pantalla completa del CONTENEDOR, no del <video>: evita la ruta de
    // render con tinte verde del share propio y conserva los botones encima.
    e.currentTarget.closest(".tile")?.requestFullscreen?.();
  }

  $: st = $voiceState;
  $: peers = Object.values(st.peers);
  // Pantallas compartidas (grandes): la mía + las de los demás.
  $: shares = [
    ...(st.sharing ? [{ id: "me-screen", name: "Tú", stream: localShareStream(), me: true }] : []),
    ...peers.filter((p) => p.hasScreen).map((p) => ({ id: p.id + "-s", name: p.name, stream: p.screen })),
  ];
  // --- Layout del mosaico calculado en JS ---
  // El CSS puro no sabe repartir N recuadros de proporción fija en un espacio
  // WxH sin que se solapen cuando falta alto (el bug de la ventana pequeña:
  // los recuadros crecían más que el área y se montaban unos sobre otros). Aquí
  // se PRUEBAN todas las columnas posibles y se elige la que da el recuadro más
  // grande cabiendo entero, ancho Y alto. Así llena el espacio y nunca desborda.
  const GAP = 12;
  const ASPECT = 16 / 10; // ancho/alto de cada recuadro
  let stageW = 0, stageH = 0;
  function measureStage(node) {
    const ro = new ResizeObserver((ents) => {
      const r = ents[0].contentRect;
      stageW = r.width; stageH = r.height;
    });
    ro.observe(node);
    return { destroy: () => ro.disconnect() };
  }
  function bestLayout(n, W, H) {
    if (n <= 0 || W <= 0 || H <= 0) return { cols: 1, w: 0, h: 0 };
    let best = { cols: 1, w: 0, h: 0 };
    for (let cols = 1; cols <= n; cols++) {
      const rows = Math.ceil(n / cols);
      const tw = (W - GAP * (cols - 1)) / cols;
      const th = (H - GAP * (rows - 1)) / rows;
      // Recuadro que respeta la proporción cabiendo en la celda.
      const w = Math.min(tw, th * ASPECT);
      if (w > best.w) best = { cols, w, h: w / ASPECT };
    }
    return best;
  }
  // Con foco activo, el mosaico de "los demás" va en una tira lateral estrecha.
  $: mosaic = focusId ? people.filter((p) => p.id !== focusId) : people;
  $: focused = focusId ? people.find((p) => p.id === focusId) : null;
  $: lay = bestLayout(mosaic.length, stageW, stageH);

  // Participantes (yo + peers) para los recuadros de personas.
  $: people = [
    {
      id: "me", name: $me.display_name, avatar: $me.avatar_url, self: true,
      camera: st.cameraOn ? localCameraStream() : null, hasCamera: st.cameraOn,
      speaking: st.meSpeaking && !st.muted, micMuted: st.muted, deafened: st.deafened,
      sharing: st.sharing, rtt: st.myRtt, quality: null,
      status: $me.status || "online", custom_status: $me.custom_status || null,
    },
    ...peers.map((p) => ({
      id: p.id, name: p.name, avatar: p.avatar, self: false,
      camera: p.camera, hasCamera: p.hasCamera, speaking: p.speaking,
      // Micro: lo dice LiveKit (TrackMuted) o la presencia; auriculares: presencia.
      micMuted: p.micMuted || !!voiceFlags[p.id]?.muted,
      deafened: !!voiceFlags[p.id]?.deafened,
      sharing: p.hasScreen,
      rtt: voiceFlags[p.id]?.rtt ?? null, // su ping, publicado por presencia
      quality: p.quality,
      status: voiceFlags[p.id]?.status || "online",
      custom_status: voiceFlags[p.id]?.custom_status || null,
    })),
  ];

  onDestroy(() => { menu = null; focusId = null; });
</script>

<section class="vv">
  <header>
    <button class="back" on:click={onBack} aria-label="Volver"><i class="ti ti-chevron-left"></i></button>
    <span class="mk"><i class="ti ti-volume"></i></span>
    <span class="display title">{channelName}</span>
    {#if st.connecting}
      <span class="count connecting"><i class="ti ti-loader-2 spin"></i> Conectando…</span>
    {:else}
      <span class="count">{people.length} en la sala</span>
    {/if}
  </header>

  {#if boardOpen && channelId != null}
    <div class="boardwrap">
      <Whiteboard {channelId} onClose={() => (boardOpen = false)} />
    </div>
  {:else}
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

    <!-- Recuadro de un participante. `w`/`h` en px: 0 = que mande el CSS
         (recuadro enfocado, que se estira). El avatar escala con el recuadro. -->
    {#snippet tile(p, w, h)}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div
        class="tile"
        class:speaking={p.speaking}
        class:auditing={auditId === p.id}
        class:focusable={true}
        style={w ? `width:${w}px;height:${h}px` : ""}
        role="button"
        tabindex="-1"
        title="{p.name}{p.self ? ' (tú)' : ''} · clic para {focusId === p.id ? 'reducir' : 'agrandar'}{p.self ? '' : ' · clic derecho para opciones'}"
        on:click={() => toggleFocus(p)}
        on:contextmenu={(e) => openMenu(e, p)}
      >
        {#if p.hasCamera && p.camera}
          <video use:srcObject={p.camera} autoplay playsinline muted={p.self}></video>
        {:else}
          <div class="mid">
            <Avatar name={p.name} url={p.avatar} size={Math.round(Math.max(40, Math.min(120, (h || 220) * 0.4)))} status={p.status} />
            {#if p.custom_status}<span class="cst" title={p.custom_status}>{p.custom_status}</span>{/if}
          </div>
        {/if}
        <span class="lbl">
          {p.name}{#if p.self}&nbsp;(tú){/if}
          {#if p.sharing}<span class="live-badge">EN DIRECTO</span>{/if}
          {#if p.deafened}<i class="ti ti-headphones-off mo" title="Ensordecido"></i>
          {:else if p.micMuted}<i class="ti ti-microphone-off mo" title="Micro silenciado"></i>{/if}
          <span class="ping" style="color:{pingColor(p.rtt, p.quality)}" title="Latencia con el servidor de voz">
            <i class="ti ti-wifi"></i>{p.rtt != null ? ` ${p.rtt} ms` : ""}
          </span>
        </span>
      </div>
    {/snippet}

    <div class="gridarea" use:measureStage>
      {#if focused}
        <!-- Modo foco: un recuadro grande + tira de miniaturas debajo. -->
        <div class="focuswrap">
          <div class="bigtile">{@render tile(focused, 0, 0)}</div>
          {#if mosaic.length}
            <div class="strip">
              {#each mosaic as p (p.id)}
                {@render tile(p, 150, 94)}
              {/each}
            </div>
          {/if}
        </div>
      {:else}
        <div class="grid">
          {#each mosaic as p (p.id)}
            {@render tile(p, lay.w, lay.h)}
          {/each}
        </div>
      {/if}
    </div>
  </div>
  {/if}

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
    <button class="cb" class:act={boardOpen} on:click={() => (boardOpen = !boardOpen)} title="Pizarra compartida" aria-label="Pizarra compartida">
      <i class="ti ti-chalkboard"></i>
    </button>
    <button class="cb leave" on:click={leaveVoice} title="Salir de la voz" aria-label="Salir de la voz">
      <i class="ti ti-phone-off"></i>
    </button>
  </div>
</section>

{#if menu}
  <UserMenu user={menu.user} x={menu.x} y={menu.y} onClose={() => (menu = null)} />
{/if}

<style>
  .vv {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    background: var(--ink);
  }
  header {
    box-sizing: border-box;
    min-height: var(--header-h); /* alineada con las demás columnas */
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 0 18px;
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
  .count { margin-left: auto; font-size: 12px; color: var(--mut); display: flex; align-items: center; gap: 6px; }
  .count.connecting { color: var(--shu); }
  .spin { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .stage {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
  }
  /* Zona medida donde se calcula el tamaño de los recuadros (rellena lo que
     sobra tras el aviso de error y las pantallas compartidas). */
  .gridarea {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  /* La pizarra ocupa el área del escenario; la barra de controles sigue abajo. */
  .boardwrap {
    flex: 1;
    min-height: 0;
    position: relative;
  }
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
  /* Mosaico: los recuadros llegan con tamaño EXACTO calculado en JS (bestLayout)
     y solo se centran aquí. Al no depender de aspect-ratio + grid, nunca se
     solapan aunque falte alto (el bug de la ventana pequeña). */
  .grid {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-content: center;
    justify-content: center;
    width: 100%;
    height: 100%;
  }
  /* Modo foco: recuadro grande arriba, tira de miniaturas debajo. */
  .focuswrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    height: 100%;
    min-height: 0;
  }
  .bigtile {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .bigtile :global(.tile) {
    width: auto;
    height: 100%;
    max-width: 100%;
    aspect-ratio: 16 / 10;
  }
  .strip {
    flex: none;
    display: flex;
    gap: 10px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .tile {
    position: relative;
    background: #0c0a08;
    border: 1px solid var(--bd2);
    border-radius: 16px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 20px var(--shadow);
    cursor: pointer;
  }
  .tile.screen { aspect-ratio: 16 / 9; width: 100%; height: auto; }
  /* Recuadro que se está auditando (menú de clic derecho abierto): acento. */
  .tile.auditing {
    border-color: var(--shu);
    box-shadow: 0 0 0 3px rgba(var(--shu-rgb), 0.5);
  }
  .tile video { width: 100%; height: 100%; object-fit: cover; }
  .tile.screen video { object-fit: contain; background: #000; }
  /* Aro de tinta al hablar. */
  .tile.speaking {
    border-color: var(--on, #6bbf59);
    box-shadow: 0 0 0 3px rgba(107, 191, 89, 0.4);
  }
  .mid {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 9px;
  }
  /* Estado personalizado bajo el avatar del recuadro. */
  .mid .cst {
    max-width: 90%;
    font-size: 11.5px;
    color: var(--mut);
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
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
  .lbl .ping {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
  }
  .lbl .ping i { font-size: 12px; }
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
