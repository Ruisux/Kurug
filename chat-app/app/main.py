"""
Punto de entrada de la aplicación.

Crea la app de FastAPI y conecta los routers. El esquema lo gestiona Alembic.
Para correr:  uvicorn app.main:app --reload
"""
import asyncio
import secrets
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import User, Channel
from .security import hash_password
from .board import board as board_manager
from .routers import auth, channels, ws, users, avatars, presence, dms, music, voice, uploads, gifs, board


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Asegura el usuario bot y el canal de música (idempotente).
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.username == settings.bot_username)) is None:
            db.add(User(
                username=settings.bot_username,
                password_hash=hash_password(secrets.token_hex(16)),
                nickname="Kurug DJ",
            ))
        has_music = db.scalar(select(Channel).where(Channel.is_music.is_(True)))
        named = db.scalar(select(Channel).where(Channel.name == "música"))
        if has_music is None and named is None:
            db.add(Channel(name="música", is_music=True))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    # Historial de pizarras: purga diaria de tableros con >15 días sin uso.
    purge_task = asyncio.create_task(board_manager.purge_loop())
    yield
    purge_task.cancel()
    with suppress(asyncio.CancelledError):
        await purge_task
    await board_manager.flush()  # apagado ordenado: no perder los últimos trazos


# El esquema lo gestiona Alembic (`alembic upgrade head`), no la app.
app = FastAPI(title="Mini Chat", lifespan=lifespan)

# CORS: la app de ESCRITORIO (Tauri) hace peticiones desde otro origen
# (tauri://localhost) hacia el servidor. Usamos tokens Bearer (no cookies), así
# que permitir cualquier origen es seguro aquí. La web normal va al mismo origen.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(avatars.router)
app.include_router(uploads.router)
app.include_router(gifs.router)
app.include_router(presence.router)
app.include_router(dms.router)
app.include_router(music.router)
app.include_router(voice.router)
app.include_router(board.router)
app.include_router(channels.router)
app.include_router(ws.router)


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
