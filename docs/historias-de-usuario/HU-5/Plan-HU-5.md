# Plan HU-5 — Autogestión de la cita desde un enlace personal

## Contexto
HU-5: "como cliente que ya reservó, quiero cancelarla o reprogramarla desde un enlace personal que llega en mi mensaje de confirmación de WhatsApp, para no tener que llamar al negocio y para que mi horario quede libre para otra persona".

Hoy no existe ninguna forma de que el cliente modifique su cita (solo el admin, con `PATCH`/`DELETE`). El mensaje de confirmación se arma en `notifications.confirmation_message` y se envía desde `routers/public.create_appointment`. Cancelar libera el horario sin trabajo extra: `availability._booked_between` ya ignora las citas `cancelled`.

Decisiones del usuario: anticipación mínima **2 horas** (`MANAGE_CUTOFF_HOURS`) y **máximo 2 reprogramaciones** por cita (`MANAGE_MAX_RESCHEDULES`); cancelar se puede siempre dentro del plazo.

Rama: `feature/historias-usuario-v2` (sin commit/push hasta que lo pidas).

## Diseño
- **Enlace sin login, igual que HU-1**: token aleatorio (`secrets.token_urlsafe(32)`) por cita; el servidor guarda **solo su SHA-256**. El enlace es `{PUBLIC_BASE_URL}/app/manage.html#t=<token>`: el token va en el *fragmento* (no llega al servidor, a los logs de uvicorn ni al `Referer`) y la página lo envía en la cabecera `X-Manage-Token`.
- **Tabla nueva `appointment_links`** (`id`, `appointment_id` único, `token_hash` único, `reschedule_count`, `created_at`). Se eligió tabla nueva en vez de columnas en `appointments` porque `create_all` solo crea tablas faltantes: así tu `citafacil.db` existente sigue funcionando sin `ALTER TABLE`. Al borrar una cita (admin) se borra también su enlace (`crud.delete_appointment`).
- **Reglas** (`app/manage.py`, `change_block_reason`): solo citas `pending`/`confirmed`, futuras y con al menos `MANAGE_CUTOFF_HOURS` de anticipación; reprogramar además exige `reschedule_count < MANAGE_MAX_RESCHEDULES`. Si no se cumple, la página muestra la cita y el motivo (p. ej. "Faltan menos de 2 horas: contacta al negocio"); las acciones devuelven 409.
- **Reprogramar**: valida con `availability.is_slot_free` **excluyendo la propia cita** (si no, un servicio de 45 min no podría moverse 30 min porque chocaría consigo mismo); actualiza `start_at`/`end_at`, `reminder_sent=False` (recibirá un recordatorio nuevo), `status` vuelve a `pending` (el admin debe reconfirmar el cambio) y `reschedule_count += 1`.
- **Cancelar** (operación delicada, solo aquí): exige una **confirmación escrita** — el cliente debe teclear **"Cancelar cita"** en un modal. La regla se aplica también en el servidor (`POST /cancel` con `{"confirmation": "Cancelar cita"}`; se compara sin distinguir mayúsculas ni espacios sobrantes, pero el texto debe coincidir; si no, 422), de modo que no se pueda cancelar con una llamada suelta sin haberlo confirmado. Al cancelar: `status="cancelled"` (el horario queda libre de inmediato) y **el enlace se revoca**: se borra la fila de `appointment_links`, así el mismo URL deja de servir (GET/cancelar/reprogramar → 404 "Enlace inválido o vencido"). **Reprogramar no revoca el enlace** (sigue siendo útil hasta agotar las reprogramaciones o cancelar). Para volver a reservar, el cliente usa la página normal.
- Ambas acciones envían un WhatsApp de aviso (nuevas plantillas en `notifications.py`); en modo demo solo se registran en el log, como hoy.
- Las citas anteriores a esta HU no tienen enlace (los tokens no se pueden regenerar porque solo se guarda el hash). Los recordatorios no llevan enlace por el mismo motivo; la HU lo pide solo en la confirmación.

## Backend
- `backend/app/models.py`: `AppointmentLink`.
- `backend/app/config.py` + `.env.example`: `public_base_url` (`http://localhost:8000`), `manage_cutoff_hours` (2), `manage_max_reschedules` (2).
- `backend/app/manage.py` (nuevo): `create_link(db, appt) -> token`, `hash_token` (reutiliza `device.hash_token`/`new_token`), dependencia `current_link` (lee `X-Manage-Token`; 404 genérico "Enlace inválido o vencido." para token ausente/desconocido), `change_block_reason`, `build_manage_url`.
- `backend/app/availability.py`: `exclude_id` opcional en `build_day_slots`, `month_overview` e `is_slot_free` (las llamadas actuales no cambian).
- `backend/app/notifications.py`: `confirmation_message(..., manage_url=None)` añade la línea del enlace; `reschedule_message` y `cancellation_message`.
- `backend/app/schemas.py`: `AppointmentCreatedOut(AppointmentOut + manage_url)` (solo el `POST /api/appointments`; el listado admin no cambia), `ManageOut` (negocio, servicio, inicio/fin, estado, nombre de pila del cliente, `can_change`, `reason`, `reschedules_left`, `cutoff_hours`; **sin teléfono**), `RescheduleIn(start_at)`, `CancelIn(confirmation)` (validador: `" ".join(texto.split()).casefold() == "cancelar cita"`).
- `backend/app/routers/public.py`: al crear la cita se genera el enlace, se incluye en el WhatsApp y se devuelve `manage_url`.
- `backend/app/routers/manage.py` (nuevo, `prefix="/api/manage"`, todos por cabecera `X-Manage-Token`):
| Método | Ruta | Uso |
|---|---|---|
| GET | `/` | Detalle de la cita y si se puede cambiar |
| POST | `/cancel` `{confirmation}` | Cancelar (exige el texto "Cancelar cita"; 422 si no coincide) y revocar el enlace |
| POST | `/reschedule` `{start_at}` | Reprogramar (409 si no libre, igual, fuera de reglas o sin cupo de reprogramaciones) |
| GET | `/schedule?date=` | Franjas del servicio de esa cita (HU-2, excluyendo la propia) |
| GET | `/calendar?month=YYYY-MM` | Calendario del servicio de esa cita (HU-2, excluyendo la propia) |
- `backend/app/main.py`: incluir el router. `backend/app/crud.py`: borrar enlace al borrar la cita.

## Frontend
- **Se extrae el calendario/franjas de HU-2 a un módulo compartido** `frontend/scheduler.js` + `frontend/scheduler.css` (fábrica con URLs parametrizables), usado por `index.html` y la página nueva, para no duplicar ~120 líneas de JS y estilos. `index.html` pasa a usar la fábrica (mismo comportamiento; es la parte de mayor riesgo, se re-verifica en el navegador).
- `frontend/manage.html` (nuevo, mismo estilo): lee `#t=` (copia a `sessionStorage` para sobrevivir a recargas), muestra la cita (servicio, fecha, hora, estado) y, si `can_change`, los botones **Reprogramar** (abre calendario + franjas, confirma y muestra la nueva hora) y **Cancelar**, que abre un **modal de confirmación propio** (no `confirm()` del navegador): explica que la acción es definitiva y que el enlace dejará de funcionar, pide escribir **"Cancelar cita"** y mantiene deshabilitado el botón "Cancelar cita definitivamente" hasta que el texto coincida (Enter confirma solo si coincide, Esc cierra, foco en el campo, `role="dialog"` accesible). Tras cancelar, la página muestra "Tu cita fue cancelada y el horario quedó libre" con un enlace a reservar de nuevo; al recargar el mismo URL, muestra "Este enlace ya no es válido". Estados: enlace inválido, cita ya cancelada/pasada, fuera de plazo (con el motivo), reprogramaciones agotadas, éxito.
- `frontend/index.html`: la tarjeta de éxito agrega "Gestionar mi cita" con `manage_url` (útil en modo demo, donde el WhatsApp no llega).

## Tests — `backend/tests/test_manage.py` (nuevo; reloj congelado en `app.availability`/`app.manage`; `send_whatsapp` interceptado para leer los mensajes)
1. **Happy path**: reservar por la API → la respuesta trae `manage_url` y el WhatsApp de confirmación lo contiene; en la BD hay solo el SHA-256 (el token en claro no aparece); `GET /api/manage` devuelve la cita sin teléfono; cancelar con `confirmation="Cancelar cita"` → estado `cancelled`, la franja reaparece en `/api/availability`, se envía el aviso de cancelación y **el mismo token queda inservible** (GET, cancelar y reprogramar → 404; la fila del enlace ya no existe).
   - Confirmación: sin texto, texto distinto (`"cancelar"`, `"Cancelar cita por favor"`) → 422 y la cita **no** se cancela ni se revoca el enlace; `"  cancelar   CITA "` (mayúsculas/espacios) sí se acepta.
2. **Límite — reprogramar**: mover a una franja libre actualiza inicio/fin, libera la anterior, bloquea la nueva, pone `status=pending` y `reminder_sent=False`; un servicio de 45 min puede correrse 30 min (excluye la propia cita); franja ocupada → 409 sin cambios; misma hora, pasado, fuera de horario y domingo → rechazados; a la 3.ª reprogramación → 409 y cancelar sigue permitido.
3. **Límite — token y plazo**: sin token, token falso o token de otra cita → 404 sin tocar nada; el token de la cita A no mueve la B; con 1 h 59 min de anticipación → 409 (con 2 h exactas se permite); cita ya cancelada, `done` o pasada → 409; `/schedule` y `/calendar` del enlace excluyen la propia cita y respetan el servicio.
`conftest.py` fija además `PUBLIC_BASE_URL`, `MANAGE_CUTOFF_HOURS`, `MANAGE_MAX_RESCHEDULES` (la lección del aislamiento de `.env`). Los 19 tests existentes no cambian.

## Docs
`docs/historias-de-usuario/HU-5/Plan-HU-5.md` (copia) y al terminar `Resultado-HU-5.md`; `README.md` (endpoints, variables) y `docs/Proyect-doc.md`.

## Verificación
1. `cd backend; .venv\Scripts\python.exe -m pytest` — 19 previos + 3 nuevos, también con `.env` ausente y con variables hostiles.
2. BD temporal + `seed.py`, servidor en `:8765` con `PUBLIC_BASE_URL=http://localhost:8765`.
3. Playwright: **regresión de `index.html`** (calendario, franjas, reserva, modal de HU-1, selector de país); reservar y abrir `manage_url`; en el modal de cancelación comprobar que el botón sigue deshabilitado con texto incorrecto y se habilita con "Cancelar cita", cancelar y **recargar el mismo URL** (debe decir que ya no es válido); reprogramar (calendario sin la propia cita bloqueada), comprobar en el panel admin el estado y la hora nuevos; ver el horario libre en la página de reservas tras cancelar; probar token inválido, cita dentro de las 2 h, 3.ª reprogramación y recarga de la página; revisar el log del servidor (mensajes de demo con el enlace) y que el token no aparezca en las rutas del log.
4. Cerrar el servidor y borrar la BD temporal; `citafacil.db` real no se toca.

## Riesgos / notas
- Como el proyecto corre solo en local, el enlace apunta a `localhost`: no abre desde el teléfono del cliente hasta definir `PUBLIC_BASE_URL` (IP de la LAN, túnel, dominio).
- Sin límite de intentos sobre el token (256 bits, no adivinable), y la carrera entre dos reprogramaciones simultáneas a la misma franja sigue resolviéndose como en las reservas (check-then-write, sin restricción única en BD).
- Reprogramar devuelve la cita a `pending`: si prefieres que conserve `confirmed`, es un cambio de una línea.
- Fuera de alcance: enlace en los recordatorios, notificar al admin por WhatsApp/correo, motivo de cancelación, políticas por servicio.
