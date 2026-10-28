"""HU-6: cuentas del panel con roles/permisos y registro de actividad."""
import hashlib
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import models
from app.auth import hash_password, verify_password
from app.database import SessionLocal
from app.main import app
from app.utils import local_now

from conftest import CSRF, STAFF_PASSWORD, login_client, make_staff_user

PHONE = "+56942916570"
SETUP_TOKEN = "test-token"                   # ADMIN_TOKEN de los tests: solo sirve para instalar


def _add_appt(name="Camila Rojas", phone=PHONE, hours_ahead=48, status=models.STATUS_PENDING) -> int:
    start = (local_now() + timedelta(hours=hours_ahead)).replace(minute=0, second=0, microsecond=0)
    db = SessionLocal()
    try:
        a = models.Appointment(customer_name=name, customer_phone=phone, service_id=1, start_at=start,
                               end_at=start + timedelta(minutes=30), status=status)
        db.add(a)
        db.commit()
        return a.id
    finally:
        db.close()


def _row(model, **filters):
    db = SessionLocal()
    try:
        r = db.query(model).filter_by(**filters).first()
        if r is not None:
            db.expunge(r)
        return r
    finally:
        db.close()


def _audit(owner, **params):
    r = owner.get("/api/admin/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_staff_flow_setup_roles_forced_password_change_and_audit():
    c = TestClient(app, headers=CSRF)
    assert c.get("/api/admin/auth/setup-status").json() == {"needs_setup": True}

    # La clave de instalación (ADMIN_TOKEN) crea al primer propietario y entra.
    bad = c.post("/api/admin/auth/setup", json={"setup_token": "mala", "username": "dueno",
                                                "display_name": "Dueña", "password": STAFF_PASSWORD})
    assert bad.status_code == 403
    ok = c.post("/api/admin/auth/setup", json={"setup_token": SETUP_TOKEN, "username": "Dueno",
                                               "display_name": "Dueña", "password": STAFF_PASSWORD})
    assert ok.status_code == 200, ok.text
    cookie = ok.headers["set-cookie"].lower()
    assert "citafacil_admin=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert ok.json()["role"] == "owner" and "users.manage" in ok.json()["permissions"]
    assert c.get("/api/admin/auth/setup-status").json() == {"needs_setup": False}

    # El propietario crea a una recepcionista con clave temporal.
    r = c.post("/api/admin/users", json={"username": "rosa", "display_name": "Rosa Pérez",
                                         "role": "reception", "password": "temporal-1234567"})
    assert r.status_code == 201, r.text
    assert r.json()["must_change_password"] is True and "appointments.delete" not in r.json()["permissions"]

    # Rosa entra, pero hasta cambiar la clave solo puede cambiarla o salir.
    rosa = login_client("rosa", "temporal-1234567")
    assert rosa.get("/api/admin/auth/me").json()["must_change_password"] is True
    blocked = rosa.get("/api/admin/appointments")
    assert blocked.status_code == 403 and "cambiar tu contraseña" in blocked.json()["detail"]
    assert rosa.post("/api/admin/auth/password", json={
        "current_password": "temporal-1234567", "new_password": "clave-nueva-segura-9"}).status_code == 200
    assert rosa.get("/api/admin/appointments").status_code == 200

    # Rosa confirma y cancela; eliminar no le corresponde; la dueña elimina.
    a1, a2, a3 = _add_appt("Ana Gómez"), _add_appt("Beto Díaz"), _add_appt("Carla Ruiz")
    assert rosa.patch(f"/api/admin/appointments/{a1}", json={"status": "confirmed"}).status_code == 200
    assert rosa.patch(f"/api/admin/appointments/{a2}", json={"status": "cancelled"}).status_code == 200
    assert rosa.delete(f"/api/admin/appointments/{a3}").status_code == 403
    assert c.delete(f"/api/admin/appointments/{a3}").status_code == 200

    # El registro dice quién hizo cada cosa.
    items = _audit(c, **{"action": "appointment."})["items"]
    by_action = {i["action"]: i for i in items}
    assert by_action["appointment.confirmed"]["actor_name"] == "Rosa Pérez"
    assert by_action["appointment.confirmed"]["detail"]["customer"] == "Ana Gómez"
    assert by_action["appointment.cancelled"]["actor_name"] == "Rosa Pérez"
    deleted = by_action["appointment.deleted"]
    assert deleted["actor_name"] == "Dueña" and deleted["actor_type"] == "staff"
    assert deleted["detail"]["customer"] == "Carla Ruiz" and deleted["detail"]["status"] == "pending"
    assert "+56" not in json.dumps(items)                      # nunca teléfonos completos
    assert {"auth.login", "user.created", "auth.password_changed"} <= {i["action"] for i in _audit(c)["items"]}


def test_edge_permission_matrix_phone_masking_csrf_and_legacy_token():
    from app import permissions as perms

    owner = login_client_for("dueno", "owner")
    a1 = _add_appt()

    # Cada endpoint protegido: 403 sin su permiso y distinto de 403 con solo ese permiso.
    matrix = [
        ("get", "/api/admin/appointments", None, "appointments.view"),
        ("get", "/api/admin/stats", None, "appointments.view"),
        ("patch", f"/api/admin/appointments/{a1}", {"status": "confirmed"}, "appointments.confirm"),
        ("patch", f"/api/admin/appointments/{a1}", {"status": "cancelled"}, "appointments.cancel"),
        ("delete", "/api/admin/appointments/9999", None, "appointments.delete"),
        ("post", "/api/admin/services", {"name": "Nuevo", "duration_min": 30, "price": 1000}, "services.manage"),
        ("put", "/api/admin/services/1", {"price": 9000}, "services.manage"),
        ("delete", "/api/admin/services/9999", None, "services.manage"),
        ("post", "/api/admin/reminders/run", None, "reminders.run"),
        ("get", "/api/admin/analytics/services", None, "analytics.view"),
        ("get", "/api/admin/users", None, "users.manage"),
        ("get", "/api/admin/permissions", None, "users.manage"),
        ("get", "/api/admin/audit", None, "audit.view"),
    ]
    for i, (method, path, body, needed) in enumerate(matrix):
        without = login_client_for(f"sin{i}", "viewer", [p for p in perms.ALL_PERMISSIONS if p != needed])
        only = login_client_for(f"solo{i}", "viewer", [needed])
        kw = {"json": body} if body is not None else {}
        assert getattr(without, method)(path, **kw).status_code == 403, (method, path, needed)
        assert getattr(only, method)(path, **kw).status_code != 403, (method, path, needed)

    # La lista de servicios sirve a quien ve reservas, gestiona servicios o ve análisis.
    for p in ("appointments.view", "services.manage", "analytics.view"):
        assert login_client_for(f"s_{p}", "viewer", [p]).get("/api/admin/services").status_code == 200
    assert login_client_for("nada", "viewer", ["audit.view"]).get("/api/admin/services").status_code == 403

    # Teléfonos enmascarados sin `customers.phones`.
    masked = login_client_for("vista", "viewer", ["appointments.view"]).get("/api/admin/appointments").json()[0]
    assert masked["customer_phone"] == "+56 ****6570"
    full = login_client_for("vista2", "viewer", ["appointments.view", "customers.phones"]).get("/api/admin/appointments").json()[0]
    assert full["customer_phone"] == PHONE
    # ...y también en la respuesta del PATCH.
    only_confirm = login_client_for("conf", "viewer", ["appointments.confirm"])
    assert only_confirm.patch(f"/api/admin/appointments/{a1}", json={"status": "confirmed"}).json()["customer_phone"] == "+56 ****6570"

    # Sin sesión, token compartido antiguo, y CSRF.
    anon = TestClient(app, headers=CSRF)
    assert anon.get("/api/admin/appointments").status_code == 401
    assert anon.get("/api/admin/appointments", headers={"X-Admin-Token": SETUP_TOKEN}).status_code == 401
    assert owner.post("/api/admin/services", json={"name": "X1", "duration_min": 30, "price": 1},
                      headers={"X-Requested-With": "otro-sitio"}).status_code == 403
    assert owner.post("/api/admin/services", json={"name": "X1", "duration_min": 30, "price": 1}).status_code == 201

    # La instalación inicial ya no se puede repetir ni con la clave correcta.
    again = anon.post("/api/admin/auth/setup", json={"setup_token": SETUP_TOKEN, "username": "intruso",
                                                     "display_name": "Intruso", "password": STAFF_PASSWORD})
    assert again.status_code == 409


def login_client_for(username, role, permissions=None):
    make_staff_user(username, role, permissions)
    return login_client(username)


def test_edge_account_security_lockout_hashes_sessions_and_owner_rules():
    # --- hash de contraseña: salado, verificable y no manipulable
    h1, h2 = hash_password("una-clave-larga-1"), hash_password("una-clave-larga-1")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("una-clave-larga-1", h1) and not verify_password("otra", h1)
    assert not verify_password("x", "scrypt$basura") and not verify_password("x", "")

    owner = login_client_for("dueno", "owner")
    ana_id = make_staff_user("ana", "reception")
    unknown = TestClient(app, headers=CSRF)

    # --- BD: solo hash de contraseña y de sesión
    stored = _row(models.StaffUser, username="ana")
    assert stored.password_hash.startswith("scrypt$") and STAFF_PASSWORD not in stored.password_hash
    ana = login_client("ana")
    token = ana.cookies.get("citafacil_admin")
    sess = _row(models.StaffSession, user_id=ana_id)
    assert sess.token_hash != token and len(sess.token_hash) == 64

    # --- mismo mensaje para usuario inexistente y contraseña errónea
    r1 = unknown.post("/api/admin/auth/login", json={"username": "fantasma", "password": "lo-que-sea-123"})
    r2 = unknown.post("/api/admin/auth/login", json={"username": "ana", "password": "lo-que-sea-123"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()

    # --- bloqueo: el 5.º fallo seguido bloquea; con la clave correcta sigue bloqueado hasta que pasa el plazo
    # (el intento con clave errónea de arriba ya contó 1; con 3 más son 4 y un acierto reinicia el contador)
    for _ in range(3):
        unknown.post("/api/admin/auth/login", json={"username": "ana", "password": "mala-clave-123"})
    assert unknown.post("/api/admin/auth/login", json={"username": "ana", "password": STAFF_PASSWORD}).status_code == 200
    for _ in range(5):                                                        # el acierto reinició el contador
        assert unknown.post("/api/admin/auth/login", json={"username": "ana", "password": "mala-clave-123"}).status_code == 401
    locked = unknown.post("/api/admin/auth/login", json={"username": "ana", "password": STAFF_PASSWORD})
    assert locked.status_code == 429 and "bloqueada" in locked.json()["detail"]
    db = SessionLocal()
    db.query(models.StaffUser).filter_by(username="ana").update({"locked_until": datetime.utcnow() - timedelta(minutes=1)})
    db.commit()
    db.close()
    assert unknown.post("/api/admin/auth/login", json={"username": "ana", "password": STAFF_PASSWORD}).status_code == 200
    assert any(i["action"] == "auth.login_failed" for i in _audit(owner)["items"])

    # --- sesión vencida
    ana = login_client("ana")
    db = SessionLocal()
    db.query(models.StaffSession).filter_by(user_id=ana_id).update({"expires_at": datetime.utcnow() - timedelta(seconds=1)})
    db.commit()
    db.close()
    expired_hash = hashlib.sha256(ana.cookies.get("citafacil_admin").encode()).hexdigest()
    assert ana.get("/api/admin/appointments").status_code == 401
    assert _row(models.StaffSession, token_hash=expired_hash) is None            # la sesión vencida se elimina

    # --- desactivar revoca sesiones y bloquea la entrada; reactivar la devuelve
    ana = login_client("ana")
    assert owner.patch(f"/api/admin/users/{ana_id}", json={"active": False}).status_code == 200
    assert ana.get("/api/admin/appointments").status_code == 401
    assert unknown.post("/api/admin/auth/login", json={"username": "ana", "password": STAFF_PASSWORD}).status_code == 401
    assert owner.patch(f"/api/admin/users/{ana_id}", json={"active": True}).status_code == 200
    ana = login_client("ana")

    # --- cambiar la contraseña cierra las demás sesiones (la actual sigue)
    other_device = login_client("ana")
    assert ana.post("/api/admin/auth/password", json={"current_password": "equivocada-123", "new_password": "otra-clave-larga-1"}).status_code == 403
    assert ana.post("/api/admin/auth/password", json={"current_password": STAFF_PASSWORD, "new_password": "corta"}).status_code == 422
    assert ana.post("/api/admin/auth/password", json={"current_password": STAFF_PASSWORD, "new_password": STAFF_PASSWORD}).status_code == 422
    assert ana.post("/api/admin/auth/password", json={"current_password": STAFF_PASSWORD, "new_password": "otra-clave-larga-1"}).status_code == 200
    assert ana.get("/api/admin/auth/me").status_code == 200 and other_device.get("/api/admin/auth/me").status_code == 401

    # --- política de contraseña al crear usuarios
    for bad in ("corta", "nuevo.usuario"):
        assert owner.post("/api/admin/users", json={"username": "nuevo.usuario", "display_name": "Nuevo",
                                                    "role": "viewer", "password": bad}).status_code == 422

    # --- propietarios: siempre debe quedar uno activo y nadie se desactiva a sí mismo
    owner_id = _row(models.StaffUser, username="dueno").id
    assert owner.patch(f"/api/admin/users/{owner_id}", json={"active": False}).status_code == 409
    assert owner.patch(f"/api/admin/users/{owner_id}", json={"role": "manager"}).status_code == 409
    second = owner.post("/api/admin/users", json={"username": "dueno2", "display_name": "Segundo", "role": "owner",
                                                  "password": "temporal-1234567"})
    assert second.status_code == 201
    owner2 = login_client("dueno2", "temporal-1234567")
    owner2.post("/api/admin/auth/password", json={"current_password": "temporal-1234567", "new_password": "clave-del-segundo-1"})
    assert owner2.patch(f"/api/admin/users/{owner_id}", json={"active": False}).status_code == 200
    assert owner.get("/api/admin/auth/me").status_code == 401                 # su sesión murió
    assert owner2.patch(f"/api/admin/users/{second.json()['id']}", json={"role": "viewer"}).status_code == 409

    # --- quien gestiona usuarios sin ser propietario no puede escalar privilegios
    boss = login_client_for("jefe", "manager", ["users.manage", "appointments.view"])
    assert boss.post("/api/admin/users", json={"username": "otro", "display_name": "Otro", "role": "owner",
                                               "password": "temporal-1234567"}).status_code == 403
    assert boss.post("/api/admin/users", json={"username": "otro", "display_name": "Otro", "role": "viewer",
                                               "permissions": ["appointments.delete"], "password": "temporal-1234567"}).status_code == 403
    assert boss.post("/api/admin/users", json={"username": "otro", "display_name": "Otro", "role": "viewer",
                                               "permissions": ["appointments.view"], "password": "temporal-1234567"}).status_code == 201
    assert boss.patch(f"/api/admin/users/{second.json()['id']}", json={"display_name": "Hackeado"}).status_code == 403
    assert boss.post(f"/api/admin/users/{second.json()['id']}/reset-password", json={"new_password": "una-clave-nueva-1"}).status_code == 403


def test_audit_log_filters_pagination_customer_actions_and_append_only():
    owner = login_client_for("dueno", "owner")
    rosa_id = make_staff_user("rosa", "reception", display_name="Rosa Pérez")
    rosa = login_client("rosa")

    a1, a2 = _add_appt("Ana Gómez"), _add_appt("Beto Díaz")
    rosa.patch(f"/api/admin/appointments/{a1}", json={"status": "confirmed"})
    rosa.patch(f"/api/admin/appointments/{a2}", json={"status": "cancelled"})
    assert owner.post("/api/admin/services", json={"name": "Nuevo", "duration_min": 30, "price": 1000}).status_code == 201
    assert rosa.post("/api/admin/reminders/run").status_code == 200

    # Acciones del cliente por su enlace (HU-5) quedan como "cliente".
    start = (local_now() + timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)
    while start.weekday() == 6:
        start += timedelta(days=1)
    booking = TestClient(app).post("/api/appointments", json={
        "customer_name": "Dora Luna", "customer_phone": PHONE, "service_id": 1, "start_at": start.isoformat()}).json()
    token = booking["manage_url"].split("#t=")[1]
    assert TestClient(app).post("/api/manage/cancel", json={"confirmation": "Cancelar cita"},
                                headers={"X-Manage-Token": token}).status_code == 200
    mine = _audit(owner, action="appointment.customer_cancelled")["items"]
    assert len(mine) == 1 and mine[0]["actor_type"] == "customer" and mine[0]["actor_name"] == "Dora"

    # Filtros: prefijo, exacto, usuario, fechas.
    assert {i["action"] for i in _audit(owner, action="appointment.")["items"]} >= {
        "appointment.confirmed", "appointment.cancelled", "appointment.customer_cancelled"}
    assert all(i["action"].startswith("appointment.") for i in _audit(owner, action="appointment.")["items"])
    assert [i["action"] for i in _audit(owner, action="service.created")["items"]] == ["service.created"]
    rosa_items = _audit(owner, user_id=rosa_id)["items"]
    assert rosa_items and all(i["user_id"] == rosa_id for i in rosa_items)
    today = local_now().date().isoformat()
    assert _audit(owner, **{"from": today, "to": today})["total"] == _audit(owner)["total"]
    assert _audit(owner, **{"from": "2000-01-01", "to": "2000-01-02"})["total"] == 0
    assert _audit(owner, entity="service")["total"] == 1

    # Paginación estable y del más nuevo al más antiguo.
    everything = _audit(owner, limit=200)
    ids = [i["id"] for i in everything["items"]]
    assert ids == sorted(ids, reverse=True) and everything["total"] == len(ids) >= 6
    first, second = _audit(owner, limit=3, offset=0), _audit(owner, limit=3, offset=3)
    assert first["total"] == second["total"] == everything["total"]
    assert [i["id"] for i in first["items"] + second["items"]] == ids[:6]

    # Nunca teléfonos completos y lista de autores para el filtro.
    assert "+5694" not in json.dumps(everything)
    names = {a["name"] for a in owner.get("/api/admin/audit/actors").json()}
    assert {"Rosa Pérez", "Dueno"} <= names

    # Solo con `audit.view`, y el registro es de solo lectura.
    assert rosa.get("/api/admin/audit").status_code == 403
    for method in ("put", "patch", "delete", "post"):
        assert getattr(owner, method)("/api/admin/audit").status_code in (404, 405), method
        assert getattr(owner, method)(f"/api/admin/audit/{ids[0]}").status_code in (404, 405), method
