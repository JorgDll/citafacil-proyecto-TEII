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
| `auth.py` | `require_admin`: cabecera `X-Admin-Token` contra `ADMIN_TOKEN` |
| `utils.py` | `normalize_cl_phone`, `local_now`, `to_local_naive` |
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

`backend/tests/conftest.py` fija la BD temporal (portable a Windows) y la fixture `fresh_db`. `backend/tests/test_device_profile.py` (3 tests, HU-1): camino feliz, varios dispositivos sin sobreescribir token, y token inválido/olvidado.

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
- **Localización fija a Chile.** Teléfono `+56 9`, textos en español, zona horaria.
- **Coherencia.** `scores.py` mezcla otro producto en la API y el README no lo documenta. El Dockerfile usa Python 3.11 y Render 3.12.6.
- **Tests.** Usan `sqlite:////tmp/...` (probablemente inválido en Windows) y asumen domingo cerrado.

## 11. Verificación sugerida para cualquier cambio

1. `cd backend; pip install -r requirements.txt; python -m pytest`
2. `python seed.py`
3. `python -m uvicorn app.main:app --reload` y probar `/docs`
4. Abrir `frontend/index.html` y `frontend/admin.html` contra la API local (`?api=http://localhost:8000`)
