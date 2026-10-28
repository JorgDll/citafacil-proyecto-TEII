"""Endpoints de administración (HU-6: cada ruta exige un permiso y deja registro de actividad)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .. import audit, crud, models, permissions, schemas
from ..auth import current_staff, require_any, require_permission
from ..database import get_db
from ..reminders import run_reminders
from ..utils import mask_phone

router = APIRouter(prefix="/api/admin", tags=["Administración"])

# Acción de auditoría según el estado al que pasa la reserva.
STATUS_ACTION = {
    models.STATUS_CONFIRMED: "appointment.confirmed",
    models.STATUS_DONE: "appointment.done",
    models.STATUS_CANCELLED: "appointment.cancelled",
    models.STATUS_PENDING: "appointment.reopened",
}


def _appt_out(user: models.StaffUser, appt: models.Appointment) -> schemas.AppointmentOut:
    out = schemas.AppointmentOut.model_validate(appt)
    if not permissions.has(user, "customers.phones"):          # proteger los datos del cliente
        out.customer_phone = mask_phone(out.customer_phone)
    return out


def _summary(appt: models.Appointment) -> dict:
    return {
        "customer": appt.customer_name,
        "service": appt.service.name if appt.service else f"#{appt.service_id}",
        "start_at": appt.start_at.isoformat(timespec="minutes"),
    }


# ---------- Servicios ----------
@router.get("/services", response_model=list[schemas.ServiceOut], summary="Listar todos los servicios")
def all_services(
    user: models.StaffUser = Depends(require_any("appointments.view", "services.manage", "analytics.view")),
    db: Session = Depends(get_db),
):
    return crud.list_services(db, only_active=False)


@router.post("/services", response_model=schemas.ServiceOut, status_code=201, summary="Crear servicio")
def add_service(
    payload: schemas.ServiceCreate, request: Request,
    user: models.StaffUser = Depends(require_permission("services.manage")), db: Session = Depends(get_db),
):
    service = crud.create_service(db, payload)
    audit.record(db, audit.Actor.from_user(user), "service.created", "service", service.id, {"name": service.name}, request)
    return service


@router.put("/services/{service_id}", response_model=schemas.ServiceOut, summary="Editar servicio")
def edit_service(
    service_id: int, payload: schemas.ServiceUpdate, request: Request,
    user: models.StaffUser = Depends(require_permission("services.manage")), db: Session = Depends(get_db),
):
    service = crud.get_service(db, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    updated = crud.update_service(db, service, payload)
    audit.record(db, audit.Actor.from_user(user), "service.updated", "service", updated.id,
                 {"name": updated.name, **payload.model_dump(exclude_unset=True)}, request)
    return updated


@router.delete("/services/{service_id}", response_model=schemas.MessageOut, summary="Eliminar servicio")
def remove_service(
    service_id: int, request: Request,
    user: models.StaffUser = Depends(require_permission("services.manage")), db: Session = Depends(get_db),
):
    service = crud.get_service(db, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado.")
    name = service.name
    crud.delete_service(db, service)
    audit.record(db, audit.Actor.from_user(user), "service.deleted", "service", service_id, {"name": name}, request)
    return {"detail": "Servicio eliminado."}


# ---------- Citas ----------
@router.get("/appointments", response_model=list[schemas.AppointmentOut], summary="Listar citas")
def all_appointments(
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    day: Optional[date] = Query(None, alias="date", description="Filtrar por fecha YYYY-MM-DD"),
    user: models.StaffUser = Depends(require_permission("appointments.view")),
    db: Session = Depends(get_db),
):
    return [_appt_out(user, a) for a in crud.list_appointments(db, status=status, day=day)]


@router.patch("/appointments/{appt_id}", response_model=schemas.AppointmentOut, summary="Cambiar estado")
def change_status(
    appt_id: int, payload: schemas.AppointmentStatusUpdate, request: Request,
    user: models.StaffUser = Depends(current_staff), db: Session = Depends(get_db),
):
    # Cancelar es un permiso distinto de confirmar/marcar realizada.
    needed = "appointments.cancel" if payload.status == models.STATUS_CANCELLED else "appointments.confirm"
    if not permissions.has(user, needed):
        raise HTTPException(status_code=403, detail="No tienes permiso para esta acción.")
    appt = crud.get_appointment(db, appt_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    previous = appt.status
    appt = crud.set_status(db, appt, payload.status)
    if previous != appt.status:
        audit.record(db, audit.Actor.from_user(user), STATUS_ACTION[appt.status], "appointment", appt.id,
                     {"from": previous, "to": appt.status, **_summary(appt)}, request)
    return _appt_out(user, appt)


@router.delete("/appointments/{appt_id}", response_model=schemas.MessageOut, summary="Eliminar cita")
def remove_appointment(
    appt_id: int, request: Request,
    user: models.StaffUser = Depends(require_permission("appointments.delete")), db: Session = Depends(get_db),
):
    appt = crud.get_appointment(db, appt_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    snapshot = {**_summary(appt), "status": appt.status}      # el registro conserva qué se borró
    crud.delete_appointment(db, appt)
    audit.record(db, audit.Actor.from_user(user), "appointment.deleted", "appointment", appt_id, snapshot, request)
    return {"detail": "Cita eliminada."}


# ---------- Estadísticas y recordatorios ----------
@router.get("/stats", response_model=schemas.StatsOut, summary="Estadísticas")
def get_stats(user: models.StaffUser = Depends(require_permission("appointments.view")), db: Session = Depends(get_db)):
    return crud.stats(db)


@router.post("/reminders/run", summary="Enviar recordatorios ahora")
def trigger_reminders(
    request: Request,
    user: models.StaffUser = Depends(require_permission("reminders.run")), db: Session = Depends(get_db),
):
    result = run_reminders(db)
    audit.record(db, audit.Actor.from_user(user), "reminders.run", "reminders", None, result, request)
    return result
