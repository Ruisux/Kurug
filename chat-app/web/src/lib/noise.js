// Supresión de ruido propia con RNNoise + puerta de ruido (noise gate).
//
// Por qué NO el paquete de Krisp de LiveKit: ese filtro pide permiso al
// servidor (`GET /settings` con el token) y exige `enhancedNoiseCancellation:
// true`, cosa que SOLO responde LiveKit Cloud (es un extra de pago). Con
// nuestro LiveKit auto-hospedado la licencia falla en silencio y el filtro no
// suprime nada. RNNoise corre 100% en tu máquina (WASM + AudioWorklet), sin
// nube ni licencias, con ~10 ms de latencia y un core de CPU de sobra.
//
// RNNoise SOLO no basta: es un denoiser espectral que rebaja el ruido de banda
// ancha MIENTRAS hablas, pero deja pasar respiración y transitorios (teclado),
// y este paquete además descarta la probabilidad VAD que calcula RNNoise. Por
// eso encadenamos una PUERTA DE RUIDO después: mide el nivel y silencia por
// completo la señal cuando baja del umbral (los silencios entre frases, los
// respiros y el teclado cuando no hablas). Juntos imitan al Krisp/Discord:
//
//   micro -> RNNoise (limpia el fondo) -> NoiseGate (corta lo que no es voz)
//         -> pista procesada -> se publica a la sala
//
// Nota honesta: el teclado MIENTRAS hablas es lo único que ningún supresor de
// un solo canal quita del todo (la puerta está abierta porque hay voz); RNNoise
// lo atenúa pero no lo borra. Para eso haría falta un modelo de IA específico.
import {
  loadRnnoise,
  RnnoiseWorkletNode,
  NoiseGateWorkletNode,
} from "@sapphi-red/web-noise-suppressor";
import rnnoiseWorkletPath from "@sapphi-red/web-noise-suppressor/rnnoiseWorklet.js?url";
import noiseGateWorkletPath from "@sapphi-red/web-noise-suppressor/noiseGateWorklet.js?url";
import rnnoiseWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise.wasm?url";
import rnnoiseSimdWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise_simd.wasm?url";

let wasmPromise = null;

// Presets de la puerta de ruido. Umbrales en dBFS sobre la SALIDA de RNNoise
// (ya limpia), así que se pueden poner altos sin comerse la voz:
//   openThreshold  = nivel que ABRE la puerta (deja pasar la voz)
//   closeThreshold = nivel que la CIERRA (histéresis: evita el parpadeo)
//   holdMs         = la puerta sigue abierta este rato tras la última voz, para
//                    no cortar el final de las palabras
// Más "fuerte" = umbral más alto = corta más respiros/teclado, pero puede
// recortar una voz MUY floja. "Medio" es el equilibrio por defecto.
export const GATE_PRESETS = {
  off:    null,
  suave:  { openThreshold: -58, closeThreshold: -64, holdMs: 350 },
  medio:  { openThreshold: -50, closeThreshold: -57, holdMs: 280 },
  fuerte: { openThreshold: -43, closeThreshold: -50, holdMs: 220 },
};
export const GATE_DEFAULT = "medio";

function gateConfig(key) {
  if (key in GATE_PRESETS) return GATE_PRESETS[key];
  return GATE_PRESETS[GATE_DEFAULT];
}

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
// `gateKey` elige el preset de la puerta de ruido (o "off" para desactivarla).
export function createNoiseProcessor(gateKey = GATE_DEFAULT) {
  const gateCfg = gateConfig(gateKey);
  let ctx = null, src = null, rnnoise = null, gate = null, dest = null;

  async function setup(opts) {
    const wasmBinary = await preloadNoiseModel();
    // Contexto propio a 48 kHz: RNNoise está entrenada a esa tasa. El navegador
    // remuestrea el micro si hiciera falta.
    ctx = new AudioContext({ sampleRate: 48000 });
    await ctx.audioWorklet.addModule(rnnoiseWorkletPath);
    if (gateCfg) await ctx.audioWorklet.addModule(noiseGateWorkletPath);

    src = ctx.createMediaStreamSource(new MediaStream([opts.track]));
    rnnoise = new RnnoiseWorkletNode(ctx, { wasmBinary, maxChannels: 1 });
    dest = ctx.createMediaStreamDestination();

    // TODO MONO, explícito. Los worklets procesan 1 canal (maxChannels: 1);
    // si el micro llega en estéreo y no se fuerza el downmix, toman SOLO el
    // canal izquierdo y a esa persona se le oye por un solo oído. Con
    // channelCount 1 + "explicit", WebAudio mezcla L+R a mono en la entrada,
    // y el mono de salida se reparte a ambos oídos al reproducir.
    for (const node of [rnnoise, dest]) {
      try { node.channelCount = 1; node.channelCountMode = "explicit"; } catch {}
    }

    // Cadena: micro -> RNNoise -> (puerta) -> destino.
    let last = src;
    last.connect(rnnoise);
    last = rnnoise;
    if (gateCfg) {
      gate = new NoiseGateWorkletNode(ctx, { ...gateCfg, maxChannels: 1 });
      try { gate.channelCount = 1; gate.channelCountMode = "explicit"; } catch {}
      last.connect(gate);
      last = gate;
    }
    last.connect(dest);

    if (ctx.state === "suspended") { try { await ctx.resume(); } catch {} }
    return dest.stream.getAudioTracks()[0];
  }

  async function teardown(proc) {
    try { rnnoise?.destroy(); } catch {}
    try { gate?.disconnect(); } catch {} // NoiseGateWorkletNode no tiene destroy()
    try { src?.disconnect(); } catch {}
    try { proc.processedTrack?.stop(); } catch {}
    try { await ctx?.close(); } catch {}
    ctx = src = rnnoise = gate = dest = null;
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
