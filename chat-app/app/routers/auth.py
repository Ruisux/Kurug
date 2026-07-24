"""
Autenticación: registro con verificación de correo y login.

Flujo:
1. POST /auth/register  -> crea la cuenta (NO verificada) y envía un código al
   correo. Aún no hay token.
2. POST /auth/verify    -> con el código correcto, marca el correo verificado y
   devuelve el token (auto-login).
3. POST /auth/resend    -> reenvía un código nuevo.
4. POST /auth/login     -> token JWT. Acepta usuario O correo. Bloquea si el
   correo no está verificado.
5. POST /auth/forgot    -> envía un código al correo para restablecer la
   contraseña (respuesta uniforme: no revela qué correos existen).
6. POST /auth/reset     -> con el código correcto, cambia la contraseña y
   devuelve el token (auto-login).
"""
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..deps import DbSession
from ..mailer import send_code
from ..models import User
from ..schemas import UserCreate, VerifyIn, ResendIn, ForgotIn, ResetIn, RegisterOut, Token
from ..security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate-limit simple en memoria para login: cuenta solo FALLOS por IP.
_login_fails: dict[str, list[float]] = {}
_RATE_MAX = 8
_RATE_WINDOW = 60.0


def _rate_check(ip: str) -> None:
    now = time.time()
    hits = _login_fails.setdefault(ip, [])
    while hits and now - hits[0] > _RATE_WINDOW:
        hits.pop(0)
    if len(hits) >= _RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Espera un momento.",
        )


def _rate_fail(ip: str) -> None:
    _login_fails.setdefault(ip, []).append(time.time())


# Rate-limit aparte para "olvidé mi contraseña": cada petición manda un CORREO,
# así que se cuenta toda petición (no solo fallos) para no dejar spamear la
# bandeja de nadie. 5 códigos por IP cada 10 minutos es de sobra para humanos.
_forgot_hits: dict[str, list[float]] = {}
_FORGOT_MAX = 5
_FORGOT_WINDOW = 600.0


def _forgot_rate_check(ip: str) -> None:
    now = time.time()
    hits = _forgot_hits.setdefault(ip, [])
    while hits and now - hits[0] > _FORGOT_WINDOW:
        hits.pop(0)
    if len(hits) >= _FORGOT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas peticiones. Espera unos minutos.",
        )
    hits.append(now)


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _set_and_send_code(user: User, db: DbSession, kind: str = "verify") -> None:
    """Genera, guarda y envía un código al correo del usuario (verify/reset)."""
    user.verification_code = _new_code()
    user.verification_expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.verification_ttl_min
    )
    db.commit()
    try:
        send_code(user.email, user.verification_code, kind)
    except Exception:
        # No revelamos detalles del SMTP; el usuario puede reintentar (resend).
        raise HTTPException(
            status_code=502,
            detail="No se pudo enviar el correo. Inténtalo de nuevo.",
        )


@router.post("/register", response_model=RegisterOut, status_code=201)
def register(data: UserCreate, db: DbSession):
    email = data.email.lower()
    # Registro por invitación: si hay lista de emails permitidos, solo esos.
    allowed = settings.allowed_email_set
    if allowed and email not in allowed:
        raise HTTPException(
            status_code=403,
            detail="El registro está limitado. Pide acceso al administrador.",
        )
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=400, detail="Ese correo ya está registrado")
    if db.scalar(select(User).where(func.lower(User.username) == data.username.lower())):
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")

    # El primer usuario HUMANO registrado se vuelve admin (el bot no cuenta).
    first_user = db.scalar(
        select(User).where(User.username != settings.bot_username).limit(1)
    ) is None

    user = User(
        username=data.username,
        email=email,
        password_hash=hash_password(data.password),
        email_verified=False,
        is_admin=first_user,
    )
    # El primer usuario (admin) arranca con el rango y la insignia de Fundador,
    # como en el mockup (el lifespan solo cubre instalaciones ya existentes).
    if first_user:
        from ..gamify import grant_badge
        user.rank = "fundador"
        grant_badge(user, "fundador")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ese correo o usuario ya existe")
    db.refresh(user)
    _set_and_send_code(user, db)
    return RegisterOut(email=user.email)


def _check_code(user: User | None, code: str, missing_detail: str) -> User:
    """Valida que el usuario tenga un código pendiente, vigente y correcto."""
    if user is None or not user.verification_code:
        raise HTTPException(status_code=400, detail=missing_detail)
    expired = (
        user.verification_expires is None
        or datetime.now(timezone.utc) > _aware(user.verification_expires)
    )
    if expired:
        raise HTTPException(status_code=400, detail="El código caducó. Pide uno nuevo.")
    if not secrets.compare_digest(code, user.verification_code):
        raise HTTPException(status_code=400, detail="Código incorrecto")
    return user


@router.post("/verify", response_model=Token)
def verify(data: VerifyIn, db: DbSession):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    user = _check_code(user, data.code, "No hay una verificación pendiente")

    user.email_verified = True
    user.verification_code = None
    user.verification_expires = None
    db.commit()
    return Token(access_token=create_access_token(user.username))


@router.post("/resend", status_code=202)
def resend(data: ResendIn, db: DbSession):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    # Respuesta uniforme aunque no exista (no filtrar qué correos hay).
    if user and not user.email_verified:
        _set_and_send_code(user, db)
    return {"message": "Si la cuenta existe, te enviamos un código nuevo."}


@router.post("/login", response_model=Token)
def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    ip = request.client.host if request.client else "?"
    _rate_check(ip)
    ident = form.username.strip().lower()
    user = db.scalar(
        select(User).where(
            or_(func.lower(User.username) == ident, func.lower(User.email) == ident)
        )
    )
    if not user or not verify_password(form.password, user.password_hash):
        _rate_fail(ip)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Tu correo no está verificado. Revisa tu bandeja o pide otro código.",
        )
    return Token(access_token=create_access_token(user.username))


@router.post("/forgot", status_code=202)
def forgot(request: Request, data: ForgotIn, db: DbSession):
    """Envía un código para restablecer la contraseña.

    La respuesta es SIEMPRE la misma exista o no la cuenta: si no, este endpoint
    serviría para averiguar qué correos están registrados.
    """
    _forgot_rate_check(request.client.host if request.client else "?")
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if user:
        _set_and_send_code(user, db, kind="reset")
    return {"message": "Si la cuenta existe, te enviamos un código."}


@router.post("/reset", response_model=Token)
def reset(request: Request, data: ResetIn, db: DbSession):
    """Cambia la contraseña con el código del correo y devuelve token (auto-login)."""
    ip = request.client.host if request.client else "?"
    _rate_check(ip)  # los códigos de 6 dígitos no se pueden dejar a fuerza bruta
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    try:
        user = _check_code(user, data.code, "No hay un restablecimiento pendiente")
    except HTTPException:
        _rate_fail(ip)
        raise

    user.password_hash = hash_password(data.password)
    # Meter el código del correo también demuestra que el correo es suyo.
    user.email_verified = True
    user.verification_code = None
    user.verification_expires = None
    db.commit()
    return Token(access_token=create_access_token(user.username))


def _aware(dt: datetime) -> datetime:
    """SQLite devuelve naive (UTC): lo marcamos explícito para comparar."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
