<script>
  import { tick, onMount } from "svelte";
  import Avatar from "./Avatar.svelte";
  import VoicePanel from "./VoicePanel.svelte";
  import EmojiPicker from "./EmojiPicker.svelte";
  import GifPicker from "./GifPicker.svelte";
  import { formatTime } from "../lib/ui.js";
  import { jpLabels, channelKanji } from "../lib/appearance.js";
  import { me } from "../lib/stores.js";
  import { api } from "../lib/api.js";
  import { voiceState } from "../lib/voice.js";
  import { mediaUrl } from "../lib/server.js";

  export let header = { kind: "none", name: "—" };
  export let channelId = null;
  export let dmUserId = null;
  export let messages = [];
  export let onSend = () => {};
  export let onDelete = () => {};
  export let onEdit = () => {};
  export let onReact = () => {};
  export let onPin = () => {};
  export let onBack = () => {};
  export let allUsers = []; // para resolver quién reaccionó (tooltip)

  // "rui, ana y tú" — quiénes usaron una reacción, para verlo al pasar el mouse.
  $: userById = new Map(allUsers.map((u) => [u.id, u]));
  function reactedBy(r) {
    const names = (r.users || []).map((id) =>
      id === $me.id ? "tú" : userById.get(id)?.display_name || "alguien",
    );
    if (!names.length) return "";
    // "tú" al final, como habla la gente: "rui, ana y tú".
    names.sort((a, b) => (a === "tú") - (b === "tú"));
    return names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} y ${names.at(-1)}`;
  }

  // Selector de emojis: guardamos a qué mensaje aplica y dónde dibujarlo.
  let pickerFor = null;
  let pickerPos = { left: 0, top: 0 };
  const PICKER_W = 296;
  const PICKER_H = 340;

  function openPicker(m, ev) {
    if (pickerFor === m.id) {
      pickerFor = null;
      return;
    }
    const r = ev.currentTarget.getBoundingClientRect();
    let left = r.right - PICKER_W;
    if (left < 8) left = 8;
    const maxLeft = window.innerWidth - PICKER_W - 8;
    if (left > maxLeft) left = maxLeft;
    // Preferimos abrir hacia arriba; si no hay sitio, hacia abajo.
    let top = r.top - PICKER_H - 6;
    if (top < 8) top = Math.min(r.bottom + 6, window.innerHeight - PICKER_H - 8);
    if (top < 8) top = 8;
    pickerPos = { left, top };
    pickerFor = m.id;
  }
  function react(emoji) {
    if (pickerFor != null) onReact(pickerFor, emoji);
    pickerFor = null;
  }

  $: inThisVoice = $voiceState.active && $voiceState.channelId === channelId;
  $: isChannel = header.kind === "channel";
  $: isDm = header.kind === "dm";

  // --- Búsqueda de mensajes (en el canal o DM actual) ---
  let searchOpen = false;
  let searchQuery = "";
  let searchResults = [];
  let searching = false;
  let searchTimer = null;
  let searchInputEl;
  let flashId = null;

  function toggleSearch() {
    searchOpen = !searchOpen;
    if (searchOpen) {
      tick().then(() => searchInputEl?.focus());
    } else {
      searchQuery = "";
      searchResults = [];
    }
  }
  function onSearchInput() {
    clearTimeout(searchTimer);
    const q = searchQuery.trim();
    if (!q) {
      searchResults = [];
      searching = false;
      return;
    }
    searching = true;
    searchTimer = setTimeout(runSearch, 250);
  }
  async function runSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    try {
      if (header.kind === "channel" && channelId != null)
        searchResults = await api.searchChannel(channelId, q);
      else if (header.kind === "dm" && dmUserId != null)
        searchResults = await api.searchDm(dmUserId, q);
    } catch {
      searchResults = [];
    } finally {
      searching = false;
    }
  }
  async function jumpTo(id) {
    const el = scroller?.querySelector(`[data-mid="${id}"]`);
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      flashId = id;
      setTimeout(() => { if (flashId === id) flashId = null; }, 1600);
      searchOpen = false;
      searchQuery = "";
      searchResults = [];
    } else {
      // El mensaje es más antiguo que el historial cargado (últimos 50).
      flashId = null;
    }
  }
  // Cierra búsqueda/paneles al cambiar de canal/DM.
  $: header, (searchOpen = false), (searchQuery = ""), (searchResults = []),
     (pinsOpen = false), (gifOpen = false);

  let draft = "";
  let scroller;

  // --- Menciones (@usuario / @everyone) ---
  let users = [];
  $: usernameSet = new Set(users.map((u) => u.username.toLowerCase()));
  $: myName = ($me?.username || "").toLowerCase();
  let mentionOpen = false;
  let mentionStart = -1;
  let mentionMatches = [];
  let mentionIndex = 0;

  onMount(async () => {
    try { users = await api.users(); } catch {}
  });

  function closeMention() {
    mentionOpen = false;
    mentionMatches = [];
  }

  function onComposerInput() {
    const el = composerInput;
    if (!el) return;
    const pos = el.selectionStart;
    const m = draft.slice(0, pos).match(/@(\w*)$/);
    if (!m) { closeMention(); return; }
    mentionStart = pos - m[0].length;
    const q = m[1].toLowerCase();
    const list = [];
    if ("everyone".startsWith(q) || "todos".startsWith(q)) list.push({ everyone: true });
    for (const u of users) {
      if (u.username.toLowerCase() === myName) continue; // no te autocompletes a ti mismo
      if (!q || u.username.toLowerCase().startsWith(q) || (u.display_name || "").toLowerCase().includes(q))
        list.push({ user: u });
    }
    mentionMatches = list.slice(0, 6);
    mentionIndex = 0;
    mentionOpen = mentionMatches.length > 0;
  }

  function pickMention(item) {
    const token = item.everyone ? "@everyone" : "@" + item.user.username;
    const before = draft.slice(0, mentionStart);
    const after = draft.slice(composerInput.selectionStart);
    draft = before + token + " " + after;
    const caret = (before + token + " ").length;
    closeMention();
    tick().then(() => {
      composerInput.focus();
      composerInput.selectionStart = composerInput.selectionEnd = caret;
    });
  }

  // Divide el texto en trozos, marcando las menciones válidas (resaltado).
  function contentSegments(text) {
    const parts = [];
    const re = /@(\w+)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parts.push({ t: text.slice(last, m.index) });
      const name = m[1].toLowerCase();
      if (name === "everyone" || name === "todos")
        parts.push({ t: m[0], mention: true, me: true });
      else if (usernameSet.has(name))
        parts.push({ t: "@" + m[1], mention: true, me: name === myName });
      else parts.push({ t: m[0] });
      last = m.index + m[0].length;
    }
    if (last < text.length) parts.push({ t: text.slice(last) });
    return parts;
  }
  let replying = null; // { id, name, content }
  let editingId = null;
  let editDraft = "";

  // Adjuntar imagen / archivo.
  let fileInput;
  let pendingImage = null; // url de imagen o GIF (se manda como image_url)
  let pendingFile = null;  // {url,name,size} de archivo genérico
  let uploading = false;
  let uploadProgress = 0;  // 0..1 (solo archivos grandes)
  let uploadError = "";
  let lightbox = null; // url de la imagen ampliada

  // Picker de emojis/GIFs (mismo botón, dos pestañas) + panel de fijados.
  let gifOpen = false;
  let pickerTab = "emoji"; // "emoji" | "gif"
  let composerInput;       // ref al input para insertar emoji en el cursor
  let mediaBtn;            // ref al botón para anclar el panel
  let mediaPos = { left: 0, bottom: 0 }; // posición fija calculada al abrir
  let pinsOpen = false;

  function toggleMedia() {
    gifOpen = !gifOpen;
    if (gifOpen && mediaBtn) {
      const r = mediaBtn.getBoundingClientRect();
      let left = r.left;
      const maxLeft = window.innerWidth - 340; // panel ~320px de ancho
      if (left > maxLeft) left = maxLeft;
      if (left < 8) left = 8;
      // Fijado al viewport, abriendo HACIA ARRIBA desde el botón.
      mediaPos = { left, bottom: window.innerHeight - r.top + 8 };
    }
  }
  let pins = [];
  let pinsLoading = false;

  async function onPickFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // permite re-subir el mismo archivo
    if (file) await handleFile(file);
  }

  // Sube un File/Blob: las imágenes van inline; el resto, como tarjeta.
  async function handleFile(file) {
    uploadError = "";
    if (file.type && file.type.startsWith("image/")) {
      uploading = true;
      try {
        const { url } = await api.uploadImage(file);
        pendingImage = url;
        pendingFile = null;
      } catch (err) {
        uploadError = err?.message || "No se pudo subir la imagen.";
      } finally {
        uploading = false;
      }
    } else {
      uploading = true;
      uploadProgress = 0;
      try {
        const r = await api.uploadFile(file, (p) => (uploadProgress = p));
        pendingFile = { url: r.url, name: r.name, size: r.size };
        pendingImage = null;
      } catch (err) {
        uploadError = err?.message || "No se pudo subir el archivo.";
      } finally {
        uploading = false;
        uploadProgress = 0;
      }
    }
  }

  // Pegar una imagen del portapapeles directamente en el compositor.
  function onPaste(e) {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const it of items) {
      if (it.type && it.type.startsWith("image/")) {
        const blob = it.getAsFile();
        if (blob) {
          e.preventDefault();
          handleFile(blob);
          return;
        }
      }
    }
  }

  function pickGif(url) {
    pendingImage = url;
    pendingFile = null;
    gifOpen = false;
  }

  // Inserta un emoji en la posición del cursor (sin cerrar el panel).
  function insertEmoji(e) {
    const el = composerInput;
    if (el && el.selectionStart != null) {
      const s = el.selectionStart, en = el.selectionEnd;
      draft = draft.slice(0, s) + e + draft.slice(en);
      tick().then(() => {
        el.focus();
        el.selectionStart = el.selectionEnd = s + e.length;
      });
    } else {
      draft += e;
    }
  }

  async function togglePins() {
    pinsOpen = !pinsOpen;
    if (!pinsOpen) return;
    pinsLoading = true;
    try {
      let raw = [];
      if (isChannel && channelId != null) raw = await api.channelPins(channelId);
      else if (isDm && dmUserId != null) raw = await api.dmPins(dmUserId);
      // Normaliza canal/DM a una forma común para el panel.
      pins = raw.map((p) => ({
        ...p,
        author_display_name: p.author_display_name ?? p.sender_display_name,
        author_avatar_url: p.author_avatar_url ?? p.sender_avatar_url,
      }));
    } catch {
      pins = [];
    } finally {
      pinsLoading = false;
    }
  }
  function unpinFromPanel(id) {
    onPin(id);
    pins = pins.filter((p) => p.id !== id);
  }

  function fmtSize(bytes) {
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }
  function fileLabel(name) {
    const n = name || "archivo";
    return n.length > 38 ? n.slice(0, 22) + "…" + n.slice(-12) : n;
  }

  async function scrollToBottom() {
    await tick();
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }
  $: messages, header, scrollToBottom();

  $: active = header.kind !== "none";
  $: placeholder =
    header.kind === "dm"
      ? `Mensaje a ${header.name}…`
      : header.kind === "channel"
        ? `Escribe en # ${header.name}…`
        : "Selecciona un canal o una persona";

  function startReply(m) {
    replying = { id: m.id, name: m.name, content: m.content };
  }
  function startEdit(m) {
    editingId = m.id;
    editDraft = m.content;
  }
  function saveEdit(m) {
    const c = editDraft.trim();
    if (c && c !== m.content) onEdit(m.id, c);
    editingId = null;
  }
  function editKey(e, m) {
    if (e.key === "Enter") { e.preventDefault(); saveEdit(m); }
    else if (e.key === "Escape") editingId = null;
  }

  function send() {
    const content = draft.trim();
    if (!content && !pendingImage && !pendingFile) return;
    onSend(content, replying?.id ?? null, pendingImage, pendingFile);
    draft = "";
    replying = null;
    pendingImage = null;
    pendingFile = null;
    uploadError = "";
    closeMention();
  }
  function onKey(e) {
    if (mentionOpen && mentionMatches.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); mentionIndex = (mentionIndex + 1) % mentionMatches.length; return; }
      if (e.key === "ArrowUp") { e.preventDefault(); mentionIndex = (mentionIndex - 1 + mentionMatches.length) % mentionMatches.length; return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickMention(mentionMatches[mentionIndex]); return; }
      if (e.key === "Escape") { e.preventDefault(); closeMention(); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<section class="chat">
  <span class="wm serif" aria-hidden="true">道</span>

  <header>
    <button class="back" on:click={onBack} aria-label="Volver"><i class="ti ti-chevron-left"></i></button>
    <div class="title">
      {#if header.kind === "dm"}
        <Avatar name={header.name} url={header.avatar} size={22} />
        <span class="display nm">{header.name}</span>
      {:else}
        <span class="hash">#</span>
        <span class="display nm">{header.name}</span>
        {#if $jpLabels && channelKanji(header.name)}<span class="hrd serif">{channelKanji(header.name)}</span>{/if}
      {/if}
    </div>
    <div class="hdr-actions">
      {#if isChannel || isDm}
        <button class="iconbtn" class:on={pinsOpen} on:click={togglePins} title="Mensajes fijados" aria-label="Mensajes fijados">
          <i class="ti ti-pin"></i>
        </button>
      {/if}
      {#if active}
        <button class="iconbtn" class:on={searchOpen} on:click={toggleSearch} title="Buscar" aria-label="Buscar">
          <i class="ti ti-search"></i>
        </button>
      {/if}
    </div>
  </header>

  {#if searchOpen}
    <div class="searchbar">
      <i class="ti ti-search"></i>
      <input
        bind:this={searchInputEl}
        bind:value={searchQuery}
        on:input={onSearchInput}
        on:keydown={(e) => e.key === "Escape" && toggleSearch()}
        placeholder={header.kind === "dm" ? `Buscar en la conversación con ${header.name}…` : `Buscar en # ${header.name}…`}
      />
      <button class="x" on:click={toggleSearch} aria-label="Cerrar búsqueda"><i class="ti ti-x"></i></button>
    </div>
    {#if searchQuery.trim()}
      <div class="results">
        {#if searching}
          <p class="res-info"><i class="ti ti-loader-2 spin"></i> Buscando…</p>
        {:else if searchResults.length === 0}
          <p class="res-info">Sin resultados para “{searchQuery.trim()}”.</p>
        {:else}
          <p class="res-count">{searchResults.length} resultado{searchResults.length === 1 ? "" : "s"}</p>
          {#each searchResults as r (r.id)}
            <button class="result" on:click={() => jumpTo(r.id)}>
              <span class="r-top">
                <b>{header.kind === "dm" ? r.sender_display_name : r.author_display_name}</b>
                <span class="r-time">{formatTime(r.created_at)}</span>
              </span>
              <span class="r-text">{r.content || "📷 Imagen"}</span>
            </button>
          {/each}
        {/if}
      </div>
    {/if}
  {/if}

  {#if pinsOpen && (isChannel || isDm)}
    <div class="pins-panel">
      {#if pinsLoading}
        <p class="pins-info"><i class="ti ti-loader-2 spin"></i> Cargando fijados…</p>
      {:else if pins.length === 0}
        <p class="pins-info"><i class="ti ti-pin"></i> Aún no hay mensajes fijados.</p>
      {:else}
        <div class="pins-head">{pins.length} mensaje{pins.length === 1 ? "" : "s"} fijado{pins.length === 1 ? "" : "s"}</div>
        {#each pins as p (p.id)}
          <div class="pinrow">
            <Avatar name={p.author_display_name} url={p.author_avatar_url} size={30} />
            <button class="pinbody" on:click={() => jumpTo(p.id)}>
              <span class="pinmeta">
                <b>{p.author_display_name}</b>
                <span class="pintime">{formatTime(p.created_at)}</span>
              </span>
              <span class="pintext">{p.content || (p.image_url ? "📷 Imagen" : (p.file_name || "📎 Archivo"))}</span>
            </button>
            <button class="unpin" on:click={() => unpinFromPanel(p.id)} title="Desfijar" aria-label="Desfijar"><i class="ti ti-pinned-off"></i></button>
          </div>
        {/each}
      {/if}
    </div>
  {/if}

  {#if inThisVoice}
    <VoicePanel />
  {/if}

  <div class="messages" bind:this={scroller}>
    {#each messages as m (m.id)}
      <article class="msg" class:flash={flashId === m.id} data-mid={m.id}>
        <Avatar name={m.name} url={m.avatar} size={36} />
        <div class="body">
          {#if m.replyTo}
            <div class="replyctx">
              <i class="ti ti-arrow-back-up"></i>
              <b>{m.replyTo.name}</b>
              <span class="snip">{m.replyTo.content || "📷 Imagen"}</span>
            </div>
          {/if}
          <div class="meta">
            <span class="author" class:mine={m.mine}>{m.name}</span>
            <span class="time">{formatTime(m.created_at)}</span>
            {#if m.edited}<span class="edited">(editado)</span>{/if}
            {#if m.pinned}<span class="pinmark"><i class="ti ti-pin"></i> fijado</span>{/if}
          </div>
          {#if editingId === m.id}
            <!-- svelte-ignore a11y-autofocus -->
            <input class="editinput" bind:value={editDraft} on:keydown={(e) => editKey(e, m)} autofocus />
            <div class="edithint">Enter para guardar · Esc para cancelar</div>
          {:else}
            {#if m.content}<div class="text">{#each contentSegments(m.content) as s}{#if s.mention}<span class="mention" class:me={s.me}>{s.t}</span>{:else}{s.t}{/if}{/each}</div>{/if}
            {#if m.image}
              <button class="imgwrap" on:click={() => (lightbox = m.image)} aria-label="Ampliar imagen">
                <img src={mediaUrl(m.image)} alt="imagen adjunta" loading="lazy" />
              </button>
            {/if}
            {#if m.file}
              <a class="filechip" href={mediaUrl(m.file.url)} download={m.file.name} target="_blank" rel="noopener">
                <i class="ti ti-file"></i>
                <span class="fmeta">
                  <span class="fname">{fileLabel(m.file.name)}</span>
                  <span class="fsize">{fmtSize(m.file.size)}</span>
                </span>
                <i class="ti ti-download dl"></i>
              </a>
            {/if}
          {/if}

          {#if m.reactions && m.reactions.length}
            <div class="reacts">
              {#each m.reactions as r (r.emoji)}
                <button class="react" class:mine={r.mine} data-tip={reactedBy(r)} on:click={() => onReact(m.id, r.emoji)}>
                  {r.emoji} {r.count}
                </button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="actions">
          <button on:click={() => startReply(m)} title="Responder" aria-label="Responder"><i class="ti ti-arrow-back-up"></i></button>
          {#if isChannel || isDm}
            <button on:click={(e) => openPicker(m, e)} title="Reaccionar" aria-label="Reaccionar"><i class="ti ti-mood-smile"></i></button>
          {/if}
          {#if m.canPin}
            <button on:click={() => onPin(m.id)} title={m.pinned ? "Desfijar" : "Fijar"} aria-label="Fijar"><i class="ti {m.pinned ? 'ti-pinned-off' : 'ti-pin'}"></i></button>
          {/if}
          {#if m.canEdit}
            <button on:click={() => startEdit(m)} title="Editar" aria-label="Editar"><i class="ti ti-pencil"></i></button>
          {/if}
          {#if m.canDelete}
            <button on:click={() => onDelete(m.id)} title="Borrar" aria-label="Borrar"><i class="ti ti-trash"></i></button>
          {/if}
        </div>

      </article>
    {/each}

    {#if messages.length === 0 && active}
      <p class="empty">間 — el silencio antes de la primera palabra.</p>
    {/if}
  </div>

  {#if pickerFor !== null}
    <button class="picker-backdrop" on:click={() => (pickerFor = null)} aria-label="cerrar"></button>
    <div class="picker-float" style="left:{pickerPos.left}px; top:{pickerPos.top}px">
      <EmojiPicker onPick={react} onClose={() => (pickerFor = null)} />
    </div>
  {/if}

  {#if replying}
    <div class="replybar">
      <i class="ti ti-arrow-back-up"></i>
      <span>Respondiendo a <b>{replying.name}</b></span>
      <span class="snip">{replying.content || "📷 Imagen"}</span>
      <button class="x" on:click={() => (replying = null)} aria-label="Cancelar"><i class="ti ti-x"></i></button>
    </div>
  {/if}

  {#if pendingImage || pendingFile || uploading || uploadError}
    <div class="attachbar">
      {#if uploading}
        <span class="att-loading"><i class="ti ti-loader-2 spin"></i> Subiendo…</span>
        {#if uploadProgress > 0}
          <div class="prog"><div class="bar" style="width:{Math.round(uploadProgress * 100)}%"></div></div>
          <span class="pct">{Math.round(uploadProgress * 100)}%</span>
        {/if}
      {:else if pendingImage}
        <img class="att-thumb" src={mediaUrl(pendingImage)} alt="adjunto" />
        <span>Listo para enviar</span>
        <button class="x" on:click={() => (pendingImage = null)} aria-label="Quitar adjunto"><i class="ti ti-x"></i></button>
      {:else if pendingFile}
        <i class="ti ti-file att-fileicon"></i>
        <span class="att-fname">{fileLabel(pendingFile.name)}</span>
        <span class="att-fsize">{fmtSize(pendingFile.size)}</span>
        <button class="x" on:click={() => (pendingFile = null)} aria-label="Quitar archivo"><i class="ti ti-x"></i></button>
      {:else if uploadError}
        <span class="att-error"><i class="ti ti-alert-triangle"></i> {uploadError}</span>
        <button class="x" on:click={() => (uploadError = "")} aria-label="Cerrar"><i class="ti ti-x"></i></button>
      {/if}
    </div>
  {/if}

  {#if gifOpen}
    <button class="picker-backdrop" on:click={() => (gifOpen = false)} aria-label="cerrar"></button>
    <div class="media-float" style="left:{mediaPos.left}px; bottom:{mediaPos.bottom}px">
      <div class="media-tabs">
        <button class:active={pickerTab === "emoji"} on:click={() => (pickerTab = "emoji")}>
          <i class="ti ti-mood-smile"></i> Emoji
        </button>
        <button class:active={pickerTab === "gif"} on:click={() => (pickerTab = "gif")}>
          <i class="ti ti-gif"></i> GIF
        </button>
      </div>
      {#if pickerTab === "emoji"}
        <EmojiPicker onPick={insertEmoji} onClose={() => (gifOpen = false)} />
      {:else}
        <GifPicker onPick={pickGif} onClose={() => (gifOpen = false)} />
      {/if}
    </div>
  {/if}

  <div class="composer">
    <input
      type="file"
      bind:this={fileInput}
      on:change={onPickFile}
      hidden
    />
    <button class="attach" on:click={() => fileInput.click()} disabled={!active || uploading} title="Adjuntar archivo" aria-label="Adjuntar archivo">
      <i class="ti ti-paperclip"></i>
    </button>
    {#if isChannel || header.kind === "dm"}
      <button class="attach gif" class:on={gifOpen} bind:this={mediaBtn} on:click={toggleMedia} disabled={!active} title="Emojis y GIFs" aria-label="Emojis y GIFs">
        <i class="ti ti-mood-smile"></i>
      </button>
    {/if}
    {#if mentionOpen}
      <div class="mention-pop">
        {#each mentionMatches as item, i (item.everyone ? "@everyone" : item.user.id)}
          <button class="mention-item" class:active={i === mentionIndex} on:click={() => pickMention(item)}>
            {#if item.everyone}
              <span class="mention-ava all"><i class="ti ti-users"></i></span>
              <span class="mention-name">@everyone</span>
              <span class="mention-sub">notifica a todos</span>
            {:else}
              <Avatar name={item.user.display_name} url={item.user.avatar_url} size={22} />
              <span class="mention-name">{item.user.display_name}</span>
              <span class="mention-sub">@{item.user.username}</span>
            {/if}
          </button>
        {/each}
      </div>
    {/if}
    <input
      {placeholder}
      bind:this={composerInput}
      bind:value={draft}
      on:keydown={onKey}
      on:input={onComposerInput}
      on:paste={onPaste}
      disabled={!active}
    />
    <button class="send" on:click={send} disabled={!active || uploading} aria-label="Enviar">
      <i class="ti ti-arrow-up"></i>
    </button>
  </div>
</section>

{#if lightbox}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="lightbox" on:click={() => (lightbox = null)}>
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <img src={mediaUrl(lightbox)} alt="imagen ampliada" on:click|stopPropagation />
    <button class="lb-close" on:click={() => (lightbox = null)} aria-label="Cerrar"><i class="ti ti-x"></i></button>
  </div>
{/if}

<style>
  .chat {
    flex: 1;
    min-width: 0;
    background: var(--ink);
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
  }
  .wm {
    position: absolute;
    right: -20px;
    bottom: -90px;
    /* Más grande para que se aprecie, pero sigue muy sutil (baja opacidad). */
    font-size: clamp(320px, 52vh, 520px);
    color: var(--tx);
    opacity: 0.05;
    pointer-events: none;
    user-select: none;
    line-height: 1;
  }
  header {
    padding: 12px 18px;
    border-bottom: 1px solid var(--bd);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .title {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .back {
    display: none; /* solo en móvil */
    background: none;
    border: none;
    color: var(--mut);
    font-size: 22px;
    padding: 0 4px 0 0;
    flex: none;
    align-items: center;
  }
  .back:hover {
    color: var(--shu);
  }
  @media (max-width: 640px) {
    .back {
      display: flex;
    }
  }
  .hdr-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: none;
  }
  .iconbtn {
    width: 32px;
    height: 32px;
    border-radius: 9px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
  }
  .iconbtn:hover,
  .iconbtn.on {
    color: var(--shu);
    border-color: var(--shu);
  }
  .searchbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 16px;
    border-bottom: 1px solid var(--bd);
    color: var(--fnt);
  }
  .searchbar input {
    flex: 1;
    min-width: 0;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 9px;
    padding: 8px 12px;
    font-size: 13.5px;
    outline: none;
    color: var(--tx);
  }
  .searchbar input:focus {
    border-color: var(--shu);
  }
  .searchbar .x {
    background: none;
    border: none;
    color: var(--mut);
    font-size: 16px;
    flex: none;
  }
  .searchbar .x:hover {
    color: var(--shu);
  }
  .results {
    max-height: 46%;
    overflow-y: auto;
    border-bottom: 1px solid var(--bd);
    background: var(--ink);
    z-index: 2;
  }
  .res-info,
  .res-count {
    padding: 10px 16px;
    font-size: 12px;
    color: var(--fnt);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .res-count {
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--bd);
  }
  .result {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-bottom: 1px solid var(--bd);
    padding: 9px 16px;
    cursor: pointer;
  }
  .result:hover {
    background: var(--hover);
  }
  .r-top {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .r-top b {
    font-size: 13px;
    font-weight: 500;
    color: var(--tx);
  }
  .r-time {
    font-size: 10.5px;
    color: var(--fnt);
  }
  .r-text {
    font-size: 13px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hash {
    color: var(--fnt);
    font-size: 17px;
  }
  .nm {
    font-size: 16px;
  }
  .hrd {
    font-size: 12px;
    color: var(--mut);
    margin-left: 2px;
  }
  .messages {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 14px 0;
    z-index: 1;
  }
  .msg {
    display: flex;
    gap: 11px;
    padding: 6px 18px;
    position: relative;
  }
  .msg:hover {
    background: rgba(255, 255, 255, 0.015);
  }
  .msg.flash {
    animation: flash 1.6s ease-out;
  }
  @keyframes flash {
    0%, 35% { background: rgba(var(--shu-rgb), 0.22); }
    100% { background: transparent; }
  }
  .body {
    min-width: 0;
    flex: 1;
  }
  .replyctx {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11.5px;
    color: var(--mut);
    margin-bottom: 2px;
    border-left: 2px solid var(--bd2);
    padding-left: 7px;
  }
  .replyctx b {
    color: var(--shu);
    font-weight: 500;
  }
  .replyctx .snip,
  .replybar .snip {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    opacity: 0.85;
  }
  .meta {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .author {
    font-size: 13.5px;
    font-weight: 500;
  }
  .author.mine {
    color: var(--shu);
  }
  .time {
    font-size: 11px;
    color: var(--fnt);
  }
  .edited {
    font-size: 11px;
    color: var(--fnt);
    font-style: italic;
  }
  .text {
    font-size: 14px;
    color: var(--tx);
    line-height: 1.55;
    margin-top: 1px;
    word-break: break-word;
    white-space: pre-wrap;
  }
  .imgwrap {
    display: block;
    margin-top: 5px;
    padding: 0;
    background: none;
    border: 1px solid var(--bd2);
    border-radius: 12px;
    overflow: hidden;
    cursor: zoom-in;
    line-height: 0;
    max-width: 380px;
  }
  .imgwrap img {
    display: block;
    max-width: 100%;
    max-height: 320px;
    object-fit: cover;
  }
  .imgwrap:hover {
    border-color: var(--shu);
  }
  .editinput {
    width: 100%;
    background: var(--field);
    border: 1px solid var(--shu);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 14px;
    outline: none;
    margin-top: 2px;
  }
  .edithint {
    font-size: 10.5px;
    color: var(--fnt);
    margin-top: 3px;
  }
  .actions {
    position: absolute;
    right: 12px;
    top: 6px;
    display: none;
    gap: 5px;
  }
  .msg:hover .actions {
    display: flex;
  }
  .actions button {
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    width: 26px;
    height: 26px;
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }
  .actions button:hover {
    color: var(--shu);
    border-color: var(--shu);
  }
  .reacts {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 5px;
  }
  /* Tooltip con quiénes reaccionaron (al mantener el mouse encima). */
  .react[data-tip]:not([data-tip=""]):hover::after {
    content: attr(data-tip);
    position: absolute;
    left: 50%;
    bottom: calc(100% + 7px);
    transform: translateX(-50%);
    white-space: nowrap;
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    background: var(--pan);
    color: var(--tx);
    border: 1px solid var(--bd2);
    border-radius: 9px;
    padding: 5px 10px;
    font-size: 11.5px;
    box-shadow: 0 8px 22px var(--shadow);
    pointer-events: none;
    z-index: 30;
  }
  .react {
    position: relative;
    display: flex;
    align-items: center;
    gap: 4px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 999px;
    padding: 1px 9px;
    font-size: 12px;
    color: var(--tx);
    line-height: 1.6;
  }
  .react:hover {
    border-color: var(--shu);
  }
  .react.mine {
    background: rgba(var(--shu-rgb), 0.16);
    border-color: var(--shu);
  }
  .picker-float {
    position: fixed;
    z-index: 50;
  }
  .picker-backdrop {
    position: fixed;
    inset: 0;
    z-index: 49;
    background: none;
    border: none;
  }
  .empty {
    text-align: center;
    color: var(--fnt);
    font-size: 13px;
    margin-top: 28px;
  }
  .replybar {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 7px 16px;
    border-top: 1px solid var(--bd);
    font-size: 12px;
    color: var(--mut);
    background: rgba(var(--shu-rgb), 0.06);
  }
  .replybar b {
    color: var(--shu);
    font-weight: 500;
  }
  .replybar .x {
    margin-left: auto;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 15px;
    flex: none;
  }
  .replybar .x:hover {
    color: var(--shu);
  }
  .attachbar {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 16px;
    border-top: 1px solid var(--bd);
    font-size: 12px;
    color: var(--mut);
    background: rgba(var(--shu-rgb), 0.06);
  }
  .att-thumb {
    width: 34px;
    height: 34px;
    border-radius: 7px;
    object-fit: cover;
    border: 1px solid var(--bd2);
  }
  .attachbar .x {
    margin-left: auto;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 15px;
  }
  .attachbar .x:hover {
    color: var(--shu);
  }
  .att-error {
    color: #c0593b;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .att-loading {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .prog {
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: var(--bd2);
    overflow: hidden;
    max-width: 240px;
  }
  .prog .bar {
    height: 100%;
    background: var(--shu);
    transition: width 0.15s linear;
  }
  .pct {
    font-variant-numeric: tabular-nums;
    color: var(--mut);
  }
  .att-fileicon {
    font-size: 18px;
    color: var(--shu);
  }
  .att-fname {
    color: var(--tx);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .att-fsize {
    color: var(--fnt);
  }
  /* Indicador de mensaje fijado */
  .pinmark {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10.5px;
    color: var(--shu);
  }
  /* Tarjeta de archivo adjunto en el mensaje */
  .filechip {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-top: 6px;
    padding: 9px 12px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 11px;
    text-decoration: none;
    color: var(--tx);
    max-width: 320px;
  }
  .filechip:hover {
    border-color: var(--shu);
  }
  .filechip > .ti-file {
    font-size: 22px;
    color: var(--shu);
    flex: none;
  }
  .filechip .fmeta {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.3;
  }
  .filechip .fname {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .filechip .fsize {
    font-size: 11px;
    color: var(--fnt);
  }
  .filechip .dl {
    margin-left: auto;
    font-size: 16px;
    color: var(--mut);
    flex: none;
  }
  .filechip:hover .dl {
    color: var(--shu);
  }
  /* Panel de mensajes fijados */
  .pins-panel {
    max-height: 52%;
    overflow-y: auto;
    border-bottom: 1px solid var(--bd);
    background: var(--ink);
    z-index: 2;
  }
  .pins-info {
    padding: 18px 16px;
    font-size: 13px;
    color: var(--mut);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
  }
  .pins-head {
    padding: 9px 16px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--fnt);
    border-bottom: 1px solid var(--bd);
  }
  .pinrow {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 10px;
    padding: 8px 12px 8px 16px;
    border-bottom: 1px solid var(--bd);
  }
  .pinrow:hover {
    background: var(--hover);
  }
  .pinbody {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    text-align: left;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
  }
  .pinmeta {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .pinmeta b {
    font-size: 13px;
    font-weight: 500;
    color: var(--tx);
  }
  .pintime {
    font-size: 10.5px;
    color: var(--fnt);
  }
  .pintext {
    font-size: 13px;
    color: var(--mut);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .unpin {
    flex: none;
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }
  .unpin:hover {
    color: var(--shu);
    border-color: var(--shu);
  }
  /* Float del picker emoji/GIF: fijo al viewport, sobre el botón. */
  .media-float {
    position: fixed;
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .media-tabs {
    display: flex;
    gap: 4px;
    align-self: flex-start;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 10px;
    padding: 3px;
    box-shadow: 0 8px 22px var(--shadow);
  }
  .media-tabs button {
    display: flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    color: var(--mut);
    font-size: 12.5px;
    padding: 5px 12px;
    border-radius: 7px;
  }
  .media-tabs button:hover {
    color: var(--tx);
  }
  .media-tabs button.active {
    color: var(--shu);
    background: rgba(var(--shu-rgb), 0.12);
  }
  .attach.gif.on {
    color: var(--shu);
    border-color: var(--shu);
  }
  /* Mención dentro de un mensaje */
  .mention {
    color: var(--shu);
    background: rgba(var(--shu-rgb), 0.12);
    border-radius: 4px;
    padding: 0 3px;
    font-weight: 500;
  }
  .mention.me {
    background: rgba(var(--shu-rgb), 0.22);
  }
  /* Autocompletado de menciones sobre el compositor */
  .mention-pop {
    position: absolute;
    left: 16px;
    bottom: 70px;
    z-index: 45;
    width: min(300px, 80vw);
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 12px;
    box-shadow: 0 14px 38px var(--shadow);
    overflow: hidden;
    padding: 4px;
  }
  .mention-item {
    display: flex;
    align-items: center;
    gap: 9px;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-radius: 8px;
    padding: 6px 8px;
    color: var(--tx);
    cursor: pointer;
  }
  .mention-item.active,
  .mention-item:hover {
    background: var(--hover);
  }
  .mention-name {
    font-size: 13px;
    font-weight: 500;
  }
  .mention-sub {
    font-size: 11.5px;
    color: var(--fnt);
    margin-left: auto;
  }
  .mention-ava {
    width: 22px;
    height: 22px;
    flex: none;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(var(--shu-rgb), 0.18);
    color: var(--shu);
    font-size: 13px;
  }
  .spin {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .composer {
    padding: 12px 16px;
    border-top: 1px solid var(--bd);
    display: flex;
    gap: 9px;
    align-items: center;
    z-index: 1;
  }
  .attach {
    width: 40px;
    height: 40px;
    border-radius: 11px;
    background: var(--pan);
    border: 1px solid var(--bd2);
    color: var(--mut);
    font-size: 19px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: none;
  }
  .attach:hover:not(:disabled) {
    color: var(--shu);
    border-color: var(--shu);
  }
  .attach:disabled {
    opacity: 0.5;
  }
  .composer input {
    flex: 1;
    min-width: 0;
    background: var(--pan);
    border: 1px solid var(--bd2);
    border-radius: 11px;
    padding: 11px 14px;
    font-size: 14px;
    outline: none;
  }
  .composer input:focus {
    border-color: var(--shu);
  }
  .send {
    width: 40px;
    height: 40px;
    border-radius: 11px;
    background: var(--shu);
    color: #1a0f0b;
    border: none;
    font-size: 19px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: none;
  }
  .send:hover {
    background: var(--shu-deep);
  }
  .send:disabled {
    opacity: 0.5;
  }
  .lightbox {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgba(0, 0, 0, 0.82);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px;
    cursor: zoom-out;
  }
  .lightbox img {
    max-width: 92vw;
    max-height: 92vh;
    border-radius: 10px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
    cursor: default;
  }
  .lb-close {
    position: fixed;
    top: 18px;
    right: 22px;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.12);
    border: none;
    color: #fff;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .lb-close:hover {
    background: rgba(255, 255, 255, 0.25);
  }
</style>
