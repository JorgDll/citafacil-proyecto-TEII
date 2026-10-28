"""Gestión de usuarios y permisos del panel (HU-6). Requiere `users.manage`."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import audit, models, permissions, schemas
from ..auth import check_password_policy, hash_password, require_permission, revoke_sessions
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["Usuarios"])
manager = Depends(require_permission("users.manage"))


def _out(u: models.StaffUser) -> schemas.StaffUserOut:
    role = permissions.ROLES.get(u.role, {"label": u.role})
    return schemas.StaffUserOut(
        id=u.id, username=u.username, display_name=u.display_name, role=u.role, role_label=role["label"],
        permissions=sorted(permissions.effective(u), key=permissions.ALL_PERMISSIONS.index),
        must_change_password=u.must_change_password, active=u.active,
        locked=bool(u.locked_until and u.locked_until > datetime.utcnow()),
        created_at=u.created_at, last_login_at=u.last_login_at,
    )


def _get(db: Session, user_id: int) -> models.StaffUser:
    u = db.query(models.StaffUser).filter(models.StaffUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return u


def _other_active_owner(db: Session, excluding_id: int) -> bool:
    return (
        db.query(models.StaffUser)
        .filter(models.StaffUser.role == "owner", models.StaffUser.active.is_(True), models.StaffUser.id != excluding_id)
        .count() > 0
    )


def _only_owner_touches_owner(actor: models.StaffUser, target_role: str) -> None:
    if target_role == "owner" and actor.role != "owner":
        raise HTTPException(status_code=403, detail="Solo un propietario puede gestionar cuentas de propietario.")


def _validate_perms(actor: models.StaffUser, perms: list[str]) -> list[str]:
    bad = permissions.invalid(perms)
    if bad:
        raise HTTPException(status_code=422, detail=f"Permisos desconocidos: {', '.join(bad)}.")
    if actor.role != "owner":                       # no se puede dar lo que uno no tiene
        extra = set(perms) - permissions.effective(actor)
        if extra:
            raise HTTPException(status_code=403, detail="No puedes otorgar permisos que tú no tienes.")
    return [p for p in permissions.ALL_PERMISSIONS if p in set(perms)]


def _check_role(role: str) -> None:
    if role not in permissions.ROLES:
        raise HTTPException(status_code=422, detail=f"Rol desconocido. Usa uno de: {', '.join(permissions.ROLES)}.")


@router.get("/permissions", summary="Catálogo de permisos y roles base")
def catalog(user: models.StaffUser = manager):
    return {
        "permissions": [{"key": k, "label": v} for k, v in permissions.PERMISSIONS.items()],
        "roles": [{"key": k, "label": v["label"], "permissions": v["permissions"]} for k, v in permissions.ROLES.items()],
    }


@router.get("/users", response_model=list[schemas.StaffUserOut], summary="Listar usuarios")
def list_users(user: models.StaffUser = manager, db: Session = Depends(get_db)):
    return [_out(u) for u in db.query(models.StaffUser).order_by(models.StaffUser.id).all()]


@router.post("/users", response_model=schemas.StaffUserOut, status_code=201, summary="Crear usuario")
def create_user(
    payload: schemas.StaffUserCreate, request: Request,
    actor: models.StaffUser = manager, db: Session = Depends(get_db),
):
    _check_role(payload.role)
    _only_owner_touches_owner(actor, payload.role)
    perms = _validate_perms(actor, payload.permissions if payload.permissions is not None else permissions.ROLES[payload.role]["permissions"])
    try:
        check_password_policy(payload.password, payload.username)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if db.query(models.StaffUser).filter(models.StaffUser.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe.")

    u = models.StaffUser(
        username=payload.username, display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password), role=payload.role,
        permissions=permissions.serialize(perms), must_change_password=True,   # la clave temporal se cambia al entrar
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    audit.record(db, audit.Actor.from_user(actor), "user.created", "user", u.id,
                 {"username": u.username, "role": u.role, "permissions": perms}, request)
    return _out(u)


@router.patch("/users/{user_id}", response_model=schemas.StaffUserOut, summary="Editar usuario")
def update_user(
    user_id: int, payload: schemas.StaffUserUpdate, request: Request,
    actor: models.StaffUser = manager, db: Session = Depends(get_db),
):
    target = _get(db, user_id)
    _only_owner_touches_owner(actor, target.role)
    changes: dict = {}

    new_role = payload.role if payload.role is not None else target.role
    if payload.role is not None:
        _check_role(payload.role)
        _only_owner_touches_owner(actor, payload.role)
        if target.role == "owner" and payload.role != "owner" and not _other_active_owner(db, target.id):
            raise HTTPException(status_code=409, detail="Siempre debe quedar al menos un propietario activo.")

    if payload.active is False:
        if target.id == actor.id:
            raise HTTPException(status_code=409, detail="No puedes desactivar tu propia cuenta.")
        if target.role == "owner" and not _other_active_owner(db, target.id):
            raise HTTPException(status_code=409, detail="Siempre debe quedar al menos un propietario activo.")

    if payload.display_name is not None and payload.display_name.strip() != target.display_name:
        changes["display_name"] = payload.display_name.strip()
        target.display_name = payload.display_name.strip()

    if payload.role is not None and payload.role != target.role:
        changes["role"] = {"from": target.role, "to": payload.role}
        target.role = payload.role
    if payload.permissions is not None or "role" in changes:
        wanted = payload.permissions if payload.permissions is not None else permissions.ROLES[new_role]["permissions"]
        perms = permissions.ALL_PERMISSIONS if new_role == "owner" else _validate_perms(actor, wanted)
        if permissions.serialize(perms) != target.permissions:
            changes["permissions"] = perms
            target.permissions = permissions.serialize(perms)

    action = "user.updated"
    if payload.active is not None and payload.active != target.active:
        target.active = payload.active
        action = "user.reactivated" if payload.active else "user.deactivated"
        if payload.active:
            target.failed_attempts, target.locked_until = 0, None
    db.commit()
    if action == "user.deactivated":
        revoke_sessions(db, target.id)
    if changes or action != "user.updated":
        audit.record(db, audit.Actor.from_user(actor), action, "user", target.id,
                     {"username": target.username, **changes}, request)
    db.refresh(target)
    return _out(target)


@router.post("/users/{user_id}/reset-password", response_model=schemas.StaffUserOut, summary="Restablecer contraseña")
def reset_password(
    user_id: int, payload: schemas.ResetPasswordIn, request: Request,
    actor: models.StaffUser = manager, db: Session = Depends(get_db),
):
    target = _get(db, user_id)
    _only_owner_touches_owner(actor, target.role)
    try:
        check_password_policy(payload.new_password, target.username)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    target.password_hash = hash_password(payload.new_password)
    target.must_change_password = True
    target.failed_attempts, target.locked_until = 0, None
    db.commit()
    revoke_sessions(db, target.id)
    audit.record(db, audit.Actor.from_user(actor), "user.password_reset", "user", target.id,
                 {"username": target.username}, request)
    db.refresh(target)
    return _out(target)
