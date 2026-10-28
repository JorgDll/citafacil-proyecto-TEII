"""Autogestión de la cita (HU-5): el cliente la consulta, reprograma o cancela con su enlace."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import manage, models, schemas
from ..availability import build_day_slots, month_overview
from ..config import settings
from ..database import get_db
from ..notifications import cancellation_message, reschedule_message, send_whatsapp
from ..routers.public import MONTH_RE

router = APIRouter(prefix="/api/manage", tags=["Autogestión"])


def _out(link: models.AppointmentLink) -> schemas.ManageOut:
    appt = link.appointment
    cancel_reason = manage.block_reason(link)
    resched_reason = manage.block_reason(link, reschedule=True)
    return schemas.ManageOut(
        business_name=settings.business_name,
        service_name=appt.service.name,
        service_duration_min=appt.service.duration_min,
        service_price=appt.service.price,
        start_at=appt.start_at,
        end_at=appt.end_at,
        status=appt.status,
        customer_first_name=appt.customer_name.split()[0],
        can_cancel=cancel_reason is None,
        can_reschedule=resched_reason is None,
        reason=cancel_reason or resched_reason,
        reschedules_left=manage.reschedules_left(link),
        cutoff_hours=settings.manage_cutoff_hours,
    )


@router.get("", response_model=schemas.ManageOut, summary="Detalle de mi cita")
def get_appointment(link: models.AppointmentLink = Depends(manage.current_link)):
    return _out(link)


@router.post("/cancel", response_model=schemas.MessageOut, summary="Cancelar mi cita (revoca el enlace)")
def cancel_appointment(
    payload: schemas.CancelIn,
    link: models.AppointmentLink = Depends(manage.current_link),
    db: Session = Depends(get_db),
):
    appt = manage.cancel(db, link)
    send_whatsapp(
        appt.customer_phone,
        cancellation_message(settings.business_name, appt.customer_name, appt.service.name, appt.start_at),
    )
    return {"detail": "Cita cancelada. El horario quedó libre."}


@router.post("/reschedule", response_model=schemas.ManageOut, summary="Reprogramar mi cita")
def reschedule_appointment(
    payload: schemas.RescheduleIn,
    link: models.AppointmentLink = Depends(manage.current_link),
    db: Session = Depends(get_db),
):
    appt = manage.reschedule(db, link, payload.start_at)
    send_whatsapp(
        appt.customer_phone,
        reschedule_message(settings.business_name, appt.customer_name, appt.service.name, appt.start_at),
    )
    return _out(link)


@router.get("/schedule", response_model=list[schemas.SlotOut], summary="Franjas para reprogramar")
def get_schedule(
    day: date = Query(..., alias="date", description="Fecha en formato YYYY-MM-DD"),
    link: models.AppointmentLink = Depends(manage.current_link),
    db: Session = Depends(get_db),
):
    appt = link.appointment
    return build_day_slots(db, appt.service, day, exclude_id=appt.id)


@router.get("/calendar", response_model=list[schemas.DayOut], summary="Calendario para reprogramar")
def get_calendar(
    month: str = Query(..., description="Mes en formato YYYY-MM"),
    link: models.AppointmentLink = Depends(manage.current_link),
    db: Session = Depends(get_db),
):
    m = MONTH_RE.fullmatch(month)
    if not m or not 1 <= int(m.group(2)) <= 12 or int(m.group(1)) < 1900:
        raise HTTPException(status_code=422, detail="Mes inválido. Usa el formato YYYY-MM.")
    appt = link.appointment
    return month_overview(db, appt.service, int(m.group(1)), int(m.group(2)), exclude_id=appt.id)
