"""Genera ~12 meses de reservas de demostración para probar los gráficos (HU-3).

Uso:
    python seed_history.py            # crea el historial (no hace nada si ya existe)
    python seed_history.py --reset    # borra SOLO las filas demo y las vuelve a crear

Las citas demo llevan la nota "[demo-historial]" (así --reset no toca reservas reales),
estado "done" y caen en los 365 días anteriores a hoy. El resultado es determinista.
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, time, timedelta

import seed
from app import models
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.utils import local_now

MARKER = "[demo-historial]"
DAYS = 365
# Más demanda hacia el fin de semana; el domingo (cerrado) sale 0 por settings.
WEEKDAY_FACTOR = {0: 1.2, 1: 1.0, 2: 1.2, 3: 1.4, 4: 2.4, 5: 2.0, 6: 1.0}
SERVICE_WEIGHTS = [5, 3, 2, 2, 1]       # popularidad relativa según el orden de los servicios
PHONE = "+56900000000"


def _clear(db) -> int:
    n = db.query(models.Appointment).filter(models.Appointment.notes == MARKER).delete()
    db.commit()
    return n


def run(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if reset:
            print(f"- Borradas {_clear(db)} citas demo.")
        elif db.query(models.Appointment).filter(models.Appointment.notes == MARKER).count():
            print("* Ya existe historial demo; usa --reset para regenerarlo.")
            return

        if db.query(models.Service).count() == 0:
            seed.run()
        services = db.query(models.Service).order_by(models.Service.id).all()
        weights = [SERVICE_WEIGHTS[i % len(SERVICE_WEIGHTS)] for i in range(len(services))]

        rng = random.Random(42)
        today = local_now().date()
        slot_min = settings.slot_interval_minutes
        slots_per_day = (settings.close_hour - settings.open_hour) * 60 // slot_min
        rows = []

        for back in range(DAYS, 0, -1):
            day = today - timedelta(days=back)
            if day.weekday() in settings.closed_weekdays_set:
                continue
            growth = 1 + 0.4 * (DAYS - back) / DAYS                  # +40 % a lo largo del año
            lam = 1.6 * WEEKDAY_FACTOR[day.weekday()] * growth
            n = max(0, min(slots_per_day, round(rng.gauss(lam, 0.8 * math.sqrt(lam)))))

            last_end = None
            for idx in sorted(rng.sample(range(slots_per_day), n)):
                start = datetime.combine(day, time(hour=settings.open_hour)) + timedelta(minutes=slot_min * idx)
                if last_end and start < last_end:                    # sin solapes dentro del día
                    continue
                svc = rng.choices(services, weights=weights)[0]
                end = start + timedelta(minutes=svc.duration_min)
                last_end = end
                rows.append(models.Appointment(
                    customer_name="Cliente demo", customer_phone=PHONE, service_id=svc.id,
                    start_at=start, end_at=end, status=models.STATUS_DONE,
                    notes=MARKER, reminder_sent=True,
                ))

        db.add_all(rows)
        db.commit()
        print(f"+ Creadas {len(rows)} citas demo ({DAYS} dias, {len(services)} servicios).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="borra las citas demo y las regenera")
    run(parser.parse_args().reset)
