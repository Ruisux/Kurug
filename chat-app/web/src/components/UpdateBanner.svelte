<script>
  // Aviso de actualización disponible (solo escritorio). Botón para descargar
  // e instalar, y reiniciar la app.
  import { onMount } from "svelte";
  import { updateState, checkForUpdates, installUpdate } from "../lib/updater.js";

  let dismissed = false;
  $: st = $updateState;

  onMount(() => {
    checkForUpdates();
    // Reintento periódico por si la app queda abierta mucho tiempo.
    const iv = setInterval(checkForUpdates, 6 * 60 * 60 * 1000); // cada 6 h
    return () => clearInterval(iv);
  });
</script>

{#if st.available && !dismissed}
  <div class="upd">
    <i class="ti ti-rocket"></i>
    <div class="txt">
      <b>Actualización disponible</b>
      <span>v{st.version}</span>
    </div>
    {#if st.installing}
      <span class="pct">Actualizando…</span>
    {:else if st.downloading}
      <div class="prog"><div class="bar" style="width:{Math.round(st.progress * 100)}%"></div></div>
      <span class="pct">{Math.round(st.progress * 100)}%</span>
    {:else if st.error}
      <span class="err" title={st.error}>No se pudo: {st.error.slice(0, 80)}</span>
      <button class="go" on:click={installUpdate}>Reintentar</button>
    {:else}
      <button class="go" on:click={installUpdate}>Actualizar</button>
      <button class="later" on:click={() => (dismissed = true)} title="Ahora no" aria-label="Ahora no"><i class="ti ti-x"></i></button>
    {/if}
  </div>
{/if}

<style>
  .upd {
    position: fixed;
    top: 14px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 90;
    display: flex;
    align-items: center;
    gap: 11px;
    max-width: min(94vw, 460px);
    background: var(--pan);
    border: 1px solid var(--shu);
    border-radius: 12px;
    padding: 10px 12px;
    box-shadow: 0 16px 40px var(--shadow);
  }
  .upd > .ti-rocket {
    font-size: 20px;
    color: var(--shu);
    flex: none;
  }
  .txt {
    display: flex;
    flex-direction: column;
    line-height: 1.3;
    min-width: 0;
    flex: 1;
  }
  .txt b { font-size: 13.5px; }
  .txt span { font-size: 11.5px; color: var(--mut); }
  .go {
    flex: none;
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    border-radius: 9px;
    padding: 8px 13px;
    font-size: 13px;
    font-weight: 500;
  }
  .go:hover { background: var(--shu-deep); }
  .later {
    flex: none;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 16px;
  }
  .later:hover { color: var(--shu); }
  .prog {
    flex: 1;
    height: 7px;
    border-radius: 4px;
    background: var(--bd2);
    overflow: hidden;
    max-width: 160px;
  }
  .prog .bar { height: 100%; background: var(--shu); transition: width 0.15s linear; }
  .pct { font-size: 12px; color: var(--mut); font-variant-numeric: tabular-nums; }
  .err { font-size: 12px; color: #c0593b; }
</style>
