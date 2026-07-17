"""
Schemas de Pydantic = la "forma" de los datos que entran y salen de la API.

FastAPI los usa para validar el cuerpo de las peticiones y para serializar
las respuestas. Son distintos a los modelos de la BD a propósito: nunca
exponemos el password_hash al cliente, por ejemplo.
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Estados de disponibilidad que el usuario puede elegir.
StatusLiteral = Literal["online", "away", "dnd", "invisible"]

# Handle de usuario: corto, sin espacios ni @ (para @menciones y login).
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def _validate_password(v: str) -> str:
    # bcrypt solo considera los primeros 72 bytes.
    if len(v.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes")
    if len(v) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("La contraseña debe incluir letras y números")
    return v


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("username")
    @classmethod
    def username_handle(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("El usuario solo admite letras, números y _ (3-20)")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        return _validate_password(v)


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class ResendIn(BaseModel):
    email: EmailStr


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    """Restablecer contraseña con el código enviado al correo."""
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        return _validate_password(v)


class RegisterOut(BaseModel):
    """Tras registrarse: aún no hay token; hay que verificar el correo."""
    email: EmailStr
    message: str = "Te enviamos un código de verificación."


class UserOut(BaseModel):
    """Perfil público de un usuario (nunca incluye password_hash)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    nickname: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    accent_color: str = "#d97a4a"
    status: StatusLiteral = "online"
    custom_status: str | None = None
    is_admin: bool = False


class MeOut(UserOut):
    """Perfil propio: incluye email y estado de verificación (privado)."""
    email: str | None = None
    email_verified: bool = True


class UserUpdate(BaseModel):
    """Campos editables del perfil. Todos opcionales (PATCH parcial)."""
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    bio: str | None = Field(default=None, max_length=280)
    accent_color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$"
    )
    status: StatusLiteral | None = None
    custom_status: str | None = Field(default=None, max_length=64)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    # "text" (chat) o "voice" (sala de voz). Por defecto, texto.
    kind: Literal["text", "voice"] = "text"


class ChannelReorder(BaseModel):
    """Nuevo orden de los canales: lista de ids en el orden deseado."""
    order: list[int]


class UnreadQuery(BaseModel):
    """El cliente manda su 'último leído' por canal; el server cuenta lo nuevo."""
    last_read: dict[int, int] = {}


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_music: bool = False
    kind: str = "text"
    position: int = 0
    # id del último mensaje del canal (para calcular no leídos al cargar).
    last_message_id: int | None = None


class ReplyPreview(BaseModel):
    """Vista mínima del mensaje citado al responder."""
    id: int
    author_display_name: str
    content: str


class ReactionGroup(BaseModel):
    """Reacciones agrupadas por emoji para un mensaje."""
    emoji: str
    count: int
    users: list[int]


class MessageOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    author_username: str
    author_display_name: str
    author_avatar_url: str | None = None
    channel_id: int
    image_url: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    pinned_at: datetime | None = None
    edited_at: datetime | None = None
    reply_to: ReplyPreview | None = None
    reactions: list[ReactionGroup] = []


class DirectMessageOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    sender_id: int
    recipient_id: int
    sender_username: str
    sender_display_name: str
    sender_avatar_url: str | None = None
    image_url: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    edited_at: datetime | None = None
    pinned_at: datetime | None = None
    reply_to: ReplyPreview | None = None
    reactions: list[ReactionGroup] = []


class GifOut(BaseModel):
    """Un GIF del buscador (Tenor): url para enviar y miniatura para el grid."""
    id: str
    url: str          # GIF a tamaño normal (se envía como image_url)
    preview: str      # GIF pequeño (tinygif) para el grid del picker
    width: int = 0
    height: int = 0
    description: str = ""


class DMConversation(BaseModel):
    """Resumen de una conversación directa (para la lista de Directos)."""
    user: UserOut
    last_at: datetime
