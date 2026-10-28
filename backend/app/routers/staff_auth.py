"""Acceso al panel de administración (HU-6): instalación, entrada, salida y contraseña."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import audit, models, permissions, schemas
from ..auth import (
    _DUMMY_HASH, check_password_policy, client_ip, csrf_guard, current_staff_any, end_cookie,
    hash_password, revoke_sessions, start_session, verify_password,
)
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api/admin/auth", tags=["Acceso admin"])

DEFAULT_ADMIN_TOKEN = "cambia-este-token-admin"
BAD_LOGIN = "Usuario o contraseña incorrectos."


def me_out(user: models.StaffUser) -> schemas.MeOut:
    role = permissions.ROLES.get(user.role, {"label": user.role})
    return schemas.MeOut(
        id=user.id, username=user.username, display_name=user.display_name, role=user.role,
        role_label=role["label"], permissions=sorted(permissions.effective(user), key=permissions.ALL_PERMISSIONS.index),
        must_change_password=user.must_change_password,
    )


def _policy(password: str, username: str) -> None:
    try:
        check_password_policy(password, username)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/setup-status", summary="¿Hace falta crear al primer propietario?")
def setup_status(db: Session = Depends(get_db)):
    return {"needs_setup": db.query(models.StaffUser).count() == 0}


@router.post("/setup", response_model=schemas.MeOut, summary="Crear al primer propietario")
def setup(payload: schemas.SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    csrf_guard(request)
    if db.query(models.StaffUser).count() > 0:
        raise HTTPException(status_code=409, detail="Ya existe un propietario; la instalación inicial ya se hizo.")
    if settings.admin_token == DEFAULT_ADMIN_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Cambia ADMIN_TOKEN en el archivo .env por un valor propio antes de crear al propietario.",
        )
    if not hmac.compare_digest(payload.setup_token.encode(), settings.admin_token.encode()):
        raise HTTPException(status_code=403, detail="La clave de instalación (ADMIN_TOKEN) es incorrecta.")
    _policy(payload.password, payload.username)

    user = models.StaffUser(
        username=payload.username, display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password), role="owner",
        permissions=permissions.serialize(permissions.ALL_PERMISSIONS), last_login_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    actor = audit.Actor.from_user(user)
    audit.record(db, actor, "user.created", "user", user.id, {"username": user.username, "role": "owner", "setup": True}, request)
    start_session(db, user, response)
    audit.record(db, actor, "auth.login", "user", user.id, {}, request)
    return me_out(user)


@router.post("/login", response_model=schemas.MeOut, summary="Entrar al panel")
def login(payload: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    csrf_guard(request)
    username = payload.username.strip().lower()
    user = db.query(models.StaffUser).filter(models.StaffUser.username == username).first()
    now = datetime.utcnow()

    # Siempre se verifica una contraseña (aunque el usuario no exista): mismo tiempo, mismo mensaje.
    ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)

    if user is not None and user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(status_code=429, detail=f"Cuenta bloqueada temporalmente. Intenta de nuevo en {minutes} min.")

    if user is None or not ok or not user.active:
        if user is not None and user.active:
            user.failed_attempts += 1
            if user.failed_attempts >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                user.failed_attempts = 0
            db.commit()
        audit.record(
            db, audit.Actor("staff", user.id if user else None, (user.display_name if user else username[:64])),
            "auth.login_failed", "user", user.id if user else None,
            {"username": username[:64], "locked": bool(user and user.locked_until and user.locked_until > now)}, request,
        )
        raise HTTPException(status_code=401, detail=BAD_LOGIN)

    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    db.commit()
    start_session(db, user, response)
    audit.record(db, audit.Actor.from_user(user), "auth.login", "user", user.id, {}, request)
    return me_out(user)


@router.post("/logout", response_model=schemas.MessageOut, summary="Salir del panel")
def logout(
    request: Request, response: Response,
    user: models.StaffUser = Depends(current_staff_any), db: Session = Depends(get_db),
):
    db.query(models.StaffSession).filter(models.StaffSession.id == request.state.session_id).delete()
    db.commit()
    end_cookie(response)
    audit.record(db, audit.Actor.from_user(user), "auth.logout", "user", user.id, {}, request)
    return {"detail": "Sesión cerrada."}


@router.get("/me", response_model=schemas.MeOut, summary="Usuario de la sesión")
def me(user: models.StaffUser = Depends(current_staff_any)):
    return me_out(user)


@router.post("/password", response_model=schemas.MeOut, summary="Cambiar mi contraseña")
def change_password(
    payload: schemas.PasswordChangeIn, request: Request,
    user: models.StaffUser = Depends(current_staff_any), db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="La contraseña actual no es correcta.")
    _policy(payload.new_password, user.username)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=422, detail="La contraseña nueva debe ser distinta de la actual.")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    revoke_sessions(db, user.id, keep_session_id=request.state.session_id)      # cierra los demás dispositivos
    audit.record(db, audit.Actor.from_user(user), "auth.password_changed", "user", user.id, {}, request)
    return me_out(user)
