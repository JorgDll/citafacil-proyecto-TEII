# Resultado HU-4 — Teléfonos internacionales (E.164) con selector de país

**Historia:** Como dueño del sistema en Panamá, quiero que mis clientes puedan usar más números telefónicos para que los mensajes de WhatsApp se entreguen a cualquier cliente, sin importar su número.

**Rama:** `feature/historias-usuario-v2` · **Plan:** `Plan-HU-4.md`

## Decisiones
- `customer_phone` sigue siendo un string E.164 (sin migración; los números chilenos ya guardados siguen siendo válidos) y el contrato de la API no cambia: se envía un solo `customer_phone`.
- Validación con `phonenumbers==9.0.42` (nueva dependencia): número válido **y móvil** (`MOBILE` o `FIXED_LINE_OR_MOBILE`). Se rechazan fijos, gratuitos, de tarifa premium y VoIP porque el sistema avisa por WhatsApp. `FIXED_LINE_OR_MOBILE` se admite porque en EE. UU. y Canadá la numeración móvil y fija comparte rangos.
- Sin `+`, el número se interpreta con `DEFAULT_COUNTRY` (por defecto `CL`, que conserva la regla chilena anterior; `.env.example` sugiere `PA`).
- Banderas con flag-icons 7.2.3 por CDN (en Windows los emojis de bandera no se dibujan). Los nombres de país salen de `Intl.DisplayNames` (es y en), así no hay datos que mantener.

## Cambios
**Nuevos:** `backend/tests/test_phone_international.py`, `docs/historias-de-usuario/HU-4/`.

**Modificados:**
- `backend/app/utils.py`: `normalize_phone`, `phone_parts`, `list_countries`.
- `backend/app/config.py` y `backend/.env.example`: `DEFAULT_COUNTRY` (validado contra las regiones soportadas).
- `backend/app/schemas.py`: validadores con `normalize_phone`; `ConfigOut.default_country`; `CountryOut`; `DeviceProfileOut.phone_country` y `phone_national`.
- `backend/app/routers/public.py`: `GET /api/countries`.
- `backend/requirements.txt`: `phonenumbers==9.0.42`.
- `frontend/index.html`: selector de país + campo del número; mensajes de error legibles para los 422.
- `backend/tests/test_device_profile.py`: un assert dejó de comparar el JSON completo (el perfil ahora trae dos campos más).
- `README.md`, `docs/Proyect-doc.md`.

## Selector de país
- Botón: `+507 | bandera | PA`. Cada fila repite ese formato y añade el nombre en gris (extra para confirmar el resultado de una búsqueda).
- La búsqueda no depende de que el ISO sean las primeras letras del nombre: encuentra por nombre en español o inglés (`alemania`/`germany` → DE, `japon` → JP, `corea` → KR y KP), por ISO (`PA`) y por código (`507`, `+507`), sin distinguir tildes. Orden: ISO/código exacto, nombre que empieza por, palabra, resto.
- Teclado: ↑/↓, Enter, Esc, Tab; ARIA combobox/listbox; clic fuera cierra.
- **Placeholder por país**: muestra un móvil de ejemplo con el formato y la longitud locales (Panamá `6123-4567`, EE. UU. `201-555-0123`, España `612 34 56 78`, Japón `90-1234-5678`). El servidor solo publica el ejemplo si realmente valida; de los 245 países solo `TA` quedó sin ejemplo.
- Se envía `+<código> <número>`; el servidor quita espacios y el `0` de marcación local. Un número pegado con `+` o `00` se envía completo.
- HU-1: al prellenar desde el dispositivo se restauran país y número; "Usar otros datos" vuelve al país base.

## API
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/countries` | `[{iso, dial_code, example}]` (245 países) |
| GET | `/api/config` | incluye `default_country` |

## Pruebas
`python -m pytest` (desde `backend/`): **19 pasan** (16 previos + 3 nuevos).

| Test | Cubre |
|---|---|
| `test_happy_path_international_booking_countries_and_examples` | Reserva `+507 6123-4567` → `+50761234567`; `/countries` y `/config`; el ejemplo de 8 países compuesto con su código valida |
| `test_edge_only_mobile_numbers_and_invalid_input_are_rejected` | Fijos de PA/CL/ES/DE, gratuito y premium → 422 sin crear cita; longitud incorrecta, letras y vacío; formatos equivalentes dan el mismo E.164 |
| `test_edge_default_country_shared_dial_codes_and_profile_split` | `DEFAULT_COUNTRY` PA y CL; `+1` de EE. UU. y Canadá se distinguen; el perfil de dispositivo devuelve `PA` + `61234567` |

Verificación manual en navegador (BD temporal, `DEFAULT_COUNTRY=PA`): banderas SVG visibles; el selector arranca en Panamá; placeholder distinto para CL, US, ES, DE, BR, AR y JP; búsquedas por nombre, ISO y código; Enter elige y pasa el foco al número; un fijo de Japón y un número con letras se rechazan con mensaje legible; una reserva con móvil japonés se guarda como `+819012345678`; tras guardar el dispositivo y recargar, el país JP y el número se restauran.

## Limitaciones conocidas
- La validación no puede saber si un móvil tiene WhatsApp. En países con rangos compartidos (EE. UU., Canadá…) un fijo puede pasar como `FIXED_LINE_OR_MOBILE`.
- `is_valid_number` depende de los metadatos de la librería; un número muy reciente podría rechazarse hasta actualizarla.
- Las banderas necesitan internet (CDN) y los nombres un navegador moderno (`Intl.DisplayNames`); sin ellos el selector sigue funcionando con ISO y código.
- La zona horaria y la moneda siguen siendo de Chile por defecto (fuera de esta HU).
- En el panel admin el teléfono se muestra tal como está guardado (E.164).
- No probado con teclado físico (solo eventos simulados) ni en un móvil real; en 375 px el panel cabe en pantalla. La página ya tenía ~35 px de desbordamiento horizontal por el resplandor decorativo del encabezado (anterior a esta HU).
