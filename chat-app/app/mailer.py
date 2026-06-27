"""
Envío de correo (verificación de cuenta) por SMTP — pensado para Gmail.

Gmail requiere una "contraseña de aplicación" (no la contraseña normal):
  Cuenta de Google -> Seguridad -> Verificación en 2 pasos -> Contraseñas de
  aplicaciones. Esa cadena va en SMTP_PASSWORD y tu dirección en SMTP_USER.

Si SMTP no está configurado, no enviamos: registramos el código en el log para
poder probar en local. `send_code` devuelve True si se envió de verdad.
"""
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("kurug.mailer")


def _build(to: str, code: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"Tu código de verificación de {settings.smtp_from_name}"
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_user}>"
    msg["To"] = to
    ttl = settings.verification_ttl_min
    msg.set_content(
        f"Tu código de verificación es: {code}\n\n"
        f"Caduca en {ttl} minutos. Si no fuiste tú, ignora este correo."
    )
    msg.add_alternative(
        f"""\
<div style="font-family:system-ui,sans-serif;max-width:420px;margin:auto">
  <h2 style="color:#d97a4a">{settings.smtp_from_name}</h2>
  <p>Tu código de verificación es:</p>
  <p style="font-size:30px;font-weight:700;letter-spacing:6px;color:#d97a4a">{code}</p>
  <p style="color:#666">Caduca en {ttl} minutos. Si no fuiste tú, ignora este correo.</p>
</div>""",
        subtype="html",
    )
    return msg


def send_code(to: str, code: str) -> bool:
    """Envía el código a `to`. True si se envió por SMTP; False si no hay SMTP."""
    if not settings.smtp_configured:
        log.warning("SMTP no configurado. Código de verificación para %s: %s", to, code)
        return False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(_build(to, code))
        return True
    except Exception as e:  # no filtrar detalles del SMTP al cliente
        log.error("Fallo enviando correo a %s: %r", to, e)
        raise
