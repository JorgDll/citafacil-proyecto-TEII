"""HU-3: histórico (barras/líneas) y proyección de demanda, contando sólo `appointments`."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import models
from app.analytics import forecast_demand
from app.database import SessionLocal
from app.main import app

client = TestClient(app)
AUTH = {"X-Admin-Token": "test-token"}

# Reloj congelado: miércoles 4-nov-2026 12:15 -> hoy = 2026-11-04.
NOW = datetime(2026, 11, 4, 12, 15)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr("app.analytics.local_now", lambda: NOW)


@pytest.fixture
def services():
    """Servicio 1 (Corte) viene de conftest; se añaden 2 (Barba) y 3 (Tinte)."""
    db = SessionLocal()
    db.add_all([
        models.Service(name="Barba", duration_min=20, price=6000, active=True),
        models.Service(name="Tinte", duration_min=60, price=18000, active=True),
    ])
    db.commit()
    db.close()


def _add(start: datetime, service_id: int = 1, status: str = models.STATUS_DONE):
    db = SessionLocal()
    try:
        db.add(models.Appointment(
            customer_name="Cliente", customer_phone="+56987654321", service_id=service_id,
            start_at=start, end_at=start + timedelta(minutes=30), status=status,
        ))
        db.commit()
    finally:
        db.close()


def _get(path: str, **params):
    return client.get(f"/api/admin/analytics/{path}", params=params, headers=AUTH)


def test_happy_path_bars_and_lines_count_requested_services(services):
    _add(datetime(2026, 11, 2, 10, 0), 1)
    _add(datetime(2026, 11, 2, 11, 0), 1)
    _add(datetime(2026, 11, 2, 12, 0), 2)
    _add(datetime(2026, 11, 4, 15, 0), 1)
    _add(datetime(2026, 11, 3, 10, 0), 1, status=models.STATUS_CANCELLED)   # no cuenta

    bars = _get("services", range="7d")
    assert bars.status_code == 200, bars.text
    body = bars.json()
    assert (body["start"], body["end"]) == ("2026-10-29", "2026-11-04")
    assert {i["name"]: i["count"] for i in body["items"]} == {"Corte": 3, "Barba": 1, "Tinte": 0}
    assert body["total"] == 4

    lines = _get("trend", range="7d").json()
    assert lines["group_by"] == "day"
    assert lines["labels"] == [(date(2026, 10, 29) + timedelta(days=i)).isoformat() for i in range(7)]
    by_name = {s["name"]: s["counts"] for s in lines["series"]}
    assert by_name["Corte"] == [0, 0, 0, 0, 2, 0, 1]       # 2-nov y 4-nov
    assert sum(by_name["Barba"]) == 1 and sum(by_name["Tinte"]) == 0


def test_edge_range_boundaries_filters_and_validation(services):
    _add(datetime(2026, 10, 28, 10, 0), 1)     # hoy-7: fuera de 7d
    _add(datetime(2026, 10, 29, 10, 0), 1)     # hoy-6: primer día de 7d
    _add(datetime(2026, 11, 4, 19, 30), 2)     # último día, última franja: dentro

    items = {i["name"]: i["count"] for i in _get("services", range="7d").json()["items"]}
    assert items == {"Corte": 1, "Barba": 1, "Tinte": 0}

    # Rango libre inclusivo en ambos extremos.
    custom = _get("services", **{"from": "2026-10-28", "to": "2026-10-29"}).json()
    assert custom["total"] == 2
    one_day = _get("services", **{"from": "2026-11-04", "to": "2026-11-04"}).json()
    assert one_day["total"] == 1

    # Filtro por servicio.
    only = _get("services", range="30d", service_ids="2").json()
    assert [i["name"] for i in only["items"]] == ["Barba"] and only["total"] == 1

    # Agrupación automática según el tamaño del rango.
    assert _get("trend", range="90d").json()["group_by"] == "week"
    assert _get("trend", range="365d").json()["group_by"] == "month"

    # Validaciones -> 422.
    assert _get("services", **{"from": "2026-11-05", "to": "2026-11-01"}).status_code == 422
    assert _get("services", **{"from": "2020-01-01", "to": "2026-11-04"}).status_code == 422   # > 3 años
    assert _get("services", **{"from": "2026-11-01"}).status_code == 422                        # falta 'to'
    assert _get("services", range="15d").status_code == 422
    assert _get("services", service_ids="a,b").status_code == 422
    assert _get("trend", range="7d", group_by="year").status_code == 422

    # Sólo administradores.
    assert client.get("/api/admin/analytics/services").status_code == 422        # sin cabecera
    assert client.get(
        "/api/admin/analytics/services", headers={"X-Admin-Token": "malo"}
    ).status_code == 401


def test_edge_forecast_keeps_weekly_pattern_and_needs_enough_data():
    # Sin historial: no se inventa una proyección.
    empty = _get("forecast", horizon=14).json()
    assert empty["enough_data"] is False and empty["forecast"] == [] and empty["message"]

    # 12 semanas: viernes 6, sábado 5, lunes-jueves 2, domingo cerrado.
    per_weekday = {0: 2, 1: 2, 2: 2, 3: 2, 4: 6, 5: 5, 6: 0}
    day = date(2026, 8, 10)                                     # lunes
    while day <= date(2026, 11, 3):                             # hasta ayer
        for n in range(per_weekday[day.weekday()]):
            _add(datetime(day.year, day.month, day.day, 10, 0) + timedelta(minutes=30 * n))
        day += timedelta(days=1)

    r = _get("forecast", horizon=14)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enough_data"] is True and body["horizon"] == 14
    assert len(body["history"]) == 28
    fc = body["forecast"]
    assert len(fc) == 14 and fc[0]["date"] == "2026-11-04"      # empieza hoy
    for p in fc:
        assert 0 <= p["lower"] <= p["expected"] <= p["upper"]
    by_date = {p["date"]: p["expected"] for p in fc}
    assert by_date["2026-11-08"] == 0 and by_date["2026-11-15"] == 0    # domingos cerrados
    assert by_date["2026-11-06"] > by_date["2026-11-10"]                # viernes > martes
    assert body["expected_total"] > 0

    assert _get("forecast", horizon=20).status_code == 422


def test_unit_forecast_trend_sign_follows_demand():
    monday = date(2026, 8, 10)
    rising = [2 + i // 7 for i in range(56)]        # sube 1 reserva/día cada semana
    flat = [3] * 56

    up = forecast_demand(rising, monday, 14, closed_weekdays=set())
    assert up["enough_data"] and up["trend_per_week"] > 0.5
    assert up["forecast"][-1]["expected"] > up["forecast"][0]["expected"] - 1   # no cae

    steady = forecast_demand(flat, monday, 14, closed_weekdays=set())
    assert abs(steady["trend_per_week"]) < 0.01
    assert all(abs(p["expected"] - 3) < 0.01 for p in steady["forecast"])
