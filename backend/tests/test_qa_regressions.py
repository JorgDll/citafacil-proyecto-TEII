"""Regresiones de los hallazgos de QA (docs/qa/Reporte-QA.md).

- QA-01: la API aceptaba inicios fuera de la grilla (p. ej. 11:13), que bloquean dos franjas.
- QA-02: el recordatorio de WhatsApp no traía el enlace de autogestión (HU-5, criterio 1).
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.reminders import run_reminders

client = TestClient(app)
PHONE = "+56 9 4291 6570"

# Miércoles 4-nov-2026 12:15; la cita de prueba es el jueves 5 a las 11:00.
NOW = datetime(2026, 11, 4, 12, 15)
THU_11 = "2026-11-05T11:00:00"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    state = {"now": NOW}
    for target in ("app.availability.local_now", "app.manage.local_now", "app.reminders.local_now"):
        monkeypatch.setattr(target, lambda: state["now"])
    return state


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    """Intercepta los WhatsApp: lista de (teléfono, texto)."""
    box = []

    def fake(to, body):
        box.append((to, body))
        return {"ok": True, "mode": "test"}

    for target in ("app.routers.public.send_whatsapp", "app.routers.manage.send_whatsapp",
                   "app.reminders.send_whatsapp"):
        monkeypatch.setattr(target, fake)
    return box


def _book(start_iso: str):
    return client.post("/api/appointments", json={
        "customer_name": "Ana Pérez", "customer_phone": PHONE, "service_id": 1, "start_at": start_iso,
    })


def _token(manage_url: str) -> dict:
    return {"X-Manage-Token": manage_url.split("#t=")[1]}


def _run_reminders():
    db = SessionLocal()
    try:
        return run_reminders(db)
    finally:
        db.close()


# ---------- QA-01: solo inicios de la grilla ----------
@pytest.mark.parametrize("start", ["2026-11-05T11:13:00", "2026-11-05T11:00:30", "2026-11-05T10:45:00"])
def test_qa01_off_grid_start_is_rejected(start):
    r = _book(start)
    assert r.status_code == 409, r.text
    db = SessionLocal()
    try:
        assert db.query(models.Appointment).count() == 0
    finally:
        db.close()


def test_qa01_grid_still_works_and_reschedule_is_also_validated():
    r = _book(THU_11)
    assert r.status_code == 201, r.text
    h = _token(r.json()["manage_url"])

    bad = client.post("/api/manage/reschedule", headers=h, json={"start_at": "2026-11-05T13:07:00"})
    assert bad.status_code == 409
    ok = client.post("/api/manage/reschedule", headers=h, json={"start_at": "2026-11-05T13:30:00"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["start_at"] == "2026-11-05T13:30:00"


# ---------- QA-02: el recordatorio lleva el enlace ----------
def test_qa02_reminder_includes_working_link_and_rotates_token(clock, sent):
    r = _book(THU_11)
    old = _token(r.json()["manage_url"])
    # Una reprogramación previa debe seguir contando tras rotar el token.
    assert client.post("/api/manage/reschedule", headers=old, json={"start_at": "2026-11-05T11:30:00"}).status_code == 200

    sent.clear()
    clock["now"] = datetime(2026, 11, 4, 18, 0)          # dentro de las 24 h previas
    assert _run_reminders() == {"candidatas": 1, "enviados": 1}

    (_, body), = sent
    assert "te recordamos tu cita" in body
    assert "http://testserver/app/manage.html#t=" in body
    new = _token(body.split("Hazlo aquí: ")[1].strip())

    # El enlace del recordatorio funciona y conserva las reprogramaciones usadas.
    detail = client.get("/api/manage", headers=new)
    assert detail.status_code == 200, detail.text
    assert detail.json()["reschedules_left"] == 1
    # El enlace anterior ya no sirve (solo se guarda un hash por cita).
    assert client.get("/api/manage", headers=old).status_code == 404

    # No se reenvía: el recordatorio ya quedó marcado.
    assert _run_reminders() == {"candidatas": 0, "enviados": 0}


def test_qa02_reminder_creates_link_for_appointments_without_one(clock, sent):
    r = _book(THU_11)
    db = SessionLocal()
    try:   # simula una cita creada antes de HU-5 (sin fila en appointment_links)
        db.query(models.AppointmentLink).delete()
        db.commit()
    finally:
        db.close()

    sent.clear()
    clock["now"] = datetime(2026, 11, 4, 18, 0)
    _run_reminders()
    (_, body), = sent
    h = _token(body.split("Hazlo aquí: ")[1].strip())
    assert client.get("/api/manage", headers=h).json()["start_at"] == THU_11


# ---------- QA-06: reservas simultáneas a la misma franja ----------
def test_qa06_concurrent_bookings_create_a_single_appointment():
    from concurrent.futures import ThreadPoolExecutor

    def book(i):
        # Un cliente por hilo y sin `with`: el `with` arrancaría el programador en cada uno.
        return TestClient(app).post("/api/appointments", json={
            "customer_name": f"Carrera {i}", "customer_phone": PHONE, "service_id": 1, "start_at": THU_11,
        }).status_code

    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(book, range(20)))
    assert codes.count(201) == 1 and codes.count(409) == 19, codes
    db = SessionLocal()
    try:
        assert db.query(models.Appointment).count() == 1
    finally:
        db.close()
