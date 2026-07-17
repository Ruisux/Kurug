<script>
  import { token, me } from "../lib/stores.js";
  import { api, ApiError } from "../lib/api.js";
  import Katana from "./Katana.svelte";
  import ThemeToggle from "./ThemeToggle.svelte";
  import PasswordInput from "./PasswordInput.svelte";

  let mode = "login"; // "login" | "register" | "verify" | "forgot" | "reset"
  let error = "";
  let info = "";
  let busy = false;

  // login
  let ident = "";
  // register
  let email = "";
  let username = "";
  let password = "";
  let confirm = "";
  // verify
  let pendingEmail = "";
  let code = "";

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const USER_RE = /^[A-Za-z0-9_]{3,20}$/;

  $: pwLongEnough = password.length >= 8;
  $: pwHasMix = /[A-Za-z]/.test(password) && /\d/.test(password);
  $: pwMatch = confirm.length > 0 && password === confirm;
  $: registerValid =
    EMAIL_RE.test(email) && USER_RE.test(username) && pwLongEnough && pwHasMix && pwMatch;

  async function doLogin() {
    error = "";
    if (!ident.trim() || !password) { error = "Introduce tu usuario/correo y contraseña."; return; }
    busy = true;
    try {
      const { access_token } = await api.login(ident.trim(), password);
      token.set(access_token);
      me.set(await api.me());
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        // No verificado: ir al paso de código (si entró con correo, reenviamos).
        error = "";
        if (ident.includes("@")) {
          pendingEmail = ident.trim();
          mode = "verify";
          info = "Tu correo no está verificado. Te enviamos un código nuevo.";
          try { await api.resendCode(pendingEmail); } catch {}
        } else {
          error = "Tu correo no está verificado. Inicia sesión con tu correo para recibir el código.";
        }
      } else {
        error = e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.";
      }
    } finally {
      busy = false;
    }
  }

  async function doRegister() {
    error = "";
    if (!registerValid) { error = "Revisa los campos marcados."; return; }
    busy = true;
    try {
      await api.register(email.trim(), username.trim(), password);
      pendingEmail = email.trim();
      code = "";
      mode = "verify";
      info = `Te enviamos un código a ${pendingEmail}.`;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.";
    } finally {
      busy = false;
    }
  }

  async function doVerify() {
    error = "";
    if (code.trim().length < 4) { error = "Introduce el código del correo."; return; }
    busy = true;
    try {
      const { access_token } = await api.verifyCode(pendingEmail, code.trim());
      token.set(access_token);
      me.set(await api.me());
    } catch (e) {
      error = e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.";
    } finally {
      busy = false;
    }
  }

  async function resend() {
    error = ""; info = "";
    try {
      await api.resendCode(pendingEmail);
      info = "Código reenviado. Revisa tu correo.";
    } catch {
      error = "No se pudo reenviar el código.";
    }
  }

  // --- Recuperar contraseña ---
  $: resetValid = code.trim().length >= 4 && pwLongEnough && pwHasMix && pwMatch;

  async function doForgot() {
    error = "";
    if (!EMAIL_RE.test(pendingEmail.trim())) { error = "Introduce un correo válido."; return; }
    busy = true;
    try {
      await api.forgotPassword(pendingEmail.trim());
      pendingEmail = pendingEmail.trim();
      code = ""; password = ""; confirm = "";
      mode = "reset";
      info = `Si la cuenta existe, enviamos un código a ${pendingEmail}.`;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.";
    } finally {
      busy = false;
    }
  }

  async function doReset() {
    error = "";
    if (!resetValid) { error = "Revisa el código y la contraseña nueva."; return; }
    busy = true;
    try {
      const { access_token } = await api.resetPassword(pendingEmail, code.trim(), password);
      token.set(access_token); // contraseña cambiada: entra directo
      me.set(await api.me());
    } catch (e) {
      error = e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.";
    } finally {
      busy = false;
    }
  }

  function goForgot() {
    // Si escribió su correo en el login, lo aprovechamos.
    pendingEmail = ident.includes("@") ? ident.trim() : "";
    go("forgot");
  }

  function go(m) {
    mode = m; error = ""; info = "";
    password = ""; confirm = ""; code = ""; // no arrastrar contraseñas entre pantallas
  }
  function onSubmit() {
    if (mode === "login") doLogin();
    else if (mode === "register") doRegister();
    else if (mode === "forgot") doForgot();
    else if (mode === "reset") doReset();
    else doVerify();
  }
</script>

<div class="screen">
  <div class="corner"><ThemeToggle /></div>
  <span class="watermark serif" aria-hidden="true">道</span>

  <form class="card" on:submit|preventDefault={onSubmit}>
    <div class="brand">
      <div class="mark serif">刃</div>
      <div><h1 class="display title">Kurug</h1></div>
    </div>

    <Katana width="100%" height={16} />

    {#if mode === "login"}
      <div class="fields">
        <input placeholder="usuario o correo" autocomplete="username" bind:value={ident} />
        <PasswordInput bind:value={password} placeholder="contraseña" autocomplete="current-password" />
        <button type="button" class="link" on:click={goForgot}>¿Olvidaste tu contraseña?</button>
      </div>

    {:else if mode === "register"}
      <div class="fields">
        <input
          class:bad={email && !EMAIL_RE.test(email)}
          type="email" placeholder="correo electrónico" autocomplete="email" bind:value={email} />
        <input
          class:bad={username && !USER_RE.test(username)}
          placeholder="usuario (para mencionarte: @tu_usuario)" autocomplete="username" bind:value={username} />
        {#if username && !USER_RE.test(username)}
          <small class="hint bad-t">3-20 caracteres: letras, números y _</small>
        {/if}
        <PasswordInput bind:value={password} placeholder="contraseña" autocomplete="new-password" />
        <PasswordInput
          bind:value={confirm} bad={!!confirm && !pwMatch}
          placeholder="confirmar contraseña" autocomplete="new-password" />
        <div class="reqs">
          <span class:ok={pwLongEnough}><i class="ti {pwLongEnough ? 'ti-check' : 'ti-point'}"></i> 8+ caracteres</span>
          <span class:ok={pwHasMix}><i class="ti {pwHasMix ? 'ti-check' : 'ti-point'}"></i> letras y números</span>
          <span class:ok={pwMatch}><i class="ti {pwMatch ? 'ti-check' : 'ti-point'}"></i> coinciden</span>
        </div>
      </div>

    {:else if mode === "forgot"}
      <div class="fields">
        <p class="verify-info">Escribe tu correo y te enviamos un código para crear una contraseña nueva.</p>
        <input type="email" placeholder="correo electrónico" autocomplete="email" bind:value={pendingEmail} />
      </div>

    {:else if mode === "reset"}
      <div class="fields">
        <p class="verify-info">Revisa <b>{pendingEmail}</b>, introduce el código y tu contraseña nueva.</p>
        <input
          class="code" placeholder="------" inputmode="numeric" maxlength="6"
          autocomplete="one-time-code" bind:value={code} />
        <PasswordInput bind:value={password} placeholder="contraseña nueva" autocomplete="new-password" />
        <PasswordInput
          bind:value={confirm} bad={!!confirm && !pwMatch}
          placeholder="confirmar contraseña" autocomplete="new-password" />
        <div class="reqs">
          <span class:ok={pwLongEnough}><i class="ti {pwLongEnough ? 'ti-check' : 'ti-point'}"></i> 8+ caracteres</span>
          <span class:ok={pwHasMix}><i class="ti {pwHasMix ? 'ti-check' : 'ti-point'}"></i> letras y números</span>
          <span class:ok={pwMatch}><i class="ti {pwMatch ? 'ti-check' : 'ti-point'}"></i> coinciden</span>
        </div>
        <button type="button" class="link" on:click={doForgot}>Reenviar código</button>
      </div>

    {:else}
      <div class="fields">
        <p class="verify-info">Revisa <b>{pendingEmail}</b> e introduce el código de 6 dígitos.</p>
        <input
          class="code" placeholder="------" inputmode="numeric" maxlength="6"
          autocomplete="one-time-code" bind:value={code} />
        <button type="button" class="link" on:click={resend}>Reenviar código</button>
      </div>
    {/if}

    {#if error}<p class="error">{error}</p>{/if}
    {#if info}<p class="info">{info}</p>{/if}

    <button
      class="primary" type="submit"
      disabled={busy || (mode === "register" && !registerValid) || (mode === "reset" && !resetValid)}>
      {busy ? "…"
        : mode === "login" ? "Entrar"
        : mode === "register" ? "Crear cuenta"
        : mode === "forgot" ? "Enviar código"
        : mode === "reset" ? "Cambiar contraseña"
        : "Verificar"}
    </button>

    <p class="switch">
      {#if mode === "login"}
        ¿No tienes cuenta? <button type="button" on:click={() => go("register")}>Regístrate</button>
      {:else if mode === "register"}
        ¿Ya tienes cuenta? <button type="button" on:click={() => go("login")}>Entra</button>
      {:else}
        <button type="button" on:click={() => go("login")}>← Volver</button>
      {/if}
    </p>
  </form>
</div>

<style>
  .screen {
    position: relative;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: var(--ink);
  }
  .corner { position: absolute; top: 18px; right: 18px; }
  .watermark {
    position: absolute;
    bottom: -60px;
    right: -10px;
    font-size: 360px;
    color: var(--tx);
    opacity: 0.035;
    pointer-events: none;
    user-select: none;
    line-height: 1;
  }
  .card {
    position: relative;
    width: 380px;
    max-width: 92vw;
    background: var(--pan);
    border: 1px solid var(--bd);
    border-radius: 16px;
    padding: 28px 28px 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    box-shadow: 0 24px 60px var(--shadow);
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .mark {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    border: 1.5px solid var(--gold);
    color: var(--shu);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    flex: none;
  }
  h1 { margin: 0; font-size: 26px; font-weight: 600; letter-spacing: 0.02em; }
  .fields { display: flex; flex-direction: column; gap: 10px; }
  input {
    background: var(--field);
    border: 1px solid var(--bd2);
    border-radius: 10px;
    padding: 11px 13px;
    font-size: 14px;
    outline: none;
    color: var(--tx);
  }
  input:focus { border-color: var(--shu); }
  input.bad { border-color: var(--dnd, #c0593b); }
  .code {
    text-align: center;
    font-size: 22px;
    letter-spacing: 8px;
    font-variant-numeric: tabular-nums;
  }
  .hint { font-size: 11.5px; color: var(--fnt); margin: -4px 0 0; }
  .bad-t { color: #c0593b; }
  .reqs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 11.5px;
    color: var(--fnt);
    margin-top: 2px;
  }
  .reqs span { display: inline-flex; align-items: center; gap: 4px; }
  .reqs span.ok { color: var(--on, #5a9); }
  .reqs i { font-size: 13px; }
  .verify-info { margin: 0; font-size: 13px; color: var(--mut); line-height: 1.5; }
  .verify-info b { color: var(--tx); }
  .primary {
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    border-radius: 10px;
    padding: 12px;
    font-size: 14px;
    font-weight: 500;
  }
  .primary:hover { background: var(--shu-deep); }
  .primary:disabled { opacity: 0.6; }
  .error { margin: 0; color: var(--shu); font-size: 13px; }
  .info { margin: 0; color: var(--mut); font-size: 13px; }
  .link {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--gold);
    font-size: 12.5px;
    padding: 0;
  }
  .link:hover { text-decoration: underline; }
  .switch { margin: 2px 0 0; text-align: center; font-size: 13px; color: var(--mut); }
  .switch button {
    background: none;
    border: none;
    color: var(--gold);
    font-size: 13px;
    padding: 0 2px;
  }
  .switch button:hover { text-decoration: underline; }
</style>
