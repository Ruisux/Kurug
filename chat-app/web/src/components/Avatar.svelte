<script>
  import { initials, avatarColor, statusColor } from "../lib/ui.js";
  import { mediaUrl } from "../lib/server.js";

  export let name = "?";
  export let url = null;
  export let size = 34;
  export let status = null; // si se pasa, muestra el punto de estado
  export let ring = "var(--pan)"; // color del borde del punto (a juego con el fondo)

  $: dot = Math.max(9, Math.round(size * 0.3));
</script>

<div class="wrap" style="width:{size}px;height:{size}px">
  {#if url}
    <img src={mediaUrl(url)} alt={name} />
  {:else}
    <div
      class="ini"
      style="background:{avatarColor(name)};font-size:{Math.round(size * 0.4)}px"
    >
      {initials(name)}
    </div>
  {/if}
  {#if status}
    <span
      class="sd"
      style="background:{statusColor(status)};width:{dot}px;height:{dot}px;border-color:{ring}"
    ></span>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
    flex: none;
  }
  img,
  .ini {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    object-fit: cover;
    display: block;
  }
  .ini {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #20180f;
    font-weight: 500;
  }
  .sd {
    position: absolute;
    right: -1px;
    bottom: -1px;
    border-radius: 50%;
    border: 2px solid var(--pan);
  }
</style>
