"""HU-4: teléfonos internacionales en formato E.164, solo móviles, con selector de país."""
from datetime import timedelta

import phonenumbers
import pytest
from fastapi.testclient import TestClient
from phonenumbers import PhoneNumberFormat, PhoneNumberType

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Appointment
from app.utils import PhoneError, list_countries, local_now, normalize_phone, phone_parts

client = TestClient(app)


def _example_e164(region: str, kind) -> str:
    return phonenumbers.format_number(phonenumbers.example_number_for_type(region, kind), PhoneNumberFormat.E164)


def _book(phone: str):
    sid = client.get("/api/services").json()[0]["id"]
    start = (local_now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
    while start.weekday() in settings.closed_weekdays_set:
        start += timedelta(days=1)
    return client.post("/api/appointments", json={
        "customer_name": "Cliente", "customer_phone": phone, "service_id": sid, "start_at": start.isoformat(),
    })


def _appointments() -> int:
    db = SessionLocal()
    try:
        return db.query(Appointment).count()
    finally:
        db.close()


def test_happy_path_international_booking_countries_and_examples():
    r = _book("+507 6123-4567")
    assert r.status_code == 201, r.text
    assert r.json()["customer_phone"] == "+50761234567"

    countries = client.get("/api/countries").json()
    by_iso = {c["iso"]: c for c in countries}
    assert by_iso["PA"]["dial_code"] == "507" and by_iso["PA"]["example"]
    assert "001" not in by_iso and len(countries) > 200
    assert client.get("/api/config").json()["default_country"] == settings.default_country

    # El placeholder de cada país es un número válido al componerlo con su código.
    for iso in ("PA", "CL", "US", "ES", "DE", "JP", "BR", "AR"):
        c = by_iso[iso]
        assert c["example"], iso
        assert normalize_phone(f"+{c['dial_code']} {c['example']}").startswith(f"+{c['dial_code']}")


def test_edge_only_mobile_numbers_and_invalid_input_are_rejected():
    for region in ("PA", "CL", "ES", "DE"):
        mobile = _example_e164(region, PhoneNumberType.MOBILE)
        fixed = _example_e164(region, PhoneNumberType.FIXED_LINE)
        assert normalize_phone(mobile) == mobile                      # el móvil sí
        with pytest.raises(PhoneError, match="móviles"):              # el fijo no
            normalize_phone(fixed)
        assert _book(fixed).status_code == 422

    for non_mobile in ("+1 800 555 0123", "+1 900 555 0123"):         # gratuito y tarifa premium
        with pytest.raises(PhoneError):
            normalize_phone(non_mobile)

    for bad in ("+507 123", "+507 61234567890", "+507 ABCD1234", "", "+", "abc"):
        with pytest.raises(PhoneError):
            normalize_phone(bad)
    assert _book("+507 123").status_code == 422
    assert _appointments() == 0                                       # ninguna cita se creó por error

    # Formatos equivalentes -> mismo E.164.
    for ok in ("+507 6123 4567", "+507 6123-4567", "(507) 6123-4567", "00507 61234567"):
        assert normalize_phone(ok, region="PA") == "+50761234567", ok


def test_edge_default_country_shared_dial_codes_and_profile_split(monkeypatch):
    # Sin "+" el número se interpreta en el país base configurado.
    monkeypatch.setattr(settings, "default_country", "PA")
    assert normalize_phone("61234567") == "+50761234567"
    monkeypatch.setattr(settings, "default_country", "CL")
    assert normalize_phone("942916570") == "+56942916570"             # regla chilena de siempre
    assert normalize_phone("4291 6570") == "+56942916570"

    # +1 lo comparten varios países: el número completo identifica cuál es.
    us = _example_e164("US", PhoneNumberType.MOBILE)
    ca = _example_e164("CA", PhoneNumberType.MOBILE)
    assert normalize_phone(us) == us and normalize_phone(ca) == ca
    assert phone_parts(us)[0] == "US" and phone_parts(ca)[0] == "CA"
    assert {c["iso"] for c in list_countries() if c["dial_code"] == "1"} >= {"US", "CA"}

    # HU-1: el perfil guardado devuelve país y número nacional para repoblar el selector.
    d = TestClient(app)
    r = d.post("/api/device/remember", json={"customer_name": "Camila Rojas", "customer_phone": "+507 6123-4567"})
    assert r.status_code == 201, r.text
    prof = d.get("/api/device/profile").json()
    assert prof["customer_phone"] == "+50761234567"
    assert (prof["phone_country"], prof["phone_national"]) == ("PA", "61234567")
