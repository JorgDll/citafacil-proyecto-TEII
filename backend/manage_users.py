"""Recuperacion de acceso al panel de administracion (HU-6). Se ejecuta en el servidor.

Uso:
    python manage_users.py list
    python manage_users.py create-owner <usuario> [--name "Nombre visible"]
    python manage_users.py reset-password <usuario>

La contrasena se pide por teclado (getpass): nunca se pasa como argumento para que no
quede en el historial de la terminal. Restablecer desbloquea y reactiva la cuenta y
cierra todas sus sesiones.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from datetime import datetime

from app import audit, models, permissions
from app.auth import check_password_policy, hash_password, revoke_sessions
from app.database import Base, SessionLocal, engine

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def _ask_password(username: str) -> str:
    pw = getpass.getpass("Contrasena nueva: ")
    if pw != getpass.getpass("Repite la contrasena: "):
        sys.exit("Las contrasenas no coinciden.")
    try:
        check_password_policy(pw, username)
    except ValueError as e:
        sys.exit(str(e))
    return pw


def cmd_list(db) -> None:
    users = db.query(models.StaffUser).order_by(models.StaffUser.id).all()
    if not users:
        print("No hay usuarios. Crea el primero con: python manage_users.py create-owner <usuario>")
    for u in users:
        state = "activo" if u.active else "DESACTIVADO"
        locked = " (bloqueado)" if u.locked_until and u.locked_until > datetime.utcnow() else ""
        print(f"{u.id:>3}  {u.username:<20} {u.role:<10} {state}{locked}  {u.display_name}")


def cmd_create_owner(db, username: str, name: str) -> None:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        sys.exit("Usuario invalido: 3 a 32 caracteres entre minusculas, numeros, punto, guion y guion bajo.")
    if db.query(models.StaffUser).filter_by(username=username).first():
        sys.exit("Ese usuario ya existe. Usa reset-password para cambiar su contrasena.")
    user = models.StaffUser(
        username=username, display_name=name or username, password_hash=hash_password(_ask_password(username)),
        role="owner", permissions=permissions.serialize(permissions.ALL_PERMISSIONS),
    )
    db.add(user)
    db.commit()
    audit.record(db, audit.Actor.system(), "user.created", "user", user.id,
                 {"username": username, "role": "owner", "via": "manage_users.py"})
    print(f"Propietario '{username}' creado.")


def cmd_reset_password(db, username: str) -> None:
    user = db.query(models.StaffUser).filter_by(username=username.strip().lower()).first()
    if not user:
        sys.exit("Usuario no encontrado. Usa 'list' para ver los existentes.")
    user.password_hash = hash_password(_ask_password(user.username))
    user.active, user.must_change_password = True, False
    user.failed_attempts, user.locked_until = 0, None
    db.commit()
    revoke_sessions(db, user.id)
    audit.record(db, audit.Actor.system(), "user.password_reset", "user", user.id,
                 {"username": user.username, "via": "manage_users.py"})
    print(f"Contrasena de '{user.username}' restablecida; sus sesiones se cerraron.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recuperacion de acceso al panel (CitaFacil).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="lista los usuarios")
    p_create = sub.add_parser("create-owner", help="crea un propietario")
    p_create.add_argument("username")
    p_create.add_argument("--name", default="", help="nombre visible")
    p_reset = sub.add_parser("reset-password", help="restablece la contrasena de un usuario")
    p_reset.add_argument("username")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.cmd == "list":
            cmd_list(db)
        elif args.cmd == "create-owner":
            cmd_create_owner(db, args.username, args.name)
        else:
            cmd_reset_password(db, args.username)
    finally:
        db.close()


if __name__ == "__main__":
    main()
