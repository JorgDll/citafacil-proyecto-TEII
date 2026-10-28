"""Configuración compartida de los tests.

La configuración se fija ANTES de importar la app (pytest carga este archivo antes
que los módulos de test). Las variables de entorno tienen prioridad sobre
`backend/.env`, así el resultado de los tests no depende de la máquina: país base,
zona horaria, horario y días cerrados quedan fijos, y Twilio vacío = modo demo
(los tests nunca envían WhatsApp reales aunque el `.env` tenga credenciales).
"""
import os
import tempfile
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "citafacil_test.db"
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_DB_FILE.as_posix()}",
    "ADMIN_TOKEN": "test-token",
    "DEFAULT_COUNTRY": "CL",
    "BUSINESS_TIMEZONE": "America/Santiago",
    "CURRENCY": "CLP",
    "OPEN_HOUR": "10",
    "CLOSE_HOUR": "20",
    "SLOT_INTERVAL_MINUTES": "30",
    "CLOSED_WEEKDAYS": "6",
    "PUBLIC_BASE_URL": "http://testserver",
    "MANAGE_CUTOFF_HOURS": "2",
    "MANAGE_MAX_RESCHEDULES": "2",
    "SESSION_HOURS": "12",
    "LOGIN_MAX_ATTEMPTS": "5",
    "LOGIN_LOCK_MINUTES": "15",
    "PASSWORD_MIN_LENGTH": "10",
    "TWILIO_ACCOUNT_SID": "",
    "TWILIO_AUTH_TOKEN": "",
    "TWILIO_WHATSAPP_FROM": "",
})

import pytest  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(models.Service(name="Corte", duration_min=30, price=8000, active=True))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


# ---------- Cuentas del panel (HU-6) ----------
CSRF = {"X-Requested-With": "citafacil"}
STAFF_PASSWORD = "clave-de-prueba-123"


def make_staff_user(username, role="reception", permissions=None, password=STAFF_PASSWORD,
                    must_change=False, display_name=None, active=True) -> int:
    """Crea un usuario directamente en la BD; `permissions=None` = los del rol."""
    from app import permissions as perms
    from app.auth import hash_password
    from app.database import SessionLocal

    granted = perms.ROLES[role]["permissions"] if permissions is None else permissions
    db = SessionLocal()
    try:
        u = models.StaffUser(
            username=username, display_name=display_name or username.capitalize(),
            password_hash=hash_password(password), role=role,
            permissions=perms.serialize(granted), must_change_password=must_change, active=active,
        )
        db.add(u)
        db.commit()
        return u.id
    finally:
        db.close()


def login_client(username, password=STAFF_PASSWORD):
    """TestClient con la cabecera de seguridad; entra por la API real (cookie de sesión)."""
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app, headers=CSRF)
    r = c.post("/api/admin/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def staff_client():
    """Fábrica: staff_client("ana", role="reception", permissions=[...]) -> cliente con sesión."""
    def factory(username="owner1", role="owner", permissions=None, **kw):
        make_staff_user(username, role, permissions, **kw)
        return login_client(username)
    return factory
