<script>
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { token, me } from "../lib/stores.js";
  import { api } from "../lib/api.js";
  import { chatSocket, presenceSocket } from "../lib/realtime.js";
  import { initNotifications, notify } from "../lib/notify.js";
  import { playSound } from "../lib/sounds.js";
  import { applyShortcuts } from "../lib/shortcuts.js";
  import { connectMusic, disconnectMusic, musicChannelId } from "../lib/music.js";
  import { joinVoice, voiceState } from "../lib/voice.js";

  import Rail from "./Rail.svelte";
  import ChannelList from "./ChannelList.svelte";
  import ChatView from "./ChatView.svelte";
  import MusicRoom from "./MusicRoom.svelte";
  import PresencePanel from "./PresencePanel.svelte";
  import ProfileModal from "./ProfileModal.svelte";
  import AudioSettings from "./AudioSettings.svelte";
  import VoiceAudio from "./VoiceAudio.svelte";
  import MiniBar from "./MiniBar.svelte";
  import UpdateBanner from "./UpdateBanner.svelte";

  let channels = [];
  let dmConvos = [];
  let online = [];
  let voiceByChannel = {}; // channel_id -> [{id, display_name, avatar_url}]
  let prevVoiceCid = null; // para avisar al WS al entrar/salir de una sala de voz
  let view = { kind: "none" }; // {kind:'channel', id} | {kind:'dm', user}
  let messages = [];
  let showProfile = false;
  let showAudio = false;

  let chatWs = null;
  let presWs = null;

  // En móvil solo cabe un panel: "list" (rail + canales) o "chat" (conversación).
  let mobilePane = "list";
  function backToList() {
    mobilePane = "list";
  }

  const meUser = $me;

  // --- No leídos por canal ---
  // lastRead: último id de mensaje visto por canal (persistido en localStorage).
  // unread: contador en vivo por canal (en memoria, reactivo).
  let unread = {};
  const LASTREAD_KEY = "kurug-lastread";
  let lastRead = loadLastRead();

  function loadLastRead() {
    try {
      return JSON.parse(localStorage.getItem(LASTREAD_KEY)) || {};
    } catch {
      return {};
    }
  }
  function saveLastRead() {
    try {
      localStorage.setItem(LASTREAD_KEY, JSON.stringify(lastRead));
    } catch {}
  }
  function markRead(channelId, upToId) {
    if (upToId != null && (lastRead[channelId] || 0) < upToId) {
      lastRead[channelId] = upToId;
      saveLastRead();
    }
    if (unread[channelId]) {
      unread = { ...unread, [channelId]: 0 };
    }
  }

  // --- normalización: canal y DM se renderizan con la misma forma ---
  function normChannel(m) {
    return {
      id: m.id,
      content: m.content,
      created_at: m.created_at,
      name: m.author_display_name,
      avatar: m.author_avatar_url,
      mine: m.author_username === meUser.username,
      canDelete: m.author_username === meUser.username || meUser.is_admin,
      canEdit: m.author_username === meUser.username,
      canPin: m.author_username === meUser.username || meUser.is_admin,
      image: m.image_url || null,
      file: m.file_url ? { url: m.file_url, name: m.file_name, size: m.file_size } : null,
      pinned: !!m.pinned_at,
      edited: !!m.edited_at,
      replyTo: m.reply_to
        ? { name: m.reply_to.author_display_name, content: m.reply_to.content }
        : null,
      reactions: normReactions(m.reactions),
    };
  }
  function normDm(m) {
    return {
      id: m.id,
      content: m.content,
      created_at: m.created_at,
      name: m.sender_display_name,
      avatar: m.sender_avatar_url,
      mine: m.sender_id === meUser.id,
      canDelete: m.sender_id === meUser.id,
      canEdit: m.sender_id === meUser.id,
      canPin: true, // cualquiera de los dos puede fijar en su DM
      image: m.image_url || null,
      file: m.file_url ? { url: m.file_url, name: m.file_name, size: m.file_size } : null,
      pinned: !!m.pinned_at,
      edited: !!m.edited_at,
      replyTo: m.reply_to
        ? { name: m.reply_to.author_display_name, content: m.reply_to.content }
        : null,
      reactions: normReactions(m.reactions),
    };
  }
  function normReactions(list) {
    return (list || []).map((r) => ({
      emoji: r.emoji,
      count: r.count,
      mine: (r.users || []).includes(meUser.id),
    }));
  }

  $: header =
    view.kind === "channel"
      ? { kind: "channel", name: channels.find((c) => c.id === view.id)?.name ?? "—" }
      : view.kind === "dm"
        ? { kind: "dm", name: view.user.display_name, avatar: view.user.avatar_url }
        : { kind: "none", name: "—" };

  $: currentChannelId = view.kind === "channel" ? view.id : null;
  $: currentDmUserId = view.kind === "dm" ? view.user.id : null;
  $: isMusicChannel =
    view.kind === "channel" && !!channels.find((c) => c.id === view.id)?.is_music;
  // La música suena en la VOZ de "general" (canal donde se conecta el bot).
  $: voiceChannelId = (channels.find((c) => c.name === "general" && !c.is_music)
    || channels.find((c) => !c.is_music) || {}).id ?? null;

  // Avisar al server (WS de presencia) en qué sala de voz estoy, para que el
  // resto vea "quién está en cada canal de voz" antes de entrar.
  $: {
    const cid = $voiceState.active ? $voiceState.channelId : null;
    if (cid !== prevVoiceCid) {
      if (cid != null) presWs?.send({ type: "voice_join", channel_id: cid });
      else presWs?.send({ type: "voice_leave" });
      prevVoiceCid = cid;
    }
  }

  onMount(async () => {
    try {
      channels = await api.channels();
      dmConvos = await api.dmConversations();
    } catch {}
    // Sembrar contadores de no leídos según lo último leído (localStorage).
    try {
      unread = await api.unreadCounts(lastRead);
    } catch {}
    presWs = presenceSocket(get(token), handlePresence);
    initNotifications();
    // Conexión de música global: el estado persiste por toda la app.
    const musicCh = channels.find((c) => c.is_music);
    if (musicCh) connectMusic(musicCh.id);
    if (channels.length) {
      const first = channels.find((c) => c.kind !== "voice" && !c.is_music)
        || channels.find((c) => c.kind !== "voice") || channels[0];
      openChannel(first.id);
    }
    // En móvil arrancamos mostrando la lista, no la conversación.
    if (window.innerWidth <= 640) mobilePane = "list";
    // Atajos de teclado (silenciar/ensordecer).
    applyShortcuts();
  });

  onDestroy(() => {
    chatWs?.close();
    presWs?.close();
    disconnectMusic();
  });

  async function openChannel(id) {
    chatWs?.close();
    chatWs = null;
    view = { kind: "channel", id };
    mobilePane = "chat";
    try {
      messages = (await api.messages(id)).map(normChannel);
    } catch {
      messages = [];
    }
    // Al abrir un canal, lo damos por leído hasta su último mensaje.
    const lastId = messages.length ? messages[messages.length - 1].id : lastRead[id];
    markRead(id, lastId);
    chatWs = chatSocket(id, get(token), handleChat);
  }

  async function openDm(user) {
    chatWs?.close();
    chatWs = null;
    view = { kind: "dm", user };
    mobilePane = "chat";
    try {
      messages = (await api.dms(user.id)).map(normDm);
    } catch {
      messages = [];
    }
  }

  function handleChat(m) {
    if (m.type === "deleted") {
      messages = messages.filter((x) => x.id !== m.id);
    } else if (m.type === "edited") {
      messages = messages.map((x) =>
        x.id === m.id ? { ...x, content: m.content, edited: true } : x,
      );
    } else if (m.type === "reactions") {
      messages = messages.map((x) =>
        x.id === m.id ? { ...x, reactions: normReactions(m.reactions) } : x,
      );
    } else if (m.type === "pinned") {
      messages = messages.map((x) =>
        x.id === m.id ? { ...x, pinned: !!m.pinned_at } : x,
      );
    } else if (m.type === "message" && view.kind === "channel" && m.channel_id === view.id) {
      messages = [...messages, normChannel(m)];
      // Estás viéndolo y con foco: márcalo leído. La notificación/sonido los
      // gestiona channel_activity (cubre todos los canales sin duplicar).
      if (document.hasFocus()) markRead(m.channel_id, m.id);
    }
  }

  function handlePresence(evt) {
    if (evt.type === "channel_activity") {
      // Aviso global: mensaje nuevo en algún canal -> no leídos + notificaciones.
      const cid = evt.channel_id;
      const isActive = view.kind === "channel" && view.id === cid;
      const focused = document.hasFocus();
      const fromMe = evt.author_id === meUser.id;
      const mentioned =
        !fromMe && (evt.mention_everyone || (evt.mentions || []).includes(meUser.id));

      if (isActive && focused) {
        markRead(cid, evt.message_id);
      } else if (!fromMe) {
        if (!isActive) unread = { ...unread, [cid]: (unread[cid] || 0) + 1 };
        const chName = channels.find((c) => c.id === cid)?.name ?? "canal";
        if (mentioned) {
          // Mención: prioridad alta, suena aunque tengas la ventana enfocada.
          playSound("mention");
          notify(`${evt.author_display_name} te mencionó en #${chName}`, evt.content, {
            priority: true,
            tag: `mention-${cid}`,
          });
        } else if (!focused) {
          playSound("notify");
          notify(`#${chName}`, `${evt.author_display_name}: ${evt.content}`, {
            tag: `ch-${cid}`,
          });
        }
      }
      return;
    }
    if (evt.type === "presence_snapshot") {
      online = evt.users;
      voiceByChannel = evt.voice || {};
    } else if (evt.type === "presence_update") {
      online = [...online.filter((u) => u.id !== evt.user.id), evt.user];
    } else if (evt.type === "presence_offline") {
      online = online.filter((u) => u.id !== evt.user_id);
    } else if (evt.type === "voice_presence") {
      // Mapa de ocupación de las salas de voz (claves = channel_id como texto).
      voiceByChannel = evt.by_channel || {};
    } else if (evt.type === "dm_deleted") {
      messages = messages.filter((x) => x.id !== evt.id);
    } else if (evt.type === "dm_edited") {
      messages = messages.map((x) =>
        x.id === evt.id ? { ...x, content: evt.content, edited: true } : x,
      );
    } else if (evt.type === "dm_reactions") {
      messages = messages.map((x) =>
        x.id === evt.id ? { ...x, reactions: normReactions(evt.reactions) } : x,
      );
    } else if (evt.type === "dm_pinned") {
      messages = messages.map((x) =>
        x.id === evt.id ? { ...x, pinned: !!evt.pinned_at } : x,
      );
    } else if (evt.type === "dm") {
      const m = evt.message;
      const partner = m.sender_id === meUser.id ? m.recipient_id : m.sender_id;
      if (view.kind === "dm" && view.user.id === partner) {
        messages = [...messages, normDm(m)];
      }
      if (m.sender_id !== meUser.id) {
        const viewingThis = view.kind === "dm" && view.user.id === partner;
        if (!(viewingThis && document.hasFocus())) {
          playSound("notify");
          notify(m.sender_display_name, m.content, { tag: `dm-${partner}` });
        }
      }
      refreshConvos();
    }
  }

  async function refreshConvos() {
    try {
      dmConvos = await api.dmConversations();
    } catch {}
  }

  function onSend(content, replyTo = null, imageUrl = null, file = null) {
    if (view.kind === "channel")
      chatWs?.send({ content, reply_to: replyTo, image_url: imageUrl, file });
    else if (view.kind === "dm")
      presWs?.send({ type: "dm", to: view.user.id, content, reply_to: replyTo, image_url: imageUrl, file });
  }

  function onDelete(id) {
    if (view.kind === "channel") chatWs?.send({ type: "delete", id });
    else if (view.kind === "dm") presWs?.send({ type: "dm_delete", id });
  }

  function onPin(id) {
    if (view.kind === "channel") chatWs?.send({ type: "pin", id });
    else if (view.kind === "dm") presWs?.send({ type: "dm_pin", id });
  }

  function onEdit(id, content) {
    if (view.kind === "channel") chatWs?.send({ type: "edit", id, content });
    else if (view.kind === "dm") presWs?.send({ type: "dm_edit", id, content });
  }

  function onReact(id, emoji) {
    if (view.kind === "channel") chatWs?.send({ type: "react", id, emoji });
    else if (view.kind === "dm") presWs?.send({ type: "dm_react", id, emoji });
  }

  async function createChannel(name, kind = "text") {
    try {
      const c = await api.createChannel(name, kind);
      // El backend asigna position al final; respetamos el orden que devuelve.
      channels = [...channels, c].sort((a, b) => (a.position - b.position) || a.name.localeCompare(b.name));
      if (kind === "voice") joinVoice(c.id); // un canal de voz se "abre" uniéndote
      else openChannel(c.id);
    } catch {}
  }

  // Seleccionar un canal de VOZ = unirse a su sala (no abre chat).
  function selectVoice(id) {
    joinVoice(id);
  }

  // Reordena de forma optimista y persiste el nuevo orden en el server.
  async function reorderChannels(orderedIds) {
    const pos = new Map(orderedIds.map((id, i) => [id, i]));
    channels = [...channels].sort(
      (a, b) => (pos.get(a.id) ?? 1e9) - (pos.get(b.id) ?? 1e9),
    );
    try {
      await api.reorderChannels(orderedIds);
    } catch {
      // Si falla, recargamos el orden real del server.
      try { channels = await api.channels(); } catch {}
    }
  }

  async function deleteChannel(id) {
    try {
      await api.deleteChannel(id);
      channels = channels.filter((c) => c.id !== id);
      if (view.kind === "channel" && view.id === id) {
        if (channels.length) openChannel(channels[0].id);
        else {
          view = { kind: "none" };
          messages = [];
        }
      }
    } catch {}
  }

  function syncProfileLive() {
    presWs?.send({ type: "sync_profile" });
  }
</script>

<div class="app" class:show-chat={mobilePane === "chat"}>
  <div class="side">
    <Rail
      me={$me}
      homeActive={view.kind === "channel" && !isMusicChannel}
      musicActive={isMusicChannel}
      onProfile={() => (showProfile = true)}
      onAudio={() => (showAudio = true)}
      onHome={() => { const c = channels.find((x) => x.kind !== "voice" && !x.is_music) || channels.find((x) => x.kind !== "voice") || channels[0]; if (c) openChannel(c.id); }}
      onMusic={() => $musicChannelId != null && openChannel($musicChannelId)}
    />
    <ChannelList
      {channels}
      {currentChannelId}
      {currentDmUserId}
      {unread}
      dms={dmConvos}
      isAdmin={$me.is_admin}
      voiceMembers={voiceByChannel}
      onSelectChannel={openChannel}
      onSelectVoice={selectVoice}
      onSelectDm={openDm}
      onCreate={createChannel}
      onDeleteChannel={deleteChannel}
      onReorder={reorderChannels}
    />
  </div>
  <div class="main">
    {#if isMusicChannel}
      <MusicRoom {voiceChannelId} onBack={backToList} />
    {:else}
      <ChatView {header} channelId={currentChannelId} dmUserId={currentDmUserId} {messages} {onSend} {onDelete} {onEdit} {onReact} {onPin} onBack={backToList} />
    {/if}
  </div>
  <div class="aside-wrap">
    <PresencePanel {online} onSelectUser={openDm} />
  </div>
</div>

{#if showProfile}
  <ProfileModal onClose={() => (showProfile = false)} onSaved={syncProfileLive} />
{/if}

{#if showAudio}
  <AudioSettings onClose={() => (showAudio = false)} />
{/if}

<!-- Aviso de actualización (solo escritorio). -->
<UpdateBanner />

<!-- Audio de voz global: persiste aunque cambies de canal (la música no se corta). -->
<VoiceAudio />

<!-- Mini-reproductor flotante: visible fuera de la sala de música. -->
{#if !isMusicChannel}
  <MiniBar {voiceChannelId} onOpen={() => $musicChannelId != null && openChannel($musicChannelId)} />
{/if}

<style>
  .app {
    display: flex;
    height: 100%;
    overflow: hidden;
  }
  /* En escritorio los grupos no generan caja: rail/canales/chat/presencia
     siguen siendo hijos directos del flex (layout de 4 columnas intacto). */
  .side,
  .main,
  .aside-wrap {
    display: contents;
  }

  /* Tablet: ocultamos el panel de conectados (es complementario). */
  @media (max-width: 900px) {
    .aside-wrap {
      display: none;
    }
  }

  /* Móvil: un panel a la vez. La lista (rail + canales) o la conversación. */
  @media (max-width: 640px) {
    .side {
      display: flex;
      width: 100%;
      min-width: 0;
    }
    .main {
      display: flex;
      flex: 1;
      min-width: 0;
    }
    .app.show-chat .side {
      display: none;
    }
    .app:not(.show-chat) .main {
      display: none;
    }
  }
</style>
