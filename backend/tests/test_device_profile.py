"""HU-1: reservar con los datos recordados en el dispositivo (cookie HttpOnly)."""
import hashlib
from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import DeviceProfile
from app.utils import local_now

COOKIE = settings.device_cookie_name
PROFILE = {"customer_name": "Camila Rojas", "customer_phone": "+56 9 8765 4321"}


def _device() -> TestClient:
    """Un 'dispositivo' = un cliente con su propio jar de cookies."""
    return TestClient(app)


def _book(client: TestClient, hour: int = 11, **overrides):
    sid = client.get("/api/services").json()[0]["id"]
    start = (local_now() + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    while start.weekday() in settings.closed_weekdays_set:
        start += timedelta(days=1)
    payload = {**PROFILE, "service_id": sid, "start_at": start.isoformat(), **overrides}
    return client.post("/api/appointments", json=payload)


def _rows():
    db = SessionLocal()
    try:
        return db.query(DeviceProfile).all()
    finally:
        db.close()


def test_happy_path_remember_and_prefill():
    d = _device()
    assert d.get("/api/device/profile").json() == {
        "known": False, "customer_name": None, "customer_phone": None, "detail": None,
    }

    assert _book(d).status_code == 201
    r = d.post("/api/device/remember", json=PROFILE)
    assert r.status_code == 201

    set_cookie = r.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    token = d.cookies.get(COOKIE)
    assert token

    # Solo se guarda el SHA-256: el token en claro no está en ninguna columna.
    (row,) = _rows()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (row.token_hash, row.customer_name, row.customer_phone)

    # Prellenado con el celular normalizado, y se puede reservar de nuevo.
    prof = d.get("/api/device/profile").json()
    assert prof["known"] is True
    assert prof["customer_name"] == "Camila Rojas"
    assert prof["customer_phone"] == "+56987654321"
    assert _book(d, hour=15).status_code == 201

    # "Actualizar datos" desde el modal.
    up = d.put("/api/device/profile", json={**PROFILE, "customer_name": "Camila R."})
    assert up.status_code == 200 and up.json()["customer_name"] == "Camila R."


def test_edge_many_devices_and_token_never_overwritten():
    a, b = _device(), _device()
    assert a.post("/api/device/remember", json=PROFILE).status_code == 201
    assert b.post("/api/device/remember", json=PROFILE).status_code == 201  # mismo celular

    token_a, token_b = a.cookies.get(COOKIE), b.cookies.get(COOKIE)
    assert token_a != token_b
    assert len(_rows()) == 2
    assert a.get("/api/device/profile").json()["known"] is True
    assert b.get("/api/device/profile").json()["known"] is True

    # Volver a aceptar en un dispositivo conocido no emite ni reemplaza el token.
    hashes_before = sorted(r.token_hash for r in _rows())
    again = a.post("/api/device/remember", json={**PROFILE, "customer_name": "Otro Nombre"})
    assert again.status_code == 200
    assert again.json()["detail"] == "already_known"
    assert again.json()["customer_name"] == "Camila Rojas"   # tampoco toca los datos
    assert "set-cookie" not in again.headers
    assert a.cookies.get(COOKIE) == token_a
    assert sorted(r.token_hash for r in _rows()) == hashes_before


def _with_cookie(token: str) -> dict:
    """Cabecera Cookie explícita: simula un token que el navegador envía tal cual."""
    return {"Cookie": f"{COOKIE}={token}"}


def test_edge_invalid_token_is_unknown_device():
    d = _device()
    forged = _with_cookie("token-forjado-que-no-existe")

    # No se filtra ningún dato y el dispositivo cuenta como desconocido.
    prof = d.get("/api/device/profile", headers=forged).json()
    assert prof["known"] is False and prof["customer_name"] is None
    assert d.put("/api/device/profile", json=PROFILE, headers=forged).status_code == 401
    assert d.delete("/api/device", headers=forged).status_code == 401

    # Un dispositivo con token inválido sí puede registrarse (se emite uno nuevo).
    assert d.post("/api/device/remember", json=PROFILE, headers=forged).status_code == 201
    good = d.cookies.get(COOKIE)
    assert good and good != "token-forjado-que-no-existe"
    assert len(_rows()) == 1

    # Tras olvidarlo, el mismo token deja de ser válido.
    assert d.delete("/api/device").status_code == 200
    other = _device().get("/api/device/profile", headers=_with_cookie(good)).json()
    assert other["known"] is False
    assert _rows() == []

    # Datos inválidos no crean perfil.
    assert _device().post(
        "/api/device/remember", json={**PROFILE, "customer_phone": "123"}
    ).status_code == 422
    assert _rows() == []
