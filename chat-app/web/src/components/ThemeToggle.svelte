<script>
  import { theme, toggleTheme } from "../lib/theme.js";
</script>

<button
  class="tt"
  on:click={toggleTheme}
  title="Cambiar tema"
  aria-label="Cambiar tema"
>
  {#if $theme === "dark"}
    <i class="ti ti-sun"></i>
  {:else}
    <i class="ti ti-moon"></i>
  {/if}
</button>

<style>
  .tt {
    background: transparent;
    border: 1px solid var(--bd2);
    color: var(--mut);
    width: 32px;
    height: 32px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
  }
  .tt:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
</style>
