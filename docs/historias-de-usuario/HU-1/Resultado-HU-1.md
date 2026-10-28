# Resultado HU-1 — Reserva rápida con datos recordados por dispositivo

**Historia:** Como usuario recurrente, quiero reservar directamente usando mis datos guardados, para no tener que rellenar el formulario en cada reserva.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-1.md`

## Decisiones
- Sin login ni contraseña: el dispositivo se identifica con un token aleatorio (`secrets.token_urlsafe(32)`) en una cookie `HttpOnly`, `SameSite=Lax`, 365 días.
- El servidor guarda solo el SHA-256 del token; el token en claro nunca se persiste.
- Un token por dispositivo: varios dispositivos del mismo cliente no chocan, y un token válido nunca se sobreescribe.
- El proyecto corre solo en local, así que el frontend se sirve desde FastAPI (`http://localhost:8000/app/`). Mismo origen que la API: la cookie funciona sin cambios de CORS (por `file://` no habría funcionado).
- Si un dispositivo conocido reserva con datos distintos a los guardados, el modal pregunta si actualizar.

## Flujo
1. Al cargar, `GET /api/device/profile`. Si el dispositivo es conocido, se prellenan nombre y celular y se muestra el aviso "Usar otros datos".
2. Tras reservar:
   - Dispositivo desconocido: modal "¿Guardar tus datos?" → `POST /api/device/remember`.
   - Dispositivo conocido con datos distintos: modal "¿Actualizar?" → `PUT /api/device/profile`.
   - Dispositivo conocido con los mismos datos: sin modal.

## Cambios
**Nuevos:** `backend/app/device.py`, `backend/app/routers/device.py`, `backend/tests/conftest.py`, `backend/tests/test_device_profile.py`, `Plan-HU-1.md`.

**Modificados:** `models.py` (tabla `device_profiles`), `schemas.py`, `crud.py`, `config.py`, `main.py` (router + montaje de `/app`), `.env.example` (`DEVICE_COOKIE_NAME`, `DEVICE_COOKIE_DAYS`, `COOKIE_SECURE`), `frontend/index.html`, `frontend/admin.html` (URL de API por defecto), `tests/test_booking.py` (entorno y fixture pasan a `conftest.py`), `README.md`, `docs/Proyect-doc.md`.

## API nueva
| Método | Ruta | Resultado |
|---|---|---|
| GET | `/api/device/profile` | `known:true` con datos, o `known:false` |
| POST | `/api/device/remember` | 201 crea token y cookie; 200 `already_known` si ya es conocido (no toca nada) |
| PUT | `/api/device/profile` | Actualiza datos; 401 sin cookie válida |
| DELETE | `/api/device` | Olvida el dispositivo; 401 sin cookie válida |

## Base de datos
Tabla nueva `device_profiles` (`token_hash` único, `customer_name`, `customer_phone`, `created_at`, `last_used_at`). `create_all` la crea al arrancar; no hay migración porque no cambia ninguna tabla existente. `seed.py` no interviene.

## Pruebas
`python -m pytest` (desde `backend/`): **9 pasan** (6 previos + 3 nuevos).

| Test | Cubre |
|---|---|
| `test_happy_path_remember_and_prefill` | Reservar, guardar, cookie HttpOnly, hash SHA-256 en BD, prellenado, segunda reserva, actualización |
| `test_edge_many_devices_and_token_never_overwritten` | Dos dispositivos con el mismo celular → dos tokens válidos; aceptar de nuevo no cambia token ni datos |
| `test_edge_invalid_token_is_unknown_device` | Token forjado = desconocido, 401 en PUT/DELETE, token inválido tras olvidar, 422 con teléfono inválido |

Verificación manual en navegador (BD temporal): el modal aparece tras reservar, `document.cookie` no muestra el token, al recargar los campos vienen prellenados y la BD solo contiene el hash de 64 caracteres.

## Limitaciones conocidas
- No probado manualmente: segundo dispositivo real ni el modal de actualizar (cubiertos solo por tests).
- Sin expiración por inactividad (solo `Max-Age` de la cookie) ni límite de uso en `/remember`.
- Quien tenga acceso al navegador ve los datos prellenados; `DELETE /api/device` permite olvidarlos, pero el frontend aún no ofrece un botón para ello.
- `seed.py` falla en consolas Windows cp1252 por los símbolos ✔ (preexistente); usar `PYTHONUTF8=1`.
