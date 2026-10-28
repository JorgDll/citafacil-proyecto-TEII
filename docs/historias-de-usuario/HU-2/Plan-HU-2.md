# Plan HU-2 — Calendario dinámico con días y franjas ocupadas

## Contexto
HU-2: "ver un calendario dinámico con los días disponibles y ocupados, para elegir mi fecha rápidamente sin intentos fallidos".

**Viabilidad:** sí se puede, y es un cambio de presentación sobre lógica que ya existe. Hoy `generate_slots` (`backend/app/availability.py`) *oculta* franjas pasadas u ocupadas, y `is_slot_free` ya impide reservar en el pasado o solapado (409). Lo observado por el usuario es correcto: una cita de 30 min el 7-nov a las 10:00 ocupa [10:00, 10:30), por eso la pantalla muestra desde 10:30. Lo nuevo es (a) mostrar toda la rejilla con las ocupadas bloqueadas y (b) un calendario mensual con el estado de cada día. No cambia ninguna regla de reserva.

Decisiones del usuario:
- Alcance: **calendario mensual + franjas**.
- Horas ya pasadas del día de hoy: **visibles, bloqueadas y atenuadas** (etiqueta distinta a "ocupado").

Rama: seguir en `feature/historias-usuario-v2` (sin commit/push hasta que se pida).

## Backend
**`backend/app/availability.py`**
- `_booked_between(db, first_day, last_day)` — una sola consulta de citas no canceladas del rango; `_booked_that_day` pasa a delegar en ella.
- `build_day_slots(db, service, day, booked=None) -> list[dict]` — recorre la misma rejilla que `generate_slots` (apertura→cierre, `slot_interval_minutes`, la franja debe caber antes del cierre) y devuelve `{time, available, reason}` con `reason` ∈ `None | "past" | "booked"` (pasado tiene prioridad). Día cerrado → `[]`. Reutiliza `_overlaps` y `local_now`.
- `generate_slots` se reescribe como filtro de `build_day_slots` (`available`): misma salida que hoy, así `/api/availability` y sus tests no cambian.
- `month_overview(db, service, year, month) -> list[dict]` — `{date, status, free}` por día del mes, con `status` ∈ `past | closed | full | available`. Una consulta para todo el mes; `full` = abierto, no pasado y 0 franjas libres (incluye "hoy sin horas restantes").

**`backend/app/schemas.py`** — `SlotOut` (`time`, `available`, `reason`) y `DayOut` (`date`, `status`, `free`).

**`backend/app/routers/public.py`** — dos endpoints nuevos (404 si el servicio no existe/está inactivo, igual que `/availability`):
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/schedule?service_id&date` | `list[SlotOut]` con **todas** las franjas |
| GET | `/api/calendar?service_id&month=YYYY-MM` | `list[DayOut]`; `month` mal formado → 422 |

`/api/availability` y `POST /api/appointments` quedan intactos (el 409 por carrera sigue siendo la red de seguridad). La disponibilidad depende de la duración del servicio, así que ambos endpoints reciben `service_id`.

## Frontend (`frontend/index.html`)
- Se reemplaza `<input type="date">` por un calendario propio: cabecera con mes y flechas (no se puede ir antes del mes actual), semana Lun–Dom, celdas con clase `avail | full | closed | past` y leyenda. Solo `avail` es clicable; hoy resaltado. Estado en `state.date` (ya no se lee de `dateInput`).
- Al elegir servicio se carga `/api/calendar` del mes visible; cambiar de servicio lo recarga (la duración cambia qué días/horas caben) y borra día/hora elegidos.
- Al elegir un día → `/api/schedule`: franjas libres clicables; `booked` deshabilitadas, tachadas y con `title="Ocupado"`; `past` atenuadas con `title="Ya pasó"`. Se mantienen los guardas de petición obsoleta (`slotsReq`, y uno análogo para el calendario).
- Tras un 409 al confirmar, se recargan franjas y calendario.
- CSS en el bloque `<style>` existente (variables `--ok`, `--err`, `--border`, `--accent`); responsive (celdas con `aspect-ratio`).
- `admin.html` no cambia.

## Tests — `backend/tests/test_schedule.py` (nuevo, usa `conftest.py`)
El "ahora" se congela con `monkeypatch.setattr("app.availability.local_now", ...)` para que sean deterministas.
1. **Happy path**: tras reservar a las 11:00 (30 min), `/api/schedule` devuelve la rejilla completa (10:00…19:30), con 11:00 `available:false, reason:"booked"` y el resto libres; `/api/availability` sigue sin listar 11:00 (compatibilidad).
2. **Límite — duración y solapes**: con servicio de 45 min y cita existente a las 11:00, también quedan `booked` 10:30 (10:30–11:15 solapa) y 11:30 si la cita dura hasta 11:45, pero no 10:00; una cita `cancelled` no bloquea nada.
3. **Límite — calendario**: con el reloj congelado, `/api/calendar` marca domingo `closed`, ayer `past`, un día con todas las franjas ocupadas `full` (citas insertadas por la sesión de BD) y un día normal `available` con `free` correcto; hoy aparece con las horas ya pasadas como `past` en `/api/schedule`; `month=2026-13` → 422 y servicio inexistente → 404.

## Docs
- `docs/historias-de-usuario/HU-2/Plan-HU-2.md` (copia de este plan) y, al terminar, `Resultado-HU-2.md`.
- `README.md` (tabla de endpoints) y `docs/Proyect-doc.md` (API, flujos).

## Verificación
1. `cd backend; .venv\Scripts\python.exe -m pytest` — 9 previos + 3 nuevos en verde.
2. BD temporal para no ensuciar `citafacil.db`: `$env:DATABASE_URL="sqlite:///$env:TEMP/e2e.db"; $env:PYTHONUTF8=1; python seed.py; python -m uvicorn app.main:app --port 8765`.
3. Playwright en `http://localhost:8765/app/index.html`: elegir servicio → calendario con domingos cerrados y días pasados atenuados; elegir día → rejilla completa; reservar 10:00 y recargar → 10:00 tachada/ocupada, resto libre; con servicio de 45 min el 09:30/10:30 vecino aparece bloqueado; llenar un día (script) → ese día pasa a "lleno" en el calendario; navegar de mes con las flechas; probar en ancho móvil.
4. Cierre limpio del servidor y de la BD temporal.

## Riesgos / notas
- Carrera: dos usuarios con la misma franja visible como libre siguen resolviéndose con el 409 (sin constraint único; ya anotado en la exploración).
- El calendario consulta el mes entero en un solo request; con muchos servicios/citas es barato (una consulta indexada por `start_at`).
- Fuera de alcance: vista por semana, múltiples profesionales, cambios en el panel admin.
