# Plan HU-3 — Histórico de demanda y proyección (panel admin)

## Contexto
HU-3: "como administrador, quiero ver gráficos de previsión de la demanda basados en el histórico". Se pide: histórico de servicios solicitados con rangos 7 días, 14 días, 30 días, trimestre, semestre y año **más un rango libre de fecha a fecha**; dos gráficos de historial (barras simples y líneas comparativas, ambos filtrables por fechas y servicios) y un tercer gráfico de proyección. **Sin tablas nuevas**: todo se calcula contando `appointments`.

Decisiones del usuario: proyección = estacionalidad semanal + tendencia (cálculo propio, sin dependencias nuevas); Chart.js por CDN; script de datos demo `backend/seed_history.py`.

Supuestos que adopto (decir si alguno no te sirve):
- Una reserva "se solicita" cuando es **no cancelada**; se cuenta por su **fecha de la cita** (`start_at`), no por cuándo se creó.
- Presets = ventanas móviles que terminan **hoy** (inclusive): 7, 14, 30, 90 (trimestre), 180 (semestre) y 365 (año) días; no son trimestres/semestres de calendario.
- Se incluyen servicios inactivos (es histórico). El rango libre acepta como máximo 3 años.

Rama: `feature/historias-usuario-v2` (sin commit/push hasta que lo pidas).

## Backend
**`backend/app/analytics.py`** (nuevo, funciones puras + consultas; agrega en Python para ser portable SQLite/PostgreSQL — el volumen es pequeño):
- `resolve_range(preset, date_from, date_to) -> (start, end)`: preset `7d|14d|30d|90d|180d|365d` termina hoy (usa `local_now` de `utils.py`); si vienen `from`/`to` mandan ellos. Valida `from <= to` y span ≤ 1095 días (`ValueError` → 422).
- `fetch_rows(db, start, end, service_ids)`: una consulta de `(start_at, service_id)` con `status != cancelled` y `start_at` entre `start 00:00` y `end 23:59:59` (reutiliza el patrón de `availability._booked_between`).
- `counts_by_service(...)` → barras: `[{service_id, name, count}]` (todos los servicios filtrados, incluso con 0).
- `trend(...)` → líneas: `labels` + una serie por servicio con ceros rellenados; agrupación `group_by` ∈ `day|week|month` (auto: ≤31 días → día, ≤182 → semana, resto → mes; semana ISO iniciando lunes).
- `forecast_demand(daily_counts, horizon, closed_weekdays)`: modelo **estacionalidad semanal + tendencia**:
  1. Entrena con los últimos 90 días (sin incluir hoy, que está incompleto), ceros rellenados.
  2. Factor por día de la semana `s_d = media(d) / media global` (días cerrados → 0).
  3. Desestacionaliza (`y/s`), ajusta una recta por mínimos cuadrados (Python puro, sin numpy) y proyecta `ŷ = max(0, a + b·t) · s_d`.
  4. Banda ≈ 80 % con la desviación estándar de los residuos: `[max(0, ŷ − 1.28σ), ŷ + 1.28σ]`; días cerrados = 0.
  5. Datos insuficientes (< 14 días con historial o < 5 reservas) → `enough_data: false` y sin proyección.

**`backend/app/schemas.py`**: `ServiceCountOut`, `SeriesOut`, `TrendOut`, `ForecastPoint`, `ForecastOut` (incluye `history` de los últimos 28 días, `forecast`, `expected_total`, `trend_per_week`, `method`, `enough_data`, `message`).

**`backend/app/routers/analytics.py`** (nuevo; `prefix="/api/admin/analytics"`, `dependencies=[Depends(require_admin)]` de `auth.py`). Parámetros comunes: `range`, `from`, `to`, `service_ids` (lista separada por comas).
| Método | Ruta | Uso |
|---|---|---|
| GET | `/services` | Gráfico de **barras** (total por servicio) |
| GET | `/trend` (+ `group_by`) | Gráfico de **líneas** (serie por servicio) |
| GET | `/forecast` (`horizon` 14/30/90, `service_ids`) | **Proyección** |

Errores: rango/preset inválido, `from > to`, span excesivo u `horizon` fuera de 14/30/90 → 422; sin token → 401/422 (igual que el resto de `/api/admin`).

**`backend/app/main.py`**: `include_router(analytics.router)`.

**`backend/seed_history.py`** (nuevo, a mano; idempotente): inserta ~12 meses de citas `done` sintéticas con `random.Random(42)` (más demanda vie/sáb, domingo cerrado, tendencia suave al alza, popularidad distinta por servicio), sin solapes por día, teléfono ficticio, `notes="[demo-historial]"`; `--reset` borra solo esas filas. Si no hay servicios, reutiliza `seed.run()`. Mensajes en ASCII (la consola cp1252 de Windows falló antes con ✔).

## Frontend (`frontend/admin.html`)
- Nueva tarjeta **"Análisis de demanda"** entre las estadísticas y las reservas, con pestañas **Barras · Líneas · Proyección**.
- Filtros compartidos: botones de rango (7 d · 14 d · 30 d · Trimestre · Semestre · Año), `Desde`/`Hasta` (al editar se activa "personalizado") y chips de servicios con checkbox (todos por defecto). Barras y líneas usan estos filtros; Proyección usa los servicios y su propio selector de horizonte (14/30/90 días).
- Chart.js `4.4.1` desde cdnjs (versión fija). Los gráficos se destruyen/recrean al cambiar filtros; color por servicio consistente entre pestañas; tema oscuro con las variables CSS existentes; barras = un servicio por barra, líneas = un trazo por servicio; proyección = histórico reciente + línea esperada + banda sombreada.
- Estados vacíos ("Sin reservas en este rango", "Aún no hay datos suficientes para proyectar") y guarda de petición obsoleta como en `index.html`.
- Se reutiliza el `api()` con `X-Admin-Token` ya existente; carga perezosa al abrir cada pestaña.

## Tests — `backend/tests/test_analytics.py` (nuevo; reloj congelado con `monkeypatch.setattr("app.analytics.local_now", ...)`)
1. **Happy path**: reservas de varios servicios en los últimos días (más una cancelada) → `/services?range=7d` da los conteos correctos por servicio, la cancelada no cuenta; `/trend` devuelve `labels` diarias y series que suman los mismos totales.
2. **Límite — fronteras de rango y filtros**: `7d` incluye exactamente hoy−6…hoy (una cita en hoy−7 queda fuera; una en el último día a las 19:30 entra); rango libre inclusivo en ambos extremos; `service_ids` restringe; `from > to`, span > 3 años y preset desconocido → 422; sin token → rechazo.
3. **Límite — proyección**: con 12 semanas sintéticas (viernes alto, domingo cerrado) la proyección tiene `horizon` puntos, `0 ≤ lower ≤ expected ≤ upper`, domingo = 0 y viernes > martes; con la base vacía → `enough_data:false`; `horizon=20` → 422.
4. **Unidad — tendencia**: `forecast_demand` con demanda creciente da `trend_per_week > 0` y con demanda constante ≈ 0 (verifica el ajuste sin pasar por HTTP).

## Docs
`docs/historias-de-usuario/HU-3/Plan-HU-3.md` (copia) y al terminar `Resultado-HU-3.md`; `README.md` (endpoints, `seed_history.py`) y `docs/Proyect-doc.md`.

## Verificación
1. `cd backend; .venv\Scripts\python.exe -m pytest` — 12 previos + 4 nuevos.
2. BD temporal: `$env:DATABASE_URL="sqlite:///$env:TEMP/e2e.db"; $env:PYTHONUTF8=1; python seed.py; python seed_history.py; python -m uvicorn app.main:app --port 8765`.
3. Playwright en `http://localhost:8765/app/admin.html`: entrar con `ADMIN_TOKEN`, comprobar en cada pestaña que el `<canvas>` se dibuja y que no hay errores de consola; cambiar los 6 rangos y uno personalizado, desmarcar servicios (barras/líneas cambian), cambiar el horizonte de la proyección; captura de las 3 vistas; probar con BD vacía (mensajes vacíos).
4. Cerrar servidor y borrar la BD temporal; `citafacil.db` real no se toca.

## Riesgos / notas
- Con pocas reservas reales la proyección es poco fiable: por eso hay umbral mínimo, banda de incertidumbre y el texto del método visible en el gráfico.
- Requiere internet para cargar Chart.js (igual que ya ocurre con fuentes e iconos).
- Fuera de alcance: previsión de **precios e inventario** (la HU lo menciona como propósito, pero se acotó a demanda), exportar a CSV y gráficos por hora.
