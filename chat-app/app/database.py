"""
Conexión a la base de datos con SQLAlchemy 2.0.

- `engine`: el motor que habla con la base de datos.
- `SessionLocal`: fábrica de sesiones (una sesión = una "conversación" con la BD).
- `Base`: clase padre de la que heredan todos los modelos (tablas).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import settings

# SQLite necesita este flag para poder usarse desde varios hilos (como en WebSockets).
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

# Pool holgado: con ~10 personas hay muchas conexiones WS a la vez. Aunque los
# handlers ahora usan sesiones CORTAS (no retienen conexión mientras esperan
# mensajes), dejamos margen de sobra. pool_pre_ping descarta conexiones muertas.
_pool_kwargs = (
    {} if settings.database_url.startswith("sqlite") else {"pool_size": 20, "max_overflow": 40}
)
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    **_pool_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
