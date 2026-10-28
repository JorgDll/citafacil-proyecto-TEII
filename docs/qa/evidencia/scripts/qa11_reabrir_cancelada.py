"""QA-11: reabrir desde el panel una cita cancelada cuya franja ya tomó otro cliente.

Uso (desde backend/, BD recién sembrada y sin usuarios del panel):
    PYTHONPATH=. ADMIN_TOKEN=<clave> python ../docs/qa/evidencia/scripts/qa11_reabrir_cancelada.py
"""
import datetime as dt
import os

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
X = {"X-Requested-With": "citafacil"}
d = dt.date.today() + dt.timedelta(days=7)
while d.weekday() != 2:
    d += dt.timedelta(days=1)
s = f"{d}T15:00:00"

a = c.post("/api/appointments", json={"service_id": 1, "start_at": s, "customer_name": "Cliente A", "customer_phone": "+50761230001"}).json()
print("cancelar A por su enlace:", c.post("/api/manage/cancel", headers={"X-Manage-Token": a["manage_url"].split("#t=")[1]}, json={"confirmation": "Cancelar cita"}).status_code)
print("reservar B en la misma franja:", c.post("/api/appointments", json={"service_id": 1, "start_at": s, "customer_name": "Cliente B", "customer_phone": "+50761230002"}).status_code)
c.post("/api/admin/auth/setup", headers=X, json={"setup_token": os.environ["ADMIN_TOKEN"], "username": "dueno", "display_name": "Dueño", "password": "ClaveSegura123"})
r = c.patch(f"/api/admin/appointments/{a['id']}", headers=X, json={"status": "pending"})
print("reabrir A desde el panel:", r.status_code, r.json().get("status"))
activas = [(x["customer_name"], x["status"]) for x in c.get("/api/admin/appointments", headers=X).json()
           if x["start_at"] == s and x["status"] != "cancelled"]
print(f"citas activas en {s}: {activas}")
print("RESULTADO:", "DOBLE RESERVA (QA-11)" if len(activas) > 1 else "ok")
