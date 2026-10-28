# 📅 CitaFácil — Sistema de reservas con recordatorios por WhatsApp

Aplicación **full-stack** para que pequeños negocios (barberías, peluquerías, clínicas, consultoras…) reciban reservas en línea y envíen **recordatorios automáticos por WhatsApp**.

Backend en **Python (FastAPI)** con base de datos **SQL**, API REST **documentada (Swagger)** e integración real con **Twilio**. Frontend liviano en **HTML/CSS/JS**: una página pública de reservas y un panel de administración.

> Proyecto de portafolio creado por **Giancarlos Alfaro** ([gianca675.github.io](https://gianca675.github.io)).

---

## ✨ Características

- **Reserva en 3 pasos**: el cliente elige servicio → día → hora libre, y deja su nombre y celular.
- **Sin choques de horario**: el motor de disponibilidad calcula los espacios libres según la duración de cada servicio y **evita el doble-booking**.
- **Recordatorios por WhatsApp**: envío automático (programado) X horas antes de la cita, además de confirmación al reservar.
- **Panel de administración**: estadísticas, gestión de reservas (confirmar / cancelar / realizar / eliminar) y de servicios (crear / activar / eliminar), protegido por token.
- **API REST documentada**: Swagger UI interactivo en `/docs`.
- **Validación de datos**: celulares de cualquier país en formato E.164 (solo móviles, porque los recordatorios van por WhatsApp), con selector de país con búsqueda; horarios de atención y días cerrados configurables.
- **Listo para desplegar**: Dockerfile, blueprint de Render y configuración por variables de entorno (SQLite en local → PostgreSQL en producción).

---

## 🧱 Stack técnico

| Capa        | Tecnología |
|-------------|------------|
| Backend     | Python 3, FastAPI, SQLAlchemy, Pydantic |
| Base de datos | SQLite (local) · PostgreSQL (producción) |
| Notificaciones | Twilio API (WhatsApp) |
| Tareas programadas | APScheduler |
| Frontend    | HTML5, CSS3, JavaScript (sin framework) |
| Tests       | pytest |
| Despliegue  | Docker · Render |

---

## 🚀 Demo

- **Reservas (frontend):** _añade aquí tu URL de GitHub Pages_
- **Panel admin:** `.../admin.html`
- **API + documentación:** _añade aquí tu URL de Render_ `/docs`

---

## 📂 Estructura

```
citafacil/
├── backend/
│   ├── app/
│   │   ├── main.py           # App FastAPI, CORS, programador de recordatorios
│   │   ├── config.py         # Configuración por variables de entorno
│   │   ├── database.py       # Conexión SQLAlchemy (SQLite/PostgreSQL)
│   │   ├── models.py         # Modelos: Service, Appointment
│   │   ├── schemas.py        # Esquemas Pydantic (validación)
│   │   ├── crud.py           # Operaciones de base de datos
│   │   ├── availability.py   # Motor de horarios + anti doble-booking
│   │   ├── notifications.py  # Envío de WhatsApp (Twilio)
│   │   ├── reminders.py      # Recordatorios automáticos
│   │   ├── auth.py           # Autenticación del panel admin
│   │   └── routers/          # Endpoints (público / admin)
│   ├── tests/                # Pruebas con pytest
│   ├── seed.py               # Datos de ejemplo (barbería)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── index.html            # Página pública de reservas
│   └── admin.html            # Panel de administración
├── render.yaml               # Despliegue en Render (API + PostgreSQL)
└── README.md
```

---

## 🖥️ Ejecutar en local

Requisitos: Python 3.10 a 3.12. Con Python 3.14 falla la instalación de las versiones fijadas de `pydantic` (2.7.4) y `psycopg2-binary` (2.9.9); si tu sistema trae uno más nuevo, crea el entorno con 3.12 (por ejemplo `uv venv --python 3.12`).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # cambia ADMIN_TOKEN (clave de instalación) y lo que quieras
python seed.py                # carga servicios y citas de ejemplo (opcional)
python -m uvicorn app.main:app --reload
```

- API y documentación: <http://localhost:8000/docs>
- Frontend: <http://localhost:8000/app/> (servido por la API; así funciona la cookie del dispositivo recordado).
  Panel admin en <http://localhost:8000/app/admin.html>: la primera vez pide la clave de instalación (`ADMIN_TOKEN`) para crear al propietario; después se entra con usuario y contraseña (ver *Cuentas del panel*).

> Sin credenciales de Twilio, la app corre en **modo demo**: los mensajes de WhatsApp se registran en el log en vez de enviarse.

---

## 🔌 Endpoints principales

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| GET  | `/api/config` | Datos del negocio (nombre, horario) | — |
| GET  | `/api/services` | Servicios activos | — |
| GET  | `/api/availability?service_id=&date=` | Horarios libres de un día | — |
| POST | `/api/appointments` | Crear una reserva | — |
| GET  | `/api/admin/appointments` | Listar reservas (filtros) | 🔒 |
| PATCH| `/api/admin/appointments/{id}` | Cambiar estado | 🔒 |
| DELETE | `/api/admin/appointments/{id}` | Eliminar reserva | 🔒 |
| GET/POST/PUT/DELETE | `/api/admin/services` | Gestionar servicios | 🔒 |
| GET  | `/api/admin/stats` | Estadísticas | 🔒 |
| POST | `/api/admin/reminders/run` | Enviar recordatorios ahora | 🔒 |

🔒 = requiere iniciar sesión en el panel y tener el permiso correspondiente (ver *Cuentas del panel*). Desde HU-6 la cabecera `X-Admin-Token` ya no abre la API.

**Cuentas del panel (HU-6)** — cada empleado entra con su usuario y contraseña, y el propietario define qué puede hacer cada uno. Cada acción queda en un registro de actividad.

- **Primer acceso:** mientras no exista ningún usuario, el panel muestra "Crear al propietario" y pide `ADMIN_TOKEN` (cámbialo antes en `.env`). Después ese token ya no abre la API.
- **Sesión:** cookie `HttpOnly` + `SameSite=Strict`; el servidor guarda solo el SHA-256 del token. Las peticiones que no son GET llevan la cabecera `X-Requested-With: citafacil` (defensa CSRF). Contraseñas con scrypt, bloqueo tras 5 fallos seguidos y cambio de clave obligatorio con contraseñas temporales.
- **Permisos** (`appointments.view`, `customers.phones`, `appointments.confirm`, `appointments.cancel`, `appointments.delete`, `services.manage`, `analytics.view`, `reminders.run`, `users.manage`, `audit.view`) con roles base ajustables por empleado: Propietario (todo), Gerente (todo menos usuarios), Recepción y Solo consulta. Sin `customers.phones` los teléfonos salen enmascarados (`+507 ****4567`).
- **Recuperación:** `python manage_users.py list | create-owner <usuario> | reset-password <usuario>` (la contraseña se pide por teclado).

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/auth/setup-status` · POST `/setup` | ¿Falta el propietario? / crearlo con `ADMIN_TOKEN` |
| POST | `/api/admin/auth/login` · `/logout` · `/password` · GET `/me` | Entrar, salir, cambiar mi contraseña, usuario actual |
| GET/POST/PATCH | `/api/admin/users` · POST `/{id}/reset-password` · GET `/api/admin/permissions` | Gestión de usuarios y permisos (`users.manage`) |
| GET | `/api/admin/audit` (+ `/actors`) | Registro de actividad con filtros (`audit.view`); solo lectura |

**Autogestión de la cita (HU-5)** — la confirmación de WhatsApp incluye un enlace personal (`{PUBLIC_BASE_URL}/app/manage.html#t=<token>`) para reprogramar o cancelar sin llamar al negocio. El token va en el fragmento de la URL (no llega a los logs) y el servidor solo guarda su SHA-256. Los endpoints usan la cabecera `X-Manage-Token`. Reglas: hasta `MANAGE_CUTOFF_HOURS` (2) horas antes y máximo `MANAGE_MAX_RESCHEDULES` (2) reprogramaciones. **Cancelar exige escribir "Cancelar cita"** y revoca el enlace (el mismo URL deja de servir); reprogramar devuelve la cita a `pending` para que el negocio la reconfirme.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/manage` | Detalle de la cita y qué se puede hacer (sin teléfono) |
| POST | `/api/manage/cancel` `{confirmation}` | Cancela y revoca el enlace; 422 si el texto no es "Cancelar cita" |
| POST | `/api/manage/reschedule` `{start_at}` | Reprograma (409 si no está libre o fuera de reglas) |
| GET | `/api/manage/schedule?date=` · `/api/manage/calendar?month=` | Disponibilidad para reprogramar (la propia cita no cuenta como ocupada) |

`POST /api/appointments` ahora devuelve además `manage_url`. En local el enlace apunta a `localhost`: para abrirlo desde un teléfono define `PUBLIC_BASE_URL` con la IP de tu red, un túnel o tu dominio.

**Teléfonos internacionales (HU-4)** — el celular se valida y guarda en E.164 (`+50761234567`). Solo se aceptan **móviles**: los fijos, gratuitos, de tarifa premium y VoIP se rechazan con 422. Los números escritos sin `+` se interpretan con `DEFAULT_COUNTRY`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/countries` | Países para el selector: `[{iso, dial_code, example}]` (`example` = móvil de ejemplo en formato local, usado como placeholder) |
| GET | `/api/config` | Ahora incluye `default_country` |

**Análisis de demanda (HU-3)** — solo admin (🔒). Se calcula contando `appointments` (no canceladas, por fecha de la cita); no hay tablas nuevas. Rango con `range=7d|14d|30d|90d|180d|365d` (trimestre/semestre/año móviles, terminan hoy) o libre con `from` y `to`; `service_ids=1,2` filtra servicios.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/analytics/services` | Barras: reservas por servicio |
| GET | `/api/admin/analytics/trend` | Líneas: reservas en el tiempo por servicio (`group_by=day\|week\|month`, automático por defecto) |
| GET | `/api/admin/analytics/forecast?horizon=14\|30\|90` | Proyección de demanda con banda de incertidumbre |

Los gráficos están en el panel admin (pestañas Barras · Líneas · Proyección, con Chart.js por CDN). Para verlos con datos de prueba: `python seed_history.py` (≈12 meses de citas demo marcadas con `[demo-historial]`; `--reset` las regenera sin tocar reservas reales).

**Calendario y franjas (HU-2)** — muestra todo el horario con lo ocupado bloqueado, en lugar de ocultarlo.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/schedule?service_id=&date=` | Todas las franjas del día: `{time, available, reason}` (`reason`: `booked` o `past`) |
| GET | `/api/calendar?service_id=&month=YYYY-MM` | Estado de cada día: `available`, `full`, `closed` o `past` (+ franjas libres) |

`/api/availability` se mantiene igual (solo franjas libres).

**Dispositivo recordado (HU-1)** — reservar sin volver a escribir tus datos, sin login. Se autentica con una cookie HttpOnly; el servidor guarda solo el SHA-256 del token.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET  | `/api/device/profile` | Datos guardados de este dispositivo (`known:false` si no se reconoce) |
| POST | `/api/device/remember` | Guarda los datos y emite el token (si el dispositivo ya es conocido, no lo reemplaza) |
| PUT  | `/api/device/profile` | Actualiza los datos guardados (requiere cookie válida) |
| DELETE | `/api/device` | Olvida este dispositivo |

El frontend ahora se sirve desde la propia API (mismo origen, necesario para la cookie): abre <http://localhost:8000/app/>.

---

## ⚙️ Configuración (variables de entorno)

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `DATABASE_URL` | `sqlite:///./citafacil.db` | Conexión a la base de datos |
| `ADMIN_TOKEN` | `cambia-este-token-admin` | Clave de instalación: solo crea al primer propietario (el valor por defecto se rechaza) |
| `SESSION_HOURS` | `12` | Duración de la sesión del panel |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_MINUTES` | `5` / `15` | Intentos fallidos antes de bloquear la cuenta y minutos de bloqueo |
| `PASSWORD_MIN_LENGTH` | `10` | Largo mínimo de las contraseñas |
| `CORS_ORIGINS` | `*` | Dominios permitidos del frontend |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base del enlace de autogestión que se envía por WhatsApp |
| `MANAGE_CUTOFF_HOURS` / `MANAGE_MAX_RESCHEDULES` | `2` / `2` | Anticipación mínima y reprogramaciones permitidas |
| `DEFAULT_COUNTRY` | `CL` | País base ISO para números sin `+` y país preseleccionado (ej. `PA`) |
| `BUSINESS_NAME` | `Barbería Don Lucho` | Nombre del negocio |
| `OPEN_HOUR` / `CLOSE_HOUR` | `10` / `20` | Horario de atención |
| `SLOT_INTERVAL_MINUTES` | `30` | Separación entre horarios |
| `CLOSED_WEEKDAYS` | `6` | Días cerrados (0=lun … 6=dom) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` | — | Credenciales de Twilio |
| `REMINDER_HOURS_BEFORE` | `24` | Horas antes para recordar |

---

## ☁️ Desplegar en Render (gratis)

1. Sube este proyecto a un repositorio de GitHub.
2. En [Render](https://render.com): **New + → Blueprint** y conecta el repo. Render leerá `render.yaml` y creará la API + una base de datos PostgreSQL.
3. Cuando termine, tu API quedará en `https://citafacil-api.onrender.com` (con `/docs`).
4. Copia esa URL en el frontend: abre la página con `?api=https://tu-api.onrender.com` o usa el enlace **“Configurar API”** del pie de página.
5. Publica el `frontend/` en GitHub Pages.

El `ADMIN_TOKEN` se genera automáticamente; puedes verlo en **Environment** dentro del panel de Render.

---

## 💬 Activar WhatsApp real (Twilio)

1. Crea una cuenta en [twilio.com](https://www.twilio.com) y activa el **WhatsApp Sandbox** (Messaging → Try it out → Send a WhatsApp message).
2. Copia tu **Account SID**, **Auth Token** y el número del sandbox (`whatsapp:+14155238886`).
3. Define en Render (o en tu `.env`): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`.
4. Para recibir mensajes en tu celular, primero únete al sandbox enviando el código que indica Twilio (ej: `join <palabra>`).

Sin estas variables, la app funciona igual en **modo demo** (registra los mensajes en el log).

---

## 🧪 Tests

```bash
cd backend
python -m pytest
```

Cubren la validación de teléfono, el cálculo de disponibilidad, la prevención de doble-booking y la autenticación del panel.

---

## 🛣️ Posibles mejoras

Notificaciones por correo, soporte multi-sucursal o multi-profesional, pagos en línea, recordatorio configurable por servicio, e internacionalización.

---

## 👤 Autor

**Giancarlos Alfaro** — Desarrollador de Software
[Portafolio](https://gianca675.github.io) · [GitHub](https://github.com/gianca675) · [LinkedIn](https://www.linkedin.com/in/giancarlos-alfaro-echeverr%C3%ADa-9ab57b2a8)

Licencia MIT.
