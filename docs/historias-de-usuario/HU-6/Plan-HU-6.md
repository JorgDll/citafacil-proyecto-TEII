# Plan HU-6 — Cuentas de administración con roles y registro de actividad

## Contexto
HU-6: "como dueño, quiero que cada empleado entre al panel con su propio usuario y contraseña, y que yo pueda definir qué puede hacer cada uno, para proteger los datos de mis clientes y saber quién confirmó, canceló o eliminó cada reserva".

Hoy todo el panel admin (`routers/admin.py`, `routers/analytics.py`) se protege con **un único `ADMIN_TOKEN` compartido** (`auth.require_admin`, cabecera `X-Admin-Token`, guardado en `localStorage`): no hay forma de saber quién hizo qué, ni de limitar a un empleado. Además, `admin.html` pinta nombres de clientes con `innerHTML` sin escapar: un nombre como `<img onerror=…>` ejecutaría código con la sesión del administrador (XSS almacenado) — se corrige aquí porque con cuentas y permisos pasa a ser más grave.

Decisiones del usuario: **roles base + permisos ajustables por empleado**; el **`ADMIN_TOKEN` queda solo para crear el primer propietario** (después deja de servir en la API).

Rama: `feature/historias-usuario-v2` (sin commit/push hasta que lo pidas).

## Diseño
- **Sesión por cookie `HttpOnly`** (como HU-1): al entrar se genera un token aleatorio; el servidor guarda solo su SHA-256 en `staff_sessions` (revocable, con vencimiento). Cookie `citafacil_admin`: `HttpOnly`, `SameSite=Strict`, `Secure` si `COOKIE_SECURE`. Defensa extra contra CSRF: toda petición que no sea GET exige la cabecera `X-Requested-With: citafacil` (un formulario de otro sitio no puede ponerla). Desaparece el token en `localStorage`.
- **Contraseñas** con `hashlib.scrypt` de la biblioteca estándar (sin dependencias nuevas): sal aleatoria de 16 bytes, formato `scrypt$n$r$p$sal$hash`, comparación con `hmac.compare_digest`. Política: mínimo 10 caracteres y distinta del usuario. Usuario desconocido → se verifica contra un hash falso (mismo tiempo y mismo mensaje genérico "Usuario o contraseña incorrectos").
- **Bloqueo**: tras 5 intentos fallidos la cuenta se bloquea 15 minutos (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES`); un acceso correcto reinicia el contador. Sesiones de 12 h (`SESSION_HOURS`).
- **Permisos** (catálogo en `app/permissions.py`) y **roles base** que solo rellenan la lista inicial:
| Permiso | Permite |
|---|---|
| `appointments.view` | Ver reservas y estadísticas |
| `customers.phones` | Ver teléfonos completos (sin él se enmascaran: `+507 ****4567`) |
| `appointments.confirm` | Confirmar y marcar como realizada |
| `appointments.cancel` | Cancelar reservas |
| `appointments.delete` | Eliminar reservas |
| `services.manage` | Crear, editar y eliminar servicios |
| `analytics.view` | Ver análisis de demanda |
| `reminders.run` | Enviar recordatorios |
| `users.manage` | Gestionar usuarios y permisos |
| `audit.view` | Ver el registro de actividad |
  Roles: **Propietario** (todo, siempre; no editable), **Gerente** (todo menos `users.manage`), **Recepción** (ver, teléfonos, confirmar, cancelar, recordatorios), **Solo consulta** (ver reservas y análisis). El propietario puede marcar/desmarcar casillas por empleado; lo guardado es la lista de permisos del usuario (el rol es la etiqueta de partida).
- **Reglas de seguridad de cuentas**: no se borran usuarios (se desactivan, para conservar la auditoría); desactivar o cambiar la contraseña revoca sus sesiones; nadie puede desactivarse a sí mismo; **siempre debe quedar al menos un propietario activo**; contraseña temporal del propietario → el empleado **debe cambiarla al entrar** (`must_change_password`: hasta entonces solo puede cambiar la clave o salir).
- **Primer propietario**: mientras `staff_users` esté vacía, el panel muestra "Crear propietario" y pide el `ADMIN_TOKEN` como clave de instalación (`POST /api/admin/auth/setup`, comparación en tiempo constante; se rechaza si sigue el valor por defecto `cambia-este-token-admin`). Con usuarios existentes, el endpoint responde 409 y el token ya no abre nada. Recuperación: `python manage_users.py reset-password <usuario>` (local, contraseña por `getpass`, nunca por argumento).
- **Registro de actividad** (`audit_log`, solo se agrega, sin API de edición/borrado): quién (usuario o "cliente por enlace"/sistema), cuándo, acción, entidad y detalle (sin teléfonos completos). Acciones: `auth.login`, `auth.login_failed`, `auth.logout`, `auth.password_changed`, `appointment.confirmed|done|cancelled|reopened|deleted` (el borrado guarda un resumen: cliente, servicio, fecha), `service.created|updated|deleted`, `reminders.run`, `user.created|updated|deactivated|reactivated|password_reset` y, de HU-5, `appointment.customer_cancelled|customer_rescheduled`. Se escribe tras ejecutarse la acción con éxito.

## Backend
- `backend/app/models.py`: `StaffUser` (`username` único en minúsculas, `display_name`, `password_hash`, `role`, `permissions`, `active`, `must_change_password`, `failed_attempts`, `locked_until`, `created_at`, `last_login_at`), `StaffSession` (`user_id`, `token_hash` único, `created_at`, `expires_at`), `AuditLog` (`created_at` indexado, `actor_type`, `user_id`, `actor_name`, `action` indexado, `entity`, `entity_id`, `detail`, `ip`). Tablas nuevas: `create_all` las crea, `citafacil.db` sigue funcionando.
- `backend/app/permissions.py` (nuevo): catálogo, roles base, `effective_permissions(user)`.
- `backend/app/auth.py` (reescribe `require_admin`): `hash_password`/`verify_password`, sesiones (reutiliza `device.new_token`/`hash_token`), dependencia `current_staff`, `require_permission(*perms)` y `require_any(*perms)`, guarda CSRF, `must_change_password`. 401 sin sesión, 403 sin permiso.
- `backend/app/audit.py` (nuevo): `record(db, actor, action, entity, entity_id, detail, request)`.
- `backend/app/config.py` + `.env.example`: `session_hours`, `login_max_attempts`, `login_lock_minutes`, `password_min_length`, `staff_cookie_name`.
- `backend/app/routers/staff_auth.py` (nuevo, `/api/admin/auth`): `GET /setup-status` (`{needs_setup}`), `POST /setup`, `POST /login`, `POST /logout`, `GET /me` (usuario, rol, permisos, `must_change_password`), `POST /password`.
- `backend/app/routers/users.py` (nuevo, `users.manage`): `GET /api/admin/users`, `POST` (usuario, nombre, rol, permisos, contraseña temporal), `PATCH /{id}` (nombre, rol, permisos, activo), `POST /{id}/reset-password`, `GET /api/admin/permissions` (catálogo y roles para la interfaz).
- `backend/app/routers/audit_log.py` (nuevo, `audit.view`): `GET /api/admin/audit` con filtros `user_id`, `action`, `entity`, `from`, `to` y paginación (`limit`, `offset`, `total`).
- `backend/app/routers/admin.py`: cada ruta con su permiso — listar reservas/estadísticas `appointments.view` (teléfonos enmascarados sin `customers.phones`); `PATCH` según el estado destino (`confirmed|done|pending` → `appointments.confirm`, `cancelled` → `appointments.cancel`); `DELETE` → `appointments.delete`; servicios `services.manage` (listar basta con `appointments.view`, `services.manage` o `analytics.view`); recordatorios `reminders.run`. Cada acción exitosa llama a `audit.record`.
- `backend/app/routers/analytics.py`: `analytics.view`. `backend/app/routers/manage.py` (HU-5): registra las acciones del cliente. `backend/app/main.py`: incluir routers.
- `backend/manage_users.py` (nuevo): `create-owner`, `reset-password`, `list` para recuperación local.

## Frontend
- `frontend/admin.html`: la entrada pasa a **usuario + contraseña** (y modo "Crear propietario" cuando `needs_setup`); pantalla de cambio de contraseña obligatorio; cabecera con nombre, rol, "Cambiar contraseña" y "Salir". `api()` usa la cookie (`credentials`) y la cabecera `X-Requested-With`; 401 → pantalla de acceso; 403 → aviso "No tienes permiso". Cada tarjeta y acción se muestra solo si el usuario tiene el permiso (cosmético: el servidor es quien manda). Se elimina el uso de `ADMIN_TOKEN`/`localStorage` y se limpia el valor antiguo.
- **Corrección XSS**: `esc()` para todo texto que viene de clientes o del servidor en `innerHTML` (nombres, servicios, mensajes).
- `frontend/admin-staff.js` (nuevo, para no inflar `admin.html`): tarjeta **Usuarios** (lista, crear, editar con rol + casillas de permisos, activar/desactivar, restablecer contraseña; modales propios) y tarjeta **Actividad** (filtros por usuario, acción y fechas, tabla paginada con acciones en español legible y quién la hizo). Textos siempre con `textContent`.

## Tests
`conftest.py`: fija `SESSION_HOURS`, `LOGIN_*`, `PASSWORD_MIN_LENGTH` y un fixture `staff_client(role|permissions)` que crea un usuario y devuelve un `TestClient` con su sesión (cabecera CSRF incluida). Se **actualizan** `test_booking::test_admin_auth` y `test_analytics.py` (usaban `X-Admin-Token`). Nuevos, con la misma estructura de camino feliz + casos límite:
1. **`test_staff_flow`** (camino feliz): `setup` con `ADMIN_TOKEN` crea al propietario → login con cookie `HttpOnly; SameSite=Strict` → crea a "Recepción" con clave temporal → ese usuario entra, debe cambiarla (antes todo lo demás → 403) → confirma, cancela y elimina reservas → el propietario ve en `/audit` quién hizo cada acción, con detalle del borrado y sin teléfonos.
2. **`test_edge_permissions_and_csrf`**: matriz de permisos (cada endpoint protegido → 403 sin el permiso, 200 con él); `PATCH` a `cancelled` exige `appointments.cancel` aunque tenga `confirm`; teléfonos enmascarados sin `customers.phones`; sin cookie → 401; el antiguo `X-Admin-Token` ya no abre nada; `setup` con usuarios existentes → 409 y con token incorrecto o por defecto → rechazo; POST sin `X-Requested-With` → 403.
3. **`test_edge_accounts_security`**: bloqueo tras 5 fallos (y con la clave correcta mientras dura → sigue bloqueado), mismo mensaje para usuario inexistente; la BD guarda solo hash `scrypt$…` (la contraseña y el token de sesión en claro no aparecen); sesión vencida rechazada; desactivar revoca sesiones; no se puede desactivar el último propietario, ni degradarlo, ni desactivarse a uno mismo; política de contraseña.
4. **`test_audit_log`**: filtros por usuario/acción/fechas y paginación; sin permiso `audit.view` → 403; acciones del cliente por enlace (HU-5) quedan como "cliente"; no existen rutas para editar o borrar registros.

## Docs
`docs/historias-de-usuario/HU-6/Plan-HU-6.md` (copia) y `Resultado-HU-6.md`; `README.md` (nuevo flujo de acceso, variables, `manage_users.py`, aviso de que `X-Admin-Token` cambió de función) y `docs/Proyect-doc.md` (quitar "token admin compartido" de los puntos de atención).

## Verificación
1. `cd backend; .venv\Scripts\python.exe -m pytest` en verde, también con `.env` ausente y variables hostiles.
2. BD temporal, servidor en `:8765`; Playwright en `/app/admin.html`: BD vacía → "Crear propietario" (rechaza token incorrecto/por defecto) → entrar → crear "Recepción" con permisos limitados → salir → entrar como ella (cambio de clave obligatorio, solo ve lo permitido, teléfonos enmascarados) → confirmar, cancelar y eliminar una reserva → entrar como propietario y comprobar en Actividad quién hizo cada cosa; desactivar al empleado y ver que su sesión muere; 5 contraseñas malas → bloqueo; reserva con nombre `<img src=x onerror=…>` se ve como texto en el panel.
3. Revisar la BD (`staff_users.password_hash`, `staff_sessions.token_hash`) y que la cookie no sea visible en `document.cookie`.
4. Cerrar servidor y borrar la BD temporal; `citafacil.db` real no se toca.

## Riesgos / notas
- **Cambio incompatible**: `X-Admin-Token` deja de abrir la API admin (queda como clave de instalación). Hay que crear el primer propietario al actualizar; mientras no exista ningún usuario, el panel no funciona.
- La auditoría se escribe después de la acción (no en la misma transacción): si fallara justo ahí, una acción quedaría sin registro. Aceptable aquí; migrar a transacción única sería un refactor de `crud.py`.
- Sin recuperación por correo ni segundo factor: la clave olvidada se restablece con el propietario o con `manage_users.py`.
- El bloqueo es por cuenta, no por IP; sesión de duración fija de 12 h (sin renovación deslizante).
- Fuera de alcance: 2FA, restablecer contraseña por correo, permisos por servicio, exportar o purgar la auditoría, limitar intentos por IP.
