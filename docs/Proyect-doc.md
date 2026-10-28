# CitaFácil — Documentación de exploración del proyecto

Mapa del repositorio para entender el sistema y revisar cambios. Basado en la lectura del código (no se ejecutaron tests ni la app).

## 1. Objetivo del sistema

Reservas en línea para pequeños negocios (demo: "Barbería Don Lucho", Chile). Flujo del cliente:

1. Elige servicio, día y hora libre.
2. Deja nombre y celular.
3. Recibe confirmación y recordatorio por WhatsApp (Twilio). Sin credenciales corre en **modo demo**: el mensaje solo se registra en el log.

Evita el doble-booking y ofrece un panel de administración protegido por token. Proyecto de portafolio de Giancarlos Alfaro. Incluye además un router ajeno al dominio: el ranking del juego "ÚLTIMA RONDA 3D".

## 2. Stack

| Capa | Tecnología |
|---|---|
| Backend | Python, FastAPI 0.111, SQLAlchemy 2, Pydantic 2 |
| Base de datos | SQLite (local) / PostgreSQL (producción). Sin migraciones: usa `create_all` |
| Tareas programadas | APScheduler |
| Notificaciones | Twilio (WhatsApp) |
| Frontend | HTML/CSS/JS sin framework |
| Tests | pytest |
| Despliegue | Docker, Render (`render.yaml`) |

## 3. Estructura

```
citafacil/
├── backend/
│   ├── app/
│   │   ├── main.py  config.py  database.py  models.py  schemas.py
│   │   ├── crud.py  availability.py  notifications.py  reminders.py
│   │   ├── auth.py  utils.py
│   │   └── routers/ (public.py, admin.py, scores.py)
│   ├── tests/test_booking.py
│   ├── seed.py  requirements.txt  Dockerfile  .env.example
├── frontend/ (index.html, admin.html)
├── render.yaml
├── docs/
└── README.md
```

## 4. Módulos del backend

| Archivo | Rol |
|---|---|
| `main.py` | App FastAPI, CORS, arranque (crea tablas e inicia el programador), `/health` (GET/HEAD), `/` redirige a `/docs` |
| `config.py` | `Settings` desde variables de entorno / `.env` |
| `database.py` | Engine y sesión; normaliza `postgres://` a `postgresql://`; `get_db` |
| `models.py` | `Service`, `Appointment`; estados `pending`, `confirmed`, `cancelled`, `done` |
| `schemas.py` | Validación Pydantic; teléfono a E.164, fecha a hora local sin zona |
| `crud.py` | Operaciones sobre servicios y citas, más `stats` |
| `availability.py` | `generate_slots`, `is_slot_free`, `_overlaps` |
| `notifications.py` | Textos de confirmación y recordatorio; `send_whatsapp` (Twilio o demo) |
| `reminders.py` | `run_reminders` y `run_reminders_job` (cada `REMINDER_POLL_MINUTES`) |
| `manage.py` | HU-5: `create_link`, `current_link`, `block_reason`, `reschedule`, `cancel` |
| `auth.py` | `require_admin`: cabecera `X-Admin-Token` contra `ADMIN_TOKEN` |
| `utils.py` | `normalize_phone` (E.164 internacional, solo móviles), `phone_parts`, `list_countries`, `normalize_cl_phone` (regla chilena lenient, solo para `DEFAULT_COUNTRY=CL`), `local_now`, `to_local_naive` |
| `routers/public.py` | Endpoints públicos |
| `routers/admin.py` | Endpoints de administración (router completo protegido) |
| `routers/scores.py` | Ranking del juego; define su propio modelo `Score` |

## 5. API

### Público (`/api`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/config` | Datos del negocio y horario |
| GET | `/services` | Servicios activos |
| GET | `/availability?service_id=&date=` | Horas libres del día |
| POST | `/appointments` | Crea reserva. 404 servicio inexistente, 409 horario ocupado, 422 teléfono inválido. Envía WhatsApp de confirmación |

### Administración (`/api/admin`, requiere `X-Admin-Token`)
| Método | Ruta | Descripción |
|---|---|---|
| GET / POST | `/services` | Listar todos / crear |
| PUT / DELETE | `/services/{id}` | Editar / eliminar |
| GET | `/appointments?status=&date=` | Listar con filtros |
| PATCH | `/appointments/{id}` | Cambiar estado |
| DELETE | `/appointments/{id}` | Eliminar |
| GET | `/stats` | Contadores por estado y próximas |
| POST | `/reminders/run` | Ejecutar recordatorios ahora |

### Autogestión de la cita (`/api/manage`, HU-5, cabecera `X-Manage-Token`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `` | `ManageOut`: servicio, inicio/fin, estado, nombre de pila, `can_cancel`, `can_reschedule`, `reason`, `reschedules_left` (sin teléfono) |
| POST | `/cancel` | Cuerpo `{confirmation}` obligatorio, debe ser "Cancelar cita" (sin distinguir mayúsculas ni espacios sobrantes; 422 si no). Cancela, **borra el enlace** y avisa por WhatsApp |
| POST | `/reschedule` | Cuerpo `{start_at}`; usa `is_slot_free(..., exclude_id=<la propia cita>)`; pasa la cita a `pending`, `reminder_sent=False`, `reschedule_count += 1` y avisa por WhatsApp |
| GET | `/schedule?date=` · `/calendar?month=` | Como HU-2 pero para el servicio de esa cita y sin contar la propia cita como ocupada |

Token ausente, desconocido o revocado → 404 "Enlace inválido o vencido.". Reglas (`app/manage.py`): solo citas `pending`/`confirmed` y futuras, con al menos `MANAGE_CUTOFF_HOURS` de anticipación (justo 2 h se permite); reprogramar además exige cupo (`MANAGE_MAX_RESCHEDULES`). `POST /api/appointments` devuelve `manage_url` (`AppointmentCreatedOut`); el listado admin no cambia.

### Teléfonos internacionales (HU-4)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/countries` | `[{iso, dial_code, example}]` desde las regiones de `phonenumbers` (245), sin el pseudo-código `001`; `example` es un móvil de ejemplo en formato internacional sin el código (se omite si no valida) |
| GET | `/config` | Incluye `default_country` |

Validación (`utils.normalize_phone`): solo caracteres de número (sin letras), `phonenumbers.is_valid_number` y tipo `MOBILE` o `FIXED_LINE_OR_MOBILE` (en EE. UU./Canadá la numeración móvil y fija comparte rangos). Con `+` el país sale del número; sin `+` se usa `DEFAULT_COUNTRY` (para `CL` rige la regla anterior). El perfil de dispositivo devuelve además `phone_country` y `phone_national` para repoblar el selector.

### Análisis de demanda (`/api/admin/analytics`, HU-3, requiere `X-Admin-Token`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/services` | Reservas por servicio (barras) |
| GET | `/trend` | Serie temporal por servicio (líneas); `group_by` day/week/month, automático según el rango |
| GET | `/forecast?horizon=` | Proyección a 14/30/90 días: `history` (28 d), `forecast` (`expected`, `lower`, `upper`), `trend_per_week`, `expected_total`, `enough_data` |

Parámetros comunes: `range` (7d, 14d, 30d, 90d, 180d, 365d; por defecto 30d) o `from`+`to` (máx. 3 años), y `service_ids`. Cuenta citas no canceladas por `start_at`. Proyección: factor por día de la semana × recta de tendencia (mínimos cuadrados) entrenada con los últimos 90 días sin contar hoy; sin datos suficientes (menos de 14 días o 5 reservas) devuelve `enough_data:false`. Lógica en `backend/app/analytics.py`.

### Calendario y franjas (HU-2)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/schedule?service_id=&date=` | Todas las franjas del día con `available` y `reason` (`booked` / `past`); día cerrado → lista vacía |
| GET | `/calendar?service_id=&month=YYYY-MM` | Por día: `status` (`available` / `full` / `closed` / `past`) y `free`. 422 si el mes es inválido, 404 si el servicio no existe |

`/availability` no cambia (solo libres). La disponibilidad depende de la duración del servicio.

### Dispositivo recordado (`/api/device`, HU-1, autenticado por cookie HttpOnly)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/profile` | Datos guardados; `{known:false}` si la cookie falta o no es válida |
| POST | `/remember` | Crea token + perfil (201). Si el dispositivo ya es conocido: 200 `already_known`, sin tocar token ni datos |
| PUT | `/profile` | Actualiza nombre/celular (401 sin cookie válida) |
| DELETE | `` | Olvida el dispositivo y borra la cookie |

### Ranking (sin autenticación)
`POST /api/scores`, `GET /api/scores/top?limit=` (1–50).

### Sistema
`GET|HEAD /health`, `/docs` (Swagger).

## 6. Modelo de datos

- **services**: `id`, `name`, `duration_min`, `price` (CLP entero), `active`.
- **appointment_links** (HU-5): `id`, `appointment_id` (único), `token_hash` (SHA-256 hex, único), `reschedule_count`, `created_at`. Una fila por cita creada desde HU-5; se borra al cancelar la cita desde el enlace o al eliminarla el admin. Las citas anteriores no tienen enlace.
- **appointments**: `id`, `customer_name`, `customer_phone` (E.164), `service_id` (FK), `start_at` / `end_at` (sin zona, hora local del negocio), `status`, `notes`, `reminder_sent`, `created_at` (UTC sin zona).
- **device_profiles** (HU-1): `id`, `token_hash` (SHA-256 hex, único), `customer_name`, `customer_phone`, `created_at`, `last_used_at`. Una fila por dispositivo; el token en claro solo existe en la cookie `citafacil_device`.
- **game_scores**: `id`, `name` (≤20), `round`, `score` (indexado), `created_at` (UTC con zona).

`seed.py` carga 5 servicios y 2 citas confirmadas de ejemplo (solo si las tablas están vacías).

## 7. Flujos clave

**Reserva.** `POST /appointments` valida servicio activo → `is_slot_free` (día abierto, dentro de horario, en el futuro, sin solape con citas no canceladas) → crea cita `pending` → envía confirmación por WhatsApp.

**Recordatorios.** Cada `REMINDER_POLL_MINUTES` (15) el programador busca citas `pending` o `confirmed`, con `reminder_sent=False`, que empiecen dentro de las próximas `REMINDER_HOURS_BEFORE` (24) horas. Envía y marca `reminder_sent` solo si el envío fue exitoso.

**Frontend.**
- Se sirve desde FastAPI en `http://localhost:8000/app/` (mismo origen que la API).
- URL de la API: `?api=` → `localStorage.citafacil_api` → origen actual (o Render si se abre por `file://`).
- HU-5: `manage.html` (enlace personal): detalle de la cita, reprogramar con el calendario compartido y cancelar con un modal que exige escribir "Cancelar cita". El calendario y las franjas viven en `scheduler.js` / `scheduler.css`, compartidos con `index.html`. La tarjeta de éxito de la reserva muestra "Cambiar o cancelar mi cita".
- HU-4: el celular es un selector de país con búsqueda (`+código | bandera | ISO`, banderas de flag-icons por CDN) más el número nacional; el placeholder cambia con el país y busca por nombre (es/en), ISO o código. Se envía `+<código> <número>`.
- HU-3: el panel admin tiene la tarjeta "Análisis de demanda" (Chart.js 4.4.1 por CDN) con pestañas Barras, Líneas y Proyección, filtros de rango (presets y fechas libres) y chips de servicios.
- HU-2: el selector de fecha es un calendario mensual propio (`/api/calendar`); al elegir día se muestran todas las franjas (`/api/schedule`): libres clicables, ocupadas tachadas y horas pasadas atenuadas.
- HU-1: al cargar, `GET /api/device/profile` prellena nombre y celular; tras reservar, un modal ofrece guardar (dispositivo nuevo) o actualizar (datos distintos) los datos.
- `index.html`: asistente de 3 pasos.
- `admin.html`: login con token (`localStorage.citafacil_token`), estadísticas, citas (filtros; confirmar, cancelar, realizada, eliminar), servicios (crear, activar, eliminar) y botón de recordatorios.

## 8. Configuración (variables de entorno)

| Variable | Defecto |
|---|---|
| `DATABASE_URL` | `sqlite:///./citafacil.db` |
| `ADMIN_TOKEN` | `cambia-este-token-admin` |
| `CORS_ORIGINS` | `*` |
| `BUSINESS_NAME` / `BUSINESS_TIMEZONE` / `CURRENCY` | Barbería Don Lucho / America/Santiago / CLP |
| `OPEN_HOUR` / `CLOSE_HOUR` / `SLOT_INTERVAL_MINUTES` | 10 / 20 / 30 |
| `CLOSED_WEEKDAYS` | `6` (domingo; 0 = lunes) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` | vacío = modo demo |
| `REMINDER_HOURS_BEFORE` / `REMINDER_POLL_MINUTES` | 24 / 15 |

## 9. Tests

`backend/tests/conftest.py` fija la BD temporal (portable a Windows), una configuración independiente de `backend/.env` (país base CL, zona horaria, horario, días cerrados y Twilio vacío) y la fixture `fresh_db`. `backend/tests/test_device_profile.py` (3 tests, HU-1): camino feliz, varios dispositivos sin sobreescribir token, y token inválido/olvidado.

`backend/tests/test_manage.py` (3 tests, HU-5), `backend/tests/test_phone_international.py` (3 tests, HU-4), `backend/tests/test_schedule.py` (3 tests, HU-2) y `backend/tests/test_analytics.py` (4 tests, HU-3).

`backend/tests/test_booking.py` (6 tests): formatos de teléfono válidos e inválidos, creación y conflicto 409, disponibilidad que excluye horas reservadas, rechazo de teléfono inválido (422) y autenticación admin.

No cubren: recordatorios, ranking, CRUD de servicios, estadísticas ni cambios de estado.

Ejecutar: `cd backend; python -m pytest`.

## 10. Puntos de atención al revisar cambios

- **Doble reserva bajo concurrencia.** Comprobar disponibilidad e insertar no es atómico y no hay restricción única en la base.
- **Disponibilidad.** `_booked_that_day` solo considera citas que *empiezan* ese día. El horario es global (sin profesionales ni sucursales) y no hay margen entre citas.
- **Zona horaria.** Citas en hora local sin zona; `created_at` en UTC. Cuidado al tocar `local_now` o `to_local_naive`.
- **Seguridad.**
  - Token admin único y compartido, con valor por defecto público.
  - Comparación con `!=`, no en tiempo constante.
  - CORS abierto (`*`).
  - `/api/scores` y `POST /appointments` sin límite de uso ni captcha.
- **Integridad.** `DELETE /services/{id}` con citas asociadas puede fallar por la clave foránea sin manejo. `PATCH` de estado no valida transiciones.
- **Programador.** Corre dentro de cada proceso: con varios workers los recordatorios se duplicarían. Si falla el envío de la confirmación, se ignora.
- **Recordatorio.** El texto pide "responder este mensaje", pero no hay webhook de entrada de Twilio.
- **Localización.** El teléfono ya es internacional (HU-4); siguen siendo de Chile por defecto la zona horaria y la moneda, y los textos están en español.
- **Coherencia.** `scores.py` mezcla otro producto en la API y el README no lo documenta. El Dockerfile usa Python 3.11 y Render 3.12.6.
- **Tests.** Usan `sqlite:////tmp/...` (probablemente inválido en Windows) y asumen domingo cerrado.

## 11. Verificación sugerida para cualquier cambio

1. `cd backend; pip install -r requirements.txt; python -m pytest`
2. `python seed.py`
3. `python -m uvicorn app.main:app --reload` y probar `/docs`
4. Abrir `frontend/index.html` y `frontend/admin.html` contra la API local (`?api=http://localhost:8000`)
