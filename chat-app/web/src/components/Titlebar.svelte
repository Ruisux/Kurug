<script>
  // Barra de título personalizada para la app de ESCRITORIO (Electron).
  //
  // La ventana se crea sin marco nativo (frame: false); esta barra la sustituye:
  // zona arrastrable + botones de ventana propios. En el navegador NO se
  // renderiza (no hay ventana que mover).
  //
  // Diseño: logo 刃 + "Kurug" a la izquierda; a la derecha, tres "semáforos"
  // estilo macOS (cerrar rojo, minimizar amarillo, maximizar verde).
  import { isDesktop, windowControls } from "../lib/desktop.js";

  // Se muestra solo en la app de escritorio (Electron), no en el navegador.
  const showBar = isDesktop;

  const minimize = () => windowControls.minimize();
  const toggleMax = () => windowControls.toggleMaximize();
  const close = () => windowControls.close();
</script>

{#if showBar}
  <!-- Arrastrar la barra mueve la ventana (CSS -webkit-app-region: drag). -->
  <div class="titlebar">
    <div class="brand">
      <span class="mark serif">刃</span>
      <span class="name display">Kurug</span>
    </div>

    <div class="lights" role="group" aria-label="Controles de ventana">
      <!-- Orden macOS: cerrar, minimizar, maximizar -->
      <button class="light close" on:click={close} aria-label="Cerrar" title="Cerrar">
        <i class="ti ti-x"></i>
      </button>
      <button class="light min" on:click={minimize} aria-label="Minimizar" title="Minimizar">
        <i class="ti ti-minus"></i>
      </button>
      <button class="light max" on:click={toggleMax} aria-label="Maximizar" title="Maximizar">
        <i class="ti ti-arrows-diagonal"></i>
      </button>
    </div>
  </div>
{/if}

<style>
  .titlebar {
    flex: none;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    background: var(--pan);
    border-bottom: 1px solid var(--bd);
    user-select: none;
    -webkit-user-select: none;
    -webkit-app-region: drag; /* Electron: arrastrar la ventana desde la barra */
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    pointer-events: none; /* que el arrastre no lo capturen textos */
  }
  .mark {
    color: var(--shu);
    font-size: 15px;
    line-height: 1;
  }
  .name {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--tx);
  }
  .lights {
    display: flex;
    align-items: center;
    gap: 8px;
    -webkit-app-region: no-drag; /* Electron: los botones sí son clicables */
  }
  .light {
    width: 13px;
    height: 13px;
    border-radius: 50%;
    border: none;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: transparent; /* el glifo solo se ve al pasar el ratón */
    font-size: 9px;
    line-height: 1;
    cursor: pointer;
    transition: filter 0.12s;
  }
  .light i {
    font-size: 9px;
  }
  .light.close { background: #ff5f57; }
  .light.min { background: #febc2e; }
  .light.max { background: #28c840; }
  .lights:hover .light { color: rgba(0, 0, 0, 0.55); }
  .light:hover { filter: brightness(1.08); }
</style>
