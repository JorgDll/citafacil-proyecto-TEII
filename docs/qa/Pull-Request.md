# Pull Request: Historias de usuario HU-1 a HU-6 + correcciones de QA

**Rama origen:** `qa/revision-historias` (incluye todo `feature/historias-usuario-v2`)
**Rama destino:** `main`

Este archivo es la descripción del PR y la revisión equivalente que pide el enunciado.

## Resumen

Sprint de 6 historias de usuario sobre CitaFácil:

| Commit | HU / cambio | Autor |
|---|---|---|
| `93be19c` | HU-1: reserva rápida con datos recordados por dispositivo | Developer |
| `b136cbf` | HU-2: calendario mensual y franjas horarias con estado | Developer |
| `df586e5` | HU-3: histórico y proyección de demanda en el panel admin | Developer |
| `7d2e317` | HU-4: teléfonos internacionales E.164 con selector de país | Developer |
| `83a5db4` | fix(tests): aislar la suite de `backend/.env` | Developer |
| `8a4e4ff` | HU-5: autogestión de la cita desde un enlace personal | Developer |
| `5bffc4b` | chore: quitar log de Playwright del repo | Developer |
| `a00d137` | HU-6: cuentas de administración con permisos y registro de actividad | Developer |
| QA | fix(QA-01): solo inicios de la grilla en `is_slot_free` | QA |
| QA | fix(QA-02): enlace de autogestión en el recordatorio | QA |
| QA | fix(QA-03): escapar el nombre del servicio en `index.html` | QA |
| QA | test(QA): regresiones de QA-01 y QA-02 | QA |
| QA | docs(QA): reporte de QA, AI Development Log y descripción del PR | QA |
| QA | fix(QA-06): impedir doble reserva con peticiones simultáneas | QA |
| QA | test(QA-06): 5 rondas de concurrencia | QA |
| QA | docs(QA): evidencias, capturas de IA y AI Log actualizado | QA |

## Cambio incompatible

`X-Admin-Token` ya no abre la API admin (HU-6). Después de fusionar, hay que crear al propietario desde el panel (`/app/admin.html`) con `ADMIN_TOKEN` como clave de instalación, o con `python manage_users.py`.

## Cómo probar

```bash
cd backend
uv venv --python 3.12 .venv && source .venv/bin/activate   # Python 3.10–3.12
pip install -r requirements.txt
python -m pytest -q                 # 33 passed
python seed.py && python seed_history.py
uvicorn app.main:app --reload       # http://localhost:8000/app/
```

## Checklist de revisión (QA)

- [x] Cada HU tiene plan, resultado y tests (`docs/historias-de-usuario/HU-x/`)
- [x] La suite completa pasa (33/33)
- [x] Cada bug encontrado en QA tiene un test que falla sin la corrección
- [x] Criterios de aceptación revisados uno por uno (`docs/qa/Reporte-QA.md` §5)
- [x] Desviaciones respecto a las HU justificadas (HU-5: tabla y endpoints; HU-6: cookie en vez de JWT)
- [x] Sin secretos en el repo (`.env` ignorado; `ADMIN_TOKEN` por defecto rechazado)
- [x] AI Development Log con respuestas incorrectas, cambios rechazados y decisiones humanas (`docs/AI-Development-Log.md`)
- [x] Evidencia de las pruebas y capturas de la sesión de IA (`docs/qa/evidencia/`)
- [ ] Verificación visual pendiente (`Reporte-QA.md` §8): XSS de QA-03 en el navegador, enlace del recordatorio y vista móvil

## Riesgos conocidos (no bloquean)

QA-06 con varios workers (el candado solo protege dentro de un proceso), QA-07 (bloqueo de cuenta por terceros), QA-08 (auditoría fuera de la transacción), QA-09 (zona horaria y moneda de Chile en `.env.example`), QA-10 (`datetime.utcnow` deprecado), QA-11 (reabrir una cita cancelada no comprueba la franja). Detalle en `docs/qa/Reporte-QA.md` §6. Seguimiento en #1.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
