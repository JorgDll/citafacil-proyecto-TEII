"""Registro de actividad (HU-6): quién hizo qué y cuándo. Sólo se agrega, nunca se edita.

Se escribe después de ejecutarse la acción con éxito. Los detalles no incluyen
teléfonos completos de clientes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .utils import local_now


@dataclass(frozen=True)
class Actor:
    type: str                     # staff | customer | system
    user_id: Optional[int]
    name: str

    @classmethod
    def from_user(cls, user: models.StaffUser) -> "Actor":
        return cls("staff", user.id, user.display_name or user.username)

    @classmethod
    def customer(cls, name: str) -> "Actor":
        return cls("customer", None, name or "Cliente")

    @classmethod
    def system(cls) -> "Actor":
        return cls("system", None, "Sistema")


def record(
    db: Session,
    actor: Actor,
    action: str,
    entity: str = "",
    entity_id: Optional[int] = None,
    detail: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    db.add(models.AuditLog(
        created_at=local_now(),
        actor_type=actor.type,
        user_id=actor.user_id,
        actor_name=actor.name[:80],
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=json.dumps(detail or {}, ensure_ascii=False, default=str),
        ip=(request.client.host if request is not None and request.client else ""),
    ))
    db.commit()
