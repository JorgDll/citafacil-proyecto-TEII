"""Permisos y roles base del panel de administración (HU-6).

Un rol sólo rellena la lista inicial de permisos; el propietario puede ajustarla por
empleado. El rol "owner" tiene todos los permisos siempre y no es editable.
"""
from __future__ import annotations

from typing import Iterable

# Catálogo (el orden es el de la interfaz).
PERMISSIONS: dict[str, str] = {
    "appointments.view": "Ver reservas y estadísticas",
    "customers.phones": "Ver teléfonos completos de los clientes",
    "appointments.confirm": "Confirmar reservas y marcarlas como realizadas",
    "appointments.cancel": "Cancelar reservas",
    "appointments.delete": "Eliminar reservas",
    "services.manage": "Crear, editar y eliminar servicios",
    "analytics.view": "Ver análisis de demanda",
    "reminders.run": "Enviar recordatorios",
    "users.manage": "Gestionar usuarios y permisos",
    "audit.view": "Ver el registro de actividad",
}
ALL_PERMISSIONS = list(PERMISSIONS)

ROLES: dict[str, dict] = {
    "owner": {"label": "Propietario", "permissions": ALL_PERMISSIONS},
    "manager": {
        "label": "Gerente",
        "permissions": [p for p in ALL_PERMISSIONS if p != "users.manage"],
    },
    "reception": {
        "label": "Recepción",
        "permissions": [
            "appointments.view", "customers.phones", "appointments.confirm",
            "appointments.cancel", "reminders.run",
        ],
    },
    "viewer": {"label": "Solo consulta", "permissions": ["appointments.view", "analytics.view"]},
}


def parse(text: str) -> set[str]:
    return {p for p in (text or "").split(",") if p}


def serialize(perms: Iterable[str]) -> str:
    return ",".join(p for p in ALL_PERMISSIONS if p in set(perms))      # orden estable


def invalid(perms: Iterable[str]) -> list[str]:
    return sorted(set(perms) - set(PERMISSIONS))


def effective(user) -> set[str]:
    """Permisos reales de un usuario (el propietario siempre tiene todos)."""
    if user.role == "owner":
        return set(ALL_PERMISSIONS)
    return parse(user.permissions) & set(PERMISSIONS)


def has(user, permission: str) -> bool:
    return permission in effective(user)
