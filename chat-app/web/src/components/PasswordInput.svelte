<script>
  // Campo de contraseña con botón para verla/ocultarla (el "ojo").
  // Mismo estilo que los inputs del Login; el botón NO envía el formulario.
  export let value = "";
  export let placeholder = "contraseña";
  export let autocomplete = "current-password";
  export let bad = false;

  let show = false;
</script>

<div class="pw">
  {#if show}
    <input type="text" class:bad {placeholder} {autocomplete} bind:value />
  {:else}
    <input type="password" class:bad {placeholder} {autocomplete} bind:value />
  {/if}
  <button
    type="button"
    class="eye"
    on:click={() => (show = !show)}
    title={show ? "Ocultar contraseña" : "Ver contraseña"}
    aria-label={show ? "Ocultar contraseña" : "Ver contraseña"}
    tabindex="-1"
  >
    <i class="ti {show ? 'ti-eye-off' : 'ti-eye'}"></i>
  </button>
</div>

<style>
  .pw {
    position: relative;
    display: flex;
  }
  input {
    flex: 1;
    min-width: 0;
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 10px;
    padding: 11px 40px 11px 13px; /* hueco a la derecha para el ojo */
    font-size: 14px;
    outline: none;
    color: var(--tx);
  }
  input:focus { border-color: var(--shu); }
  input.bad { border-color: var(--dnd, #c0593b); }
  .eye {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: var(--fnt);
    font-size: 17px;
    border-radius: 8px;
    cursor: pointer;
  }
  .eye:hover { color: var(--shu); }
</style>
