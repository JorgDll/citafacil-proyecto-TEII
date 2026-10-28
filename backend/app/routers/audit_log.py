"""Consulta del registro de actividad (HU-6). Sólo lectura: no hay rutas para editar o borrar."""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_permission
from ..database import get_db

router = APIRouter(
    prefix="/api/admin/audit",
    tags=["Actividad"],
    dependencies=[Depends(require_permission("audit.view"))],
)


def _detail(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {"valor": value}
    except ValueError:
        return {}


@router.get("", response_model=schemas.AuditPageOut, summary="Registro de actividad")
def list_audit(
    user_id: Optional[int] = Query(None, description="Filtrar por usuario"),
    action: Optional[str] = Query(None, description='Acción exacta, o prefijo si termina en "." (ej. "appointment.")'),
    entity: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.AuditLog)
    if user_id is not None:
        q = q.filter(models.AuditLog.user_id == user_id)
    if action:
        q = q.filter(models.AuditLog.action.like(action + "%")) if action.endswith(".") else q.filter(models.AuditLog.action == action)
    if entity:
        q = q.filter(models.AuditLog.entity == entity)
    if date_from:
        q = q.filter(models.AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.filter(models.AuditLog.created_at <= datetime.combine(date_to, time.max))
    total = q.count()
    rows = q.order_by(models.AuditLog.id.desc()).offset(offset).limit(limit).all()
    items = [
        schemas.AuditItemOut(
            id=r.id, created_at=r.created_at, actor_type=r.actor_type, user_id=r.user_id,
            actor_name=r.actor_name, action=r.action, entity=r.entity, entity_id=r.entity_id,
            detail=_detail(r.detail), ip=r.ip,
        )
        for r in rows
    ]
    return schemas.AuditPageOut(total=total, limit=limit, offset=offset, items=items)


@router.get("/actors", summary="Usuarios que aparecen en el registro (para el filtro)")
def actors(db: Session = Depends(get_db)):
    rows = (
        db.query(models.AuditLog.user_id, models.AuditLog.actor_name)
        .filter(models.AuditLog.user_id.isnot(None))
        .distinct()
        .all()
    )
    seen: dict[int, str] = {}
    for uid, name in rows:
        seen[uid] = name
    return [{"user_id": uid, "name": name} for uid, name in sorted(seen.items())]
