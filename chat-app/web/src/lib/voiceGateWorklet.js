// Puerta de ruido de Kurug (AudioWorklet, JS puro — sin WASM ni imports, para
// poder cargarlo con `?url` igual que los worklets del paquete de RNNoise).
//
// POR QUÉ NO USAMOS LA DEL PAQUETE: la NoiseGate de
// @sapphi-red/web-noise-suppressor decide por bloque de 128 muestras y aplica
// la decisión EN SECO — si está abierta copia el bloque tal cual, y si está
// cerrada no escribe nada. Es decir, la ganancia salta de 1 a 0 (y de 0 a 1)
// de golpe cada 2,7 ms: cada apertura y cada cierre mete una discontinuidad en
// la onda, que se oye como un CLIC. Con voz entrecortada eso es un chisporroteo
// constante ("pequeñas interferencias"), y además el salto seco decapita el
// inicio de las palabras que arrancan flojas.
//
// Aquí la decisión es la misma idea (histéresis + hold), pero la ganancia se
// mueve MUESTRA A MUESTRA con rampas exponenciales:
//   - ataque rápido (~4 ms): abre a tiempo, sin comerse el arranque de la voz
//   - cierre lento (~140 ms): se desvanece en vez de cortar
// Sin saltos no hay clic, y al no chasquear se pueden usar umbrales más altos
// (más agresivos con respiros y teclado) sin que suene troceado.
const FRAME = 128;

// Coeficiente de un filtro exponencial de un polo para una constante de tiempo
// dada: cuánto se conserva del valor anterior en cada muestra.
function coef(ms, sr) {
  if (ms <= 0) return 0;
  return Math.exp(-1 / ((ms / 1000) * sr));
}

const dbToLin = (db) => Math.pow(10, db / 20);

class KurugVoiceGate extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = options.processorOptions || {};
    const sr = sampleRate;

    this.openLin = dbToLin(o.openThreshold ?? -50);
    this.closeLin = dbToLin(o.closeThreshold ?? -57);
    this.holdSamples = Math.round(((o.holdMs ?? 280) / 1000) * sr);
    // Suelo al que baja la puerta cerrada. 0 = silencio total (lo normal);
    // un suelo pequeño (p. ej. -35 dB) deja un hilo de ambiente más natural.
    this.floor = o.floorDb == null ? 0 : dbToLin(o.floorDb);

    this.attackCoef = coef(o.attackMs ?? 4, sr);
    this.releaseCoef = coef(o.releaseMs ?? 140, sr);
    // Caída de la envolvente, a ritmo de BLOQUE (128 muestras = 2,7 ms). Sube
    // al instante y baja despacio, para que la decisión no parpadee entre
    // sílabas.
    this.envDownCoef = Math.exp(-(FRAME / sr) / 0.06);

    this.env = 0;      // nivel seguido de la señal (lineal)
    this.gain = 0;     // ganancia aplicada ahora mismo
    this.open = false; // estado de la puerta
    this.held = 0;     // muestras que lleva en "cerrando" (hold)

    this.port.onmessage = (e) => {
      if (e.data === "destroy") this.dead = true;
    };
  }

  process(inputs, outputs) {
    if (this.dead) return false;
    const input = inputs[0];
    const output = outputs[0];
    if (!input || !input.length || !output || !output.length) return true;

    const inCh = input[0];
    const outCh = output[0];
    if (!inCh || !outCh) return true;

    // Nivel del bloque en RMS. Es la MISMA medida que usaba la puerta anterior,
    // a propósito: así los umbrales en dBFS de los presets significan lo mismo
    // de siempre. (Con envolvente de pico, un siseo de -60 dBFS marcaba ~-50 y
    // la puerta no llegaba a cerrar nunca.)
    let sum = 0;
    for (let i = 0; i < inCh.length; i++) sum += inCh[i] * inCh[i];
    const rms = Math.sqrt(sum / inCh.length);
    // Sube al instante (no perder el arranque), baja despacio (no parpadear).
    this.env = rms > this.env ? rms : rms + (this.env - rms) * this.envDownCoef;

    // Estado con histéresis: abre por encima del umbral alto, y una vez
    // abierta aguanta hasta caer bajo el umbral bajo durante todo el hold
    // (así no se corta entre palabras de una misma frase).
    if (this.env > this.openLin) {
      this.open = true;
      this.held = 0;
    } else if (this.open && this.env < this.closeLin) {
      this.held += inCh.length;
      if (this.held > this.holdSamples) this.open = false;
    }

    // La ganancia se mueve MUESTRA A MUESTRA hacia el objetivo del bloque:
    // aquí es donde desaparecen los clics.
    const target = this.open ? 1 : this.floor;
    for (let i = 0; i < inCh.length; i++) {
      const c = target > this.gain ? this.attackCoef : this.releaseCoef;
      this.gain = target + (this.gain - target) * c;
      // La rampa es exponencial y nunca llega a cero del todo. Por debajo de
      // -80 dB ya es inaudible, así que la clavamos a cero: silencio DIGITAL
      // de verdad (el codec no gasta nada) y sin números desnormalizados, que
      // en algunas CPU disparan el consumo.
      if (target === 0 && this.gain < 1e-3) this.gain = 0;
      outCh[i] = inCh[i] * this.gain;
    }

    // Mono de salida: si hubiera más canales, replicamos (la voz es mono y la
    // cadena fuerza channelCount 1, pero así nunca sale un canal vacío).
    for (let ch = 1; ch < output.length; ch++) {
      if (output[ch]) output[ch].set(outCh);
    }
    return true;
  }
}

registerProcessor("kurug-voice-gate", KurugVoiceGate);
