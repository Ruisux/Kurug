<script>
  // Pizarra colaborativa: lienzo SVG (viewBox lógico 1920×1080, así todos ven
  // exactamente lo mismo escale como escale su ventana) + barra de herramientas.
  // Lápiz, línea, flecha, rectángulo, elipse, texto, goma, colores, grosor,
  // deshacer (lo propio) y limpiar. Sincronizada en vivo por canal de voz.
  import { onMount, onDestroy } from "svelte";
  import { me } from "../lib/stores.js";
  import { boardState, boardOps, connectBoard, disconnectBoard, newElementId } from "../lib/board.js";
  import { uiZoom } from "../lib/ui.js";

  export let channelId;
  export let onClose = () => {};

  const W = 1920;
  const H = 1080;
  const COLORS = ["#e2553b", "#c2a35b", "#6f9e5a", "#5a76c4", "#9a6cc0", "#dd8bab", "#e8e0d0", "#171310"];
  const WIDTHS = [2, 4, 8];
  const TOOLS = [
    { id: "pen", icon: "ti-pencil", label: "Lápiz" },
    { id: "line", icon: "ti-line", label: "Línea" },
    { id: "arrow", icon: "ti-arrow-up-right", label: "Flecha" },
    { id: "rect", icon: "ti-square", label: "Rectángulo" },
    { id: "ellipse", icon: "ti-circle", label: "Elipse" },
    { id: "text", icon: "ti-typography", label: "Texto" },
    { id: "eraser", icon: "ti-eraser", label: "Goma (borra elementos)" },
  ];

  let svgEl;
  let wbEl;
  let tool = "pen";
  let color = COLORS[0];
  let width = 4;

  // Dibujo en curso
  let stroke = null;   // lápiz: { el, pending: [] }
  let shape = null;    // formas: { kind, a, b } (preview local hasta soltar)
  let erasing = false;
  let strokeTimer = 0; // lotes del lápiz cada ~100 ms

  // Editor de texto flotante
  let textEdit = null; // { x, y, id (si edita uno existente), value }
  let textInput;

  // Enfocar al montar (acción): el input se crea en el evento `click`, cuando
  // el navegador YA terminó el manejo de foco del gesto. Si se creara en
  // `pointerdown`, el `mousedown` del mismo click lo desenfocaría al instante
  // (el SVG no es enfocable) y el blur lo cerraría vacío: "no funciona".
  function autofocus(node) {
    node.focus();
  }

  onMount(() => connectBoard(channelId));
  onDestroy(() => {
    clearInterval(strokeTimer);
    disconnectBoard();
  });

  $: elements = $boardState.elements;

  function toLogical(e) {
    const r = svgEl.getBoundingClientRect();
    const x = Math.round(((e.clientX - r.left) / r.width) * W);
    const y = Math.round(((e.clientY - r.top) / r.height) * H);
    return [Math.max(0, Math.min(W, x)), Math.max(0, Math.min(H, y))];
  }

  function flushStroke() {
    if (stroke && stroke.pending.length) {
      boardOps.addPoints(stroke.el.id, stroke.pending);
      stroke.pending = [];
    }
  }

  function eraseAt(e) {
    const hit = e.target.closest?.("[data-id]");
    if (hit) boardOps.remove(hit.dataset.id);
  }

  function pointerDown(e) {
    if (e.button !== 0 || textEdit) return;
    if (tool === "eraser") {
      erasing = true;
      eraseAt(e);
      return;
    }
    if (tool === "text") return; // el texto se coloca en `click` (ver canvasClick)
    const pt = toLogical(e);
    if (tool === "pen") {
      const el = {
        id: newElementId(), user_id: $me.id, kind: "pen",
        points: [pt], color, width,
      };
      stroke = { el, pending: [] };
      boardOps.add(el); // los demás ven el trazo "dibujándose" con los lotes
      strokeTimer = setInterval(flushStroke, 100);
    } else {
      shape = { kind: tool, a: pt, b: pt };
    }
    svgEl.setPointerCapture?.(e.pointerId);
  }

  function pointerMove(e) {
    if (erasing) {
      eraseAt(e);
      return;
    }
    if (stroke) {
      const pt = toLogical(e);
      const last = stroke.el.points[stroke.el.points.length - 1];
      // Filtro de densidad: solo puntos que se muevan de verdad (>3 px lógicos).
      if (Math.abs(pt[0] - last[0]) + Math.abs(pt[1] - last[1]) > 3) {
        stroke.el.points.push(pt);
        stroke.pending.push(pt);
        boardOps.touchLocal();
      }
    } else if (shape) {
      shape = { ...shape, b: toLogical(e) };
    }
  }

  function pointerUp() {
    erasing = false;
    if (stroke) {
      clearInterval(strokeTimer);
      strokeTimer = 0;
      // Un toque sin arrastre = un punto: con un solo vértice la polilínea no
      // pinta nada, así que se añade un vecino (el linecap redondo hace el punto).
      if (stroke.el.points.length === 1) {
        const [x, y] = stroke.el.points[0];
        const pt = [Math.min(W, x + 1), y];
        stroke.el.points.push(pt);
        stroke.pending.push(pt);
        boardOps.touchLocal();
      }
      flushStroke();
      stroke = null;
    }
    if (shape) {
      const { kind, a, b } = shape;
      shape = null;
      // Un clic sin arrastre no crea una forma invisible.
      if (Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) > 4) {
        boardOps.add({
          id: newElementId(), user_id: $me.id, kind,
          points: [a, b], color, width,
        });
      }
    }
  }

  // Colocar el editor de texto. Va en `click` (no en pointerdown) a propósito:
  // en ese momento el navegador ya no va a mover el foco y el input sobrevive.
  function canvasClick(e) {
    if (tool !== "text" || textEdit) return;
    const [x, y] = toLogical(e);
    textEdit = { x, y, id: null, value: "" };
  }

  function dblClick(e) {
    // Doble clic sobre un texto PROPIO: editarlo.
    const hit = e.target.closest?.("[data-id]");
    if (!hit) return;
    const el = elements.find((x) => x.id === hit.dataset.id);
    if (el && el.kind === "text" && el.user_id === $me.id) {
      textEdit = { x: el.points[0][0], y: el.points[0][1], id: el.id, value: el.text };
    }
  }

  function commitText() {
    if (!textEdit) return;
    const value = textEdit.value.trim().slice(0, 256);
    const { x, y, id } = textEdit;
    textEdit = null;
    if (!value) return;
    if (id) boardOps.update(id, { text: value });
    else boardOps.add({
      id: newElementId(), user_id: $me.id, kind: "text",
      points: [[x, y]], text: value, color, width,
    });
  }

  function textKey(e) {
    if (e.key === "Enter") { e.preventDefault(); commitText(); }
    else if (e.key === "Escape") textEdit = null;
  }

  function clearAll() {
    if (confirm("¿Limpiar TODA la pizarra para todos?")) boardOps.clear();
  }

  // Exportar el flujo como imagen PNG: se serializa el SVG tal cual (mismo
  // viewBox lógico) y se rasteriza a 1920×1080 sobre el color de fondo real.
  let exporting = false;
  async function exportPng() {
    if (exporting || !svgEl) return;
    exporting = true;
    try {
      const clone = svgEl.cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.setAttribute("width", W);
      clone.setAttribute("height", H);
      // Los estilos del componente no viajan en la serialización: fijar la
      // fuente de los textos y quitar las zonas de impacto invisibles.
      clone.style.fontFamily = getComputedStyle(svgEl).fontFamily;
      for (const hit of clone.querySelectorAll(".hit")) hit.remove();
      const svgText = new XMLSerializer().serializeToString(clone);
      const url = URL.createObjectURL(new Blob([svgText], { type: "image/svg+xml" }));
      try {
        const img = new Image();
        await new Promise((ok, bad) => {
          img.onload = ok;
          img.onerror = bad;
          img.src = url;
        });
        const canvas = document.createElement("canvas");
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = getComputedStyle(wbEl).backgroundColor || "#141414";
        ctx.fillRect(0, 0, W, H);
        ctx.drawImage(img, 0, 0, W, H);
        const blob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        const stamp = new Date().toISOString().slice(0, 16).replace("T", "-").replace(":", "");
        a.download = `pizarra-${stamp}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch {
      alert("No se pudo exportar la pizarra.");
    } finally {
      exporting = false;
    }
  }

  // ---- geometría de render ----
  function poly(points) {
    return points.map((p) => p.join(",")).join(" ");
  }
  // La punta de la flecha va DENTRO del mismo path (los <marker> de SVG no
  // heredan bien el color por elemento).
  function arrowPath(a, b, w) {
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const L = 14 + w * 2.5;
    const h1 = [b[0] - L * Math.cos(ang - 0.45), b[1] - L * Math.sin(ang - 0.45)];
    const h2 = [b[0] - L * Math.cos(ang + 0.45), b[1] - L * Math.sin(ang + 0.45)];
    return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]} M ${h1[0].toFixed(1)} ${h1[1].toFixed(1)} L ${b[0]} ${b[1]} L ${h2[0].toFixed(1)} ${h2[1].toFixed(1)}`;
  }
  function rectOf(a, b) {
    return {
      x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]),
      w: Math.abs(a[0] - b[0]), h: Math.abs(a[1] - b[1]),
    };
  }
  function fontSize(w) {
    return 18 + w * 5; // el grosor elegido también dimensiona el texto
  }
  // Posición del input de texto. El rect del lienzo viene en píxeles de
  // viewport, pero el input es `fixed` DENTRO de la interfaz escalada: hay que
  // dividir por el zoom o aparece desplazado (o fuera de la pantalla) en cuanto
  // el tamaño de interfaz no es "Normal".
  function textEditStyle(te) {
    if (!svgEl) return "";
    const z = uiZoom();
    const r = svgEl.getBoundingClientRect();
    const left = (r.left + (te.x / W) * r.width) / z;
    const top = (r.top + (te.y / H) * r.height) / z;
    return `left:${left}px; top:${top}px; color:${color};`;
  }
</script>

<div class="wb" bind:this={wbEl}>
  <div class="toolbar">
    {#each TOOLS as t (t.id)}
      <button class="tb" class:on={tool === t.id} title={t.label} aria-label={t.label} on:click={() => (tool = t.id)}>
        <i class="ti {t.icon}"></i>
      </button>
    {/each}
    <span class="sep"></span>
    {#each COLORS as c (c)}
      <button class="swatch" class:on={color === c} style="background:{c}" title={c} aria-label="Color {c}" on:click={() => (color = c)}></button>
    {/each}
    <span class="sep"></span>
    {#each WIDTHS as w (w)}
      <button class="tb wdth" class:on={width === w} title="Grosor {w}" aria-label="Grosor {w}" on:click={() => (width = w)}>
        <span class="dot" style="width:{4 + w * 2}px; height:{4 + w * 2}px"></span>
      </button>
    {/each}
    <span class="sep"></span>
    <button class="tb" on:click={boardOps.undo} title="Deshacer (lo tuyo)" aria-label="Deshacer"><i class="ti ti-arrow-back-up"></i></button>
    <button class="tb" on:click={exportPng} disabled={exporting} title="Exportar como imagen (PNG)" aria-label="Exportar como imagen"><i class="ti ti-download"></i></button>
    <button class="tb" on:click={clearAll} title="Limpiar todo" aria-label="Limpiar todo"><i class="ti ti-trash"></i></button>
    <span class="spacer"></span>
    <button class="tb close" on:click={onClose} title="Cerrar pizarra" aria-label="Cerrar pizarra"><i class="ti ti-x"></i></button>
  </div>

  <!-- svelte-ignore a11y-no-noninteractive-element-interactions a11y-click-events-have-key-events -->
  <svg
    bind:this={svgEl}
    class="canvas"
    class:erasing={tool === "eraser"}
    viewBox="0 0 {W} {H}"
    role="img"
    aria-label="Pizarra"
    on:pointerdown={pointerDown}
    on:pointermove={pointerMove}
    on:pointerup={pointerUp}
    on:pointerleave={pointerUp}
    on:click={canvasClick}
    on:dblclick={dblClick}
  >
    {#each elements as el (el.id)}
      <g data-id={el.id} class="el">
        {#if el.kind === "pen"}
          <polyline points={poly(el.points)} fill="none" stroke={el.color} stroke-width={el.width} stroke-linecap="round" stroke-linejoin="round" />
          <polyline class="hit" points={poly(el.points)} fill="none" stroke="transparent" stroke-width={Math.max(el.width, 16)} />
        {:else if el.kind === "line"}
          <line x1={el.points[0][0]} y1={el.points[0][1]} x2={el.points[1][0]} y2={el.points[1][1]} stroke={el.color} stroke-width={el.width} stroke-linecap="round" />
          <line class="hit" x1={el.points[0][0]} y1={el.points[0][1]} x2={el.points[1][0]} y2={el.points[1][1]} stroke="transparent" stroke-width={Math.max(el.width, 16)} />
        {:else if el.kind === "arrow"}
          <path d={arrowPath(el.points[0], el.points[1], el.width)} fill="none" stroke={el.color} stroke-width={el.width} stroke-linecap="round" stroke-linejoin="round" />
          <path class="hit" d={arrowPath(el.points[0], el.points[1], el.width)} fill="none" stroke="transparent" stroke-width={Math.max(el.width, 16)} />
        {:else if el.kind === "rect"}
          {@const r = rectOf(el.points[0], el.points[1])}
          <rect x={r.x} y={r.y} width={r.w} height={r.h} fill="none" stroke={el.color} stroke-width={el.width} rx="3" />
          <rect class="hit" x={r.x} y={r.y} width={r.w} height={r.h} fill="none" stroke="transparent" stroke-width={Math.max(el.width, 16)} />
        {:else if el.kind === "ellipse"}
          {@const r = rectOf(el.points[0], el.points[1])}
          <ellipse cx={r.x + r.w / 2} cy={r.y + r.h / 2} rx={r.w / 2} ry={r.h / 2} fill="none" stroke={el.color} stroke-width={el.width} />
          <ellipse class="hit" cx={r.x + r.w / 2} cy={r.y + r.h / 2} rx={r.w / 2} ry={r.h / 2} fill="none" stroke="transparent" stroke-width={Math.max(el.width, 16)} />
        {:else if el.kind === "text"}
          <text x={el.points[0][0]} y={el.points[0][1]} fill={el.color} font-size={fontSize(el.width)} class="txt">{el.text}</text>
        {/if}
      </g>
    {/each}

    <!-- Preview local de la forma en curso (aún no enviada). -->
    {#if shape}
      {#if shape.kind === "line"}
        <line x1={shape.a[0]} y1={shape.a[1]} x2={shape.b[0]} y2={shape.b[1]} stroke={color} stroke-width={width} stroke-linecap="round" opacity="0.8" />
      {:else if shape.kind === "arrow"}
        <path d={arrowPath(shape.a, shape.b, width)} fill="none" stroke={color} stroke-width={width} stroke-linecap="round" opacity="0.8" />
      {:else if shape.kind === "rect"}
        {@const r = rectOf(shape.a, shape.b)}
        <rect x={r.x} y={r.y} width={r.w} height={r.h} fill="none" stroke={color} stroke-width={width} rx="3" opacity="0.8" />
      {:else if shape.kind === "ellipse"}
        {@const r = rectOf(shape.a, shape.b)}
        <ellipse cx={r.x + r.w / 2} cy={r.y + r.h / 2} rx={r.w / 2} ry={r.h / 2} fill="none" stroke={color} stroke-width={width} opacity="0.8" />
      {/if}
    {/if}
  </svg>

  {#if textEdit}
    <input
      use:autofocus
      class="textedit"
      style={textEditStyle(textEdit)}
      bind:value={textEdit.value}
      maxlength="256"
      placeholder="Escribe…"
      on:keydown={textKey}
      on:blur={commitText}
    />
  {/if}
</div>

<style>
  .wb {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    background: var(--ink);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--bd);
    background: var(--pan);
    flex-wrap: wrap;
  }
  .tb {
    width: 34px;
    height: 34px;
    border-radius: 9px;
    border: 1px solid var(--bd2);
    background: var(--field);
    color: var(--mut);
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: none;
  }
  .tb:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .tb.on {
    color: var(--shu);
    border-color: var(--shu);
    background: rgba(var(--shu-rgb), 0.14);
  }
  .swatch {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 2px solid transparent;
    flex: none;
    cursor: pointer;
  }
  .swatch.on {
    border-color: var(--tx);
    box-shadow: 0 0 0 2px var(--pan), 0 0 0 3px var(--bd2);
  }
  .tb.wdth .dot {
    border-radius: 50%;
    background: currentColor;
  }
  .sep {
    width: 1px;
    height: 22px;
    background: var(--bd2);
    margin: 0 5px;
    flex: none;
  }
  .spacer {
    flex: 1;
  }
  .tb.close:hover {
    color: var(--shu);
  }
  .canvas {
    flex: 1;
    min-height: 0;
    width: 100%;
    touch-action: none; /* el puntero dibuja; sin scroll/zoom táctil */
    cursor: crosshair;
    display: block;
  }
  .canvas.erasing {
    cursor: cell;
  }
  /* Las zonas de impacto (goma) solo reciben clics en modo goma. */
  .el :global(.hit) {
    pointer-events: none;
  }
  .canvas.erasing .el :global(.hit) {
    pointer-events: stroke;
  }
  .canvas text {
    /* Reciben eventos SIEMPRE: sin esto el doble clic para editar tu texto
       (y la goma) no encuentran el elemento. Dibujar encima sigue funcionando
       porque el trazo usa coordenadas del puntero, no el target. */
    pointer-events: all;
    user-select: none;
    font-family: inherit;
  }
  .textedit {
    position: fixed;
    z-index: 60;
    transform: translateY(-50%);
    background: var(--pan);
    border: 1px solid var(--shu);
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 15px;
    outline: none;
    min-width: 160px;
  }
</style>
