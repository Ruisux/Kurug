<script>
  import Avatar from "./Avatar.svelte";
  import ThemeToggle from "./ThemeToggle.svelte";

  export let me;
  export let onProfile = () => {};
  export let onHome = () => {};
  export let onMusic = () => {};
  export let onAudio = () => {};
  export let homeActive = false;
  export let musicActive = false;
</script>

<nav class="rail">
  <button class="navbtn" class:active={homeActive} on:click={onHome} title="Inicio" aria-label="Inicio">
    <i class="ti ti-home"></i>
  </button>
  <button class="navbtn" class:active={musicActive} on:click={onMusic} title="Sala de música" aria-label="Sala de música">
    <i class="ti ti-disc"></i>
  </button>

  <div class="spacer"></div>

  <button class="navbtn small" on:click={onAudio} title="Ajustes de audio" aria-label="Ajustes de audio">
    <i class="ti ti-settings"></i>
  </button>
  <ThemeToggle />
  <button class="me" on:click={onProfile} title="Tu perfil" aria-label="Tu perfil">
    <Avatar
      name={me.display_name}
      url={me.avatar_url}
      size={38}
      status={me.status}
      ring="var(--rail)"
    />
  </button>
</nav>

<style>
  .rail {
    width: 58px;
    background: var(--rail);
    border-right: 1px solid var(--bd);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 0;
    gap: 10px;
  }
  .navbtn {
    width: 42px;
    height: 42px;
    border-radius: 13px;
    background: var(--pan);
    border: 1px solid var(--bd);
    color: var(--mut);
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: none;
  }
  .navbtn:hover {
    color: var(--tx);
    border-color: var(--shu);
  }
  .navbtn.active {
    background: rgba(var(--shu-rgb), 0.14);
    border-color: var(--bd2);
    color: var(--shu);
  }
  .navbtn.small {
    width: 38px;
    height: 38px;
    border-radius: 11px;
    font-size: 17px;
  }
  .spacer {
    flex: 1;
  }
  .me {
    background: none;
    border: none;
    padding: 0;
    border-radius: 50%;
  }
</style>
