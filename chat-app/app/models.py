"""
Modelos = tablas de la base de datos.

Tablas: usuarios, canales, mensajes de canal y mensajes directos (DMs).
Un mensaje de canal pertenece a un usuario (author) y a un canal.
Un DM va de un usuario (sender) a otro (recipient).
"""
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # username = handle corto único (para @menciones y login). nickname = visible.
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # email único: identidad de contacto y login alternativo. Nullable para no
    # romper cuentas antiguas (se rellenará en registros nuevos).
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default="0")
    # Código de verificación pendiente (y su caducidad). Se borran al verificar.
    verification_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    verification_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- Perfil ---
    nickname: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(280), nullable=True)
    accent_color: Mapped[str] = mapped_column(
        String(7), server_default="#d97a4a"
    )
    # Estado de disponibilidad elegido por el usuario.
    status: Mapped[str] = mapped_column(String(16), server_default="online")
    # Texto libre opcional tipo "trabajando", "jugando", etc.
    custom_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Permisos: el primer usuario registrado se vuelve admin (ver auth.register).
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="0")

    messages: Mapped[list["Message"]] = relationship(back_populates="author")

    @property
    def display_name(self) -> str:
        """Nombre visible: el nickname si lo hay, si no el username."""
        return self.nickname or self.username


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Canal especial: muestra el reproductor de música en vez del chat normal.
    is_music: Mapped[bool] = mapped_column(Boolean, server_default="0")
    # Tipo de canal: "text" (chat) o "voice" (sala de voz, sin chat propio).
    kind: Mapped[str] = mapped_column(String(8), server_default="text")
    # Orden en la lista (menor = más arriba). Se reordena por arrastre.
    position: Mapped[int] = mapped_column(Integer, server_default="0")

    messages: Mapped[list["Message"]] = relationship(back_populates="channel")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Indexado: el historial filtra por channel_id y ordena por id.
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)

    # Imagen adjunta (URL en /static/uploads, o un GIF de media.tenor.com).
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Archivo adjunto genérico (no imagen): URL local, nombre original y tamaño.
    file_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)

    # Fijado en el canal (None = no fijado). Solo para mensajes de canal.
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Edición y respuesta (cita de otro mensaje).
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )

    author: Mapped["User"] = relationship(back_populates="messages")
    channel: Mapped["Channel"] = relationship(back_populates="messages")


class DirectMessage(Base):
    """Mensaje directo 1-a-1 entre dos usuarios."""

    __tablename__ = "direct_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Imagen adjunta (URL en /static/uploads, o un GIF de media.tenor.com).
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Archivo adjunto genérico (no imagen).
    file_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    # Edición y fijado (paridad con los mensajes de canal).
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("direct_messages.id"), nullable=True
    )

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])
    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])


class DMReaction(Base):
    """Reacción (emoji) de un usuario a un mensaje directo."""

    __tablename__ = "dm_reactions"
    __table_args__ = (
        UniqueConstraint("dm_id", "user_id", "emoji", name="uq_dm_reaction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dm_id: Mapped[int] = mapped_column(ForeignKey("direct_messages.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    emoji: Mapped[str] = mapped_column(String(16))


class Reaction(Base):
    """Reacción (emoji) de un usuario a un mensaje de canal."""

    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    emoji: Mapped[str] = mapped_column(String(16))
