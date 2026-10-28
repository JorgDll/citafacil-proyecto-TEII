"""Identificación de dispositivos recordados (HU-1).

El cliente conserva un token aleatorio en una cookie HttpOnly; el servidor sólo
guarda su SHA-256. Un token desconocido (borrado, forjado) equivale a "dispositivo
no reconocido".
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from . import crud, models
from .config import settings
from .database import get_db


def new_token() -> str:
    """Token aleatorio de 256 bits, seguro para URL/cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_device_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.device_cookie_name,
        value=token,
        max_age=settings.device_cookie_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_device_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.device_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def current_device(
    request: Request, db: Session = Depends(get_db)
) -> Optional[models.DeviceProfile]:
    """Perfil del dispositivo según la cookie, o None si no hay/ no es válida."""
    token = request.cookies.get(settings.device_cookie_name)
    if not token:
        return None
    return crud.get_device_by_hash(db, hash_token(token))
