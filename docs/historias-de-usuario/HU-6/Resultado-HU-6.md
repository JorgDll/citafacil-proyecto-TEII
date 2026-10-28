# Resultado HU-6 — Cuentas de administración con roles y registro de actividad

**Historia:** Como dueño del negocio, quiero que cada empleado entre al panel con su propio usuario y contraseña, y que yo pueda definir qué puede hacer cada uno, para proteger los datos de mis clientes y saber quién confirmó, canceló o eliminó cada reserva.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-6.md`

## Decisiones
- **Permisos:** roles base (Propietario, Gerente, Recepción, Solo consulta) que solo rellenan la lista inicial; el propietario puede marcar o desmarcar permisos por empleado (usuario).
- **`ADMIN_TOKEN`:** queda solo como clave de instalación para crear al primer propietario; después deja de abrir la API (usuario).
- **Sesión por cookie `HttpOnly` + `SameSite=Strict`**, como HU-1; el servidor guarda solo el SHA-256 del token. Toda petición que no es GET exige `X-Requested-With: citafacil` (defensa extra contra CSRF).
- **Contraseñas con `hashlib.scrypt`** de la biblioteca estándar (sin dependencias nuevas), sal por usuario; un usuario inexistente se verifica contra un hash falso (mismo tiempo, mismo mensaje).
- **Bloqueo** de la cuenta 15 min tras 5 fallos seguidos; sesiones de 12 h; las contraseñas temporales obligan a cambiarlas al entrar.
- **Los usuarios se desactivan, no se borran** (para que la auditoría conserve al autor); siempre queda un propietario activo; nadie se desactiva a sí mismo; quien no es propietario no puede crear ni tocar propietarios ni otorgar permisos que no tiene.
- **Teléfonos protegidos:** sin `customers.phones` se enmascaran (`+507 ****4567`) en el listado y en las respuestas.

## Cambios
**Nuevos:** `backend/app/permissions.py`, `audit.py`, `routers/staff_auth.py`, `routers/users.py`, `routers/audit_log.py`, `backend/manage_users.py`, `backend/tests/test_staff.py`, `frontend/admin-staff.js`, `docs/historias-de-usuario/HU-6/`.

**Modificados:**
- `backend/app/auth.py` (se reescribe: ya no hay `require_admin` por token), `models.py` (`StaffUser`, `StaffSession`, `AuditLog`), `config.py` y `.env.example`, `utils.py` (`mask_phone`), `schemas.py`, `main.py`.
- `backend/app/routers/admin.py` (permiso por ruta y registro de cada acción), `analytics.py` (`analytics.view`), `manage.py` (acciones del cliente por enlace al registro).
- `frontend/admin.html` (acceso con usuario y contraseña, instalación, cambio de clave, tarjetas por permiso, escape de texto).
- `backend/tests/conftest.py` (fábrica `staff_client` con sesión real), `test_booking.py` y `test_analytics.py` (usaban `X-Admin-Token`), `README.md`, `docs/Proyect-doc.md`.

## Registro de actividad
Solo se agrega (no hay rutas para editar o borrar). Guarda quién (usuario, "Cliente" por enlace o "Sistema"), cuándo (hora local), acción, entidad, detalle sin teléfonos completos e IP. Acciones: acceso (`auth.login`, `login_failed`, `logout`, `password_changed`), reservas (`confirmed`, `done`, `cancelled`, `reopened`, `deleted` con resumen de lo borrado), servicios, recordatorios, usuarios y, de HU-5, `customer_cancelled` / `customer_rescheduled`. La pantalla **Actividad** filtra por usuario, acción y fechas, y pagina.

## Pruebas
`python -m pytest` (desde `backend/`): **26 pasan** (22 previos + 4 nuevos), también con variables de entorno hostiles. Los 3 tests que usaban `X-Admin-Token` se adaptaron a sesiones reales.

| Test | Cubre |
|---|---|
| `test_staff_flow_setup_roles_forced_password_change_and_audit` | Instalación con `ADMIN_TOKEN` (token incorrecto → 403), cookie `HttpOnly; SameSite=Strict`, creación de la recepcionista, cambio de clave obligatorio, confirmar/cancelar sí y eliminar no, y el registro dice quién hizo cada cosa |
| `test_edge_permission_matrix_phone_masking_csrf_and_legacy_token` | 13 endpoints: 403 sin el permiso y distinto de 403 con solo ese; cancelar exige su propio permiso; teléfonos enmascarados; sin sesión → 401; el token compartido ya no abre nada; POST sin cabecera de seguridad → 403; la instalación no se repite |
| `test_edge_account_security_lockout_hashes_sessions_and_owner_rules` | Hash salado y no manipulable; solo hashes en la BD; mismo mensaje para usuario inexistente; bloqueo tras 5 fallos (y 429 aun con la clave correcta); sesión vencida; desactivar revoca sesiones; cambiar la clave cierra las demás; política de contraseña; último propietario; sin escalada de privilegios |
| `test_audit_log_filters_pagination_customer_actions_and_append_only` | Filtros (prefijo, exacto, usuario, fechas), paginación estable, acciones del cliente por enlace como "Cliente", sin teléfonos completos, `audit.view` obligatorio y solo lectura |

Cuatro de los fallos iniciales fueron suposiciones erróneas de los propios tests (contar los intentos fallidos, varias sesiones de un mismo usuario), no de la aplicación.

**Verificación manual en navegador (BD temporal):** BD vacía → "Crear al propietario" (token incorrecto rechazado) → entra como Propietario con todas las tarjetas; la cookie no es visible desde JavaScript; creación de "Rosa" con el rol Recepción y sin "Ver teléfonos"; Rosa entra, ve el error si la clave nueva es corta y debe cambiarla; solo ve Reservas y Servicios, sin eliminar ni añadir servicios y con teléfonos enmascarados; un `DELETE` directo suyo devuelve 403; confirma y cancela reservas; el propietario ve en **Actividad** cada acción con su autor, el intento de acceso fallido y el resumen de la reserva eliminada. Una reserva con el nombre `<img src=x onerror=…>` se ve como texto y no se ejecuta. En la BD solo hay hashes `scrypt$…` y un token de sesión de 64 caracteres hasheado; ningún teléfono completo en `audit_log`.

## Limitaciones conocidas
- **Cambio incompatible:** `X-Admin-Token` ya no abre la API admin; hay que crear al propietario al actualizar (panel o `manage_users.py`). Mientras no exista, el panel no funciona.
- La auditoría se escribe después de la acción, no en la misma transacción: un fallo justo ahí dejaría una acción sin registro.
- Sin recuperación por correo ni segundo factor. El bloqueo es por cuenta, no por IP, y la sesión dura 12 h fijas (sin renovación).
- No probado en el navegador: el bloqueo por intentos, la desactivación en vivo de una sesión abierta y el ancho móvil (sí por tests de API). El flujo interactivo de `manage_users.py` (contraseña por teclado) tampoco; sí sus mensajes de error.
- Fuera de alcance: 2FA, restablecer por correo, permisos por servicio, exportar o purgar la auditoría, límite por IP.
