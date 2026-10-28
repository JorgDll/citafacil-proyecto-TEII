# Evidencia del trabajo de QA

Salidas reales de las pruebas y capturas de la sesión de IA usada en QA. Cada archivo `.txt` indica en su cabecera el commit probado, la fecha y el comando. El reporte completo está en [`../Reporte-QA.md`](../Reporte-QA.md).

**Código comparado:** el del developer (`a00d137`, último commit de `feature/historias-usuario-v2`) contra la rama `qa/revision-historias` con las correcciones.

## 1. Pruebas automatizadas (pytest)

| Archivo | Qué muestra | Resultado |
|---|---|---|
| [`01-pytest-codigo-developer.txt`](01-pytest-codigo-developer.txt) | Suite del developer sobre su propio código | **26 passed** |
| [`02-regresion-qa-contra-codigo-developer.txt`](02-regresion-qa-contra-codigo-developer.txt) | Los tests de QA (`test_qa_regressions.py`) contra el código **sin** correcciones: prueba que detectan los bugs | **7 failed** (QA-01 ×4, QA-02 ×2, QA-06 ×1) |
| [`03-pytest-rama-qa.txt`](03-pytest-rama-qa.txt) | Suite completa en la rama de QA | **33 passed** |

## 2. Pruebas exploratorias (caja negra, servidor real)

Script: [`scripts/qa_exploratorias.py`](scripts/qa_exploratorias.py), ejecutado con [`scripts/run_exploratorias.sh`](scripts/run_exploratorias.sh). El runner siembra una BD temporal, levanta `uvicorn` y guarda la salida junto con los recordatorios del log del servidor. Cubre la concurrencia y los casos de HU-2, HU-4, HU-5 y HU-6 (≈45 casos).

| Archivo | Resultado |
|---|---|
| [`04-exploratorias-codigo-developer.txt`](04-exploratorias-codigo-developer.txt) | **5 casos fallan.** La reserva a las 10:13 se acepta (QA-01), y por efecto dominó también falla la de las 10:30, que esa cita bloquea. La reprogramación a las 13:07 se acepta (QA-01), lo que consume una reprogramación y descuadra los 2 casos siguientes. Los recordatorios llegan **sin** enlace (QA-02) |
| [`05-exploratorias-rama-qa.txt`](05-exploratorias-rama-qa.txt) | **Sin fallos.** Los recordatorios llegan con enlace de autogestión |

## 3. Concurrencia (QA-06)

Script: [`scripts/qa_concurrencia.py`](scripts/qa_concurrencia.py). Hace 20 rondas, y en cada una lanza 20 reservas simultáneas a una misma franja.

| Archivo | Resultado |
|---|---|
| [`06-concurrencia-codigo-developer.txt`](06-concurrencia-codigo-developer.txt) | **15 de 20 rondas con doble reserva** (hasta 15 citas en la misma franja) |
| [`07-concurrencia-rama-qa.txt`](07-concurrencia-rama-qa.txt) | **0 de 20** |

> La primera prueba de concurrencia de QA dio 1 reserva creada y 19 rechazadas, y se concluyó por error que no había bug. Al repetirla salió a la luz el problema. Está registrado en el AI Log como ejemplo de conclusión incorrecta.

## 3b. Reabrir una cita cancelada (QA-11)

| Archivo | Resultado |
|---|---|
| [`08-qa11-reabrir-cancelada.txt`](08-qa11-reabrir-cancelada.txt) | Con [`scripts/qa11_reabrir_cancelada.py`](scripts/qa11_reabrir_cancelada.py): A cancela, B toma la franja, el dueño reabre A → **2 citas activas en la misma franja**. Queda en el issue de riesgos |

## 4. Capturas de la sesión de IA (Claude Code, Claude Opus 5.5)

| Captura | Qué se ve |
|---|---|
| [`01-ia-pasos-sugeridos-para-qa.png`](capturas-ia/01-ia-pasos-sugeridos-para-qa.png) | Primera revisión: la IA contrasta la rama con el PDF y propone los pasos de QA (PR, AI Log, pruebas manuales pendientes) |
| [`02-ia-detecta-xss-y-planifica-correcciones.png`](capturas-ia/02-ia-detecta-xss-y-planifica-correcciones.png) | La IA busca `innerHTML` sin escapar, detecta el XSS de `index.html:537` (QA-03) y planifica la rama `qa/revision-historias` |
| [`03-ia-correccion-qa01-qa03-diff.png`](capturas-ia/03-ia-correccion-qa01-qa03-diff.png) | Diff de la validación de la grilla (QA-01) y del escape `esc()` (QA-03) |
| [`04-ia-correccion-qa02-rotate-link-diff.png`](capturas-ia/04-ia-correccion-qa02-rotate-link-diff.png) | Diff de `rotate_link` y del enlace en el recordatorio (QA-02) |
| [`05-ia-verificacion-y-recoleccion-ai-log.png`](capturas-ia/05-ia-verificacion-y-recoleccion-ai-log.png) | Verificación de punta a punta (reserva fuera de la grilla → 409; WhatsApp demo) y búsqueda en los docs de los errores de la IA y las decisiones humanas |
| [`06-ia-genera-reporte-qa.png`](capturas-ia/06-ia-genera-reporte-qa.png) | Actualización de `Resultado-HU-5.md` y creación de `docs/qa/Reporte-QA.md` |
| [`07-ia-genera-ai-log-y-pr.png`](capturas-ia/07-ia-genera-ai-log-y-pr.png) | La IA comprueba en el plan de HU-6 quién propuso la cookie en vez de JWT antes de atribuir la decisión, y escribe el AI Log y la descripción del PR |
| [`08-ia-resumen-de-hallazgos.png`](capturas-ia/08-ia-resumen-de-hallazgos.png) | Resumen entregado al humano: QA-01 a QA-03 y entregables (en ese momento eran 32 tests; después se agregó QA-06) |
| [`09-ia-detecta-qa06-doble-reserva.png`](capturas-ia/09-ia-detecta-qa06-doble-reserva.png) | Script de concurrencia y hallazgo de QA-06: hasta 15 reservas por franja. Se sube a severidad alta |

## 5. Revisión en GitHub (Pull Request e issue)

| Elemento | Enlace | Contenido |
|---|---|---|
| Pull Request | [#2 — HU-1 a HU-6 + correcciones de QA](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2) | `qa/revision-historias` → `main`, con la descripción de [`../Pull-Request.md`](../Pull-Request.md) |
| Revisión de QA | [Review en el PR #2](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2#pullrequestreview-5690040938) | Veredicto, tabla antes/después y **12 comentarios en línea** sobre las correcciones (QA-01, 02, 03, 06) y los riesgos abiertos (QA-07, 08, 09, 11) |
| Issue de riesgos | [#1](https://github.com/JorgDll/citafacil-proyecto-TEII/issues/1) | QA-06 con varios workers, QA-07 a QA-11, con evidencia y propuesta para cada uno |

GitHub no permite aprobar un PR propio, así que la revisión de QA queda como *comentario*. La **aprobación** corresponde al reviewer (tercer integrante del grupo).

## Cómo reproducir

```bash
cd backend
python -m pytest -v                                              # 33 passed
PYTHON=.venv/bin/python ../docs/qa/evidencia/scripts/run_exploratorias.sh . /tmp/salida.txt
```

Para la concurrencia: levantar el servidor y ejecutar `BASE_URL=http://localhost:8000 python docs/qa/evidencia/scripts/qa_concurrencia.py 20`.
