"""Configuración compartida de los tests.

La base de datos de prueba y el token admin se fijan ANTES de importar la app
(pytest carga este archivo antes que los módulos de test).
"""
import os
import tempfile
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "citafacil_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["ADMIN_TOKEN"] = "test-token"

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
