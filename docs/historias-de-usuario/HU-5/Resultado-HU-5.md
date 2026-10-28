# Resultado HU-5 — Autogestión de la cita desde un enlace personal

**Historia:** Como cliente que ya reservó una cita, quiero cancelarla o reprogramarla desde un enlace personal que llega en mi mensaje de confirmación de WhatsApp, para no tener que llamar al negocio y para que mi horario quede libre para otra persona.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-5.md`

## Decisiones
- **Enlace sin login, como HU-1:** token aleatorio por cita (`secrets.token_urlsafe(32)`); el servidor guarda solo su SHA-256. El enlace es `{PUBLIC_BASE_URL}/app/manage.html#t=<token>`: el token va en el *fragmento*, así no llega al servidor, a los logs ni al `Referer`; la página lo envía en `X-Manage-Token`.
- **Tabla nueva `appointment_links`** en vez de columnas en `appointments`: `create_all` crea la tabla sola y `citafacil.db` sigue funcionando sin `ALTER TABLE`.
- **Reglas del usuario:** anticipación mínima de 2 h (`MANAGE_CUTOFF_HOURS`) y máximo 2 reprogramaciones (`MANAGE_MAX_RESCHEDULES`).
- **Cancelar es una operación delicada** (indicación del usuario): exige escribir **"Cancelar cita"** en un modal y **revoca el enlace** (se borra la fila), de modo que el mismo URL deja de servir. La confirmación también se valida en el servidor (campo obligatorio; sin distinguir mayúsculas ni espacios sobrantes). Reprogramar no revoca el enlace.
- **Reprogramar** excluye a la propia cita al comprobar disponibilidad (si no, un servicio de 45 min no podría correrse 30 min), devuelve la cita a `pending` (el negocio la reconfirma) y reinicia `reminder_sent`.
- Ambas acciones envían un WhatsApp de aviso (demo: se registra en el log).

## Cambios
**Nuevos:** `backend/app/manage.py`, `backend/app/routers/manage.py`, `backend/tests/test_manage.py`, `frontend/manage.html`, `frontend/scheduler.js`, `frontend/scheduler.css`, `docs/historias-de-usuario/HU-5/`.

**Modificados:**
- `backend/app/models.py` (`AppointmentLink`), `config.py` y `.env.example` (`PUBLIC_BASE_URL`, `MANAGE_CUTOFF_HOURS`, `MANAGE_MAX_RESCHEDULES`).
- `backend/app/availability.py`: `exclude_id` opcional en `build_day_slots`, `month_overview` e `is_slot_free`.
- `backend/app/notifications.py`: el enlace en la confirmación y los avisos de reprogramación y cancelación.
- `backend/app/schemas.py`, `routers/public.py` (`POST /api/appointments` devuelve `manage_url`), `crud.py` (al borrar una cita se borra su enlace), `main.py`.
- `frontend/index.html`: el calendario y las franjas pasan al módulo compartido `scheduler.js`/`.css` (mismo comportamiento) y la tarjeta de éxito agrega "Cambiar o cancelar mi cita".
- `backend/tests/conftest.py` fija las nuevas variables (lección del aislamiento de `.env`), `README.md`, `docs/Proyect-doc.md`.

## API (cabecera `X-Manage-Token`)
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/manage` | `ManageOut` (sin teléfono) |
| POST | `/api/manage/cancel` `{confirmation}` | 200; 422 si el texto no es "Cancelar cita"; 409 fuera de reglas |
| POST | `/api/manage/reschedule` `{start_at}` | `ManageOut` actualizado; 409 si no se puede |
| GET | `/api/manage/schedule?date=` · `/calendar?month=` | Disponibilidad del servicio de esa cita sin contar la propia |

Token ausente, desconocido o revocado: 404 "Enlace inválido o vencido.".

## Pruebas
`python -m pytest` (desde `backend/`): **22 pasan** (19 previos + 3 nuevos), también con variables de entorno hostiles.

| Test | Cubre |
|---|---|
| `test_happy_path_link_in_whatsapp_cancel_with_typed_confirmation_revokes_link` | `manage_url` en la respuesta y en el WhatsApp; solo el SHA-256 en la BD; detalle sin teléfono; textos de confirmación incorrectos o ausentes → 422 sin cancelar; cancelación válida libera la hora, avisa y deja el token inservible (404 en todo) |
| `test_edge_reschedule_rules_own_slot_cap_and_reset` | Correrse 30 min con servicio de 45 (excluye a la propia cita); `pending` y `reminder_sent` reiniciados; hora vieja libre y nueva ocupada; franja de otra persona, misma hora, pasado, fuera de horario y domingo → 409; la 3.ª reprogramación → 409 pero cancelar sigue permitido |
| `test_edge_token_scope_cutoff_status_and_own_schedule` | Sin token o inventado → 404; el token de A no toca a B; 2 h exactas se permite y 1 h 59 min no; cita `done`, cancelada o pasada → 409; el calendario/franjas del enlace no cuentan la propia cita |

**Un fallo real que encontraron los tests:** `CancelIn.confirmation` tenía valor por defecto `""`; los validadores de Pydantic no corren sobre valores por defecto, así que el cuerpo `{}` cancelaba la cita sin confirmación. Ahora el campo es obligatorio.

Verificación manual en navegador (BD temporal): regresión de `index.html` tras extraer el calendario (calendario, franjas, reserva con móvil panameño); la tarjeta de éxito muestra el enlace; en `manage.html` se reprogramó (la hora propia no aparecía bloqueada), el botón del modal sigue deshabilitado con "cancelar" y se habilita con "Cancelar cita"; tras cancelar la página lo indica y **al recargar el mismo URL dice "Este enlace ya no es válido"** (API 404); la cita quedó `cancelled`, no queda ningún enlace y la hora volvió a estar libre; el token no aparece en las rutas del log (solo dentro del WhatsApp de demo).

## Limitaciones conocidas
- Con el proyecto solo en local, el enlace apunta a `localhost` y no abre desde un teléfono hasta definir `PUBLIC_BASE_URL`.
- Las citas anteriores a esta HU no tienen enlace, y los recordatorios no lo llevan (el token no se puede regenerar porque solo se guarda el hash).
- Sin límite de intentos sobre el token (256 bits). La carrera entre dos reprogramaciones simultáneas a la misma franja se resuelve como en las reservas (comprobar y luego escribir, sin restricción única en la BD).
- No probado en el navegador: la vista dentro de las 2 h previas, la 3.ª reprogramación y el ancho móvil (sí por tests de API).
- En modo demo (sin Twilio) el enlace aparece en el log del servidor y en la tarjeta de éxito, no llega por WhatsApp.
- Fuera de alcance: enlace en los recordatorios, aviso al admin cuando el cliente cancela o reprograma, motivo de cancelación.
