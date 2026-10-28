"""HU-5: el cliente cancela o reprograma su cita desde un enlace personal."""
import hashlib
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app

client = TestClient(app)
PHONE = "+56 9 4291 6570"

# Miércoles 4-nov-2026 12:15 (domingo cerrado). `clock` permite mover el reloj.
NOW = datetime(2026, 11, 4, 12, 15)
THU_11 = "2026-11-05T11:00:00"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr("app.availability.local_now", lambda: state["now"])
    monkeypatch.setattr("app.manage.local_now", lambda: state["now"])
    return state


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    """Intercepta los WhatsApp: lista de (teléfono, texto)."""
    box = []
    monkeypatch.setattr("app.routers.public.send_whatsapp", lambda to, body: box.append((to, body)))
    monkeypatch.setattr("app.routers.manage.send_whatsapp", lambda to, body: box.append((to, body)))
    return box


def _book(start_iso: str, service_id: int = 1, name: str = "Ana Pérez"):
    r = client.post("/api/appointments", json={
        "customer_name": name, "customer_phone": PHONE, "service_id": service_id, "start_at": start_iso,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    return body, {"X-Manage-Token": body["manage_url"].split("#t=")[1]}


def _db_get(model, **filters):
    db = SessionLocal()
    try:
        row = db.query(model).filter_by(**filters).first()
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def _set(appt_id: int, **fields):
    db = SessionLocal()
    try:
        db.query(models.Appointment).filter_by(id=appt_id).update(fields)
        db.commit()
    finally:
        db.close()


def _links() -> int:
    db = SessionLocal()
    try:
        return db.query(models.AppointmentLink).count()
    finally:
        db.close()


def test_happy_path_link_in_whatsapp_cancel_with_typed_confirmation_revokes_link(sent):
    appt, h = _book(THU_11)
    token = h["X-Manage-Token"]

    # El enlace va en la respuesta y en el WhatsApp de confirmación.
    assert appt["manage_url"] == f"http://testserver/app/manage.html#t={token}"
    assert len(sent) == 1 and sent[0][0] == "+56942916570" and appt["manage_url"] in sent[0][1]

    # En la BD sólo hay el SHA-256, nunca el token.
    link = _db_get(models.AppointmentLink, appointment_id=appt["id"])
    assert link.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (link.token_hash, str(link.appointment_id))

    # Detalle: nombre de pila, sin teléfono.
    detail = client.get("/api/manage", headers=h)
    assert detail.status_code == 200
    d = detail.json()
    assert d["customer_first_name"] == "Ana" and d["can_cancel"] and d["can_reschedule"]
    assert d["reschedules_left"] == 2 and "customer_phone" not in d and "4291" not in detail.text

    # Cancelar exige escribir "Cancelar cita": sin eso la cita y el enlace no se tocan.
    for bad in ("", "cancelar", "Cancelar cita por favor", "Cancelar"):
        assert client.post("/api/manage/cancel", json={"confirmation": bad}, headers=h).status_code == 422, bad
    assert client.post("/api/manage/cancel", json={}, headers=h).status_code == 422
    assert _db_get(models.Appointment, id=appt["id"]).status == models.STATUS_PENDING and _links() == 1
    assert len(sent) == 1

    # Con el texto (mayúsculas y espacios aparte) se cancela, se libera la hora y se avisa.
    ok = client.post("/api/manage/cancel", json={"confirmation": "  cancelar   CITA "}, headers=h)
    assert ok.status_code == 200, ok.text
    assert _db_get(models.Appointment, id=appt["id"]).status == models.STATUS_CANCELLED
    assert "11:00" in client.get("/api/availability?service_id=1&date=2026-11-05").json()
    assert len(sent) == 2 and "cancelada" in sent[1][1]

    # El enlace queda inservible para todo.
    assert _links() == 0
    assert client.get("/api/manage", headers=h).status_code == 404
    assert client.post("/api/manage/cancel", json={"confirmation": "Cancelar cita"}, headers=h).status_code == 404
    assert client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T15:00:00"}, headers=h).status_code == 404
    assert client.get("/api/manage/schedule?date=2026-11-05", headers=h).status_code == 404


def test_edge_reschedule_rules_own_slot_cap_and_reset(sent):
    db = SessionLocal()
    db.add(models.Service(name="Largo", duration_min=45, price=12000, active=True))
    db.commit()
    long_id = db.query(models.Service).filter_by(name="Largo").one().id
    db.close()

    appt, h = _book(THU_11, service_id=long_id)              # 11:00–11:45
    other, _ = _book("2026-11-05T13:00:00", name="Otra Persona")
    _set(appt["id"], status=models.STATUS_CONFIRMED, reminder_sent=True)

    # Correrse 30 min solapa con la propia cita: debe permitirse (se excluye a sí misma).
    r = client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T11:30:00"}, headers=h)
    assert r.status_code == 200, r.text
    moved = _db_get(models.Appointment, id=appt["id"])
    assert (moved.start_at.hour, moved.start_at.minute, moved.end_at.minute) == (11, 30, 15)
    assert moved.status == models.STATUS_PENDING and moved.reminder_sent is False
    assert _db_get(models.AppointmentLink, appointment_id=appt["id"]).reschedule_count == 1
    assert "reprogramada" in sent[-1][1]

    # La hora anterior queda libre para otros y la nueva queda ocupada.
    slots = {s["time"]: s for s in client.get("/api/schedule?service_id=1&date=2026-11-05").json()}
    assert slots["11:00"]["available"] and slots["11:30"]["reason"] == "booked"

    # Rechazos: franja de otra persona, misma hora, pasado, fuera de horario y domingo.
    for bad in ("2026-11-05T13:00:00", "2026-11-05T11:30:00", "2026-11-03T11:00:00",
                "2026-11-05T21:00:00", "2026-11-08T11:00:00"):
        assert client.post("/api/manage/reschedule", json={"start_at": bad}, headers=h).status_code == 409, bad
    assert _db_get(models.Appointment, id=appt["id"]).start_at == moved.start_at
    assert _db_get(models.Appointment, id=other["id"]).start_at.hour == 13

    # Segunda reprogramación OK; la tercera supera el máximo, pero cancelar sigue permitido.
    assert client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T15:00:00"}, headers=h).status_code == 200
    third = client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T16:00:00"}, headers=h)
    assert third.status_code == 409 and "máximo" in third.json()["detail"]
    d = client.get("/api/manage", headers=h).json()
    assert d["can_reschedule"] is False and d["can_cancel"] is True and d["reschedules_left"] == 0
    assert client.post("/api/manage/cancel", json={"confirmation": "Cancelar cita"}, headers=h).status_code == 200


def test_edge_token_scope_cutoff_status_and_own_schedule(clock):
    a, ha = _book(THU_11)
    b, hb = _book("2026-11-05T15:00:00", name="Beto Díaz")
    assert ha != hb

    # Token ausente o inventado -> 404 en todo; el token de A solo mueve A.
    for headers in ({}, {"X-Manage-Token": "inventado"}):
        assert client.get("/api/manage", headers=headers).status_code == 404
        assert client.get("/api/manage/calendar?month=2026-11", headers=headers).status_code == 404
    assert client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T12:00:00"}, headers=ha).status_code == 200
    assert _db_get(models.Appointment, id=a["id"]).start_at.hour == 12
    assert _db_get(models.Appointment, id=b["id"]).start_at.hour == 15

    # Plazo: exactamente 2 h antes se permite; 1 h 59 min no.
    clock["now"] = datetime(2026, 11, 5, 10, 0)          # cita de A a las 12:00
    assert client.get("/api/manage", headers=ha).json()["can_cancel"] is True
    clock["now"] = datetime(2026, 11, 5, 10, 1)
    late = client.get("/api/manage", headers=ha).json()
    assert late["can_cancel"] is False and late["can_reschedule"] is False
    assert "Faltan menos de 2 horas" in late["reason"]
    assert client.post("/api/manage/cancel", json={"confirmation": "Cancelar cita"}, headers=ha).status_code == 409
    assert client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T17:00:00"}, headers=ha).status_code == 409
    assert _db_get(models.Appointment, id=a["id"]).status != models.STATUS_CANCELLED

    # Estados que no admiten cambios.
    clock["now"] = NOW
    _set(b["id"], status=models.STATUS_DONE)
    assert "realizada" in client.get("/api/manage", headers=hb).json()["reason"]
    _set(b["id"], status=models.STATUS_CANCELLED)                      # cancelada por el admin
    assert client.post("/api/manage/reschedule", json={"start_at": "2026-11-05T17:00:00"}, headers=hb).status_code == 409
    _set(b["id"], status=models.STATUS_PENDING)
    clock["now"] = datetime(2026, 11, 6, 9, 0)                         # después de la cita
    assert client.get("/api/manage", headers=hb).json()["reason"] == "La cita ya pasó."

    # El calendario/franjas del enlace no cuentan la propia cita como ocupada (el público sí).
    clock["now"] = NOW
    own = {s["time"]: s for s in client.get("/api/manage/schedule?date=2026-11-05", headers=ha).json()}
    public = {s["time"]: s for s in client.get("/api/schedule?service_id=1&date=2026-11-05").json()}
    assert own["12:00"]["available"] is True and public["12:00"]["reason"] == "booked"
    assert own["15:00"]["reason"] == "booked"                           # la de Beto sí sigue ocupada
    assert len(client.get("/api/manage/calendar?month=2026-11", headers=ha).json()) == 30
    assert client.get("/api/manage/calendar?month=2026-13", headers=ha).status_code == 422
