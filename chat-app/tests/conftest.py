"""
Configuración de los tests.

Importante: la configuración de la app (`app/config.py`) se evalúa al importar,
y ahora exige una SECRET_KEY válida y lee DATABASE_URL. Por eso fijamos las
variables de entorno ANTES de que cualquier test importe la app. Las variables
de entorno tienen prioridad sobre el archivo `.env`.
"""
import glob
import os
import tempfile

import pytest

# BD temporal y aislada para los tests (no toca chat.db real).
_tmp_db = os.path.join(tempfile.mkdtemp(), "test_chat.db")

os.environ["SECRET_KEY"] = "clave-de-test-suficientemente-larga-1234567890"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
# Forzar SIN key de Giphy en los tests: deterministas y sin llamadas de red.
os.environ["GIPHY_API_KEY"] = ""


def register_token(client, username, password="secret123"):
    """Registra una cuenta, verifica el correo (lee el código de la BD, ya que
    en tests no hay SMTP) y devuelve el token de acceso."""
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models import User

    email = f"{username}@test.com"
    client.post("/auth/register", json={"email": email, "username": username, "password": password})
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.email) == email))
        code = u.verification_code if u else None
    if code is None:
        r = client.post("/auth/login", data={"username": username, "password": password})
        return r.json().get("access_token")
    return client.post("/auth/verify", json={"email": email, "code": code}).json()["access_token"]


@pytest.fixture(autouse=True)
def clean_avatars():
    """Borra los avatares que generen los tests (deja el .gitkeep)."""
    yield
    for f in glob.glob("static/avatars/*"):
        if not f.endswith(".gitkeep"):
            try:
                os.remove(f)
            except OSError:
                pass
