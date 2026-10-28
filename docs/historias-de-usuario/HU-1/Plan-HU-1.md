# Plan HU-1 — Reserva rápida con datos recordados por dispositivo

## Contexto
HU-1: el usuario recurrente no debe volver a rellenar nombre y celular (no existe formulario de pago; los campos son nombre, celular y nota). Sin login: tras reservar, un modal ofrece "guardar mis datos en este dispositivo". Si acepta, el servidor genera un token aleatorio, lo entrega en cookie HttpOnly y guarda solo su SHA-256. Cada dispositivo tiene su propio token (varios dispositivos por cliente no chocan) y un token válido nunca se sobreescribe.

Decisiones del usuario:
- El proyecto corre **solo en local** (sin GitHub Pages/Render) → el frontend se sirve desde FastAPI, mismo origen que la API: cookie de primera parte, `SameSite=Lax`, sin cambios de CORS. (Hoy se abre por `file://`, donde las cookies no funcionan.)
- Si un dispositivo conocido reserva con datos distintos a los guardados → el modal **pregunta si actualizar** el perfil.

## Rama de trabajo
`main` no se toca. Primer paso al aprobar: `git switch -c feature/historias-usuario-v2` desde `main` (estado limpio). Todas las HU de `HU-v2.md` se implementan en esa rama, una por una; HU-1 va en commits propios (sin commit ni push salvo que lo pidas). Los archivos de `docs/` también se crean en la rama.

## Diseño
**Tabla nueva `device_profiles`**: `id`, `token_hash` (SHA-256 hex, único, indexado), `customer_name`, `customer_phone` (E.164), `created_at`, `last_used_at`. El token en claro nunca se persiste.

**Cookie** `citafacil_device`: valor `secrets.token_urlsafe(32)`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age` configurable (365 días), `Secure` solo si `COOKIE_SECURE=true` (local es http).

**Endpoints nuevos** (`/api/device`, sin token admin; autenticados por la cookie):
| Método | Ruta | Comportamiento |
|---|---|---|
| GET | `/profile` | Cookie válida → `{known:true, customer_name, customer_phone}` y actualiza `last_used_at`; si no → `{known:false}` (200, sin filtrar nada) |
| POST | `/remember` `{customer_name, customer_phone}` | Sin cookie válida → crea token + fila y hace `Set-Cookie` (201). **Con cookie válida → no genera token ni toca la fila** (200, `already_known`) |
| PUT | `/profile` `{customer_name, customer_phone}` | Requiere cookie válida (si no, 401); actualiza nombre/celular. Es la acción "sí, actualizar" |
| DELETE | `/` | Borra el perfil del dispositivo y la cookie ("olvidar este dispositivo") |

Teléfono validado con `normalize_cl_phone` (`utils.py`), igual que las reservas. Cookie presente pero hash inexistente (borrada/forjada) = dispositivo desconocido.

**Flujo frontend** (`index.html`):
1. `init()` → `GET /api/device/profile`. Si `known`: prellena nombre/celular y muestra aviso "Usando los datos de este dispositivo · Usar otros datos" (limpia campos).
2. Tras `POST /api/appointments` exitoso se compara la respuesta (`customer_name`, `customer_phone` ya normalizado) con el perfil:
   - Dispositivo desconocido → modal "¡Reserva hecha! ¿Guardar tus datos en este dispositivo?" Sí → `POST /remember` / No → nada.
   - Conocido y datos distintos → modal "¿Actualizar tus datos guardados?" Sí → `PUT /profile`.
   - Conocido y datos iguales → sin modal, va directo a la tarjeta de éxito.
3. Cerrar el modal (Sí/No) muestra la tarjeta "¡Reserva confirmada!" existente.
4. `fetch` con `credentials:"same-origin"`; la URL de API por defecto pasa a `location.origin` cuando se sirve por http(s) (se mantiene `?api=` y `localStorage` como override).

## Archivos
**Nuevos**
- `backend/app/device.py` — `hash_token`, `new_token`, `get_device_profile(request, db)` (dependencia), constantes de cookie.
- `backend/app/routers/device.py` — los 4 endpoints.
- `backend/tests/conftest.py` — fija `DATABASE_URL` (archivo temporal, portable a Windows) y `ADMIN_TOKEN` antes de importar la app; fixture `fresh_db`.
- `backend/tests/test_device_profile.py` — tests de HU-1.
- `Plan-HU-1.md` — copia de este plan (se crea al salir del modo plan).

**Modificados**
- `backend/app/models.py` — modelo `DeviceProfile`.
- `backend/app/schemas.py` — `DeviceProfileIn` (reutiliza `normalize_cl_phone`), `DeviceProfileOut`.
- `backend/app/crud.py` — crear/obtener por hash/actualizar/borrar perfil.
- `backend/app/config.py` y `backend/.env.example` — `DEVICE_COOKIE_NAME`, `DEVICE_COOKIE_DAYS`, `COOKIE_SECURE`.
- `backend/app/main.py` — incluir router `device` y montar `StaticFiles` del directorio `frontend/` en `/app` (después de los routers).
- `frontend/index.html` — prellenado, aviso, modal y lógica descrita. `frontend/admin.html` — solo el cambio de URL por defecto a `location.origin`.
- `backend/tests/test_booking.py` — quitar el bloque de env y la fixture `fresh_db` (pasan a `conftest.py`); los tests no cambian.
- `README.md` y `docs/Proyect-doc.md` — documentar endpoints, tabla y cómo abrir el frontend (`http://localhost:8000/app/`).

Sin migraciones: `create_all` crea la tabla nueva; no se altera ninguna existente.

## Tests (`test_device_profile.py`)
1. **Happy path**: reservar → `POST /remember` → respuesta con `Set-Cookie` que contiene `HttpOnly` y `SameSite=Lax`; en BD hay una fila con `token_hash == sha256(cookie)` y el token en claro no aparece en ninguna columna; `GET /profile` devuelve nombre y celular normalizado; una segunda reserva con ese cliente funciona y `PUT /profile` actualiza los datos.
2. **Límite — varios dispositivos y no sobreescritura**: dos clientes (dos `TestClient`) con el mismo celular obtienen tokens distintos y ambos siguen válidos (2 filas); repetir `POST /remember` desde un dispositivo ya conocido devuelve `already_known`, no emite cookie nueva y el hash en BD no cambia.
3. **Límite — token inválido**: cookie forjada/aleatoria o con hash inexistente → `GET /profile` da `{known:false}` sin datos; `PUT /profile` y `DELETE` sin cookie válida → 401; tras `DELETE` con cookie válida, el mismo token deja de funcionar.

## Verificación
1. `cd backend; <venv>\python -m pytest` — los 6 tests previos + 3 nuevos en verde (incluye que la fixture portable corre en Windows).
2. `python seed.py; python -m uvicorn app.main:app --reload`, abrir `http://localhost:8000/app/index.html`.
3. Manual en navegador (DevTools → Application → Cookies): reservar → modal → "Sí" → cookie `citafacil_device` con HttpOnly (no visible vía `document.cookie`); recargar → campos prellenados; reservar con otros datos → modal de actualizar; ventana privada (otro "dispositivo") → formulario vacío y vuelve a preguntar; "Usar otros datos" limpia los campos.
4. Revisar en la BD (`sqlite3 citafacil.db "select token_hash from device_profiles"`) que solo hay hashes de 64 hex.

## Riesgos / notas
- Quien tenga acceso al navegador ve los datos prellenados (inherente a "recordar"); por eso existe "olvidar este dispositivo".
- HU-4 (teléfonos internacionales) cambiará `normalize_cl_phone`; el perfil lo reutiliza, así que heredará el cambio.
- Fuera de alcance: expiración por inactividad (solo `Max-Age`), límite de uso en `/remember`.
