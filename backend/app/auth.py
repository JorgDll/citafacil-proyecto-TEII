"""Autenticación del panel de administración (HU-6): usuarios, contraseñas y sesiones.

- Contraseñas con `hashlib.scrypt` (biblioteca estándar): sal aleatoria por usuario.
- Sesión por cookie HttpOnly; el servidor sólo guarda el SHA-256 del token.
- Toda petición que no sea GET exige la cabecera `X-Requested-With: citafacil` (defensa
  extra contra CSRF: un formulario de otro sitio no puede añadirla).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from . import models, permissions
from .config import settings
from .database import get_db
from .device import hash_token, new_token

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "citafacil"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1      # ~16 MB y decenas de ms por verificación


# ---------- Contraseñas ----------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


# Hash falso: un usuario inexistente cuesta el mismo tiempo que uno existente.
_DUMMY_HASH = hash_password("contraseña-falsa-para-igualar-tiempos")


def check_password_policy(password: str, username: str = "") -> None:
    """Lanza ValueError con el motivo si la contraseña no cumple la política."""
    if len(password or "") < settings.password_min_length:
        raise ValueError(f"La contraseña debe tener al menos {settings.password_min_length} caracteres.")
    if username and password.strip().lower() == username.strip().lower():
        raise ValueError("La contraseña no puede ser igual al usuario.")


# ---------- Sesiones ----------
def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def start_session(db: Session, user: models.StaffUser, response: Response) -> None:
    token = new_token()
    db.add(models.StaffSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.utcnow() + timedelta(hours=settings.session_hours),
    ))
    db.commit()
    response.set_cookie(
        key=settings.staff_cookie_name, value=token, max_age=settings.session_hours * 3600,
        httponly=True, samesite="strict", secure=settings.cookie_secure, path="/",
    )


def end_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.staff_cookie_name, path="/", httponly=True,
        samesite="strict", secure=settings.cookie_secure,
    )


def revoke_sessions(db: Session, user_id: int, keep_session_id: Optional[int] = None) -> None:
    q = db.query(models.StaffSession).filter(models.StaffSession.user_id == user_id)
    if keep_session_id is not None:
        q = q.filter(models.StaffSession.id != keep_session_id)
    q.delete()
    db.commit()


# ---------- Dependencias ----------
def csrf_guard(request: Request) -> None:
    if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail="Falta la cabecera de seguridad de la petición.")


def current_staff_any(request: Request, db: Session = Depends(get_db)) -> models.StaffUser:
    """Usuario de la sesión (aunque deba cambiar su contraseña). 401 sin sesión válida."""
    csrf_guard(request)
    token = request.cookies.get(settings.staff_cookie_name)
    session = None
    if token:
        session = (
            db.query(models.StaffSession)
            .filter(models.StaffSession.token_hash == hash_token(token))
            .first()
        )
    if session is not None and session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        session = None
    if session is None or session.user is None or not session.user.active:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    request.state.session_id = session.id
    return session.user


def current_staff(user: models.StaffUser = Depends(current_staff_any)) -> models.StaffUser:
    """Usuario de la sesión con la contraseña al día."""
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Debes cambiar tu contraseña antes de continuar.")
    return user


def require_permission(*needed: str):
    """Dependencia: exige TODOS los permisos indicados."""
    def dep(user: models.StaffUser = Depends(current_staff)) -> models.StaffUser:
        missing = [p for p in needed if not permissions.has(user, p)]
        if missing:
            raise HTTPException(status_code=403, detail="No tienes permiso para esta acción.")
        return user
    return dep


def require_any(*options: str):
    """Dependencia: basta con UNO de los permisos indicados."""
    def dep(user: models.StaffUser = Depends(current_staff)) -> models.StaffUser:
        if not any(permissions.has(user, p) for p in options):
            raise HTTPException(status_code=403, detail="No tienes permiso para esta acción.")
        return user
    return dep
