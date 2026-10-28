# Resultado HU-3 — Histórico de demanda y proyección

**Historia:** Como administrador, quiero ver gráficos de previsión de la demanda basados en el histórico, para ajustar los precios y el inventario de forma inteligente.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-3.md`

## Decisiones
- Sin tablas nuevas: todo se calcula contando `appointments` (no canceladas, por fecha de la cita `start_at`).
- Presets móviles que terminan hoy (inclusive): 7, 14, 30, 90 (trimestre), 180 (semestre) y 365 (año) días, más rango libre `from`/`to` (máx. 3 años). Incluye servicios inactivos.
- Proyección propia, sin dependencias nuevas: factor por día de la semana × recta de tendencia (mínimos cuadrados) sobre la serie desestacionalizada, banda de ~80 % con la desviación de los residuos, días cerrados = 0. Entrena con los últimos 90 días sin contar hoy y desde la primera reserva de la ventana (los días previos al uso del sistema no cuentan como demanda cero).
- Chart.js 4.4.1 desde cdnjs; datos demo con `backend/seed_history.py`.

## Cambios
**Nuevos:** `backend/app/analytics.py`, `backend/app/routers/analytics.py`, `backend/seed_history.py`, `backend/tests/test_analytics.py`, `docs/historias-de-usuario/HU-3/`.

**Modificados:** `backend/app/schemas.py` (esquemas de salida), `backend/app/main.py` (router), `frontend/admin.html` (tarjeta "Análisis de demanda"), `README.md`, `docs/Proyect-doc.md`.

## API (admin, `X-Admin-Token`)
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/admin/analytics/services` | `{start, end, total, items:[{service_id, name, count}]}` |
| GET | `/api/admin/analytics/trend` | `{labels, group_by, series:[{service_id, name, counts}]}` |
| GET | `/api/admin/analytics/forecast?horizon=14\|30\|90` | `{enough_data, history, forecast:[{date, expected, lower, upper}], expected_total, trend_per_week, method}` |

Parámetros: `range` o `from`+`to`, `service_ids`, `group_by` (solo trend). Entradas inválidas (preset desconocido, `from > to`, rango > 3 años, `horizon` fuera de 14/30/90, `service_ids` no numérico) devuelven 422.

## Panel admin
Tarjeta con tres pestañas. Barras: un servicio por barra. Líneas: un trazo por servicio, agrupado por día, semana o mes (automático según el rango). Proyección: histórico de 28 días, línea esperada y banda sombreada, con el método y el total esperado como texto. Filtros: botones de rango, fechas libres y chips de servicios (el color de cada servicio es el mismo en todas las pestañas). Estados vacíos y mensajes de error propios; si "Desde" es posterior a "Hasta" no se llama a la API.

## Pruebas
`python -m pytest` (desde `backend/`): **16 pasan** (12 previos + 4 nuevos). El reloj se congela (`app.analytics.local_now`).

| Test | Cubre |
|---|---|
| `test_happy_path_bars_and_lines_count_requested_services` | Conteos por servicio y serie diaria; una cita cancelada no cuenta |
| `test_edge_range_boundaries_filters_and_validation` | `7d` = hoy-6…hoy (hoy-7 queda fuera, la última franja del último día entra); rango libre inclusivo; filtro por servicio; agrupación automática; 422 y control de acceso |
| `test_edge_forecast_keeps_weekly_pattern_and_needs_enough_data` | Sin datos no proyecta; con 12 semanas sintéticas: `0 ≤ lower ≤ expected ≤ upper`, domingos en 0, viernes > martes, `horizon=20` → 422 |
| `test_unit_forecast_trend_sign_follows_demand` | Tendencia positiva con demanda creciente y ≈ 0 con demanda constante |

Verificación manual en navegador (BD temporal con `seed_history.py`, 879 citas): las tres pestañas dibujan su gráfico; cambio de presets, rango libre, filtro de servicios y horizonte; estado vacío con un rango sin datos; sin errores de consola.

## Limitaciones conocidas
- La proyección es una extrapolación simple (prueba de concepto): con poco historial real es poco fiable (por eso el umbral mínimo y la banda). No modela feriados ni campañas.
- Ajustar **precios e inventario** sigue siendo una decisión humana: los gráficos son solo apoyo y no generan recomendaciones. La proyección es una prueba de concepto, no una predicción real.
- Los meses extremos del rango anual son parciales (el primero y el actual), lo que hace caer la línea en el último punto.
- Requiere internet para cargar Chart.js.
- No probado visualmente: estado "sin datos suficientes" de la proyección en el navegador (sí por test) ni la vista móvil.
- Si cambian la zona horaria o los días cerrados, la proyección usa `CLOSED_WEEKDAYS` del momento.
