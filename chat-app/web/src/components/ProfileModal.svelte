<script>
  import Avatar from "./Avatar.svelte";
  import { STATUSES } from "../lib/ui.js";
  import { api } from "../lib/api.js";
  import { token, me } from "../lib/stores.js";
  import { activity } from "../lib/desktop.js";
  import { prefs, setPref } from "../lib/prefs.js";

  export let onClose = () => {};
  export let onSaved = () => {};

  const user = $me;
  let nickname = user.nickname || "";
  let bio = user.bio || "";
  let status = user.status || "online";
  let custom = user.custom_status || "";
  let preview = user.avatar_url;
  let selectedFile = null;
  let fileInput;
  let busy = false;
  let error = "";

  // Banner de la tarjeta (imagen ancha 4:1).
  import { mediaUrl } from "../lib/server.js";
  let bannerPreview = user.banner_url ? mediaUrl(user.banner_url) : null;
  let bannerFile = null;
  let bannerRemoved = false;
  let bannerInput;
  function pickBanner(e) {
    const f = e.target.files[0];
    if (!f) return;
    bannerFile = f;
    bannerRemoved = false;
    bannerPreview = URL.createObjectURL(f);
  }
  function clearBanner() {
    bannerFile = null;
    bannerRemoved = true;
    bannerPreview = null;
  }

  function pickFile(e) {
    const f = e.target.files[0];
    if (!f) return;
    selectedFile = f;
    preview = URL.createObjectURL(f);
  }

  async function save() {
    busy = true;
    error = "";
    try {
      if (selectedFile) await api.uploadAvatar(selectedFile);
      if (bannerFile) await api.uploadBanner(bannerFile);
      else if (bannerRemoved) await api.removeBanner();
      // El color de acento se cambia en Apariencia (aquí estaba duplicado).
      const updated = await api.updateMe({
        nickname: nickname.trim() || null,
        bio: bio.trim() || null,
        status,
        custom_status: custom.trim() || null,
      });
      me.set(updated);
      onSaved();
      onClose();
    } catch (e) {
      error = e.message || "No se pudo guardar.";
    } finally {
      busy = false;
    }
  }

  function logout() {
    token.set(null);
    me.set(null);
  }
</script>

<div
  class="overlay"
  on:click={(e) => e.target === e.currentTarget && onClose()}
  on:keydown={(e) => e.key === "Escape" && onClose()}
  role="presentation"
>
  <div class="modal" role="dialog" aria-label="Tu perfil">
    <div class="head">
      <h2 class="display">Tu perfil</h2>
      <button class="x" on:click={onClose} aria-label="Cerrar">
        <i class="ti ti-x"></i>
      </button>
    </div>

    <!-- Banner: se sube como imagen ancha; el avatar se monta encima como en
         la tarjeta de perfil. -->
    <div class="bannerbox">
      <button
        class="bannerimg"
        style={bannerPreview ? `background-image:url(${bannerPreview})` : `--a:${user.accent_color || '#e2553b'}`}
        class:has={!!bannerPreview}
        on:click={() => bannerInput.click()}
        aria-label="Cambiar banner"
      >
        {#if !bannerPreview}<span class="bhint"><i class="ti ti-photo"></i> Añadir banner</span>{/if}
      </button>
      {#if bannerPreview}
        <button class="bclear" on:click={clearBanner} title="Quitar banner" aria-label="Quitar banner"><i class="ti ti-x"></i></button>
      {/if}
      <input type="file" accept="image/*" bind:this={bannerInput} on:change={pickBanner} hidden />
    </div>

    <div class="ident">
      <button class="avbtn" on:click={() => fileInput.click()} aria-label="Cambiar foto">
        <Avatar name={nickname || user.username} url={preview} size={64} />
        <span class="cam"><i class="ti ti-camera"></i></span>
      </button>
      <input
        type="file"
        accept="image/*"
        bind:this={fileInput}
        on:change={pickFile}
        hidden
      />
      <div>
        <div class="uname">@{user.username}</div>
        <div class="hint">Toca la foto para cambiarla</div>
      </div>
    </div>

    <label class="fld">
      <span>Nombre visible</span>
      <input bind:value={nickname} maxlength="32" placeholder={user.username} />
    </label>

    <label class="fld">
      <span>Biografía</span>
      <textarea bind:value={bio} maxlength="280" rows="2" placeholder="Algo sobre ti…"></textarea>
    </label>

    <label class="fld">
      <span>Estado personalizado</span>
      <input bind:value={custom} maxlength="64" placeholder="trabajando, jugando…" />
    </label>

    {#if activity.supported}
      <div class="fld">
        <span>Actividad</span>
        <label class="sharerow">
          <span class="sharelbl"><i class="ti ti-device-gamepad-2"></i> Mostrar el juego</span>
          <button
            type="button" class="sw" class:on={$prefs.shareGameActivity !== false}
            on:click={() => setPref("shareGameActivity", !($prefs.shareGameActivity !== false))}
            role="switch" aria-checked={$prefs.shareGameActivity !== false} aria-label="Compartir juego"
          ><span class="knob"></span></button>
        </label>
        <label class="sharerow">
          <span class="sharelbl"><i class="ti ti-music"></i> Mostrar la música</span>
          <button
            type="button" class="sw" class:on={$prefs.shareMusicActivity !== false}
            on:click={() => setPref("shareMusicActivity", !($prefs.shareMusicActivity !== false))}
            role="switch" aria-checked={$prefs.shareMusicActivity !== false} aria-label="Compartir música"
          ><span class="knob"></span></button>
        </label>
        <small>La app detecta juegos conocidos y la música de Spotify (solo en escritorio).</small>
      </div>
    {/if}

    <div class="fld">
      <span>Disponibilidad</span>
      <div class="statuses">
        {#each STATUSES as s (s.key)}
          <button
            class="st"
            class:on={status === s.key}
            on:click={() => (status = s.key)}
            type="button"
          >
            <span class="dot" style="background:{s.color}"></span>{s.label}
          </button>
        {/each}
      </div>
    </div>

    {#if error}<p class="error">{error}</p>{/if}

    <div class="actions">
      <button class="logout" on:click={logout}>
        <i class="ti ti-logout"></i> Salir
      </button>
      <button class="save" on:click={save} disabled={busy}>
        {busy ? "Guardando…" : "Guardar"}
      </button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
    padding: 20px;
  }
  .modal {
    width: 420px;
    max-width: 100%;
    max-height: calc(90 * var(--vh));
    overflow-y: auto;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 16px;
    padding: 20px 22px 22px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    box-shadow: 0 30px 80px var(--shadow);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h2 {
    margin: 0;
    font-size: 19px;
    font-weight: 600;
  }
  .x {
    background: none;
    border: none;
    color: var(--mut);
    font-size: 19px;
  }
  .x:hover {
    color: var(--tx);
  }
  /* Banner del perfil (subida). */
  .bannerbox {
    position: relative;
    margin-bottom: 12px;
  }
  .bannerimg {
    width: 100%;
    height: 92px;
    border-radius: 12px;
    border: 1px solid var(--bd2);
    background-size: cover;
    background-position: center;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }
  .bannerimg:not(.has) {
    background:
      radial-gradient(130% 150% at 82% -20%, color-mix(in srgb, var(--a) 60%, transparent), transparent 62%),
      linear-gradient(135deg, #3a2016, #241812 72%);
    color: #f0d9c8;
  }
  .bannerimg:hover { border-color: var(--shu); }
  .bhint {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: #f0d9c8;
    background: rgba(0, 0, 0, 0.35);
    padding: 5px 11px;
    border-radius: 999px;
  }
  .bclear {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }
  .bclear:hover { background: var(--shu); color: #1c0f0a; }
  .ident {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .avbtn {
    position: relative;
    background: none;
    border: none;
    padding: 0;
    border-radius: 50%;
  }
  .cam {
    position: absolute;
    right: -2px;
    bottom: -2px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--shu);
    color: #1a0f0b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    border: 2px solid var(--pan);
  }
  .uname {
    font-size: 14px;
    font-weight: 500;
  }
  .hint {
    font-size: 11.5px;
    color: var(--mut);
    margin-top: 2px;
  }
  .fld {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .fld > span {
    font-size: 12px;
    color: var(--mut);
    letter-spacing: 0.02em;
  }
  input,
  textarea {
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 9px;
    padding: 9px 11px;
    font-size: 13.5px;
    outline: none;
    resize: none;
  }
  input:focus,
  textarea:focus {
    border-color: var(--shu);
  }
  .statuses {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .st {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--field);
    border: 1px solid var(--bd);
    border-radius: 9px;
    padding: 9px 11px;
    font-size: 13px;
    color: var(--mut);
  }
  .st.on {
    border-color: var(--shu);
    color: var(--tx);
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
  }
  .error {
    margin: 0;
    color: var(--shu);
    font-size: 13px;
  }
  /* Interruptores de actividad (juego / música), mismo look que Apariencia. */
  .sharerow {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
  }
  .sharelbl {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 13.5px;
    color: var(--tx);
  }
  .sharelbl i {
    color: var(--shu);
    font-size: 15px;
  }
  .sharerow .sw {
    margin-left: auto;
  }
  .fld small {
    color: var(--fnt);
    font-size: 11px;
    display: block;
    margin-top: 2px;
  }
  .sw {
    width: 38px;
    height: 22px;
    flex: none;
    border-radius: 999px;
    background: var(--field);
    border: 1px solid var(--bd2);
    position: relative;
    padding: 0;
    cursor: pointer;
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--mut);
    transition: transform 0.15s, background 0.15s;
  }
  .sw.on {
    background: rgba(var(--shu-rgb), 0.3);
    border-color: var(--shu);
  }
  .sw.on .knob {
    transform: translateX(16px);
    background: var(--shu);
  }
  .actions {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
  }
  .logout {
    background: none;
    border: 1px solid var(--bd2);
    color: var(--mut);
    border-radius: 9px;
    padding: 9px 14px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .logout:hover {
    color: var(--shu);
    border-color: var(--shu);
  }
  .save {
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    border-radius: 9px;
    padding: 9px 20px;
    font-size: 13.5px;
    font-weight: 500;
  }
  .save:hover {
    background: var(--shu-deep);
  }
  .save:disabled {
    opacity: 0.6;
  }
</style>
