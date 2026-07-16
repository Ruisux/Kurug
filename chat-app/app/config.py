"""
Configuración de la aplicación.

Lee variables de entorno (o el archivo .env) y las expone como un objeto
`settings` tipado. pydantic-settings valida los tipos automáticamente.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores placeholder que NO deben usarse en producción: si SECRET_KEY es uno
# de estos, cualquiera podría forjar tokens JWT, así que la app no arranca.
_PLACEHOLDER_SECRETS = {
    "cambia-esto-en-produccion",
    "cambia-esto-por-una-cadena-larga-y-aleatoria",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Obligatoria: sin default. Genera una con:
    #   python3 -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str
    # Sesión larga a propósito: es un chat privado entre conocidos y la gracia es
    # NO tener que iniciar sesión cada vez que se reinicia el PC. Con 1 día, el
    # token vencía de un día para otro y la app pedía login otra vez. El cliente
    # guarda el token en localStorage, así que con esto la sesión sobrevive a
    # apagar y prender. OJO: un JWT no se puede revocar antes de que expire; si
    # alguna vez hace falta echar a alguien, cambiar SECRET_KEY invalida TODOS.
    access_token_expire_minutes: int = 60 * 24 * 365  # 1 año
    database_url: str = "sqlite:///./chat.db"
    # Usuario reservado para el bot de música (se une a la voz a reproducir).
    bot_username: str = "kurug-bot"

    # Tamaño máximo por archivo adjunto (MB). Subida en streaming a disco, así
    # que no carga el archivo entero en memoria. Por defecto 2 GB.
    max_upload_mb: int = 2048
    # Lado máximo (px) al reescalar imágenes adjuntas (los GIF no se tocan).
    image_max_side: int = 1600

    # API key de Giphy (GIFs). Gratis en developers.giphy.com (crea una "App"
    # tipo API). Si está vacía, el buscador de GIFs queda deshabilitado.
    giphy_api_key: str = ""

    # --- Correo (verificación de cuenta por código) ---
    # SMTP de Gmail: usa una "contraseña de aplicación" (no la normal).
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""        # tu dirección Gmail (también el remitente)
    smtp_password: str = ""    # contraseña de aplicación de Google
    smtp_from_name: str = "Kurug"
    # Minutos de validez del código de verificación.
    verification_ttl_min: int = 15

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_user.strip() and self.smtp_password.strip())

    # --- Registro por invitación ---
    # Emails permitidos para registrarse, separados por comas. Si está VACÍA el
    # registro es ABIERTO (cualquiera puede crear cuenta). Con uno o más, SOLO
    # esos correos pueden registrarse. Las cuentas YA existentes no se ven
    # afectadas (esto solo controla /auth/register).
    allowed_emails: str = ""

    @property
    def allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}

    # --- LiveKit (SFU de voz/pantalla) ---
    # URL que usa el NAVEGADOR para conectarse (ws en local, wss en prod).
    livekit_url: str = "ws://localhost:7880"
    # Claves de la API. Los defaults son las del modo --dev de LiveKit; en
    # producción SE DEBEN sobreescribir por entorno.
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    @property
    def livekit_http_url(self) -> str:
        """URL HTTP del servidor LiveKit para llamadas de API del backend."""
        return self.livekit_url.replace("wss://", "https://").replace("ws://", "http://")

    @field_validator("secret_key")
    @classmethod
    def secret_key_no_placeholder(cls, v: str) -> str:
        if not v.strip() or v in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "SECRET_KEY no configurada o con valor placeholder. "
                "Genera una con: "
                'python3 -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v


settings = Settings()
