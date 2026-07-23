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
// y este paquete además descarta la probabilidad VAD que calcula RNNoise. La
// cadena completa es:
//
//   micro -> paso-alto 90 Hz (golpes de mesa, roces, retumbe del ventilador)
//         -> RNNoise (limpia el ruido de fondo continuo)
//         -> puerta propia (silencia lo que no es voz, CON rampas)
//         -> pista procesada -> se publica a la sala
//
// El paso-alto va primero porque un golpe que entra en RNNoise se modela como
// ruido y ensucia la voz. La puerta es nuestra (voiceGateWorklet.js) y no la
// del paquete: aquella conmutaba la ganancia de golpe y metía un clic en cada
// apertura y cierre.
//
// Nota honesta: el teclado MIENTRAS hablas es lo único que ningún supresor de
// un solo canal quita del todo (la puerta está abierta porque hay voz); RNNoise
// lo atenúa pero no lo borra. Para eso haría falta un modelo de IA específico.
import { loadRnnoise, RnnoiseWorkletNode } from "@sapphi-red/web-noise-suppressor";
import rnnoiseWorkletPath from "@sapphi-red/web-noise-suppressor/rnnoiseWorklet.js?url";
import rnnoiseWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise.wasm?url";
import rnnoiseSimdWasmPath from "@sapphi-red/web-noise-suppressor/rnnoise_simd.wasm?url";
import gateWorkletPath from "./voiceGateWorklet.js?url";

let wasmPromise = null;

// Corte del paso-alto (Hz). Los golpes en la mesa, los roces del micro y el
// retumbe del ventilador viven casi todos por DEBAJO de esta frecuencia,
// mientras que la voz se entiende de 300 Hz para arriba. Cortando aquí, esos
// golpes ni siquiera llegan a RNNoise (que no está entrenada para impulsos) ni
// abren la puerta. 90 Hz respeta los graves de una voz masculina.
const HPF_HZ = 90;

// Presets de la puerta de ruido. Umbrales en dBFS sobre la SALIDA de RNNoise
// (ya limpia), así que se pueden poner altos sin comerse la voz:
//   openThreshold  = nivel que ABRE la puerta (deja pasar la voz)
//   closeThreshold = nivel que la CIERRA (histéresis: evita el parpadeo)
//   holdMs         = sigue abierta este rato tras la última voz (no corta el
//                    final de las palabras ni los huecos entre sílabas)
//   attackMs/releaseMs = rampas de la ganancia. Son las que evitan los clics:
//                    la puerta se abre y se cierra en pendiente, no de golpe.
// Más "fuerte" = umbral más alto = corta más respiros y teclado de fondo, pero
// puede recortar una voz MUY floja. "Medio" es el equilibrio por defecto.
export const GATE_PRESETS = {
  off:    null,
  suave:  { openThreshold: -58, closeThreshold: -64, holdMs: 350, attackMs: 5, releaseMs: 180 },
  medio:  { openThreshold: -48, closeThreshold: -55, holdMs: 300, attackMs: 4, releaseMs: 140 },
  fuerte: { openThreshold: -40, closeThreshold: -47, holdMs: 240, attackMs: 3, releaseMs: 110 },
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
  let ctx = null, src = null, hpf1 = null, hpf2 = null, rnnoise = null, gate = null, dest = null;

  async function setup(opts) {
    const wasmBinary = await preloadNoiseModel();
    // Contexto propio a 48 kHz: RNNoise está entrenada a esa tasa. El navegador
    // remuestrea el micro si hiciera falta.
    ctx = new AudioContext({ sampleRate: 48000 });
    await ctx.audioWorklet.addModule(rnnoiseWorkletPath);
    if (gateCfg) await ctx.audioWorklet.addModule(gateWorkletPath);

    src = ctx.createMediaStreamSource(new MediaStream([opts.track]));
    // Dos biquads en cascada = 24 dB/octava: a 45 Hz un golpe de mesa baja
    // ~24 dB. Uno solo (12 dB/oct) se quedaba corto con los porrazos fuertes.
    hpf1 = ctx.createBiquadFilter();
    hpf2 = ctx.createBiquadFilter();
    for (const f of [hpf1, hpf2]) {
      f.type = "highpass";
      f.frequency.value = HPF_HZ;
      f.Q.value = 0.707; // Butterworth: sin resonancia en el codo
    }
    rnnoise = new RnnoiseWorkletNode(ctx, { wasmBinary, maxChannels: 1 });
    dest = ctx.createMediaStreamDestination();

    // TODO MONO, explícito. Los worklets procesan 1 canal (maxChannels: 1);
    // si el micro llega en estéreo y no se fuerza el downmix, toman SOLO el
    // canal izquierdo y a esa persona se le oye por un solo oído. Con
    // channelCount 1 + "explicit", WebAudio mezcla L+R a mono en la entrada,
    // y el mono de salida se reparte a ambos oídos al reproducir.
    for (const node of [hpf1, hpf2, rnnoise, dest]) {
      try { node.channelCount = 1; node.channelCountMode = "explicit"; } catch {}
    }

    // Cadena: micro -> paso-alto -> RNNoise -> (puerta) -> destino.
    // El paso-alto va PRIMERO a propósito: si el golpe llega a RNNoise, el
    // denoiser intenta modelarlo como ruido de fondo y ensucia la voz.
    let last = src;
    last.connect(hpf1);
    hpf1.connect(hpf2);
    last = hpf2;
    last.connect(rnnoise);
    last = rnnoise;
    if (gateCfg) {
      gate = new AudioWorkletNode(ctx, "kurug-voice-gate", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions: gateCfg,
      });
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
    try { gate?.port.postMessage("destroy"); } catch {}
    try { gate?.disconnect(); } catch {}
    try { hpf1?.disconnect(); } catch {}
    try { hpf2?.disconnect(); } catch {}
    try { src?.disconnect(); } catch {}
    try { proc.processedTrack?.stop(); } catch {}
    try { await ctx?.close(); } catch {}
    ctx = src = hpf1 = hpf2 = rnnoise = gate = dest = null;
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
