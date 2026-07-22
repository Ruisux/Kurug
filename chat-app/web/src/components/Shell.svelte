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
  import { activity } from "../lib/desktop.js";
  import { prefs } from "../lib/prefs.js";

  import Rail from "./Rail.svelte";
  import ChannelList from "./ChannelList.svelte";
  import ChatView from "./ChatView.svelte";
  import MusicRoom from "./MusicRoom.svelte";
  import VoiceView from "./VoiceView.svelte";
  import PresencePanel from "./PresencePanel.svelte";
  import ProfileModal from "./ProfileModal.svelte";
  import AudioSettings from "./AudioSettings.svelte";
  import AppearanceModal from "./AppearanceModal.svelte";
  import MiniBar from "./MiniBar.svelte";
  import UpdateBanner from "./UpdateBanner.svelte";

  let channels = [];
  let dmConvos = [];
  let online = [];
  let allUsers = []; // todos los miembros (conectados y no) para el panel de personas
  let voiceByChannel = {}; // channel_id -> [{id, display_name, avatar_url}]
  let prevVoiceCid = null; // para avisar al WS al entrar/salir de una sala de voz
  let view = { kind: "none" }; // {kind:'channel', id} | {kind:'dm', user}
  let messages = [];
  let showProfile = false;
  let showAudio = false;
  let showAppearance = false;

  // Los modales son position:fixed del documento; un <video> en pantalla
  // completa vive en la top-layer del navegador y los tapa (el modal "se sale
  // y no se puede cerrar"). Antes de abrir cualquiera, salir de fullscreen.
  function openModal(set) {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    set();
  }

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

  // --- Actividad automática (jugando/escuchando) — app de escritorio ---
  let currentActivity = null; // lo último que detectó el main de Electron
  function pushActivity() {
    if (!activity.supported) return;
    if (get(prefs).shareActivity !== false && currentActivity) {
      presWs?.send({ type: "set_activity", ...currentActivity });
    } else {
      presWs?.send({ type: "set_activity" }); // limpiar
    }
  }
  // Reaccionar al toggle de privacidad en vivo.
  let lastShareActivity = null;
  $: {
    const share = $prefs.shareActivity !== false;
    if (activity.supported && share !== lastShareActivity) {
      if (lastShareActivity !== null) {
        activity.setEnabled(share);
        if (!share) {
          currentActivity = null;
          pushActivity();
        }
      }
      lastShareActivity = share;
    }
  }

  // --- "X está escribiendo…" (efímero, se apaga solo a los 4 s) ---
  let typingUsers = {}; // userId -> { name, until }
  const typingPrune = setInterval(() => {
    const now = Date.now();
    const keep = Object.entries(typingUsers).filter(([, v]) => v.until > now);
    if (keep.length !== Object.keys(typingUsers).length) {
      typingUsers = Object.fromEntries(keep);
    }
  }, 1000);
  onDestroy(() => clearInterval(typingPrune));

  function noteTyping(id, name) {
    if (id === meUser.id) return;
    typingUsers = { ...typingUsers, [id]: { name, until: Date.now() + 4000 } };
  }
  function clearTyping(id) {
    if (typingUsers[id]) {
      const { [id]: _gone, ...rest } = typingUsers;
      typingUsers = rest;
    }
  }

  // Emisión con freno: como mucho un aviso cada 3 s por destino.
  let lastTypingSent = 0;
  function sendTyping() {
    const now = Date.now();
    if (now - lastTypingSent < 3000) return;
    lastTypingSent = now;
    if (view.kind === "channel") chatWs?.send({ type: "typing" });
    else if (view.kind === "dm") presWs?.send({ type: "typing_dm", to: view.user.id });
  }

  // --- No leídos por conversación de DM (partnerId -> contador) ---
  // Antes las notificaciones de DM SONABAN pero no se veía quién escribió ni
  // cuántos mensajes: mismo esquema que los canales, badge en DIRECTOS.
  let dmUnread = {};
  const DM_LASTREAD_KEY = "kurug-dm-lastread";
  let dmLastRead = loadDmLastRead();

  function loadDmLastRead() {
    try {
      return JSON.parse(localStorage.getItem(DM_LASTREAD_KEY)) || {};
    } catch {
      return {};
    }
  }
  function markDmRead(partnerId, upToId) {
    if (upToId != null && (dmLastRead[partnerId] || 0) < upToId) {
      dmLastRead[partnerId] = upToId;
      try { localStorage.setItem(DM_LASTREAD_KEY, JSON.stringify(dmLastRead)); } catch {}
    }
    if (dmUnread[partnerId]) {
      dmUnread = { ...dmUnread, [partnerId]: 0 };
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
      user: m.author_username, // para pintar su nombre con SU color de acento
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
      userId: m.sender_id, // para pintar su nombre con SU color de acento
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
      users: r.users || [], // para el tooltip de "quiénes reaccionaron"
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
  $: voiceViewName = view.kind === "voice"
    ? (channels.find((c) => c.id === view.id)?.name ?? "voz") : "voz";

  // Estado REAL (en vivo) por usuario para los DMs: solo los presentes en la
  // presencia (online) tienen su estado; el resto se muestra desconectado.
  $: dmStatus = Object.fromEntries((online || []).map((u) => [u.id, u.status]));
  $: isMusicChannel =
    view.kind === "channel" && !!channels.find((c) => c.id === view.id)?.is_music;
  // La música suena en la VOZ de "general" (canal donde se conecta el bot).
  $: voiceChannelId = (channels.find((c) => c.name === "general" && !c.is_music)
    || channels.find((c) => !c.is_music) || {}).id ?? null;

  // usuario_id -> nombre del canal de voz donde está (para el panel de personas).
  $: userVoice = (() => {
    const m = {};
    for (const [cid, members] of Object.entries(voiceByChannel)) {
      const name = channels.find((c) => String(c.id) === String(cid))?.name;
      for (const u of members) m[u.id] = name || "voz";
    }
    return m;
  })();

  // usuario_id -> { muted, deafened, rtt } (iconos y ping en los recuadros).
  $: voiceFlags = (() => {
    const live = new Map(online.map((u) => [u.id, u]));
    const m = {};
    for (const members of Object.values(voiceByChannel))
      for (const u of members) {
        const p = live.get(u.id);
        m[u.id] = {
          muted: !!u.muted,
          deafened: !!u.deafened,
          rtt: u.rtt ?? null,
          // Estado del perfil: quien está en voz está conectado, así que a
          // falta de dato vivo el mínimo es "online" (nunca gris).
          status: p?.status || "online",
          custom_status: p?.custom_status || null,
        };
      }
    return m;
  })();

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

  // Y también mi estado de micro/auriculares/compartiendo, para que los demás
  // vean los iconos y el badge EN DIRECTO en la lista de ocupantes.
  let prevVoiceFlags = "";
  $: {
    const flags = $voiceState.active
      ? JSON.stringify({
          muted: $voiceState.muted,
          deafened: $voiceState.deafened,
          sharing: $voiceState.sharing,
        })
      : "";
    if (flags && flags !== prevVoiceFlags) {
      presWs?.send({ type: "voice_state", ...JSON.parse(flags), rtt: $voiceState.myRtt ?? null });
    }
    prevVoiceFlags = flags;
  }

  // El ping (RTT) se reenvía periódicamente mientras estoy en voz: los flags
  // solo viajan al cambiar, pero la latencia cambia sola cada pocos segundos.
  const rttTimer = setInterval(() => {
    const st = get(voiceState);
    if (st.active && st.myRtt != null) {
      presWs?.send({
        type: "voice_state",
        muted: st.muted, deafened: st.deafened, sharing: st.sharing,
        rtt: st.myRtt,
      });
    }
  }, 5000);
  onDestroy(() => clearInterval(rttTimer));

  onMount(async () => {
    try {
      channels = await api.channels();
      dmConvos = await api.dmConversations();
      allUsers = await api.users();
    } catch {}
    // Sembrar contadores de no leídos según lo último leído (localStorage).
    try {
      unread = await api.unreadCounts(lastRead);
    } catch {}
    try {
      dmUnread = await api.dmUnreadCounts(dmLastRead);
    } catch {}
    // Al (re)abrir el socket de presencia, re-publicar la actividad vigente
    // (el server la pierde si se cayó la conexión).
    presWs = presenceSocket(get(token), handlePresence, () => pushActivity());
    if (activity.supported) {
      activity.onUpdate((act) => {
        currentActivity = act;
        pushActivity();
      });
      activity.setEnabled(get(prefs).shareActivity !== false);
    }
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
    typingUsers = {}; // los "escribiendo…" son de la vista anterior
    lastTypingSent = 0;
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
    typingUsers = {};
    lastTypingSent = 0;
    mobilePane = "chat";
    try {
      messages = (await api.dms(user.id)).map(normDm);
    } catch {
      messages = [];
    }
    // Abrir la conversación la marca leída (el badge de DIRECTOS se apaga).
    markDmRead(user.id, messages.at(-1)?.id);
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
    } else if (m.type === "typing") {
      noteTyping(m.user_id, m.display_name);
    } else if (m.type === "message" && view.kind === "channel" && m.channel_id === view.id) {
      messages = [...messages, normChannel(m)];
      if (m.author_id != null) clearTyping(m.author_id); // envió: ya no escribe
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
      // Si es un miembro que aún no teníamos (registro reciente), recargar lista.
      if (!allUsers.some((u) => u.id === evt.user.id)) {
        api.users().then((us) => (allUsers = us)).catch(() => {});
      }
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
    } else if (evt.type === "dm_typing") {
      // Solo interesa si estás mirando ESA conversación.
      if (view.kind === "dm" && view.user.id === evt.from) {
        noteTyping(evt.from, evt.display_name);
      }
    } else if (evt.type === "dm") {
      const m = evt.message;
      const partner = m.sender_id === meUser.id ? m.recipient_id : m.sender_id;
      clearTyping(m.sender_id); // envió: ya no está escribiendo
      if (view.kind === "dm" && view.user.id === partner) {
        messages = [...messages, normDm(m)];
      }
      if (m.sender_id !== meUser.id) {
        const viewingThis = view.kind === "dm" && view.user.id === partner;
        if (viewingThis && document.hasFocus()) {
          markDmRead(partner, m.id); // lo estás leyendo ahora mismo
        } else {
          dmUnread = { ...dmUnread, [partner]: (dmUnread[partner] || 0) + 1 };
          playSound("notify");
          notify(m.sender_display_name, m.content, { tag: `dm-${partner}` });
        }
      } else {
        markDmRead(partner, m.id); // lo que TÚ envías cuenta como leído
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

  // Seleccionar un canal de VOZ = abrir su vista (recuadros + controles) y unirse.
  function selectVoice(id) {
    view = { kind: "voice", id };
    if (window.innerWidth <= 640) mobilePane = "chat";
    if (!($voiceState.active && $voiceState.channelId === id)) joinVoice(id);
  }

  // Al SALIR de la llamada (botón de colgar, desconexión…) no tiene sentido
  // seguir viendo los recuadros: volvemos al primer canal de texto. El flag
  // distingue "estuve dentro y salí" de "aún me estoy conectando" (mientras
  // conecta, active también es false y no hay que echar a nadie de la vista).
  let wasInVoice = false;
  $: {
    if ($voiceState.active) wasInVoice = true;
    else if (wasInVoice) {
      wasInVoice = false;
      if (view.kind === "voice") {
        const first = channels.find((c) => c.kind !== "voice" && !c.is_music)
          || channels.find((c) => c.kind !== "voice");
        if (first) openChannel(first.id);
        else view = { kind: "none" };
      }
    }
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
      onProfile={() => openModal(() => (showProfile = true))}
      onAudio={() => openModal(() => (showAudio = true))}
      onAppearance={() => openModal(() => (showAppearance = true))}
      onHome={() => { const c = channels.find((x) => x.kind !== "voice" && !x.is_music) || channels.find((x) => x.kind !== "voice") || channels[0]; if (c) openChannel(c.id); }}
      onMusic={() => $musicChannelId != null && openChannel($musicChannelId)}
    />
    <ChannelList
      {channels}
      {currentChannelId}
      {currentDmUserId}
      {unread}
      {dmUnread}
      dms={dmConvos}
      {dmStatus}
      isAdmin={$me.is_admin}
      {online}
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
    {#if view.kind === "voice"}
      <VoiceView channelName={voiceViewName} channelId={view.id} {voiceFlags} onBack={backToList} />
    {:else if isMusicChannel}
      <MusicRoom {voiceChannelId} onBack={backToList} />
    {:else}
      <ChatView
        {header} channelId={currentChannelId} dmUserId={currentDmUserId} {messages} {allUsers}
        {online} onOpenDm={openDm}
        typing={Object.values(typingUsers).map((t) => t.name)} onTyping={sendTyping}
        {onSend} {onDelete} {onEdit} {onReact} {onPin} onBack={backToList}
      />
    {/if}
  </div>
  <div class="aside-wrap">
    <PresencePanel {online} {allUsers} {userVoice} onSelectUser={openDm} />
  </div>
</div>

{#if showProfile}
  <ProfileModal onClose={() => (showProfile = false)} onSaved={syncProfileLive} />
{/if}

{#if showAudio}
  <AudioSettings onClose={() => (showAudio = false)} />
{/if}

{#if showAppearance}
  <AppearanceModal onClose={() => (showAppearance = false)} onSaved={syncProfileLive} />
{/if}

<!-- Aviso de actualización (solo escritorio). -->
<UpdateBanner />

<!-- Mini-reproductor flotante: visible fuera de la sala de música. -->
{#if !isMusicChannel}
  <MiniBar {voiceChannelId} voiceView={view.kind === "voice"} onOpen={() => $musicChannelId != null && openChannel($musicChannelId)} />
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
