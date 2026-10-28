"""Tests de la lógica de reservas y de la API."""
# La BD de prueba y la fixture `fresh_db` viven en conftest.py.
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils import PhoneError, local_now, normalize_cl_phone

client = TestClient(app)


def _next_open_day_at(hour: int):
    d = (local_now() + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    while d.weekday() == 6:  # saltar domingo
        d += timedelta(days=1)
    return d


# ---------- Validación de teléfono ----------
def test_phone_valid_formats():
    assert normalize_cl_phone("+56 9 4291 6570") == "+56942916570"
    assert normalize_cl_phone("942916570") == "+56942916570"
    assert normalize_cl_phone("56942916570") == "+56942916570"
    assert normalize_cl_phone("4291 6570") == "+56942916570"  # 8 dígitos -> antepone 9


def test_phone_invalid():
    with pytest.raises(PhoneError):
        normalize_cl_phone("12345")


# ---------- Reservas ----------
def test_create_and_conflict():
    sid = client.get("/api/services").json()[0]["id"]
    start = _next_open_day_at(11)
    payload = {
        "customer_name": "Camila",
        "customer_phone": "+56 9 8765 4321",
        "service_id": sid,
        "start_at": start.isoformat(),
    }
    r = client.post("/api/appointments", json=payload)
    assert r.status_code == 201, r.text

    # mismo horario -> 409 (no doble-booking)
    r2 = client.post("/api/appointments", json={**payload, "customer_name": "Otro"})
    assert r2.status_code == 409


def test_availability_removes_booked_slot():
    sid = client.get("/api/services").json()[0]["id"]
    day = _next_open_day_at(11)
    date_str = day.date().isoformat()

    before = client.get(f"/api/availability?service_id={sid}&date={date_str}").json()
    assert "11:00" in before

    client.post(
        "/api/appointments",
        json={
            "customer_name": "Ana",
            "customer_phone": "+56 9 4291 6570",
            "service_id": sid,
            "start_at": day.isoformat(),
        },
    )
    after = client.get(f"/api/availability?service_id={sid}&date={date_str}").json()
    assert "11:00" not in after


def test_reject_invalid_phone_on_booking():
    sid = client.get("/api/services").json()[0]["id"]
    start = _next_open_day_at(13)
    r = client.post(
        "/api/appointments",
        json={
            "customer_name": "Mal Tel",
            "customer_phone": "123",
            "service_id": sid,
            "start_at": start.isoformat(),
        },
    )
    assert r.status_code == 422  # falla validación de teléfono


# ---------- Administración ----------
def test_admin_auth():
    assert client.get("/api/admin/appointments").status_code == 422  # falta cabecera
    assert client.get(
        "/api/admin/appointments", headers={"X-Admin-Token": "malo"}
    ).status_code == 401  # token incorrecto
    assert client.get(
        "/api/admin/appointments", headers={"X-Admin-Token": "test-token"}
    ).status_code == 200  # correcto
