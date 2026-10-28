"""Modelos de base de datos (SQLAlchemy)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base

# Estados posibles de una cita
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
STATUS_DONE = "done"
VALID_STATUSES = {STATUS_PENDING, STATUS_CONFIRMED, STATUS_CANCELLED, STATUS_DONE}


class Service(Base):
    """Un servicio que ofrece el negocio (ej: Corte de pelo, 30 min, $8.000)."""

    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    duration_min = Column(Integer, nullable=False, default=30)
    price = Column(Integer, nullable=False, default=0)  # CLP, entero
    active = Column(Boolean, nullable=False, default=True)

    appointments = relationship("Appointment", back_populates="service")


class Appointment(Base):
    """Una reserva/cita hecha por un cliente."""

    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(120), nullable=False)
    customer_phone = Column(String(20), nullable=False)   # E.164: +569XXXXXXXX
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    start_at = Column(DateTime, nullable=False, index=True)  # hora local (naive)
    end_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default=STATUS_PENDING)
    notes = Column(String(300), nullable=False, default="")
    reminder_sent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    service = relationship("Service", back_populates="appointments")


class AppointmentLink(Base):
    """Enlace personal para que el cliente gestione SU cita (HU-5).

    Solo se guarda el SHA-256 del token (que viaja en el enlace de WhatsApp). Se borra
    la fila al cancelar la cita: así el enlace deja de servir.
    """

    __tablename__ = "appointment_links"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False, unique=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    reschedule_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    appointment = relationship("Appointment")


class StaffUser(Base):
    """Cuenta de un empleado del negocio para entrar al panel (HU-6).

    Los usuarios no se borran, se desactivan (así el registro de actividad conserva
    a su autor). `permissions` es la lista guardada, separada por comas; el rol
    "owner" tiene todos los permisos siempre.
    """

    __tablename__ = "staff_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(32), nullable=False, unique=True, index=True)   # en minúsculas
    display_name = Column(String(80), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="reception")
    permissions = Column(Text, nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)
    must_change_password = Column(Boolean, nullable=False, default=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)                           # UTC
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class StaffSession(Base):
    """Sesión del panel: sólo se guarda el SHA-256 del token de la cookie."""

    __tablename__ = "staff_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("staff_users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)                            # UTC

    user = relationship("StaffUser")


class AuditLog(Base):
    """Registro de actividad: quién hizo qué y cuándo. Sólo se agrega, nunca se edita."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, nullable=False, index=True)                # hora local del negocio
    actor_type = Column(String(12), nullable=False)                          # staff | customer | system
    user_id = Column(Integer, nullable=True, index=True)
    actor_name = Column(String(80), nullable=False, default="")
    action = Column(String(40), nullable=False, index=True)
    entity = Column(String(20), nullable=False, default="")
    entity_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=False, default="")                        # JSON
    ip = Column(String(45), nullable=False, default="")


class DeviceProfile(Base):
    """Datos de un cliente recordados en UN dispositivo (HU-1).

    Solo se guarda el SHA-256 del token; el token en claro vive únicamente en la
    cookie HttpOnly del navegador. Cada dispositivo tiene su propia fila.
    """

    __tablename__ = "device_profiles"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    customer_name = Column(String(120), nullable=False)
    customer_phone = Column(String(20), nullable=False)   # E.164
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=False, default=datetime.utcnow)
