"""Endpoints públicos: config, servicios, disponibilidad y creación de reservas."""
from __future__ import annotations

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..availability import build_day_slots, generate_slots, is_slot_free, month_overview
from ..config import settings
from ..database import get_db
from ..notifications import confirmation_message, send_whatsapp

router = APIRouter(prefix="/api", tags=["Público"])


@router.get("/config", response_model=schemas.ConfigOut, summary="Configuración del negocio")
def get_config():
    return schemas.ConfigOut(
        business_name=settings.business_name,
        timezone=settings.business_timezone,
        currency=settings.currency,
        open_hour=settings.open_hour,
        close_hour=settings.close_hour,
        slot_interval_minutes=settings.slot_interval_minutes,
        closed_weekdays=sorted(settings.closed_weekdays_set),
    )


@router.get("/services", response_model=list[schemas.ServiceOut], summary="Servicios activos")
def get_services(db: Session = Depends(get_db)):
    return crud.list_services(db, only_active=True)


@router.get("/availability", response_model=list[str], summary="Horarios disponibles")
def get_availability(
    service_id: int = Query(..., description="ID del servicio"),
    day: date = Query(..., alias="date", description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = crud.get_service(db, service_id)
    if not service or not service.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    return generate_slots(db, service, day)


@router.get("/schedule", response_model=list[schemas.SlotOut], summary="Todas las franjas del día (libres y bloqueadas)")
def get_schedule(
    service_id: int = Query(..., description="ID del servicio"),
    day: date = Query(..., alias="date", description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = crud.get_service(db, service_id)
    if not service or not service.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    return build_day_slots(db, service, day)


@router.get("/calendar", response_model=list[schemas.DayOut], summary="Estado de cada día del mes")
def get_calendar(
    service_id: int = Query(..., description="ID del servicio"),
    month: str = Query(..., description="Mes en formato YYYY-MM"),
    db: Session = Depends(get_db),
):
    m = re.fullmatch(r"(\d{4})-(\d{2})", month)
    if not m or not 1 <= int(m.group(2)) <= 12 or int(m.group(1)) < 1900:
        raise HTTPException(status_code=422, detail="Mes inválido. Usa el formato YYYY-MM.")
    service = crud.get_service(db, service_id)
    if not service or not service.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    return month_overview(db, service, int(m.group(1)), int(m.group(2)))


@router.post(
    "/appointments",
    response_model=schemas.AppointmentOut,
    status_code=201,
    summary="Crear una reserva",
)
def create_appointment(payload: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    service = crud.get_service(db, payload.service_id)
    if not service or not service.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    if not is_slot_free(db, service, payload.start_at):
        raise HTTPException(
            status_code=409,
            detail="Ese horario ya no está disponible. Por favor elige otro.",
        )
    end_at = payload.start_at + timedelta(minutes=service.duration_min)
    appt = crud.create_appointment(db, payload, service, end_at)

    # Confirmación por WhatsApp (real si Twilio está configurado; simulada si no)
    body = confirmation_message(
        settings.business_name, appt.customer_name, service.name, appt.start_at
    )
    send_whatsapp(appt.customer_phone, body)
    return appt
