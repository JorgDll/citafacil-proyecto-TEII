"""Autogestión de la cita por el cliente (HU-5): enlace personal, reglas y reprogramación.

El enlace lleva un token aleatorio en el fragmento de la URL (`#t=...`); la página lo
envía en la cabecera `X-Manage-Token` y el servidor sólo guarda su SHA-256. Al cancelar
se borra la fila del enlace, de modo que el mismo URL deja de servir.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models
from .availability import booking_lock, is_slot_free
from .config import settings
from .database import get_db
from .device import hash_token, new_token
from .utils import local_now

INVALID_LINK = "Enlace inválido o vencido."


def build_manage_url(token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/app/manage.html#t={token}"


def create_link(db: Session, appt: models.Appointment) -> str:
    """Crea el enlace de la cita y devuelve el token en claro (sólo existe aquí)."""
    token = new_token()
    db.add(models.AppointmentLink(appointment_id=appt.id, token_hash=hash_token(token)))
    db.commit()
    return token


def rotate_link(db: Session, appt: models.Appointment) -> str:
    """Token nuevo para un mensaje posterior (p. ej. el recordatorio).

    Como solo se guarda el hash, el token original no se puede reenviar: se reemplaza
    en la misma fila (se conserva `reschedule_count`) y el enlace anterior deja de servir.
    Una cita sin enlace (anterior a HU-5) recibe uno nuevo.
    """
    link = db.query(models.AppointmentLink).filter_by(appointment_id=appt.id).first()
    if link is None:
        return create_link(db, appt)
    token = new_token()
    link.token_hash = hash_token(token)
    db.commit()
    return token


def current_link(
    x_manage_token: Optional[str] = Header(None, alias="X-Manage-Token"),
    db: Session = Depends(get_db),
) -> models.AppointmentLink:
    """Enlace de la cabecera. Ausente, desconocido o revocado -> 404 genérico."""
    link = None
    if x_manage_token:
        link = (
            db.query(models.AppointmentLink)
            .filter(models.AppointmentLink.token_hash == hash_token(x_manage_token))
            .first()
        )
    if link is None or link.appointment is None:
        raise HTTPException(status_code=404, detail=INVALID_LINK)
    return link


def reschedules_left(link: models.AppointmentLink) -> int:
    return max(0, settings.manage_max_reschedules - link.reschedule_count)


def block_reason(link: models.AppointmentLink, reschedule: bool = False) -> Optional[str]:
    """Motivo por el que la cita no se puede cambiar (None = se puede)."""
    appt = link.appointment
    if appt.status == models.STATUS_CANCELLED:
        return "Esta cita fue cancelada."
    if appt.status == models.STATUS_DONE:
        return "Esta cita ya fue realizada."
    now = local_now()
    if appt.start_at <= now:
        return "La cita ya pasó."
    if appt.start_at - now < timedelta(hours=settings.manage_cutoff_hours):
        return (
            f"Faltan menos de {settings.manage_cutoff_hours} horas para la cita: "
            "para cambiarla contacta al negocio."
        )
    if reschedule and reschedules_left(link) == 0:
        return (
            f"Alcanzaste el máximo de {settings.manage_max_reschedules} reprogramaciones. "
            "Puedes cancelar y reservar de nuevo."
        )
    return None


def reschedule(db: Session, link: models.AppointmentLink, new_start: datetime) -> models.Appointment:
    """Mueve la cita a `new_start`; 409 si no se puede. La propia cita no cuenta como choque."""
    reason = block_reason(link, reschedule=True)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    appt = link.appointment
    if new_start == appt.start_at:
        raise HTTPException(status_code=409, detail="Elige un horario distinto al actual.")
    with booking_lock:
        if not is_slot_free(db, appt.service, new_start, exclude_id=appt.id):
            raise HTTPException(status_code=409, detail="Ese horario ya no está disponible. Elige otro.")

        appt.start_at = new_start
        appt.end_at = new_start + timedelta(minutes=appt.service.duration_min)
        appt.status = models.STATUS_PENDING       # el negocio debe reconfirmar el cambio
        appt.reminder_sent = False                # recibirá un recordatorio para la hora nueva
        link.reschedule_count += 1
        db.commit()
    db.refresh(appt)
    return appt


def cancel(db: Session, link: models.AppointmentLink) -> models.Appointment:
    """Cancela la cita y revoca el enlace (el mismo URL deja de servir)."""
    reason = block_reason(link)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    appt = link.appointment
    appt.status = models.STATUS_CANCELLED
    db.delete(link)
    db.commit()
    db.refresh(appt)
    return appt
