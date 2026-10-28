# AI Development Log — CitaFácil (Proyecto #1)

Registro del uso de IA durante el sprint, en el formato que pide el enunciado. Como indica el PDF, no se anota cada prompt: solo los que afectaron de forma significativa el desarrollo.

**Herramientas de IA usadas**

| Herramienta | Modelo | Quién la usó | Para qué |
|---|---|---|---|
| Claude Code (CLI de escritorio) | Claude Sonnet 5.5 | Developer (JorgDll) | Análisis del repo, planes por HU, código, tests y documentación (commits con `Co-Authored-By: Claude Sonnet 5.5`) |
| Playwright (MCP dentro de Claude Code) | — | Developer | Verificación de cada HU en el navegador |
| Claude Code (CLI de escritorio) | Claude Opus 5.5 | QA (Chrisvlj) | Revisión contra el PDF, pruebas exploratorias, correcciones de QA, este log y el reporte |

**Forma de trabajo:** para cada HU, la IA primero analizaba el código existente y escribía un **plan** (`docs/historias-de-usuario/HU-x/Plan-HU-x.md`). El developer lo aprobaba o corregía tomando las "decisiones del usuario" que figuran en cada plan, y solo entonces se implementaba. Al terminar, la IA escribía el `Resultado-HU-x.md`. Así se cumple la indicación del PDF de analizar el proyecto antes de pedirle a la IA que modifique código.

---

## 1. Registro de actividades

| # | Actividad | Herramienta IA | Qué se solicitó | Resultado | Decisión humana |
|---|---|---|---|---|---|
| 1 | Arquitectura | Claude Code (Sonnet) | Analizar el repo original y documentarlo | `docs/Proyect-doc.md` con capas, endpoints, modelos y limitaciones | Aceptada; base para todas las HU |
| 2 | Arquitectura (HU-1) | Claude Code (Sonnet) | Plan para "reservar con mis datos guardados" | Propuso identificar el dispositivo con una cookie `HttpOnly` y guardar solo el SHA-256 del token, sin login | **Modificada:** la HU habla de "formulario de pago", pero la app no tiene pagos, así que se decidió que la HU se refiere al nombre y celular. Se decidió servir el frontend desde FastAPI (desde `file://` las cookies no funcionan) y preguntar antes de actualizar datos distintos |
| 3 | Código (HU-1) | Claude Code (Sonnet) | Implementar el plan | `device.py`, `routers/device.py`, modal en `index.html` | Aceptado |
| 4 | Testing (HU-1) | Claude Code (Sonnet) | Camino feliz + 2 casos límite | 3 tests (9 en total) | Aceptado |
| 5 | Arquitectura (HU-2) | Claude Code (Sonnet) | Analizar la viabilidad del calendario dinámico | Diagnóstico: el motor ya impedía el doble booking y el cambio era de presentación | **Aceptada**, con el alcance que eligió el humano: "calendario mensual + franjas", horas pasadas visibles y atenuadas |
| 6 | Código + Testing (HU-2) | Claude Code (Sonnet) | `/api/schedule`, `/api/calendar`, calendario en `index.html` | 3 tests con reloj congelado (12 en total) | Aceptado. **QA encontró después que el motor aceptaba horas fuera de la grilla (QA-01)** |
| 7 | Arquitectura (HU-3) | Claude Code (Sonnet) | Plan de previsión de demanda | Opciones de modelo y de librería de gráficos | **Decisión humana:** estacionalidad semanal + tendencia con cálculo propio (sin dependencias nuevas), Chart.js por CDN y datos demo con `seed_history.py` |
| 8 | Código + Testing (HU-3) | Claude Code (Sonnet) | Endpoints de analítica, tarjeta en el panel y tests | 4 tests (16 en total), 879 citas demo | Aceptado. Ajustar precios queda como decisión humana: los gráficos no recomiendan |
| 9 | Código (HU-4) | Claude Code (Sonnet) | Teléfonos internacionales | Validación con `phonenumbers`, solo móviles, selector de país | **Decisión humana:** banderas con flag-icons (en Windows los emojis de bandera no se ven) y país base configurable con `DEFAULT_COUNTRY` |
| 10 | Debug | Claude Code (Sonnet) | Analizar por qué fallaban 2 tests en la máquina del developer | Los tests dependían del `.env` local (`DEFAULT_COUNTRY=PA` invalidaba un móvil chileno sin `+`) | Corregido: `conftest.py` fija todo el entorno (commit `83a5db4`) |
| 11 | Arquitectura (HU-5) | Claude Code (Sonnet) | Plan de autogestión por enlace | Token en el fragmento `#t=` (no llega a los logs), tabla `appointment_links` en vez del campo `manage_token` | **Modificada:** el humano fijó un plazo de 2 h, un máximo de 2 reprogramaciones y que cancelar exija escribir "Cancelar cita" |
| 12 | Testing (HU-5) | Claude Code (Sonnet) | 3 tests de la HU | Un test detectó un bug del propio código generado (ver §2, caso A) | Código corregido |
| 13 | Arquitectura (HU-6) | Claude Code (Sonnet) | Plan de cuentas y roles | Sesión opaca por cookie `HttpOnly` en vez del JWT que pedía la HU; scrypt; bloqueo; auditoría de solo agregar | **Modificada:** el humano decidió roles base con permisos ajustables por empleado y que `ADMIN_TOKEN` sirva solo para la instalación. **La desviación respecto a JWT se aceptó en QA** (§4) |
| 14 | Testing (HU-6) | Claude Code (Sonnet) | 4 tests de cuentas, permisos y auditoría | 4 de los fallos iniciales eran errores de los tests escritos por la IA (§2, caso B) | Tests corregidos; la app no cambió |
| 15 | Revisión QA | Claude Code (Opus) | Contrastar la rama con el PDF y las HU | Tabla de cumplimiento; primero concluyó mal que HU-4/5/6 no existían (§2, caso D) | Corregido tras arreglar el acceso SSH y repetir el `git fetch` |
| 16 | Testing QA | Claude Code (Opus) | Pruebas exploratorias contra el servidor | Encontró QA-01 (hora 10:13 aceptada), QA-03 (XSS) y confirmó QA-02 | Aceptados como hallazgos |
| 17 | Debug QA | Claude Code (Opus) | Hipótesis de doble booking por concurrencia | 20 peticiones simultáneas: no se reprodujo en SQLite | **Hipótesis rechazada como bug**; queda como riesgo QA-06 para PostgreSQL |
| 18 | Código QA | Claude Code (Opus) | Corregir QA-01, QA-02 y QA-03 | Validación de la grilla, `rotate_link` en recordatorios, `esc()` en `index.html` | Aceptado; se descartó cambiar zona horaria y moneda (QA-09) porque son configuración del despliegue, no código |
| 19 | Testing QA | Claude Code (Opus) | Tests de regresión | 6 tests: **fallan con el código del developer y pasan con la corrección** (32 en total) | Aceptado |

---

## 2. Ejemplos de respuestas incorrectas de la IA

| Caso | Dónde | Qué hizo mal la IA | Cómo se detectó | Corrección |
|---|---|---|---|---|
| **A** | HU-5, `schemas.CancelIn` | Generó `confirmation: str = ""` con un validador. Pydantic no valida los valores por defecto, así que un cuerpo `{}` **cancelaba la cita sin confirmación** | El test de la HU (`test_happy_path_..._cancel_with_typed_confirmation`) | Campo obligatorio (`Field(...)`), con un comentario que explica el motivo |
| **B** | HU-6, `tests/test_staff.py` | 4 tests escritos por la IA partían de supuestos falsos (cómo se cuentan los intentos fallidos; varias sesiones del mismo usuario) | Fallaban contra una app que se comportaba bien | Se corrigieron los tests, no la app (documentado en `Resultado-HU-6.md`) |
| **C** | Tests en general | Los tests generados dependían del `.env` de la máquina: con `DEFAULT_COUNTRY=PA` fallaban 2 | Ejecución en la máquina del developer | `conftest.py` aísla el entorno (commit `83a5db4`) |
| **D** | Sesión de QA | La IA concluyó que HU-4, HU-5 y HU-6 "solo estaban como texto". Revisaba una copia local desactualizada porque el `git fetch` había fallado por permisos SSH | El humano sabía que el developer había terminado y lo contradijo | Se arregló el acceso, se repitió el `fetch` y se revisó el commit `a00d137` |
| **E** | HU-5, limitación documentada | La IA del developer dio por imposible poner el enlace en el recordatorio ("el token no se puede regenerar porque solo se guarda el hash") y el criterio 1 quedó incumplido | Revisión de QA contra los criterios de aceptación | Se rota el token en la misma fila (`manage.rotate_link`) (QA-02) |
| **F** | HU-2 / HU-5 | La IA afirmó que el motor de disponibilidad "ya era correcto" y lo reutilizó sin revisar la alineación con la grilla | Prueba exploratoria de QA: reserva a las 10:13 → 201 | Validación de la grilla en `is_slot_free` (QA-01) |
| **G** | Commit de HU-5 | La IA incluyó en el commit un archivo de log de Playwright | Revisión del historial | Commit `5bffc4b`: se borró y se agregó `.playwright-mcp/` al `.gitignore` |
| **H** | Sesión de QA | La IA intentó instalar las dependencias con el Python 3.14 del sistema, incompatible con las versiones fijadas | Error de compilación de `pydantic-core` y `psycopg2-binary` | Entorno con Python 3.12 y README corregido (QA-05) |

## 3. Cambios de la IA que se rechazaron o modificaron

| Propuesta de la IA | Decisión | Motivo |
|---|---|---|
| HU-1: interpretar "formulario de pago" literalmente | Rechazada | La app no tiene pagos; la HU se aplicó a los datos de contacto |
| HU-3: que los gráficos sugieran ajustes de precio o inventario | No se implementó | El ajuste de precios es una decisión humana; la proyección es una prueba de concepto |
| HU-5: campo `manage_token` en `Appointment` (como decía el "impacto técnico" de la HU) | Reemplazado por la tabla `appointment_links` | Evita un `ALTER TABLE` en bases existentes y permite revocar el enlace borrando la fila |
| HU-5: dejar los recordatorios sin enlace | Rechazado en QA | Incumplía el criterio 1 → QA-02 |
| QA: tratar la concurrencia como un bug confirmado | Rechazado | No se reprodujo; se registra como riesgo (QA-06) |
| QA: cambiar en `.env.example` la zona horaria y la moneda a Panamá | Rechazado | Es configuración del despliegue; queda como QA-09 |
| QA: reescribir HU-6 con JWT para cumplir el criterio literal | Rechazado | La sesión en cookie es más segura en este contexto (§4) |

## 4. Decisiones tomadas por humanos

| HU | Decisión | Tomada por |
|---|---|---|
| General | Trabajar todas las HU en `feature/historias-usuario-v2` y no tocar `main` hasta la revisión | Developer |
| General | La app corre solo en local: el frontend se sirve desde FastAPI | Developer |
| HU-1 | Preguntar antes de actualizar los datos guardados si el cliente escribe otros | Developer |
| HU-2 | Alcance: calendario mensual + franjas; horas pasadas atenuadas | Developer |
| HU-3 | Modelo de previsión propio (estacionalidad + tendencia), Chart.js por CDN y datos demo | Developer |
| HU-4 | flag-icons por CDN; país base configurable (`PA` sugerido) | Developer |
| HU-5 | Plazo de 2 h, máximo 2 reprogramaciones y cancelación con el texto "Cancelar cita" | Developer |
| HU-6 | Roles base con permisos por empleado; `ADMIN_TOKEN` solo para la instalación | Developer |
| HU-6 | **Aceptar la sesión en cookie `HttpOnly` en vez de JWT.** Un XSS no puede robarla y se revoca al instante al desactivar un usuario | QA |
| HU-5 | Al llegar el recordatorio, el enlace de la confirmación deja de servir (vale el del último mensaje) | QA |
| General | Ante la salida del developer, QA corrige los hallazgos y prepara el PR | Equipo |
| General | QA-06 a QA-10 quedan como riesgos conocidos para el siguiente sprint | QA |

## 5. Métricas del uso de IA

| Métrica | Valor |
|---|---|
| HU implementadas con IA | 6 (3 obligatorias + 3 propias) |
| Tests generados por la IA del developer | 26 (todos pasan) |
| Tests generados en QA | 6 (regresión) → 32 en total |
| Bugs en código generado por la IA, detectados por sus propios tests | 1 (caso A) |
| Bugs que pasaron la etapa de desarrollo y detectó QA | 3 (QA-01, QA-02, QA-03) |
| Tests generados por la IA que estaban mal | 4 (caso B) + 2 dependientes del entorno (caso C) |
| Conclusiones incorrectas de la IA corregidas por humanos | 3 (casos D, E, F) |
