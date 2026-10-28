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
