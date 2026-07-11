// Supresión de ruido propia con RNNoise (la red neuronal open-source de Xiph
// que hizo famosa la supresión de Discord antes de que licenciaran Krisp).
//
// Por qué NO el paquete de Krisp de LiveKit: ese filtro pide permiso al
// servidor (`GET /settings` con el token) y exige `enhancedNoiseCancellation:
// true`, cosa que SOLO responde LiveKit Cloud (es un extra de pago). Con
// nuestro LiveKit auto-hospedado la licencia falla en silencio y el filtro no
// suprime nada. RNNoise corre 100% en tu máquina (WASM + AudioWorklet), sin
// nube ni licencias, con ~10 ms de latencia y un core de CPU de sobra.
//
// Se integra como un TrackProcessor de LiveKit: micro -> RNNoise -> pista
// procesada que es la que se publica a la sala.
import { loadRnnoise, RnnoiseWorkletNode } from "@sapphi-red/web-noise-suppressor";
import rnnoiseWorkletPath from "@sapphi-red/web-noise-suppressor/rnnoiseWorklet.js?url";
import rnnoiseWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise.wasm?url";
import rnnoiseSimdWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise_simd.wasm?url";

let wasmPromise = null;

// Descarga el WASM de RNNoise (~200 KB) una sola vez; se puede precargar al
// abrir la app para que al entrar a la voz el filtro aplique al instante.
export function preloadNoiseModel() {
  if (!wasmPromise) {
    wasmPromise = loadRnnoise({ url: rnnoiseWasmPath, simdUrl: rnnoiseSimdWasmPath })
      .catch((e) => { wasmPromise = null; throw e; });
  }
  return wasmPromise;
}

export function isNoiseSupported() {
  return typeof AudioWorkletNode !== "undefined" && typeof AudioContext !== "undefined";
}

// Crea un TrackProcessor de LiveKit (interfaz: init/restart/destroy +
// processedTrack). Instancia de UN solo uso: siempre crear una nueva.
export function createNoiseProcessor() {
  let ctx = null, src = null, node = null, dest = null;

  async function setup(opts) {
    const wasmBinary = await preloadNoiseModel();
    // Contexto propio a 48 kHz: RNNoise está entrenada a esa tasa. El navegador
    // remuestrea el micro si hiciera falta.
    ctx = new AudioContext({ sampleRate: 48000 });
    await ctx.audioWorklet.addModule(rnnoiseWorkletPath);
    src = ctx.createMediaStreamSource(new MediaStream([opts.track]));
    node = new RnnoiseWorkletNode(ctx, { wasmBinary, maxChannels: 1 });
    dest = ctx.createMediaStreamDestination();
    src.connect(node);
    node.connect(dest);
    if (ctx.state === "suspended") { try { await ctx.resume(); } catch {} }
    return dest.stream.getAudioTracks()[0];
  }

  async function teardown(proc) {
    try { node?.destroy(); } catch {}
    try { src?.disconnect(); } catch {}
    try { proc.processedTrack?.stop(); } catch {}
    try { await ctx?.close(); } catch {}
    ctx = src = node = dest = null;
    proc.processedTrack = undefined;
  }

  return {
    name: "rnnoise-noise-filter",
    processedTrack: undefined,
    async init(opts) {
      this.processedTrack = await setup(opts);
    },
    async restart(opts) {
      await teardown(this);
      this.processedTrack = await setup(opts);
    },
    async destroy() {
      await teardown(this);
    },
  };
}
