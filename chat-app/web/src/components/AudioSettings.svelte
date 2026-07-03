<script>
  import { onMount, onDestroy } from "svelte";
  import { prefs, setPref } from "../lib/prefs.js";
  import {
    listAudioDevices, setInputDevice, setOutputDevice, refreshMicConstraints, setKrisp,
  } from "../lib/voice.js";
  import { playSound } from "../lib/sounds.js";
  import { applyShortcuts, codeCombo, prettyCombo } from "../lib/shortcuts.js";

  export let onClose = () => {};

  // --- Atajos de teclado ---
  // Capturamos el ACORDE completo (todas las teclas mantenidas) para permitir
  // combos solo de modificadores, p. ej. Alt + Ctrl izquierdo. Se registra el
  // "pico" (máximo de teclas pulsadas) y se confirma al soltar todas.
  let capturing = null; // "muteShortcut" | "deafenShortcut" | null
  let capHeld = new Set();
  let capPeak = new Set();
  let capDisplay = "";
  function startCapture(key) {
    capturing = key;
    capHeld = new Set();
    capPeak = new Set();
    capDisplay = "Pulsa una combinación…";
  }
  function onCaptureDown(e, key) {
    if (capturing !== key) return;
    e.preventDefault();
    if (e.code === "Escape") { capturing = null; return; }
    capHeld.add(e.code);
    capPeak.add(e.code);
    capDisplay = prettyCombo(codeCombo([...capPeak]));
  }
  function onCaptureUp(e, key) {
    if (capturing !== key) return;
    e.preventDefault();
    capHeld.delete(e.code);
    if (capHeld.size === 0 && capPeak.size) {
      setPref(key, codeCombo([...capPeak]));
      capturing = null;
      applyShortcuts();
    }
  }
  function clearShortcut(key) {
    setPref(key, "");
    applyShortcuts();
  }

  let inputs = [];
  let outputs = [];
  let micError = "";

  // --- Medidor del micrófono ---
  let stream = null;
  let meterCtx = null;
  let analyser = null;
  let srcNode = null;
  let raf = 0;
  let level = 0; // 0-100
  let supportsOutputPick = false;

  // --- Prueba "grabar y escuchar" (sin bucle en vivo => sin recortes del eco) ---
  let recState = "idle"; // idle | recording | playing
  let recCountdown = 0;
  let mediaRec = null;
  let recordedUrl = null;
  let recAudio = null;
  const REC_SECS = 4;

  async function loadDevices() {
    try {
      const d = await listAudioDevices();
      inputs = d.inputs;
      outputs = d.outputs;
      supportsOutputPick = outputs.length > 0 && outputs.some((o) => o.deviceId);
    } catch {
      micError = "No se pudieron listar los dispositivos.";
    }
  }

  async function startMeter() {
    stopMeter();
    micError = "";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: $prefs.inputDeviceId || undefined,
          noiseSuppression: $prefs.noiseSuppression,
          echoCancellation: $prefs.echoCancellation,
          autoGainControl: $prefs.autoGainControl,
        },
      });
      meterCtx = new (window.AudioContext || window.webkitAudioContext)();
      srcNode = meterCtx.createMediaStreamSource(stream);
      analyser = meterCtx.createAnalyser();
      analyser.fftSize = 512;
      srcNode.connect(analyser); // solo medir; NO conectamos a la salida (sin bucle)
      const data = new Uint8Array(analyser.frequencyBinCount);
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) {
          const d = Math.abs(v - 128);
          if (d > peak) peak = d;
        }
        level = Math.min(100, (peak / 128) * 140);
        raf = requestAnimationFrame(loop);
      };
      loop();
    } catch {
      micError = "No se pudo acceder al micrófono (¿permiso denegado?).";
    }
  }

  function stopMeter() {
    cancelAnimationFrame(raf);
    raf = 0;
    level = 0;
    try { stream?.getTracks().forEach((t) => t.stop()); } catch {}
    try { meterCtx?.close(); } catch {}
    stream = null;
    meterCtx = null;
    analyser = null;
    srcNode = null;
  }

  // Graba unos segundos del micro y los reproduce: oyes cómo suenas SIN el
  // bucle en vivo (que con la cancelación de eco entrecorta la voz).
  async function recordTest() {
    if (recState !== "idle") return;
    if (!stream) await startMeter();
    if (!stream) return;
    let mr;
    try {
      mr = new MediaRecorder(stream);
    } catch {
      micError = "Tu navegador no permite grabar la prueba.";
      return;
    }
    mediaRec = mr;
    const chunks = [];
    mr.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    mr.onstop = async () => {
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
      recordedUrl = URL.createObjectURL(new Blob(chunks, { type: mr.mimeType || "audio/webm" }));
      recAudio = new Audio(recordedUrl);
      if ($prefs.outputDeviceId && recAudio.setSinkId) {
        try { await recAudio.setSinkId($prefs.outputDeviceId); } catch {}
      }
      recAudio.onended = () => { recState = "idle"; };
      recState = "playing";
      try { await recAudio.play(); } catch { recState = "idle"; }
    };
    recState = "recording";
    recCountdown = REC_SECS;
    mr.start();
    const iv = setInterval(() => {
      recCountdown -= 1;
      if (recCountdown <= 0) {
        clearInterval(iv);
        try { mr.stop(); } catch {}
      }
    }, 1000);
  }

  async function onPickInput(e) {
    await setInputDevice(e.target.value);
    startMeter(); // reabrir el medidor con el nuevo micro
  }
  async function onPickOutput(e) {
    await setOutputDevice(e.target.value);
  }
  async function onToggleConstraint(key, value) {
    setPref(key, value);
    await refreshMicConstraints(); // aplica en la llamada en curso
    startMeter(); // y refresca el medidor
  }

  async function testOutput() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      if ($prefs.outputDeviceId && ctx.setSinkId) {
        try { await ctx.setSinkId($prefs.outputDeviceId); } catch {}
      }
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = 523;
      o.connect(g).connect(ctx.destination);
      const t = ctx.currentTime;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.09, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.45);
      o.start(t);
      o.stop(t + 0.5);
      setTimeout(() => ctx.close(), 700);
    } catch {}
  }

  onMount(async () => {
    await loadDevices();
    startMeter();
  });
  onDestroy(() => {
    stopMeter();
    try { mediaRec?.state === "recording" && mediaRec.stop(); } catch {}
    try { recAudio?.pause(); } catch {}
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
  });
</script>

<button class="backdrop" on:click={onClose} aria-label="Cerrar"></button>
<div class="modal" role="dialog" aria-label="Ajustes de audio">
  <header>
    <span class="display title">Ajustes de audio</span>
    <button class="x" on:click={onClose} aria-label="Cerrar"><i class="ti ti-x"></i></button>
  </header>

  <div class="body">
    <!-- Micrófono -->
    <section class="card">
      <div class="card-h"><i class="ti ti-microphone"></i> Micrófono</div>
      <select value={$prefs.inputDeviceId} on:change={onPickInput}>
        <option value="">Por defecto del sistema</option>
        {#each inputs as d}
          <option value={d.deviceId}>{d.label || "Micrófono"}</option>
        {/each}
      </select>
      <div class="meter" class:rec={recState === "recording"}><div class="meterfill" style="width:{level}%"></div></div>
      <div class="row">
        <button class="test" class:on={recState !== "idle"} on:click={recordTest} disabled={recState !== "idle"}>
          {#if recState === "recording"}
            <i class="ti ti-microphone"></i> Grabando… {recCountdown}
          {:else if recState === "playing"}
            <i class="ti ti-player-play"></i> Reproduciendo…
          {:else}
            <i class="ti ti-microphone"></i> Grabar y escuchar
          {/if}
        </button>
        <small class="note">graba {REC_SECS}s y te los reproduce</small>
      </div>
      {#if micError}<div class="err">{micError}</div>{/if}
    </section>

    <!-- Salida -->
    <section class="card">
      <div class="card-h"><i class="ti ti-volume"></i> Salida de audio</div>
      <div class="row">
        <select value={$prefs.outputDeviceId} on:change={onPickOutput} disabled={!supportsOutputPick}>
          <option value="">Por defecto del sistema</option>
          {#each outputs as d}
            <option value={d.deviceId}>{d.label || "Salida"}</option>
          {/each}
        </select>
        <button class="test" on:click={testOutput}><i class="ti ti-player-play"></i> Probar</button>
      </div>
      {#if !supportsOutputPick}
        <small class="note">Tu navegador no permite elegir salida (usa la del sistema).</small>
      {/if}
    </section>

    <!-- Procesado del micro -->
    <section class="card">
      <div class="card-h"><i class="ti ti-adjustments-alt"></i> Procesado del micrófono</div>
      <label class="switch">
        <input type="checkbox" checked={$prefs.krisp} on:change={(e) => setKrisp(e.target.checked)} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Supresión de ruido avanzada (Krisp)<small>quita teclado, ventilador, voces de fondo</small></span>
      </label>
      <label class="switch">
        <input type="checkbox" checked={$prefs.noiseSuppression} on:change={(e) => onToggleConstraint("noiseSuppression", e.target.checked)} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Supresión de ruido básica (navegador)</span>
      </label>
      <label class="switch">
        <input type="checkbox" checked={$prefs.echoCancellation} on:change={(e) => onToggleConstraint("echoCancellation", e.target.checked)} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Cancelación de eco</span>
      </label>
      <label class="switch">
        <input type="checkbox" checked={$prefs.autoGainControl} on:change={(e) => onToggleConstraint("autoGainControl", e.target.checked)} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Control automático de ganancia</span>
      </label>
    </section>

    <!-- Sonidos -->
    <section class="card">
      <div class="card-h"><i class="ti ti-bell"></i> Sonidos</div>
      <label class="switch">
        <input type="checkbox" checked={$prefs.soundsEnabled}
          on:change={(e) => { setPref("soundsEnabled", e.target.checked); if (e.target.checked) playSound("test"); }} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Efectos de la app<small>mutear, entrar y salir de la voz</small></span>
      </label>
      <label class="switch">
        <input type="checkbox" checked={$prefs.notificationSound}
          on:change={(e) => { setPref("notificationSound", e.target.checked); if (e.target.checked) playSound("notify"); }} />
        <span class="track"><span class="thumb"></span></span>
        <span class="sw-txt">Sonidos de notificación<small>mensajes nuevos y menciones</small></span>
      </label>
    </section>

    <!-- Atajos de teclado -->
    <section class="card">
      <div class="card-h"><i class="ti ti-keyboard"></i> Atajos de teclado</div>
      <p class="note">En la app de escritorio funcionan en todo el sistema; en el navegador, solo con la ventana enfocada.</p>
      <div class="shortcut">
        <span class="sc-label">Silenciar micrófono</span>
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <button class="sc-key" class:capturing={capturing === "muteShortcut"}
          on:click={() => startCapture("muteShortcut")}
          on:keydown={(e) => onCaptureDown(e, "muteShortcut")}
          on:keyup={(e) => onCaptureUp(e, "muteShortcut")}>
          {capturing === "muteShortcut" ? capDisplay : prettyCombo($prefs.muteShortcut)}
        </button>
        <button class="sc-clear" on:click={() => clearShortcut("muteShortcut")} title="Quitar" aria-label="Quitar"><i class="ti ti-x"></i></button>
      </div>
      <div class="shortcut">
        <span class="sc-label">Ensordecer</span>
        <button class="sc-key" class:capturing={capturing === "deafenShortcut"}
          on:click={() => startCapture("deafenShortcut")}
          on:keydown={(e) => onCaptureDown(e, "deafenShortcut")}
          on:keyup={(e) => onCaptureUp(e, "deafenShortcut")}>
          {capturing === "deafenShortcut" ? capDisplay : prettyCombo($prefs.deafenShortcut)}
        </button>
        <button class="sc-clear" on:click={() => clearShortcut("deafenShortcut")} title="Quitar" aria-label="Quitar"><i class="ti ti-x"></i></button>
      </div>
    </section>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    border: none;
    z-index: 80;
  }
  .modal {
    position: fixed;
    z-index: 81;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(440px, 92vw);
    max-height: 88vh;
    overflow-y: auto;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 16px;
    box-shadow: 0 24px 60px var(--shadow);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 18px;
    border-bottom: 1px solid var(--bd);
  }
  .title {
    font-size: 16px;
  }
  .x {
    background: none;
    border: none;
    color: var(--mut);
    font-size: 18px;
  }
  .x:hover {
    color: var(--shu);
  }
  .body {
    padding: 14px 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 9px;
    background: var(--ink);
    border: 1px solid var(--bd);
    border-radius: 12px;
    padding: 13px 14px;
  }
  .card-h {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--mut);
  }
  .card-h i {
    color: var(--shu);
    font-size: 15px;
  }
  .note {
    color: var(--fnt);
    font-size: 12px;
  }
  /* Interruptor estilo switch */
  .switch {
    display: flex;
    align-items: center;
    gap: 11px;
    cursor: pointer;
  }
  .switch input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }
  .track {
    flex: none;
    width: 38px;
    height: 22px;
    border-radius: 999px;
    background: var(--field);
    border: 1px solid var(--bd2);
    position: relative;
    transition: background 0.15s, border-color 0.15s;
  }
  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--mut);
    transition: transform 0.15s, background 0.15s;
  }
  .switch input:checked + .track {
    background: rgba(var(--shu-rgb), 0.30);
    border-color: var(--shu);
  }
  .switch input:checked + .track .thumb {
    transform: translateX(16px);
    background: var(--shu);
  }
  .switch input:focus-visible + .track {
    box-shadow: 0 0 0 3px rgba(var(--shu-rgb), 0.25);
  }
  .sw-txt {
    display: flex;
    flex-direction: column;
    font-size: 13px;
    color: var(--tx);
    line-height: 1.35;
  }
  .sw-txt small {
    color: var(--fnt);
    font-size: 11.5px;
  }
  select {
    width: 100%;
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 9px;
    padding: 9px 10px;
    font-size: 13px;
    color: var(--tx);
    outline: none;
  }
  select:focus {
    border-color: var(--shu);
  }
  .row {
    display: flex;
    gap: 8px;
  }
  .row select {
    flex: 1;
    min-width: 0;
  }
  .test {
    flex: none;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    border-radius: 9px;
    padding: 0 14px;
    font-size: 13px;
  }
  .test:hover {
    color: var(--shu);
    border-color: var(--shu);
  }
  .test.on {
    color: var(--shu);
    border-color: var(--shu);
    background: rgba(var(--shu-rgb), 0.14);
  }
  .test {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 32px;
  }
  .meter {
    height: 12px;
    border-radius: 999px;
    background: var(--field);
    border: 1px solid var(--bd2);
    overflow: hidden;
  }
  .meterfill {
    height: 100%;
    background: linear-gradient(90deg, var(--on), var(--shu));
    transition: width 0.06s linear;
  }
  .meter.rec {
    border-color: var(--dnd);
    box-shadow: 0 0 0 2px rgba(226, 85, 59, 0.25);
  }
  .shortcut {
    display: flex;
    align-items: center;
    gap: 9px;
  }
  .sc-label {
    flex: 1;
    min-width: 0;
    font-size: 13px;
    color: var(--tx);
  }
  .sc-key {
    flex: none;
    min-width: 140px;
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12.5px;
    color: var(--tx);
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .sc-key:hover {
    border-color: var(--shu);
  }
  .sc-key.capturing {
    border-color: var(--shu);
    color: var(--shu);
    background: rgba(var(--shu-rgb), 0.12);
  }
  .sc-clear {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }
  .sc-clear:hover {
    color: var(--shu);
    border-color: var(--shu);
  }
  .err {
    color: #c0593b;
    font-size: 12.5px;
  }
</style>
