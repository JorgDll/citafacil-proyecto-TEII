"""Endpoints del dispositivo recordado (HU-1): prellenado sin login."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..device import (
    clear_device_cookie,
    current_device,
    hash_token,
    new_token,
    set_device_cookie,
)

router = APIRouter(prefix="/api/device", tags=["Dispositivo"])


def _require_device(device: Optional[models.DeviceProfile]) -> models.DeviceProfile:
    if device is None:
        raise HTTPException(status_code=401, detail="Dispositivo no reconocido.")
    return device


@router.get("/profile", response_model=schemas.DeviceProfileOut, summary="Datos guardados de este dispositivo")
def get_profile(
    device: Optional[models.DeviceProfile] = Depends(current_device),
    db: Session = Depends(get_db),
):
    if device is None:
        return schemas.DeviceProfileOut(known=False)
    crud.touch_device(db, device)
    return schemas.DeviceProfileOut(
        known=True, customer_name=device.customer_name, customer_phone=device.customer_phone
    )


@router.post("/remember", response_model=schemas.DeviceProfileOut, summary="Recordar este dispositivo")
def remember(
    payload: schemas.DeviceProfileIn,
    response: Response,
    device: Optional[models.DeviceProfile] = Depends(current_device),
    db: Session = Depends(get_db),
):
    # Dispositivo ya conocido: jamás se emite ni se reemplaza el token.
    if device is not None:
        return schemas.DeviceProfileOut(
            known=True,
            customer_name=device.customer_name,
            customer_phone=device.customer_phone,
            detail="already_known",
        )

    token = new_token()
    created = crud.create_device(db, hash_token(token), payload)
    set_device_cookie(response, token)
    response.status_code = 201
    return schemas.DeviceProfileOut(
        known=True,
        customer_name=created.customer_name,
        customer_phone=created.customer_phone,
        detail="created",
    )


@router.put("/profile", response_model=schemas.DeviceProfileOut, summary="Actualizar datos guardados")
def update_profile(
    payload: schemas.DeviceProfileIn,
    device: Optional[models.DeviceProfile] = Depends(current_device),
    db: Session = Depends(get_db),
):
    updated = crud.update_device(db, _require_device(device), payload)
    return schemas.DeviceProfileOut(
        known=True, customer_name=updated.customer_name, customer_phone=updated.customer_phone
    )


@router.delete("", response_model=schemas.MessageOut, summary="Olvidar este dispositivo")
def forget(
    response: Response,
    device: Optional[models.DeviceProfile] = Depends(current_device),
    db: Session = Depends(get_db),
):
    crud.delete_device(db, _require_device(device))
    clear_device_cookie(response)
    return {"detail": "Dispositivo olvidado."}
