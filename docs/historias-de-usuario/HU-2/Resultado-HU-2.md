# Resultado HU-2 — Calendario dinámico con días y franjas ocupadas

**Historia:** Como cliente, quiero ver un calendario dinámico con los días disponibles y ocupados, para elegir mi fecha rápidamente sin intentos fallidos.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-2.md`

## Viabilidad
Sí era viable, y no cambia ninguna regla de reserva. El comportamiento previo era correcto: una cita de 30 min a las 10:00 ocupa [10:00, 10:30), por eso la pantalla mostraba desde 10:30; `generate_slots` ocultaba lo ocupado y pasado, y `is_slot_free` ya rechazaba (409) reservas en el pasado o solapadas. El cambio es de presentación: mostrar toda la rejilla con lo no disponible bloqueado y añadir un calendario mensual.

## Decisiones
- Alcance: calendario mensual + franjas.
- Horas pasadas de hoy: visibles, atenuadas y bloqueadas (distintas de "ocupado").
- `/api/availability` y `POST /api/appointments` quedan intactos; se añadieron endpoints nuevos.

## Cambios
**Nuevos:** `backend/tests/test_schedule.py`, `docs/historias-de-usuario/HU-2/`.

**Modificados:**
- `backend/app/availability.py`: `build_day_slots` (todas las franjas con estado), `month_overview` (estado por día, una sola consulta al mes), `_booked_between`; `generate_slots` pasa a filtrar `build_day_slots`.
- `backend/app/schemas.py`: `SlotOut`, `DayOut`.
- `backend/app/routers/public.py`: `GET /api/schedule` y `GET /api/calendar`.
- `frontend/index.html`: calendario mensual (flechas, semana Lun-Dom, leyenda, no se navega a meses anteriores) y franjas con estados.
- `README.md`, `docs/Proyect-doc.md`.

## API nueva
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/schedule?service_id&date` | `[{time, available, reason}]`, `reason`: `null`, `booked` o `past` |
| GET | `/api/calendar?service_id&month=YYYY-MM` | `[{date, status, free}]`, `status`: `available`, `full`, `closed`, `past` |

## Pruebas
`python -m pytest` (desde `backend/`): **12 pasan** (9 previos + 3 nuevos). El reloj se congela (`app.availability.local_now`) para que sean deterministas.

| Test | Cubre |
|---|---|
| `test_happy_path_schedule_shows_every_slot_with_booked_blocked` | Reserva real; `/schedule` devuelve las 20 franjas con 11:00 bloqueada; `/availability` sigue sin listarla |
| `test_edge_overlap_depends_on_duration_and_cancelled_does_not_block` | Con servicio de 45 min la cita de las 11:00 bloquea también 10:30; una cita cancelada no bloquea; 19:30 no cabe antes del cierre |
| `test_edge_calendar_statuses_past_hours_and_validation` | Domingo `closed`, ayer `past`, día completo `full`, hoy con horas `past`; mes inválido 422; servicio inexistente 404 |

Verificación manual en navegador (BD temporal): calendario con días pasados atenuados y domingos cerrados; el 10:00 reservado aparece tachado y el resto libre; un día con las 20 franjas reservadas aparece como "lleno"; navegación al mes siguiente; las horas ya pasadas de hoy aparecen atenuadas.

## Limitaciones conocidas
- La carrera entre dos usuarios que ven la misma franja libre sigue resolviéndose con el 409 (no hay restricción única en BD); tras el 409 el frontend recarga franjas y calendario.
- No probado en pantalla móvil real ni el flujo del 409 desde la interfaz.
- "Hoy" y las horas pasadas las decide el servidor según `BUSINESS_TIMEZONE` (por defecto `America/Santiago`); si el negocio está en otra zona (p. ej. Panamá) hay que configurarla.
- Fuera de alcance: vista semanal, varios profesionales, panel admin.
