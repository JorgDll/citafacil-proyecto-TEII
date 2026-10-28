"""QA-06: N rondas de 20 reservas simultáneas, cada ronda a una franja distinta.

Uso: BASE_URL=http://localhost:8000 python qa_concurrencia.py [rondas]
Una ronda es doble reserva si se crea más de una cita (201) para la misma franja.
"""
import datetime as dt
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/") + "/api"
rondas = int(sys.argv[1]) if len(sys.argv) > 1 else 20

d = dt.date.today() + dt.timedelta(days=1)
while d.weekday() != 2:            # miércoles: abierto y sin citas del seed
    d += dt.timedelta(days=1)
franjas = [f"{d + dt.timedelta(weeks=w)}T{h:02d}:{m:02d}:00"
           for w in range(4, 12) for h in range(10, 20) for m in (0, 30)][:rondas]


def reservar(args):
    start, i = args
    with httpx.Client(base_url=BASE, timeout=30) as c:
        return c.post("/appointments", json={"service_id": 1, "start_at": start, "customer_name": f"Carrera {i}",
                                             "customer_phone": f"+5076{i:03d}0000"}).status_code


dobles = 0
for start in franjas:
    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(reservar, [(start, i) for i in range(20)]))
    creadas = codes.count(201)
    dobles += creadas > 1
    print(f"{start}: 201={creadas} 409={codes.count(409)} otros={len(codes) - creadas - codes.count(409)}"
          + ("   <-- DOBLE RESERVA" if creadas > 1 else ""))
print(f"\nRondas con doble reserva: {dobles} de {len(franjas)}")
