<script>
  // Audio de voz GLOBAL: se monta una vez a nivel de app y permanece aunque
  // navegues entre canales. Mantiene vivos los streams remotos (los <audio>
  // muted) para que el sonido por Web Audio no se corte al cambiar de vista.
  import { voiceState } from "../lib/voice.js";

  // Solo reasigna si el stream cambió: re-poner el mismo srcObject reinicia
  // el elemento (cortes/parpadeos en cada re-render).
  function srcObject(node, stream) {
    node.srcObject = stream || null;
    return {
      update(s) {
        if (node.srcObject !== (s || null)) node.srcObject = s || null;
      },
      destroy() {
        node.srcObject = null;
      },
    };
  }

  $: peers = Object.values($voiceState.peers);
</script>

{#each peers as p (p.id)}
  {#if p.stream}
    <audio use:srcObject={p.stream} autoplay muted></audio>
  {/if}
{/each}
