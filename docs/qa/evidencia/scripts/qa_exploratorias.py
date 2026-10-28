"""Pruebas exploratorias de QA (caja negra) contra un servidor CitaFácil en ejecución.

Uso (BD recién sembrada con `python seed.py`, servidor sin usuarios del panel):
    BASE_URL=http://localhost:8000 ADMIN_TOKEN=<clave> python qa_exploratorias.py

Cada caso imprime [PASA] o [FALLA] con el código esperado y el obtenido.
Al final, `POST /api/admin/reminders/run` dispara los recordatorios: los mensajes
(modo demo) quedan en el log del servidor, que se revisa aparte (QA-02).
"""
import datetime as dt
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/") + "/api"
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
CSRF = {"X-Requested-With": "citafacil"}
fallos = 0


def check(caso, esperado, r):
    global fallos
    ok = r.status_code == esperado
    fallos += not ok
    print(f"[{'PASA ' if ok else 'FALLA'}] {caso}: esperado {esperado}, obtenido {r.status_code} -> {r.text[:110]}")
    return r


def dia(semanas):
    """Martes dentro de `semanas` semanas (abierto, siempre en el futuro)."""
    d = dt.date.today() + dt.timedelta(days=1)
    while d.weekday() != 1:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=semanas - 1)


def at(semanas, hhmm):
    return f"{dia(semanas)}T{hhmm}:00" if hhmm.count(":") == 1 else f"{dia(semanas)}T{hhmm}"


def reservar(c, start, phone="+50761234567", service_id=1, name="QA"):
    return c.post("/appointments", json={"service_id": service_id, "start_at": start,
                                         "customer_name": name, "customer_phone": phone})


def token(r):
    return {"X-Manage-Token": r.json()["manage_url"].split("#t=")[1]}


c = httpx.Client(base_url=BASE, timeout=20)

print("== Concurrencia (HU-2): 20 reservas simultáneas a la misma franja ==")
start = at(1, "11:00")
with ThreadPoolExecutor(20) as ex:
    codes = list(ex.map(lambda i: reservar(httpx.Client(base_url=BASE), start, f"+5076123{i:04d}").status_code, range(20)))
ok = codes.count(201) == 1 and codes.count(409) == 19
fallos += not ok
print(f"[{'PASA ' if ok else 'FALLA'}] 201={codes.count(201)} 409={codes.count(409)} (esperado 1 y 19)")

print("\n== QA-01 (HU-2/HU-5): solo inicios de la grilla ==")
check("reserva 10:13 (fuera de la grilla)", 409, reservar(c, at(2, "10:13")))
check("reserva 10:00:30 (segundos)", 409, reservar(c, at(2, "10:00:30"), "+50761230001"))
check("reserva 10:30 (en la grilla)", 201, reservar(c, at(2, "10:30"), "+50761230002"))

print("\n== HU-4: teléfonos internacionales ==")
for i, (ph, esp) in enumerate([("+507 6123-4567", 201), ("61234567", 201), ("+507 223-4567", 422),
                               ("+1 800 555 0100", 422), ("abc", 422), ("+56 9 4291 6570", 201)]):
    check(f"teléfono {ph!r}", esp, reservar(c, at(3, f"{10 + i}:00"), ph, service_id=3))

print("\n== HU-5: autogestión por enlace ==")
r = check("reserva Corte + Barba 12:00", 201, reservar(c, at(1, "12:00"), "+50761112222", 2, "<script>alert(1)</script> Ana"))
h = token(r)
check("detalle con el token", 200, c.get("/manage", headers=h))
check("token por query string (no cabecera)", 404, c.get(f"/manage?t={h['X-Manage-Token']}"))
check("reprogramar 12:30 (solapa consigo misma, 45 min)", 200, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "12:30")}))
check("reprogramar a 11:00 (ocupada)", 409, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "11:00")}))
check("reprogramar fuera de horario 19:45", 409, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "19:45")}))
check("QA-01: reprogramar a 13:07", 409, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "13:07")}))
libres = c.get("/availability", params={"service_id": 2, "date": str(dia(1))}).json()
ok = "12:00" not in libres and "11:30" in libres
fallos += not ok
print(f"[{'PASA ' if ok else 'FALLA'}] disponibilidad tras mover a 12:30: 11:30 libre, 12:00 ocupada por la propia cita -> {libres}")
check("reprogramar #2 a 14:00", 200, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "14:00")}))
check("reprogramar #3 (máximo 2)", 409, c.post("/manage/reschedule", headers=h, json={"start_at": at(1, "15:00")}))
check("cancelar sin texto de confirmación", 422, c.post("/manage/cancel", headers=h, json={}))
check("cancelar con '  cancelar   CITA '", 200, c.post("/manage/cancel", headers=h, json={"confirmation": "  cancelar   CITA "}))
check("token revocado tras cancelar", 404, c.get("/manage", headers=h))

print("\n== HU-6: cuentas, permisos y auditoría ==")
o = httpx.Client(base_url=BASE + "/admin", headers=CSRF)
check("X-Admin-Token antiguo", 401, o.get("/appointments", headers={"X-Admin-Token": ADMIN_TOKEN}))
check("instalación con clave incorrecta", 403, o.post("/auth/setup", json={"setup_token": "mala", "username": "dueno", "display_name": "Dueño QA", "password": "ClaveSegura123"}))
check("instalación correcta", 200, o.post("/auth/setup", json={"setup_token": ADMIN_TOKEN, "username": "dueno", "display_name": "Dueño QA", "password": "ClaveSegura123"}))
check("instalación repetida", 409, o.post("/auth/setup", json={"setup_token": ADMIN_TOKEN, "username": "otro", "display_name": "Otro", "password": "ClaveSegura123"}))
rosa_id = check("crear recepcionista", 201, o.post("/users", json={"username": "rosa", "display_name": "Rosa", "role": "reception", "password": "Temporal12345"})).json()["id"]
check("QA-03: crear servicio con HTML en el nombre", 201, o.post("/services", json={"name": "<img src=x onerror=alert(1)>", "duration_min": 30, "price": 1000}))
rc = httpx.Client(base_url=BASE + "/admin", headers=CSRF)
check("login recepcionista", 200, rc.post("/auth/login", json={"username": "rosa", "password": "Temporal12345"}))
check("listar antes de cambiar la clave temporal", 403, rc.get("/appointments"))
check("cambiar clave", 200, rc.post("/auth/password", json={"current_password": "Temporal12345", "new_password": "RosaNueva12345"}))
citas = check("listar citas", 200, rc.get("/appointments")).json()
aid = next(a["id"] for a in citas if a["status"] == "pending")   # seed.py deja las suyas confirmadas
check("confirmar cita pendiente", 200, rc.patch(f"/appointments/{aid}", json={"status": "confirmed"}))
check("eliminar cita (sin permiso)", 403, rc.delete(f"/appointments/{aid}"))
check("crear servicio (sin permiso)", 403, rc.post("/services", json={"name": "X", "duration_min": 30, "price": 1}))
check("ver auditoría (sin permiso)", 403, rc.get("/audit"))
check("darse permisos a sí misma", 403, rc.patch(f"/users/{rosa_id}", json={"permissions": ["users.manage"]}))
audit = check("dueño ve la auditoría", 200, o.get("/audit", params={"limit": 50})).json()
acciones = sorted({i["action"] for i in audit["items"]})
print(f"        acciones registradas: {acciones}")
ok = {"appointment.confirmed", "auth.login", "auth.password_changed", "user.created"} <= set(acciones)
fallos += not ok
print(f"[{'PASA ' if ok else 'FALLA'}] la auditoría registra la confirmación de la recepcionista, su acceso, su cambio de clave y su alta")
check("dueño desactiva a la recepcionista", 200, o.patch(f"/users/{rosa_id}", json={"active": False}))
check("sesión abierta de la recepcionista tras desactivarla", 401, rc.get("/appointments"))
check("QA-02: disparar recordatorios (ver log del servidor)", 200, o.post("/reminders/run"))
lc = httpx.Client(base_url=BASE + "/admin", headers=CSRF)
for _ in range(5):
    lc.post("/auth/login", json={"username": "dueno", "password": "mala"})
check("clave correcta tras 5 fallos (bloqueo)", 429, lc.post("/auth/login", json={"username": "dueno", "password": "ClaveSegura123"}))
check("usuario inexistente (mismo mensaje)", 401, lc.post("/auth/login", json={"username": "nadie", "password": "mala"}))

print(f"\nTOTAL: {'sin fallos' if not fallos else f'{fallos} caso(s) fallan'}")
sys.exit(1 if fallos else 0)
