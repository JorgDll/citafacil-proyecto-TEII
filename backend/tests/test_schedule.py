"""HU-2: franjas visibles con estado y calendario mensual de disponibilidad."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app

client = TestClient(app)

# Reloj congelado: miércoles 4-nov-2026, 12:15 (domingo = cerrado por defecto).
NOW = datetime(2026, 11, 4, 12, 15)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr("app.availability.local_now", lambda: NOW)


def _add_appt(start: datetime, service_id: int = 1, minutes: int = 30, status: str = models.STATUS_CONFIRMED):
    db = SessionLocal()
    try:
        db.add(models.Appointment(
            customer_name="Cliente", customer_phone="+56987654321", service_id=service_id,
            start_at=start, end_at=start + timedelta(minutes=minutes), status=status,
        ))
        db.commit()
    finally:
        db.close()


def _schedule(day: str, service_id: int = 1) -> dict:
    r = client.get(f"/api/schedule?service_id={service_id}&date={day}")
    assert r.status_code == 200, r.text
    return {s["time"]: s for s in r.json()}


def test_happy_path_schedule_shows_every_slot_with_booked_blocked():
    # Reserva real por la API (30 min a las 11:00 del jueves 5-nov).
    r = client.post("/api/appointments", json={
        "customer_name": "Ana", "customer_phone": "942916570",
        "service_id": 1, "start_at": "2026-11-05T11:00:00",
    })
    assert r.status_code == 201, r.text

    slots = _schedule("2026-11-05")
    assert len(slots) == 20                                  # 10:00 … 19:30
    assert slots["11:00"] == {"time": "11:00", "available": False, "reason": "booked"}
    assert slots["10:30"]["available"] and slots["11:30"]["available"]
    assert sum(1 for s in slots.values() if not s["available"]) == 1

    # Compatibilidad: el endpoint anterior sigue ocultando la franja ocupada.
    old = client.get("/api/availability?service_id=1&date=2026-11-05").json()
    assert "11:00" not in old and len(old) == 19


def test_edge_overlap_depends_on_duration_and_cancelled_does_not_block():
    db = SessionLocal()
    db.add(models.Service(name="Largo", duration_min=45, price=12000, active=True))
    db.commit()
    long_id = db.query(models.Service).filter_by(name="Largo").one().id
    db.close()

    _add_appt(datetime(2026, 11, 5, 11, 0))                                   # 11:00–11:30
    _add_appt(datetime(2026, 11, 5, 15, 0), status=models.STATUS_CANCELLED)   # no bloquea

    slots = _schedule("2026-11-05", service_id=long_id)
    assert slots["10:00"]["available"]                  # 10:00–10:45 no toca
    assert slots["10:30"]["reason"] == "booked"         # 10:30–11:15 solapa con 11:00
    assert slots["11:00"]["reason"] == "booked"
    assert slots["11:30"]["available"]                  # empieza justo al terminar la cita
    assert slots["15:00"]["available"]                  # la cancelada libera el horario
    assert slots["19:00"]["available"]                  # 19:00–19:45 aún cabe
    assert "19:30" not in slots                         # 45 min no entran antes de las 20:00


def test_edge_calendar_statuses_past_hours_and_validation():
    # Hoy (mié 4): las horas hasta las 12:15 quedan visibles pero bloqueadas como "past".
    today = _schedule("2026-11-04")
    assert today["12:00"] == {"time": "12:00", "available": False, "reason": "past"}
    assert today["12:30"]["available"]

    # Jueves 5 vacío; viernes 6 con TODAS las franjas ocupadas.
    for n in range(20):
        _add_appt(datetime(2026, 11, 6, 10, 0) + timedelta(minutes=30 * n))

    r = client.get("/api/calendar?service_id=1&month=2026-11")
    assert r.status_code == 200
    days = {d["date"]: d for d in r.json()}
    assert len(days) == 30
    assert days["2026-11-08"]["status"] == "closed"       # domingo
    assert days["2026-11-03"]["status"] == "past"         # ayer
    assert days["2026-11-04"] == {"date": "2026-11-04", "status": "available", "free": 15}
    assert days["2026-11-05"] == {"date": "2026-11-05", "status": "available", "free": 20}
    assert days["2026-11-06"] == {"date": "2026-11-06", "status": "full", "free": 0}

    # Entradas inválidas.
    assert client.get("/api/calendar?service_id=1&month=2026-13").status_code == 422
    assert client.get("/api/calendar?service_id=1&month=nov").status_code == 422
    assert client.get("/api/calendar?service_id=999&month=2026-11").status_code == 404
    assert client.get("/api/schedule?service_id=999&date=2026-11-05").status_code == 404
