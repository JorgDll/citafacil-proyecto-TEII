"""Lógica de disponibilidad: genera horarios libres y evita el doble-booking."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .utils import local_now

REASON_PAST = "past"
REASON_BOOKED = "booked"


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True si dos intervalos [inicio, fin) se solapan."""
    return a_start < b_end and b_start < a_end


def _booked_between(db: Session, first_day: date, last_day: date) -> list[models.Appointment]:
    """Citas no canceladas que empiezan entre dos días (ambos incluidos)."""
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.status != models.STATUS_CANCELLED,
            models.Appointment.start_at >= datetime.combine(first_day, time.min),
            models.Appointment.start_at <= datetime.combine(last_day, time.max),
        )
        .all()
    )


def _booked_that_day(db: Session, day: date) -> list[models.Appointment]:
    return _booked_between(db, day, day)


def build_day_slots(
    db: Session,
    service: models.Service,
    day: date,
    booked: Optional[list[models.Appointment]] = None,
    exclude_id: Optional[int] = None,
) -> list[dict]:
    """TODAS las franjas del día para un servicio, con su estado.

    Cada elemento: {"time": "HH:MM", "available": bool, "reason": None|"past"|"booked"}.
    Un día cerrado no tiene franjas. `booked` permite reutilizar una consulta ya hecha.
    """
    if day.weekday() in settings.closed_weekdays_set:
        return []

    duration = timedelta(minutes=service.duration_min)
    open_dt = datetime.combine(day, time(hour=settings.open_hour))
    close_dt = datetime.combine(day, time(hour=settings.close_hour))
    if booked is None:
        booked = _booked_that_day(db, day)
    if exclude_id is not None:                       # reprogramación: ignorar la propia cita
        booked = [b for b in booked if b.id != exclude_id]
    now = local_now()
    step = timedelta(minutes=settings.slot_interval_minutes)

    slots: list[dict] = []
    cursor = open_dt
    while cursor + duration <= close_dt:
        slot_end = cursor + duration
        if cursor <= now:  # no se puede reservar una hora ya pasada
            reason = REASON_PAST
        elif any(_overlaps(cursor, slot_end, b.start_at, b.end_at) for b in booked):
            reason = REASON_BOOKED
        else:
            reason = None
        slots.append({"time": cursor.strftime("%H:%M"), "available": reason is None, "reason": reason})
        cursor += step
    return slots


def generate_slots(db: Session, service: models.Service, day: date) -> list[str]:
    """Horas 'HH:MM' disponibles para un servicio en un día dado."""
    return [s["time"] for s in build_day_slots(db, service, day) if s["available"]]


def month_overview(
    db: Session, service: models.Service, year: int, month: int, exclude_id: Optional[int] = None
) -> list[dict]:
    """Estado de cada día del mes: past | closed | full | available (+ franjas libres)."""
    days_in_month = calendar.monthrange(year, month)[1]
    first, last = date(year, month, 1), date(year, month, days_in_month)

    # Una sola consulta para todo el mes, agrupada por día.
    by_day: dict[date, list[models.Appointment]] = {}
    for appt in _booked_between(db, first, last):
        by_day.setdefault(appt.start_at.date(), []).append(appt)

    today = local_now().date()
    result: list[dict] = []
    for n in range(1, days_in_month + 1):
        day = date(year, month, n)
        if day < today:
            status, free = "past", 0
        elif day.weekday() in settings.closed_weekdays_set:
            status, free = "closed", 0
        else:
            free = sum(1 for s in build_day_slots(db, service, day, by_day.get(day, []), exclude_id) if s["available"])
            status = "available" if free else "full"
        result.append({"date": day.isoformat(), "status": status, "free": free})
    return result


def is_slot_free(
    db: Session, service: models.Service, start_at: datetime, exclude_id: Optional[int] = None
) -> bool:
    """Valida que un inicio concreto esté dentro de horario y libre."""
    if start_at.weekday() in settings.closed_weekdays_set:
        return False

    end_at = start_at + timedelta(minutes=service.duration_min)
    open_dt = datetime.combine(start_at.date(), time(hour=settings.open_hour))
    close_dt = datetime.combine(start_at.date(), time(hour=settings.close_hour))
    if start_at < open_dt or end_at > close_dt:
        return False
    # Solo inicios de la grilla (p. ej. 10:00, 10:30): una cita a las 10:13 bloquearía
    # dos franjas a la vez y dejaría huecos que nadie puede reservar.
    if (start_at - open_dt) % timedelta(minutes=settings.slot_interval_minutes):
        return False
    if start_at <= local_now():
        return False

    booked = [b for b in _booked_that_day(db, start_at.date()) if b.id != exclude_id]
    return not any(_overlaps(start_at, end_at, b.start_at, b.end_at) for b in booked)
