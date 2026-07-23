// Verificación de la puerta de ruido (correr con: node test/voice-gate.mjs).
//
// Ejecuta el ARCHIVO REAL del worklet con los globales de AudioWorklet
// simulados y lo compara con el algoritmo del paquete al que sustituye.
// Comprueba lo que de verdad importa:
//   1. que la puerta NO invente discontinuidades en la onda (los clics que
//      metía la anterior al conmutar la ganancia de golpe),
//   2. que la voz por encima del umbral pase con el nivel intacto,
//   3. que el fondo por debajo del umbral quede inaudible,
//   4. que el ataque sea lo bastante rápido para no decapitar palabras.
// Sale con código 1 si algo falla.
import { readFileSync } from "node:fs";

const SRC = new URL("../src/lib/voiceGateWorklet.js", import.meta.url);
const SR = 48000, N = 128;
const PRESET = { openThreshold: -48, closeThreshold: -55, holdMs: 300, attackMs: 4, releaseMs: 140 };

// --- cargar el worklet real ---
let Klass = null;
const code = readFileSync(SRC, "utf8");
new Function("sampleRate", "AudioWorkletProcessor", "registerProcessor", code)(
  SR,
  class { constructor() { this.port = { onmessage: null, postMessage() {} }; } },
  (_name, cls) => { Klass = cls; },
);
if (!Klass) throw new Error("el worklet no registró la clase");

// --- señal de prueba: silencio -> voz -> silencio ---
const amp = 10 ** (-20 / 20);              // voz a -20 dBFS
const hiss = 10 ** (-60 / 20);             // ruido de fondo a -60 dBFS (siempre presente)
const total = Math.round(SR * 1.6);
const sig = new Float32Array(total);
const v0 = Math.round(SR * 0.3), v1 = Math.round(SR * 0.8);
let seed = 7;
const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) * 2 - 1;
// Señal CONTINUA a propósito: un tono de 200 Hz cuya amplitud sube y baja en
// rampa suave, cruzando el umbral por los dos lados. Al no tener saltos
// propios, CUALQUIER discontinuidad en la salida la ha metido la puerta.
for (let i = 0; i < total; i++) {
  let env = 0;
  if (i >= v0 && i < v1) {
    const t = (i - v0) / (v1 - v0);        // 0..1
    env = Math.sin(Math.PI * t) ** 2;      // sube y baja suave
  }
  sig[i] = hiss * rnd() + amp * env * Math.sin((2 * Math.PI * 200 * i) / SR);
}

const run = (fn) => {
  const out = new Float32Array(total);
  for (let off = 0; off + N <= total; off += N) fn(sig.subarray(off, off + N), out.subarray(off, off + N));
  return out;
};

// NUEVA: el archivo real
const inst = new Klass({ processorOptions: PRESET });
const nueva = run((i, o) => inst.process([[i]], [[o]]));

// ANTIGUA: algoritmo del paquete (decisión por bloque, copia o silencio)
const lin = (d) => 10 ** (d / 20);
const openL = lin(PRESET.openThreshold), closeL = lin(PRESET.closeThreshold);
const holdBlocks = Math.ceil(PRESET.holdMs / ((1000 / SR) * N));
let st = 0, cnt = 0;
const vieja = run((i, o) => {
  let s = 0; for (const x of i) s += x * x;
  const rms = Math.sqrt(s / i.length);
  if (st === 0) { if (rms > openL) st = 1; }
  else if (st === 1) { if (rms < closeL) { st = 2; cnt = 0; } }
  else { if (rms > closeL) st = 1; else if (cnt > holdBlocks) st = 0; else cnt++; }
  if (st === 1 || st === 2) o.set(i);
});

const maxJump = (a) => { let m = 0; for (let i = 1; i < a.length; i++) { const d = Math.abs(a[i] - a[i - 1]); if (d > m) m = d; } return m; };
const rms = (a, s, e) => { let t = 0; for (let i = s; i < e; i++) t += a[i] * a[i]; return Math.sqrt(t / (e - s)); };
const db = (x) => (x <= 1e-12 ? -Infinity : 20 * Math.log10(x));

// Salto "natural" de la señal entre muestras: cualquier salto mayor es un clic.
const natural = maxJump(sig);

// Zona central (voz a pleno nivel) para comprobar que no se toca.
const c0 = Math.round(v0 + (v1 - v0) * 0.4), c1 = Math.round(v0 + (v1 - v0) * 0.6);
const rVozIn = rms(sig, c0, c1);
const rVozNueva = rms(nueva, c0, c1);
const rSilVieja = rms(vieja, total - 6000, total);
const rSilNueva = rms(nueva, total - 6000, total);

// Ataque: desde que la ENTRADA cruza el umbral de apertura hasta que la salida
// alcanza el 90% de la entrada (mide lo que la puerta añade, no la rampa de la
// propia señal de prueba).
let attackMs = null;
{
  let cruce = null;
  for (let off = v0; off + N <= v1; off += N) {
    let s = 0; for (let i = off; i < off + N; i++) s += sig[i] * sig[i];
    if (Math.sqrt(s / N) > openL) { cruce = off; break; }
  }
  if (cruce != null) {
    for (let i = cruce; i < v1; i++) {
      if (Math.abs(sig[i]) > 1e-4 && Math.abs(nueva[i]) >= 0.9 * Math.abs(sig[i])) {
        attackMs = ((i - cruce) / SR) * 1000;
        break;
      }
    }
  }
}

console.log(JSON.stringify({
  discontinuidades_en_la_onda: {
    natural_de_la_senal: +natural.toFixed(5),
    puerta_vieja: +maxJump(vieja).toFixed(5),
    puerta_nueva: +maxJump(nueva).toFixed(5),
    escalon_que_INVENTA_la_vieja: +(maxJump(vieja) - natural).toFixed(5),
    escalon_que_INVENTA_la_nueva: +(maxJump(nueva) - natural).toFixed(5),
  },
  voz: { entrada_dBFS: +db(rVozIn).toFixed(2), salida_dBFS: +db(rVozNueva).toFixed(2), ataque_ms: +attackMs?.toFixed(1) },
  fondo_al_final: { vieja_dBFS: +db(rSilVieja).toFixed(1), nueva_dBFS: +db(rSilNueva).toFixed(1) },
}, null, 1));

// Criterios de aceptación
const okClick = maxJump(nueva) <= natural * 1.5;
const okVoz = Math.abs(db(rVozNueva) - db(rVozIn)) < 1.0;
const okSilencio = db(rSilNueva) < -80;
const okAtaque = attackMs != null && attackMs < 15;
console.log("\nsin clics:", okClick, "| voz intacta:", okVoz, "| silencio limpio:", okSilencio, "| ataque rápido:", okAtaque);
process.exit(okClick && okVoz && okSilencio && okAtaque ? 0 : 1);
