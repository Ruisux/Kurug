"""
Personalización de perfiles: niveles (XP), insignias y rangos.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from app.gamify import level_from_xp, xp_for_level, grant_badge, parse_badges
from conftest import register_token


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------- Curva de niveles (pura) ----------------

def test_level_curve_monotonic_and_consistent():
    # Nivel 1 desde 0 XP; cada nivel cuesta más que el anterior.
    assert level_from_xp(0) == {"level": 1, "into": 0, "span": xp_for_level(1)}
    assert xp_for_level(2) > xp_for_level(1)
    # Justo al completar el nivel 1 se pasa al 2 con "into" 0.
    span1 = xp_for_level(1)
    assert level_from_xp(span1)["level"] == 2
    assert level_from_xp(span1)["into"] == 0
    # `into` nunca supera el `span` del nivel.
    for xp in (1, 50, 99, 100, 250, 999, 5000):
        lv = level_from_xp(xp)
        assert 0 <= lv["into"] < lv["span"]


# ---------------- Insignias (helpers) ----------------

class _U:
    def __init__(self, badges="[]"):
        self.badges = badges


def test_grant_badge_dedupes_and_ignores_unknown():
    u = _U()
    assert grant_badge(u, "melomano") is True
    assert grant_badge(u, "melomano") is False       # ya la tiene
    assert grant_badge(u, "inventada") is False       # no existe en el catálogo
    assert parse_badges(u.badges) == ["melomano"]


# ---------------- Endpoints ----------------

def test_user_out_exposes_gamify_fields(client):
    ta = register_token(client, "alice")
    me = client.get("/users/me", headers={"Authorization": f"Bearer {ta}"}).json()
    # El primer usuario es admin -> el lifespan le da rango e insignia de Fundador.
    assert me["rank"] == "fundador"
    assert "fundador" in me["badges"]
    assert me["level"] == 1 and me["xp_span"] > 0


def test_admin_sets_rank_and_badges(client):
    ta = register_token(client, "alice")   # admin (primero)
    tb = register_token(client, "bob")     # normal
    bob = client.get("/users", headers={"Authorization": f"Bearer {ta}"}).json()
    bob_id = next(u["id"] for u in bob if u["username"] == "bob")

    # Admin asigna rango.
    r = client.post(f"/users/{bob_id}/rank", json={"rank": "moderador"},
                    headers={"Authorization": f"Bearer {ta}"})
    assert r.status_code == 200 and r.json()["rank"] == "moderador"

    # Admin da y quita una insignia.
    r = client.post(f"/users/{bob_id}/badges", json={"key": "mvp", "action": "add"},
                    headers={"Authorization": f"Bearer {ta}"})
    assert "mvp" in r.json()["badges"]
    r = client.post(f"/users/{bob_id}/badges", json={"key": "mvp", "action": "remove"},
                    headers={"Authorization": f"Bearer {ta}"})
    assert "mvp" not in r.json()["badges"]

    # Rango/insignia desconocidos -> 422.
    assert client.post(f"/users/{bob_id}/rank", json={"rank": "rey"},
                       headers={"Authorization": f"Bearer {ta}"}).status_code == 422
    assert client.post(f"/users/{bob_id}/badges", json={"key": "x"},
                       headers={"Authorization": f"Bearer {ta}"}).status_code == 422


def test_non_admin_cannot_manage(client):
    register_token(client, "alice")        # admin
    tb = register_token(client, "bob")     # normal
    users = client.get("/users", headers={"Authorization": f"Bearer {tb}"}).json()
    alice_id = next(u["id"] for u in users if u["username"] == "alice")
    # Bob (no admin) intenta tocar a alice -> 403.
    assert client.post(f"/users/{alice_id}/rank", json={"rank": "veterano"},
                       headers={"Authorization": f"Bearer {tb}"}).status_code == 403
    assert client.post(f"/users/{alice_id}/badges", json={"key": "mvp"},
                       headers={"Authorization": f"Bearer {tb}"}).status_code == 403
