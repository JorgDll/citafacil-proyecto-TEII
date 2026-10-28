# Revisión del PR #2 — paquete para el reviewer

| Campo | Valor |
|---|---|
| PR | [#2 — HU-1 a HU-6 + correcciones de QA](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2) |
| Reviewer | Eriel Tensu |
| Preparado por | QA (Christian Valdespino) con Claude Code, para que el reviewer lo verifique |
| Estado | ⏳ **Pendiente de la decisión del reviewer** (sección 4) |

> **Cómo se repartió el trabajo.** El reviewer no tiene acceso a una herramienta de IA. Por eso QA preparó con IA la verificación funcional y este checklist, y el reviewer los revisa, decide y pide los cambios que hagan falta. Las decisiones del reviewer se registran como **decisiones humanas** en el AI Log.

## 1. Qué revisar (≈15 min)

| # | Qué | Dónde |
|---|---|---|
| 1 | Resumen del PR y los commits | Pestaña *Conversation* y *Commits* del PR #2 |
| 2 | Revisión de QA con 12 comentarios en línea | Pestaña *Files changed* del PR #2 |
| 3 | Que cada HU cumpla su historia | [`docs/qa/Reporte-QA.md`](../qa/Reporte-QA.md) §5 |
| 4 | Las capturas de la verificación funcional | Sección 2 de este documento |
| 5 | Los hallazgos visuales R-01 y R-02 | Sección 3: decidir si se corrigen ahora |

## 2. Verificación funcional en navegador

Se ejecutó [`scripts/verificacion_funcional.py`](scripts/verificacion_funcional.py) con Chromium sobre un servidor real (BD temporal, `DEFAULT_COUNTRY=PA`). Resultado completo: [`verificacion-funcional-salida.txt`](verificacion-funcional-salida.txt). **14 de 15 comprobaciones pasan**; la que falla es R-02.

| ID | Qué se comprueba | Resultado | Captura |
|---|---|---|---|
| R-1 | QA-03: un servicio llamado `<img src=x onerror=…>` se ve como texto y no ejecuta nada (página pública, panel y auditoría) | ✅ | [R1](capturas/R1-servicio-xss-escapado-escritorio.png) · [panel](capturas/R4-panel-admin-escritorio.png) |
| R-2 | QA-02: el enlace de la confirmación abre la cita… | ✅ | [R2a](capturas/R2a-enlace-confirmacion-antes-del-recordatorio.png) |
| R-2 | …el recordatorio trae un enlace nuevo que funciona… | ✅ | [R2b](capturas/R2b-enlace-recordatorio-funciona.png) |
| R-2 | …y el de la confirmación pasa a «Este enlace ya no es válido» | ✅ | [R2c](capturas/R2c-enlace-confirmacion-ya-no-sirve.png) |
| R-3 | Móvil 390 px: página de autogestión y acceso al panel sin desborde | ✅ | [autogestión](capturas/R3-movil-autogestion.png) · [panel](capturas/R3-movil-admin-login.png) |
| R-3 | Móvil 390 px: página pública | ❌ 425 px de ancho → **R-02** | [index](capturas/R3-movil-index.png) |
| R-4 | Calendario y franjas al elegir un servicio | ✅ | [R4](capturas/R4-calendario-y-franjas-escritorio.png) |
| R-4 | Panel del dueño: reservas, servicios, usuarios y actividad (quién hizo qué) | ✅ | [R4](capturas/R4-panel-admin-escritorio.png) |

## 3. Hallazgos del revisor (para decidir)

| ID | Severidad | Hallazgo | Propuesta | ¿Se corrige ahora? |
|---|---|---|---|---|
| R-01 | Baja (visual) | Un nombre de servicio con una palabra muy larga se sale de su tarjeta en escritorio (captura R1, sexta tarjeta) | `overflow-wrap:anywhere` en `.svc .n` de `index.html` | ☐ Sí ☐ No / issue #1 |
| R-02 | Baja (visual) | En móvil la página pública mide 425 px en una pantalla de 390: aparece desplazamiento horizontal. Ya venía de antes (anotado en `Resultado-HU-4.md`: el resplandor decorativo del encabezado) | `overflow-x:hidden` en `body`, o recortar el resplandor | ☐ Sí ☐ No / issue #1 |
| R-03 | Info | El panel muestra «Precio (CLP)» y montos `$8.000` en un negocio de Panamá. Es la configuración de QA-09 (moneda y zona horaria de Chile) | Ya está en el issue #1 | — |

## 4. Decisión del reviewer

*Lo completa el reviewer. Si pide cambios, se aplican en `qa/revision-historias` con su commit y su test, y esta tabla se actualiza.*

| Pregunta | Respuesta |
|---|---|
| ¿Cada HU cumple su historia? | |
| ¿Se aceptan las desviaciones (HU-5: tabla y endpoints; HU-6: cookie en vez de JWT)? | |
| ¿R-01 y R-02 se corrigen ahora o van al issue #1? | |
| Cambios solicitados | |
| **Veredicto** | ☐ Aprobado ☐ Aprobado con cambios ☐ Cambios requeridos |
| Fecha | |

**En GitHub** (cuenta del reviewer, no hace falta IA): PR #2 → *Files changed* → *Review changes* → escribir el veredicto → **Approve** → *Submit review*. Luego *Merge pull request*.

## Notas de proceso

Al escribir el script, la IA cometió dos errores que se corrigieron antes de entregarlo. Están registrados en el AI Log, caso L:
1. Tomaba el último enlace del log del servidor, que era de otra cita recordada, no de la de prueba.
2. Comparaba el ancho de la página contra `window.innerWidth`, que en modo móvil crece con el contenido; así el desborde de R-02 quedaba oculto.
