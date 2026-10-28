"""Histórico y proyección de demanda (HU-3), calculados sólo a partir de `appointments`.

Una reserva "solicitada" es una cita no cancelada, contada por la fecha de la cita.
Se agrega en Python (no con funciones de fecha SQL) para que funcione igual en SQLite
y PostgreSQL; el volumen de un negocio pequeño lo permite.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .utils import local_now

PRESETS = {"7d": 7, "14d": 14, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
DEFAULT_PRESET = "30d"
MAX_SPAN_DAYS = 1095            # rango libre máximo: 3 años
HORIZONS = (14, 30, 90)
TRAIN_DAYS = 90                 # ventana de entrenamiento de la proyección
MIN_HISTORY_DAYS = 14
MIN_BOOKINGS = 5
Z_80 = 1.28                     # banda de incertidumbre ~80 %
METHOD = "estacionalidad semanal + tendencia lineal"


# ---------- Rangos y consultas ----------
def resolve_range(
    preset: Optional[str], date_from: Optional[date], date_to: Optional[date]
) -> tuple[date, date]:
    """(inicio, fin) inclusivos. Un preset termina hoy; from/to tienen prioridad."""
    if date_from or date_to:
        if not (date_from and date_to):
            raise ValueError("Indica 'from' y 'to' juntos.")
        start, end = date_from, date_to
    else:
        preset = preset or DEFAULT_PRESET
        if preset not in PRESETS:
            raise ValueError(f"Rango inválido. Usa uno de: {', '.join(PRESETS)}.")
        end = local_now().date()
        start = end - timedelta(days=PRESETS[preset] - 1)
    if start > end:
        raise ValueError("'from' no puede ser posterior a 'to'.")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise ValueError(f"El rango no puede superar {MAX_SPAN_DAYS} días.")
    return start, end


def _services(db: Session, service_ids: Optional[list[int]]) -> list[models.Service]:
    q = db.query(models.Service)
    if service_ids:
        q = q.filter(models.Service.id.in_(service_ids))
    return q.order_by(models.Service.id).all()


def fetch_rows(
    db: Session, start: date, end: date, service_ids: Optional[list[int]] = None
) -> list[tuple[datetime, int]]:
    """(start_at, service_id) de las citas no canceladas entre dos días inclusive."""
    q = db.query(models.Appointment.start_at, models.Appointment.service_id).filter(
        models.Appointment.status != models.STATUS_CANCELLED,
        models.Appointment.start_at >= datetime.combine(start, time.min),
        models.Appointment.start_at <= datetime.combine(end, time.max),
    )
    if service_ids:
        q = q.filter(models.Appointment.service_id.in_(service_ids))
    return [(r[0], r[1]) for r in q.all()]


# ---------- Barras: total por servicio ----------
def counts_by_service(
    db: Session, start: date, end: date, service_ids: Optional[list[int]] = None
) -> dict:
    services = _services(db, service_ids)
    totals = {s.id: 0 for s in services}
    for _, sid in fetch_rows(db, start, end, service_ids):
        if sid in totals:
            totals[sid] += 1
    items = [{"service_id": s.id, "name": s.name, "count": totals[s.id]} for s in services]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": sum(totals.values()),
        "items": items,
    }


# ---------- Líneas: serie temporal por servicio ----------
def auto_group_by(start: date, end: date) -> str:
    span = (end - start).days + 1
    return "day" if span <= 31 else ("week" if span <= 182 else "month")


def _bucket(d: date, group_by: str) -> date:
    if group_by == "week":
        return d - timedelta(days=d.weekday())      # semana iniciando lunes
    if group_by == "month":
        return d.replace(day=1)
    return d


def _label(b: date, group_by: str) -> str:
    return b.strftime("%Y-%m") if group_by == "month" else b.isoformat()


def trend(
    db: Session,
    start: date,
    end: date,
    service_ids: Optional[list[int]] = None,
    group_by: Optional[str] = None,
) -> dict:
    group_by = group_by or auto_group_by(start, end)
    if group_by not in ("day", "week", "month"):
        raise ValueError("group_by debe ser day, week o month.")

    # Cubetas ordenadas que cubren todo el rango (con ceros donde no hay citas).
    buckets: list[date] = []
    d = start
    while d <= end:
        b = _bucket(d, group_by)
        if not buckets or buckets[-1] != b:
            buckets.append(b)
        d += timedelta(days=1)
    index = {b: i for i, b in enumerate(buckets)}

    services = _services(db, service_ids)
    series = {s.id: [0] * len(buckets) for s in services}
    for start_at, sid in fetch_rows(db, start, end, service_ids):
        if sid in series:
            series[sid][index[_bucket(start_at.date(), group_by)]] += 1

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "group_by": group_by,
        "labels": [_label(b, group_by) for b in buckets],
        "series": [{"service_id": s.id, "name": s.name, "counts": series[s.id]} for s in services],
    }


# ---------- Proyección ----------
def forecast_demand(
    counts: list[int], first_day: date, horizon: int, closed_weekdays: set[int]
) -> dict:
    """Proyecta la demanda diaria de los `horizon` días siguientes a `counts`.

    `counts` son reservas por día, consecutivas desde `first_day`. Modelo:
    factor por día de la semana (estacionalidad) × recta de tendencia ajustada por
    mínimos cuadrados sobre la serie desestacionalizada. La banda (~80 %) sale de la
    desviación estándar de los residuos. Los días cerrados proyectan 0.
    """
    n, total = len(counts), sum(counts)
    if n < MIN_HISTORY_DAYS or total < MIN_BOOKINGS:
        return {
            "enough_data": False,
            "message": (
                f"Aún no hay datos suficientes para proyectar (se necesitan al menos "
                f"{MIN_HISTORY_DAYS} días de historial y {MIN_BOOKINGS} reservas)."
            ),
            "trend_per_week": 0.0,
            "forecast": [],
        }

    weekday = [(first_day + timedelta(days=i)).weekday() for i in range(n)]
    mean_all = total / n
    factor = {}
    for wd in range(7):
        vals = [c for c, w in zip(counts, weekday) if w == wd]
        factor[wd] = 0.0 if wd in closed_weekdays or not vals else (sum(vals) / len(vals)) / mean_all

    # Recta y' = a + b·t sobre la serie desestacionalizada (sólo días con factor > 0).
    pts = [(i, c / factor[w]) for i, (c, w) in enumerate(zip(counts, weekday)) if factor[w] > 0]
    m = len(pts)
    if m >= 2:
        mt = sum(t for t, _ in pts) / m
        my = sum(y for _, y in pts) / m
        sxx = sum((t - mt) ** 2 for t, _ in pts)
        b = sum((t - mt) * (y - my) for t, y in pts) / sxx if sxx else 0.0
        a = my - b * mt
    else:
        b, a = 0.0, (pts[0][1] if pts else 0.0)

    def level(t: int) -> float:
        return max(0.0, a + b * t)

    residuals = [c - level(i) * factor[w] for i, (c, w) in enumerate(zip(counts, weekday)) if factor[w] > 0]
    sigma = math.sqrt(sum(r * r for r in residuals) / max(1, len(residuals) - 2)) if residuals else 0.0

    forecast = []
    for k in range(horizon):
        t = n + k
        day = first_day + timedelta(days=t)
        f = factor[day.weekday()]
        if f == 0:
            exp = lo = hi = 0.0
        else:
            exp = level(t) * f
            lo, hi = max(0.0, exp - Z_80 * sigma), exp + Z_80 * sigma
        forecast.append({
            "date": day.isoformat(),
            "expected": round(exp, 2),
            "lower": round(lo, 2),
            "upper": round(hi, 2),
        })

    return {
        "enough_data": True,
        "message": None,
        "trend_per_week": round(b * 7, 3),     # variación del promedio diario por semana
        "forecast": forecast,
    }


def forecast(
    db: Session, horizon: int, service_ids: Optional[list[int]] = None, closed_weekdays: Optional[set[int]] = None
) -> dict:
    """Proyección a partir del historial real (últimos 90 días, sin contar hoy)."""
    today = local_now().date()
    yesterday = today - timedelta(days=1)
    rows = fetch_rows(db, today - timedelta(days=TRAIN_DAYS), yesterday, service_ids)

    base = {"horizon": horizon, "method": METHOD, "history": [], "expected_total": 0.0}
    if not rows:
        res = forecast_demand([], today, horizon, set())
        return {**base, **res}

    # Se empieza en la primera reserva de la ventana: los días previos al uso del
    # sistema no son "demanda cero" y sesgarían la tendencia.
    first = min(r[0].date() for r in rows)
    n = (yesterday - first).days + 1
    daily = [0] * n
    for start_at, _ in rows:
        daily[(start_at.date() - first).days] += 1

    res = forecast_demand(
        daily, first, horizon,
        settings.closed_weekdays_set if closed_weekdays is None else closed_weekdays,
    )
    history = [
        {"date": (first + timedelta(days=i)).isoformat(), "count": daily[i]}
        for i in range(max(0, n - 28), n)
    ]
    return {**base, **res, "history": history,
            "expected_total": round(sum(p["expected"] for p in res["forecast"]), 1)}
