# Entrega — Proyecto #1 (Tópicos Especiales II)

**Desarrollo asistido por IA con herramientas de escritorio** · Prof. Regis Rivera

| | |
|---|---|
| Aplicación elegida | CitaFácil (opción 4: HTML/CSS/JS · FastAPI + SQLAlchemy + Pydantic · SQLite/PostgreSQL) |
| Repositorio | https://github.com/JorgDll/citafacil-proyecto-TEII |
| Herramienta de IA | Claude Code (CLI de escritorio): Claude Sonnet 5.5 para el desarrollo y Claude Opus 5.5 para QA |
| Roles | Developer: JorgDll · QA: Chrisvlj · Reviewer: [nombre del reviewer] |

## Restricciones del proyecto → dónde se demuestran

| # | Restricción del enunciado | Evidencia |
|---|---|---|
| 1 | Repositorio Git | Este repositorio |
| 2 | Issues o historias de usuario | [`docs/historias-de-usuario/HU-v2.md`](docs/historias-de-usuario/HU-v2.md) (6 HU en formato *como / quiero / para*) y un `Plan-HU-x.md` + `Resultado-HU-x.md` por HU · [Issue #1](https://github.com/JorgDll/citafacil-proyecto-TEII/issues/1) (riesgos abiertos) |
| 3 | Commits identificables | Un commit por HU (`feat(HU-1)` … `feat(HU-6)`) y uno por hallazgo de QA (`fix(QA-01)` … `fix(QA-06)`), con `Co-Authored-By` de la IA |
| 4 | Uso de ramas | `feature/historias-usuario-v2` (developer) → `qa/revision-historias` (QA) → `main` |
| 5 | Pull Request o revisión equivalente | [PR #2](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2), con la [revisión de QA](https://github.com/JorgDll/citafacil-proyecto-TEII/pull/2#pullrequestreview-5690040938) (12 comentarios en línea) y la aprobación del reviewer · [`docs/qa/Pull-Request.md`](docs/qa/Pull-Request.md) |
| 6 | Pruebas automatizadas | 33 tests de pytest en [`backend/tests/`](backend/tests/), incluidos 7 de regresión de QA · salidas en [`docs/qa/evidencia/`](docs/qa/evidencia/README.md) |
| 7 | Evidencia del uso de IA | [`docs/AI-Development-Log.md`](docs/AI-Development-Log.md) · planes y resultados por HU escritos con la IA · [capturas de la sesión](docs/qa/evidencia/capturas-ia/) |
| 8 | Ejemplos de respuestas incorrectas de la IA | [AI Log §2](docs/AI-Development-Log.md#2-ejemplos-de-respuestas-incorrectas-de-la-ia): casos A a K |
| 9 | Cambios que se rechazaron de la IA | [AI Log §3](docs/AI-Development-Log.md#3-cambios-de-la-ia-que-se-rechazaron-o-modificaron) |
| 10 | Decisiones tomadas por humanos | [AI Log §4](docs/AI-Development-Log.md#4-decisiones-tomadas-por-humanos) · «Decisiones del usuario» en cada `Plan-HU-x.md` |

## Historias de usuario

| HU | Historia | Tipo | Resultado |
|---|---|---|---|
| HU-1 | Reservar con mis datos guardados | Obligatoria | [Resultado](docs/historias-de-usuario/HU-1/Resultado-HU-1.md) |
| HU-2 | Calendario dinámico con días disponibles y ocupados | Obligatoria | [Resultado](docs/historias-de-usuario/HU-2/Resultado-HU-2.md) |
| HU-3 | Gráficos de previsión de la demanda | Obligatoria | [Resultado](docs/historias-de-usuario/HU-3/Resultado-HU-3.md) |
| HU-4 | Teléfonos internacionales | Propia | [Resultado](docs/historias-de-usuario/HU-4/Resultado-HU-4.md) |
| HU-5 | Autogestión de la cita por enlace | Propia | [Resultado](docs/historias-de-usuario/HU-5/Resultado-HU-5.md) |
| HU-6 | Cuentas con roles y registro de actividad | Propia | [Resultado](docs/historias-de-usuario/HU-6/Resultado-HU-6.md) |

Validación de cada HU contra sus criterios de aceptación: [`docs/qa/Reporte-QA.md`](docs/qa/Reporte-QA.md).

## Material de presentación

Presentación de 12 diapositivas con notas del orador y guion: [`docs/presentacion/`](docs/presentacion/README.md) (PDF y PPTX).

## Cómo ejecutar

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # Python 3.10 a 3.12
pip install -r requirements.txt
python -m pytest -q                                     # 33 passed
cp .env.example .env                                    # cambiar ADMIN_TOKEN
python seed.py && python seed_history.py
uvicorn app.main:app --reload                           # http://localhost:8000/app/
```

El primer acceso a `/app/admin.html` pide crear al propietario, usando `ADMIN_TOKEN` como clave de instalación.
