# Reporte de QA — Sprint de historias de usuario (HU-1 a HU-6)

| Campo | Valor |
|---|---|
| Proyecto | CitaFácil (Tópicos Especiales II — Proyecto #1) |
| Rol | QA (rotación: Developer → **QA** → Reviewer) |
| Responsable QA | Chrisvlj |
| Fecha | 2026-10-28 |
| Rama revisada | `feature/historias-usuario-v2` @ `a00d137` |
| Rama de QA | `qa/revision-historias` (correcciones + documentación) |
| Herramienta de IA usada en QA | Claude Code (Claude Opus 5.5), ver `docs/AI-Development-Log.md` |

> **Nota de equipo:** el developer de este sprint (JorgDll) ya no está disponible. Lo que le tocaba hacer después de la revisión (corregir los hallazgos y abrir el Pull Request) lo hizo el rol de QA en la rama `qa/revision-historias`. Cada corrección quedó en su propio commit, con su test de regresión.

---

## 1. Alcance

| HU | Historia | Origen |
|---|---|---|
| HU-1 | Como usuario recurrente, quiero reservar directamente usando mis datos guardados, para no tener que rellenar el formulario en cada compra. | Obligatoria (PDF) |
| HU-2 | Como cliente, quiero ver un calendario dinámico con los días disponibles y ocupados, para elegir mi fecha rápidamente sin intentos fallidos. | Obligatoria (PDF) |
| HU-3 | Como administrador del sistema, quiero ver gráficos de previsión de la demanda basados en el histórico, para ajustar los precios y el inventario de forma inteligente. | Obligatoria (PDF) |
| HU-4 | Como dueño del sistema en Panamá, quiero que mis clientes puedan usar números de cualquier país, para que los WhatsApp lleguen a todos. | Propia del equipo |
| HU-5 | Como cliente que ya reservó una cita, quiero cancelarla o reprogramarla desde un enlace personal que llega por WhatsApp, para no llamar al negocio y liberar el horario. | Propia del equipo |
| HU-6 | Como dueño del negocio, quiero que cada empleado entre con su propio usuario y contraseña y que yo defina qué puede hacer, para proteger los datos y saber quién confirmó, canceló o eliminó cada reserva. | Propia del equipo |
| HU-03 opcional | Recordatorio configurable por servicio. | Propuesta opcional: **no implementada** (sigue en "mejoras futuras" del README) |

El PDF pide como mínimo 2 HU propias y el equipo entregó 3 (HU-4, HU-5 y HU-6).

## 2. Entorno de prueba

| Elemento | Detalle |
|---|---|
| SO | Arch Linux (kernel 7.2) |
| Python | 3.12 (entorno creado con `uv venv --python 3.12`) |
| BD | SQLite temporal (fuera del repo), poblada con `seed.py` |
| Servidor | `uvicorn app.main:app` en un puerto local, `DEFAULT_COUNTRY=PA`, `BUSINESS_TIMEZONE=America/Panama`, Twilio vacío (modo demo: los WhatsApp se ven en el log) |
| Cliente | `pytest` + `fastapi.TestClient` y scripts `httpx` de prueba exploratoria |

**Hallazgo de entorno (QA-05):** con el Python 3.14 del sistema, `pip install -r requirements.txt` falla al compilar `psycopg2-binary==2.9.9` y `pydantic-core` (de `pydantic==2.7.4`). El README decía "Python 3.10+", así que se corrigió a "3.10 a 3.12".

## 3. Estrategia

1. **Revisión estática:** leer el código de cada HU contra su historia, sus criterios y los `Plan-HU-x.md` / `Resultado-HU-x.md` del developer.
2. **Pruebas automatizadas existentes:** correr la suite completa del developer.
3. **Pruebas exploratorias de caja negra** contra el servidor levantado: entradas límite, concurrencia, seguridad y permisos.
4. **Regresión de los hallazgos:** cada bug confirmado tiene un test que **falla con el código original y pasa con la corrección** (`backend/tests/test_qa_regressions.py`).
5. **Evidencia:** las salidas reales de cada ejecución y las capturas de la sesión de IA están en [`evidencia/`](evidencia/README.md).

## 4. Resultado de la suite automatizada

| Momento | Comando | Resultado |
|---|---|---|
| Rama del developer (`a00d137`) | `python -m pytest -q` | **26 passed** (632 warnings de `datetime.utcnow()` deprecado) |
| Tests de QA contra el código del developer | `pytest tests/test_qa_regressions.py` | **7 failed**: confirman QA-01, QA-02 y QA-06 ([evidencia 02](evidencia/02-regresion-qa-contra-codigo-developer.txt)) |
| Rama de QA con las correcciones | `python -m pytest -q` | **33 passed** (26 + 7 nuevos) ([evidencia 03](evidencia/03-pytest-rama-qa.txt)) |

## 5. Verificación por historia de usuario

Leyenda: ✅ cumple · ⚠️ cumple con observación · ❌ no cumple (antes de QA) · 🔧 corregido en QA

### HU-1 — Reserva rápida con datos recordados

| # | Criterio (derivado de la HU y del plan) | Evidencia | Estado |
|---|---|---|---|
| 1 | Tras reservar se ofrece guardar los datos en el dispositivo | Test `test_happy_path_remember_and_prefill`; el developer lo verificó en el navegador | ✅ |
| 2 | En la siguiente visita el formulario se rellena solo | Mismo test; `GET /api/device/profile` → `known:true` | ✅ |
| 3 | El token no se guarda en claro y la cookie no es legible desde JS | Cookie `HttpOnly`; en BD solo hay SHA-256 (test) | ✅ |
| 4 | Varios dispositivos del mismo cliente no se pisan | `test_edge_many_devices_and_token_never_overwritten` | ✅ |
| 5 | Token falso u olvidado → dispositivo desconocido | `test_edge_invalid_token_is_unknown_device` | ✅ |

**Observación:** la HU del PDF habla de "formulario de pago", pero la app no tiene pagos. El equipo interpretó la HU como "no volver a escribir nombre y celular" (decisión humana registrada en el AI Log). El frontend tampoco ofrece un botón para olvidar el dispositivo, aunque la API (`DELETE /api/device`) sí existe.

### HU-2 — Calendario dinámico

| # | Criterio | Evidencia | Estado |
|---|---|---|---|
| 1 | Calendario mensual con días disponibles, llenos, cerrados y pasados | `GET /api/calendar`; test `test_edge_calendar_statuses_...` | ✅ |
| 2 | Las franjas ocupadas o pasadas se ven bloqueadas | `GET /api/schedule` con `reason` `booked`/`past` (prueba exploratoria y test) | ✅ |
| 3 | "Sin intentos fallidos": lo que muestra el calendario coincide con lo que acepta la API | **QA-01:** la API aceptaba inicios fuera de la grilla (10:13), que bloquean dos franjas del calendario a la vez | ❌ → 🔧 |
| 4 | Dos clientes que eligen la misma franja a la vez no pueden reservar los dos | **QA-06:** 20 rondas de 20 `POST` simultáneos → doble reserva en 15 de 20 rondas, con hasta 15 citas en la misma franja ([evidencia 06](evidencia/06-concurrencia-codigo-developer.txt)). Tras la corrección: 0 de 20 ([evidencia 07](evidencia/07-concurrencia-rama-qa.txt)) | ❌ → 🔧 |

### HU-3 — Previsión de la demanda

| # | Criterio | Evidencia | Estado |
|---|---|---|---|
| 1 | Gráfico de demanda histórica por servicio (barras y líneas) | `test_happy_path_bars_and_lines_...`; el developer verificó las 3 pestañas en el navegador | ✅ |
| 2 | Proyección basada en el histórico | `test_edge_forecast_keeps_weekly_pattern_...` y `test_unit_forecast_trend_...` | ✅ |
| 3 | Filtros de rango y servicio; entradas inválidas → 422 | `test_edge_range_boundaries_filters_and_validation` | ✅ |
| 4 | Solo el personal con permiso ve el análisis | Desde HU-6 se exige el permiso `analytics.view` (test de matriz de permisos) | ✅ |

**Observación:** la proyección es un modelo simple (estacionalidad semanal + tendencia). La parte de "ajustar precios e inventario" de la HU queda como decisión humana: los gráficos no recomiendan nada. Está documentado como limitación.

### HU-4 — Teléfonos internacionales

| # | Criterio | Evidencia (exploratoria, `DEFAULT_COUNTRY=PA`) | Estado |
|---|---|---|---|
| 1 | Acepta móviles de cualquier país en E.164 | `+507 6123-4567` → `201`, guardado como `+50761234567` | ✅ |
| 2 | Sin `+`, usa el país base | `61234567` → `+50761234567` | ✅ |
| 3 | Rechaza fijos, gratuitos y texto | `+507 223-4567` → 422; `+1 800 555 0100` → 422; `abc` → 422 | ✅ |
| 4 | Selector de país con búsqueda | Verificado por el developer en el navegador; 3 tests de API | ✅ |

**Observación:** `+56 9 1234 5678` (formato chileno de ejemplo) se rechaza por inválido. No es un bug: `phonenumbers` no considera válido ese rango. Los números reales de los tests (`+56 9 4291 6570`) sí pasan.

### HU-5 — Autogestión de la cita

| # | Criterio (lista entregada al equipo) | Evidencia | Estado |
|---|---|---|---|
| 1 | La confirmación **y el recordatorio** por WhatsApp incluyen un enlace único no adivinable | Confirmación: ✅. **Recordatorio: no lo incluía (QA-02).** Corregido: el recordatorio rota el token y envía el enlace nuevo | ❌ → 🔧 |
| 2 | Desde el enlace se ve la cita y se puede cancelar o elegir otra hora libre del mismo servicio | Exploratoria: `GET /api/manage` 200; reprogramar 200; cancelar 200 | ✅ |
| 3 | Al cancelar o reprogramar, la hora original vuelve a `/api/availability` | Exploratoria: tras mover la cita de 12:00, la franja de 12:00 aparece libre | ✅ |
| 4 | La reprogramación usa el mismo motor de disponibilidad (sin doble reserva) | Reprogramar a una franja ocupada → 409. **Pero aceptaba 13:07 (QA-01) y no era atómica frente a peticiones simultáneas (QA-06)**; ambas cosas se corrigieron en el motor común | ❌ → 🔧 |
| 5 | Límite de anticipación (2 h); después solo se puede consultar | Test: 2 h exactas sí, 1 h 59 min → 409 | ✅ |
| 6 | WhatsApp de confirmación del cambio; el admin ve el nuevo estado | Aviso de reprogramación/cancelación en el log demo; la cita vuelve a `pending` y aparece en el panel y en la auditoría como "Cliente" | ✅ |
| — | Seguridad adicional | Sin token o con token falso → 404; enviarlo por query string no sirve; cancelar sin el texto "Cancelar cita" → 422; tras cancelar, el token queda revocado (404); 3.ª reprogramación → 409 | ✅ |

**Diferencias de diseño aceptadas** (decisión humana, ver AI Log):
- Tabla `appointment_links` en vez de un campo `manage_token` en `Appointment`, para evitar un `ALTER TABLE` en bases existentes.
- Endpoints `POST /api/manage/{cancel,reschedule}` con cabecera `X-Manage-Token`, en vez de `GET/PATCH /api/appointments/manage/{token}`. Así el token nunca aparece en la URL ni en los logs.

### HU-6 — Cuentas con roles y auditoría

| # | Criterio (lista entregada al equipo) | Evidencia (exploratoria + tests) | Estado |
|---|---|---|---|
| 1 | Usuarios con contraseña cifrada y roles: dueño (todo) y recepcionista (ver y cambiar estado, sin servicios ni eliminar) | Hash `scrypt$…`; la recepcionista confirma (200), pero eliminar, crear servicio y ver la auditoría dan 403 | ✅ |
| 2 | El login devuelve un **token JWT** con expiración que reemplaza al `X-Admin-Token` | Se implementó **sesión opaca en cookie `HttpOnly; SameSite=Strict`** con expiración de 12 h, no JWT. `X-Admin-Token` ya no abre la API (401) | ⚠️ desviación aceptada |
| 3 | Cada cambio de estado o eliminación guarda usuario, acción y fecha | `GET /api/admin/audit` lista quién confirmó, eliminó, inició sesión o falló el acceso | ✅ |
| 4 | El dueño ve el historial y puede desactivar usuarios | Desactivar a "rosa" → su sesión abierta pasa a 401 en la siguiente petición | ✅ |
| 5 | Un rol sin permiso recibe 403 | Matriz de 13 endpoints (test) y exploratoria; intentar darse permisos a sí misma → 403 | ✅ |
| 6 | Pruebas pytest de login, expiración y permisos | `tests/test_staff.py` (4 tests) | ✅ |
| — | Extras | Clave temporal obligatoria de cambiar (403 hasta hacerlo); bloqueo tras 5 fallos (429 incluso con la clave correcta); mismo mensaje para un usuario inexistente; `setup` no se puede repetir (409) | ✅ |

**Justificación de la desviación del criterio 2 (decisión humana):** una cookie `HttpOnly` no se puede leer desde JavaScript, así que un XSS no puede robar la sesión, cosa que sí pasaría con un JWT guardado en `localStorage`. Además, una sesión guardada en el servidor se puede revocar al instante (al desactivar un usuario o cambiar la contraseña), y un JWT sigue siendo válido hasta que expira. Se acepta el cambio y se deja registrado en vez de reescribir la HU-6.

## 6. Hallazgos

| ID | Severidad | HU | Hallazgo | Estado |
|---|---|---|---|---|
| **QA-01** | Alta | HU-2, HU-5 | `is_slot_free` no validaba que el inicio cayera en la grilla (`SLOT_INTERVAL_MINUTES`). `POST /api/appointments` con `10:13` → **201**, y la cita bloqueaba a la vez las franjas de 10:00 y 10:30 del calendario. Lo mismo pasaba al reprogramar (`13:07` → 200). El bug ya estaba en el repo original, pero contradice "sin intentos fallidos" de HU-2. | 🔧 Corregido |
| **QA-02** | Media | HU-5 | El recordatorio de WhatsApp no incluía el enlace de autogestión (criterio 1). El developer lo dio por imposible porque solo se guarda el hash del token. | 🔧 Corregido |
| **QA-03** | Baja (seguridad) | HU-2/HU-4 (frontend) | `index.html` insertaba `service.name` con `innerHTML` sin escapar. Un empleado con permiso `services.manage` podía guardar un nombre con HTML/JS que se ejecutaría en la página pública (XSS almacenado). `admin.html` y `manage.html` sí escapan. | 🔧 Corregido |
| **QA-04** | Info | HU-6 | La HU pedía JWT; se implementó una sesión en cookie. Desviación justificada (sección 5). | Aceptado |
| **QA-05** | Baja | General | El README decía "Python 3.10+", pero con 3.14 no se instalan las dependencias fijadas. | 🔧 Documentado |
| **QA-06** | **Alta** | HU-2, HU-5 | Comprobar disponibilidad e insertar no era atómico. Con ráfagas de 20 reservas simultáneas a la misma franja hubo **doble reserva en 15 de 20 rondas (hasta 15 citas por franja)**. Una primera prueba única dio bien por casualidad y se había clasificado como "riesgo". | 🔧 Corregido en un proceso; varios workers → issue |
| **QA-07** | Baja (riesgo) | HU-6 | El bloqueo es por cuenta: quien conozca el usuario del dueño puede dejarlo fuera 15 min con 5 intentos fallidos. No hay límite por IP. | Abierto: documentado por el developer |
| **QA-08** | Baja | HU-6 | La auditoría se escribe después de la acción, no en la misma transacción. | Abierto: documentado por el developer |
| **QA-09** | Baja | General | `.env.example` sugiere `DEFAULT_COUNTRY=PA` pero deja `BUSINESS_TIMEZONE=America/Santiago` y `CURRENCY=CLP`. Para un negocio en Panamá, "hoy" y las horas pasadas se calcularían con la hora de Chile. | Abierto: configuración del despliegue |
| **QA-10** | Info | HU-6 | 632 warnings por `datetime.utcnow()`, deprecado en Python 3.12. | Abierto: deuda técnica |
| **QA-11** | Media | HU-5, HU-6 | Si el cliente cancela por su enlace, otro cliente toma la franja y el personal **reabre** la primera cita desde el panel (`PATCH` a `pending`), la API no comprueba la disponibilidad: quedan **dos citas activas en la misma franja** ([evidencia 08](evidencia/08-qa11-reabrir-cancelada.txt)). Hace falta una acción del personal, así que no lo provoca un cliente. | Abierto: issue |

### Detalle de las correcciones

**QA-01:** `backend/app/availability.py` → `is_slot_free` rechaza un `start_at` que no esté a un múltiplo exacto de `SLOT_INTERVAL_MINUTES` desde la apertura (también segundos y microsegundos). Como reservar y reprogramar usan la misma función, la corrección cubre los dos casos.

**QA-02:**
- `backend/app/manage.py` → nueva función `rotate_link(db, appt)`. Genera un token nuevo y reemplaza el hash **en la misma fila**, así se conserva `reschedule_count`. Si la cita no tenía enlace (creada antes de HU-5), lo crea.
- `backend/app/reminders.py` envía ese enlace.
- `notifications.reminder_message` acepta `manage_url`, igual que `confirmation_message`.
- Consecuencia aceptada: el enlace de la confirmación deja de servir cuando llega el recordatorio. El cliente siempre usa el enlace del mensaje más reciente.

**QA-03:** `frontend/index.html` → función `esc()` (la misma de `admin.html`) aplicada a `s.name` y `state.service.name`.

**QA-06:** `availability.booking_lock` (un `threading.Lock`) envuelve "comprobar + insertar" en `POST /api/appointments` y "comprobar + mover" en `manage.reschedule`. Basta mientras la app corra en un solo proceso, que es lo que ya exige el programador de recordatorios (`Proyect-doc.md`). Con varios workers o instancias haría falta un bloqueo en la BD (por ejemplo `pg_advisory_xact_lock` o `SELECT … FOR UPDATE`); queda en el issue de riesgos.

### Tests de regresión (`backend/tests/test_qa_regressions.py`)

| Test | Hallazgo | Con el código del developer | Con la corrección |
|---|---|---|---|
| `test_qa01_off_grid_start_is_rejected` ×3 (11:13, 11:00:30, 10:45) | QA-01 | ❌ 201 | ✅ 409 |
| `test_qa01_grid_still_works_and_reschedule_is_also_validated` | QA-01 | ❌ 13:07 aceptada | ✅ |
| `test_qa02_reminder_includes_working_link_and_rotates_token` | QA-02 | ❌ sin enlace | ✅ enlace válido, el anterior da 404, conserva las reprogramaciones, no se reenvía |
| `test_qa02_reminder_creates_link_for_appointments_without_one` | QA-02 | ❌ | ✅ |
| `test_qa06_concurrent_bookings_create_a_single_appointment` (5 rondas × 20 hilos) | QA-06 | ❌ 10 de 10 ejecuciones | ✅ 5 de 5 ejecuciones |

**Verificación contra el servidor real (BD temporal):** reserva a las `10:13` → 409 y a las `10:30` → 201. `run_reminders` envió 3 recordatorios, todos con enlace, incluidas 2 citas del `seed.py` que no tenían enlace.

## 7. Pruebas exploratorias ejecutadas (resumen)

| Área | Caso | Resultado |
|---|---|---|
| Concurrencia | 20 reservas simultáneas a la misma franja (1 ronda) | 1 creada, 19 × 409: **falso negativo** |
| Concurrencia | 20 rondas × 20 reservas simultáneas | **Doble reserva en 15 de 20 rondas ❌ → QA-06** |
| HU-4 | 6 formatos de teléfono (móvil PA con y sin `+`, fijo PA, gratuito US, texto, ejemplo CL) | Esperado ✅ |
| HU-5 | Reprogramar solapando con la propia cita (45 min corrido 30) | 200 ✅ |
| HU-5 | Reprogramar a una franja ocupada / fuera de horario | 409 ✅ |
| HU-5 | Reprogramar a 13:07 | **200 ❌ → QA-01** |
| HU-5 | Cancelar con `{}` / con "  cancelar   CITA " | 422 / 200 ✅ |
| HU-5 | Token en query string en vez de cabecera | 404 ✅ |
| HU-5 | Nombre del cliente `<script>alert(1)</script>` | Se guarda como texto; `manage.html` usa `textContent` ✅ |
| HU-6 | `X-Admin-Token` antiguo | 401 ✅ |
| HU-6 | Recepcionista: listar antes de cambiar la clave temporal | 403 ✅ |
| HU-6 | Recepcionista: eliminar / crear servicio / ver auditoría / darse permisos | 403 ✅ |
| HU-6 | Dueño desactiva a la recepcionista con su sesión abierta | La siguiente petición da 401 ✅ |
| HU-6 | 5 fallos y luego la clave correcta | 429 ✅ |
| Frontend | Uso de `innerHTML` con datos del servidor | **`service.name` sin escapar → QA-03** |

## 8. Pendiente de verificación manual en el navegador

El developer ya probó en el navegador los flujos principales de cada HU. Quedan para el reviewer o para la demo:
- La página pública con un servicio llamado `<img src=x onerror=alert(1)>` debe mostrar el texto sin ejecutarlo (QA-03).
- Abrir el enlace de un recordatorio y comprobar que el de la confirmación ya da "enlace no válido" (QA-02).
- Todas las vistas en ancho móvil (~375 px).

## 9. Veredicto

**Aprobado con correcciones.** Las 6 HU cumplen su objetivo. Los incumplimientos de criterios (QA-01, QA-02 y QA-06, la doble reserva) y el XSS (QA-03) quedan corregidos y cubiertos por tests en `qa/revision-historias`. La desviación de HU-6 (sesión en cookie en lugar de JWT) se acepta como decisión humana documentada. QA-06 con varios workers y QA-07 a QA-11 quedan como riesgos conocidos en el [issue #1](https://github.com/JorgDll/citafacil-proyecto-TEII/issues/1) para el siguiente sprint.

Recomendación: fusionar `qa/revision-historias` (que contiene todo `feature/historias-usuario-v2`) en `main` mediante el [Pull Request #2](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2), que ya tiene la [revisión de QA](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2#pullrequestreview-5690040938) y espera la aprobación del reviewer.
