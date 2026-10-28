# Plan HU-4 — Teléfonos internacionales (E.164) con selector de país

## Contexto
HU-4: el dueño en Panamá necesita aceptar clientes con cualquier número telefónico para que los WhatsApp se entreguen. Hoy `normalize_cl_phone` (`backend/app/utils.py`) solo acepta móviles chilenos (`+56 9 …`), lo usan los validadores de `AppointmentCreate` y `DeviceProfileIn` (`schemas.py`), `seed.py` y los tests.

Objetivo: el validador acepta **cualquier número internacional en formato E.164**; el cliente elige el país en un **desplegable con búsqueda** que muestra **código | bandera | ISO 3166-1 alpha-2** y solo escribe su número nacional (sin tipear el prefijo). La búsqueda no depende de que el ISO sean las dos primeras letras del nombre: encuentra por **nombre del país** (y además por ISO y por código de marcación).

Decisiones del usuario: banderas con **flag-icons por CDN** (en Windows los emojis de bandera no se dibujan); país base por **`DEFAULT_COUNTRY`** (valor por defecto `CL` en código, `PA` sugerido en `.env.example`).

Rama: `feature/historias-usuario-v2` (sin commit/push hasta que lo pidas).

## Diseño
- **Almacenamiento sin cambios**: `customer_phone` sigue siendo un string E.164 (máx. 15 dígitos + `+` caben en `String(20)`). No hay migración; los números chilenos ya guardados siguen siendo válidos. El contrato de la API tampoco cambia: se sigue enviando un único `customer_phone`.
- **Validación con `phonenumbers`** (port de libphonenumber, pura Python; se agrega a `requirements.txt`). Se exige `is_valid_number` (longitud y prefijos reales por país: atrapa errores de tipeo que harían fallar el WhatsApp) **y que sea móvil**, porque el sistema funciona con recordatorios por WhatsApp: se acepta solo `number_type` ∈ {`MOBILE`, `FIXED_LINE_OR_MOBILE`}. Se rechazan fijos (`FIXED_LINE`), VoIP, gratuitos, de tarifa premium, pagers y demás tipos. `FIXED_LINE_OR_MOBILE` se admite porque en países como EE. UU. y Canadá la numeración móvil y fija comparte rangos y no hay forma de distinguirlas. Mensaje de error: "Solo se aceptan números móviles (los recordatorios se envían por WhatsApp)." Se normaliza a E.164 (`+50761234567`).
- **Sin `+`**: el número se interpreta con `settings.default_country` (acepta también el prefijo `00` del país base). Para `CL` se conserva el comportamiento lenient de hoy (delegando en `normalize_cl_phone`, que se mantiene), así los 6 tests y `seed.py` actuales no cambian.
- **Nombres de países**: no se guardan; el navegador los resuelve con `Intl.DisplayNames('es' y 'en')` a partir del ISO, y la búsqueda ignora mayúsculas y tildes. Cero datos extra que mantener.
- **Códigos compartidos** (+1 EE. UU./Canadá/Caribe, +7 Rusia/Kazajistán…): el desplegable trabaja por ISO (cada país es una fila), y el servidor valida el E.164 completo, que ya identifica la región.

## Backend
- `backend/requirements.txt`: `phonenumbers==9.0.42` (instalar en `backend/.venv` con `uv pip install`, ya que ese venv no trae pip).
- `backend/app/config.py` + `backend/.env.example`: `default_country: str = "CL"` (ISO alpha-2; en `.env.example` `DEFAULT_COUNTRY=PA` con comentario). Se valida que sea una región soportada.
- `backend/app/utils.py`: `normalize_phone(raw, region=None) -> str` (lanza `PhoneError` con mensaje no centrado en Chile); `phone_parts(e164) -> (iso, nacional)` con `region_code_for_number` y `national_significant_number`; `list_countries() -> [{iso, dial_code, example}]` desde las regiones soportadas por la librería (sin el pseudo-código `001`), ordenadas por ISO. `example` es un **número móvil de ejemplo en formato nacional** de ese país (`example_number_for_type(region, MOBILE)` formateado con `NATIONAL`; si no hay móvil, el de cualquier tipo; si no hay ninguno, `""`), p. ej. PA → `6123-4567`. Se calcula una vez y se cachea (la lista es estática).
- `backend/app/schemas.py`: ambos validadores pasan a `normalize_phone`; `ConfigOut` gana `default_country`; `DeviceProfileOut` gana `phone_country` y `phone_national` (para repoblar el selector al prellenar, ya que el ISO no se deduce del `+1`).
- `backend/app/routers/public.py`: `GET /api/countries` → `[{iso, dial_code, example}]`; `GET /api/config` incluye `default_country`.
- `backend/app/routers/device.py`: rellena `phone_country`/`phone_national` en las respuestas de perfil.
- Sin cambios en `notifications.py` (ya envía a `whatsapp:{e164}`), `seed.py` ni `normalize_cl_phone`.

## Frontend (`frontend/index.html`)
- Se carga `flag-icons` 7.2.3 desde cdnjs (`<span class="fi fi-pa">`).
- El campo "Celular" pasa a **[selector de país] + [número nacional]**. Selector propio, sin librerías, accesible (patrón combobox/listbox):
  - Botón cerrado: `+507 | 🇵🇦(svg) | PA ▾`.
  - Panel abierto: caja de búsqueda con foco automático y lista con filas `+507 | bandera | PA` más el nombre en gris para poder confirmar el resultado (extra respecto a tu formato; fácil de quitar).
  - Búsqueda: nombre en español e inglés, ISO y código de marcación (con o sin `+`), sin tildes; orden: ISO exacto → nombre que empieza por → contiene.
  - Teclado: ↑/↓, Enter, Esc, Tab; clic fuera cierra.
- **Placeholder dinámico**: el campo del número nacional muestra `Ej: <example>` del país elegido (p. ej. Panamá `6123-4567`, Chile `9 1234 5678`, EE. UU. `(201) 555-0123`) y se actualiza al cambiar de país, de modo que el usuario ve la longitud y el formato típicos de ese país. Si el país no tiene ejemplo, el placeholder genérico es "Número de celular". El `inputmode="tel"` y el `autocomplete="tel-national"` se mantienen.
- Se compone `customer_phone = "+" + dial + dígitos` (se quita el `0` inicial de marcación local y espacios/guiones; si el usuario pega un número que empieza con `+`, se envía tal cual). País preseleccionado: `default_country` de `/api/config`.
- **HU-1**: el prefill de dispositivo usa `phone_country` + `phone_national` para elegir el país y rellenar el número; "Usar otros datos" restaura el país por defecto.
- Los 422 de FastAPI vienen como lista: se muestra un mensaje legible ("Número de teléfono inválido para el país seleccionado") en vez de `[object Object]`.
- El texto del paso final usa el número en E.164.

## Tests — `backend/tests/test_phone_international.py` (nuevo)
1. **Happy path**: `POST /api/appointments` con `+507 6123-4567` guarda `+50761234567`; `GET /api/countries` trae `PA` con `507` y `example` no vacío, y no trae `001`; `GET /api/config` incluye `default_country`. Además, para una muestra de países (PA, CL, US, ES, DE, JP, BR, AR), el `example` devuelto, compuesto como `+dial` + dígitos, **es aceptado por `normalize_phone`** (garantiza que el placeholder de cada país es un número con formato válido).
2. **Límite — solo móviles y números inválidos**: el número **fijo** de ejemplo de varios países (PA, CL, ES, DE, `example_number_for_type(region, FIXED_LINE)`), uno gratuito y uno de tarifa premium → 422 sin crear cita, mientras que el móvil de ejemplo del mismo país se acepta; además longitud incorrecta para el país, demasiado corto y con letras → 422; formatos válidos equivalentes (`+507 6123 4567`, `00507 61234567`, `(507) 6123-4567`) normalizan al mismo E.164.
3. **Límite — país base y códigos compartidos**: con `DEFAULT_COUNTRY=PA` (monkeypatch) `61234567` sin `+` se interpreta como Panamá, y con `CL` sigue la regla chilena de hoy; un número `+1` de EE. UU. y otro de Canadá son válidos y `phone_parts` devuelve el ISO correcto; `POST /api/device/remember` con número panameño devuelve `phone_country="PA"` y `phone_national="61234567"`.
Los 16 tests existentes no cambian.

## Docs
`docs/historias-de-usuario/HU-4/Plan-HU-4.md` (copia) y al terminar `Resultado-HU-4.md`; `README.md` (`DEFAULT_COUNTRY`, `/api/countries`, ya no solo Chile) y `docs/Proyect-doc.md` (quitar la nota "localización fija a Chile", documentar la validación).

## Verificación
1. `uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.txt`; luego `cd backend; .venv\Scripts\python.exe -m pytest` — 16 previos + 3 nuevos.
2. BD temporal (`DATABASE_URL` en `%TEMP%`, `DEFAULT_COUNTRY=PA`, `PYTHONUTF8=1`), `python seed.py`, servidor en `:8765`.
3. Playwright en `/app/index.html`: banderas SVG visibles (no letras); el selector arranca en Panamá; comprobar que el placeholder cambia al elegir otro país (Panamá → Chile → EE. UU. → Japón); buscar `pana`, `panamá`, `PA`, `507`, `+507`, `alemania`/`germany` (ISO `DE`, no empieza igual) y `corea` (KR y KP); navegación por teclado; reservar con un número panameño y con uno de otro país y ver el E.164 en la BD; número inválido → mensaje legible; modal de HU-1 → recargar y comprobar que el país y el número se rellenan igual; captura del panel abierto.
4. Cerrar el servidor y borrar la BD temporal; `citafacil.db` real no se toca.

## Riesgos / notas
- `is_valid_number` depende de los metadatos de la librería (se actualizan con las versiones); es el equilibrio entre rechazar errores y no bloquear números nuevos. Si preocupara, se podría degradar a `is_possible_number`.
- Se admiten solo móviles, pero la validación no puede saber si ese móvil tiene WhatsApp. En países con rangos compartidos (EE. UU., Canadá…) un fijo podría pasar como `FIXED_LINE_OR_MOBILE`: es un límite de los datos de la librería, no de la lógica.
- Los clientes o perfiles de dispositivo ya guardados con un fijo (no hay: el sistema anterior solo aceptaba móviles chilenos) no se revalidan; la regla aplica a reservas y perfiles nuevos.
- Banderas y nombres necesitan internet (CDN) / un navegador moderno (`Intl.DisplayNames`); sin ellos el selector sigue funcionando con ISO y código.
- La zona horaria (`BUSINESS_TIMEZONE`, hoy `America/Santiago`) y la moneda siguen siendo de Chile por defecto: quedan fuera de esta HU, solo se menciona en el `.env.example`.
