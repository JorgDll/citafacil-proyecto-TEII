"""Utilidades: validación de teléfono chileno y manejo de fechas locales."""
from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

from .config import settings


class PhoneError(ValueError):
    """Error de validación de número telefónico."""


def normalize_cl_phone(raw: str) -> str:
    """Normaliza un celular chileno a formato E.164 (+569XXXXXXXX).

    Acepta entradas como:
        "+56 9 4291 6570", "56942916570", "9 4291 6570",
        "942916570", "+569 4291 6570"
    """
    digits = re.sub(r"[^\d]", "", raw or "")
    if digits.startswith("56"):          # prefijo país
        digits = digits[2:]
    if digits.startswith("0"):           # 0 de larga distancia
        digits = digits[1:]
    if len(digits) == 8:                 # faltó el 9 inicial del móvil
        digits = "9" + digits
    if len(digits) != 9 or not digits.startswith("9"):
        raise PhoneError(
            "Número de celular chileno inválido. Usa el formato +56 9 XXXX XXXX."
        )
    return "+56" + digits


def format_cl_phone(e164: str) -> str:
    """Formatea +56912345678 -> '+56 9 1234 5678' para mostrar."""
    d = e164.replace("+56", "")
    if len(d) == 9:
        return f"+56 {d[0]} {d[1:5]} {d[5:]}"
    return e164


# ---------- Teléfonos internacionales (E.164) ----------
MSG_PHONE_INVALID = "Número de teléfono inválido para el país seleccionado."
MSG_PHONE_MOBILE_ONLY = "Solo se aceptan números móviles (los recordatorios se envían por WhatsApp)."
# FIXED_LINE_OR_MOBILE: en países como EE. UU. o Canadá la numeración móvil y fija
# comparte rangos y no se puede distinguir, así que se admite.
MOBILE_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}
_ALLOWED_CHARS = re.compile(r"^[+\d\s().\-/]+$")   # sin letras (libphonenumber las traduce a dígitos)


def normalize_phone(raw: str, region: Optional[str] = None) -> str:
    """Valida un celular de cualquier país y lo devuelve en formato E.164.

    - Con prefijo "+" (o "00" del país base) se identifica el país por el número.
    - Sin prefijo se interpreta en `region` (por defecto `settings.default_country`);
      para Chile se mantiene la regla lenient anterior (`normalize_cl_phone`).
    - Solo se aceptan móviles: el sistema avisa por WhatsApp.
    """
    text = (raw or "").strip()
    region = (region or settings.default_country).upper()
    if not text or not _ALLOWED_CHARS.match(text):
        raise PhoneError(MSG_PHONE_INVALID)
    if not text.startswith("+") and region == "CL":
        return normalize_cl_phone(text)
    try:
        number = phonenumbers.parse(text, None if text.startswith("+") else region)
    except NumberParseException:
        raise PhoneError(MSG_PHONE_INVALID)
    if not phonenumbers.is_valid_number(number):
        raise PhoneError(MSG_PHONE_INVALID)
    if phonenumbers.number_type(number) not in MOBILE_TYPES:
        raise PhoneError(MSG_PHONE_MOBILE_ONLY)
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def phone_parts(e164: str) -> tuple[Optional[str], str]:
    """(ISO del país, número nacional) de un E.164, para repoblar el selector."""
    try:
        number = phonenumbers.parse(e164, None)
    except NumberParseException:
        return None, re.sub(r"\D", "", e164 or "")
    return phonenumbers.region_code_for_number(number), phonenumbers.national_significant_number(number)


def mask_phone(e164: str) -> str:
    """'+50761234567' -> '+507 ****4567' (para quien no puede ver teléfonos completos)."""
    try:
        number = phonenumbers.parse(e164, None)
        return f"+{number.country_code} ****{str(number.national_number)[-4:]}"
    except NumberParseException:
        return "****" + (e164 or "")[-4:]


@lru_cache(maxsize=1)
def list_countries() -> tuple[dict, ...]:
    """Países soportados: ISO, código de marcación y un móvil de ejemplo (sin el código)."""
    countries = []
    for iso in sorted(phonenumbers.SUPPORTED_REGIONS):
        dial = phonenumbers.country_code_for_region(iso)
        sample = phonenumbers.example_number_for_type(iso, PhoneNumberType.MOBILE) or phonenumbers.example_number(iso)
        example = ""
        if sample is not None:
            # Formato internacional sin "+<código>": siempre es un número que, compuesto
            # con el código, valida (el nacional puede incluir prefijos locales como "0" o "15").
            intl = phonenumbers.format_number(sample, PhoneNumberFormat.INTERNATIONAL)
            example = intl.split(" ", 1)[1] if " " in intl else ""
        if example:
            try:
                normalize_phone(f"+{dial} {example}")
            except PhoneError:
                example = ""        # sin ejemplo fiable (p. ej. territorios con numeración atípica)
        countries.append({"iso": iso, "dial_code": str(dial), "example": example})
    return tuple(countries)


def local_now() -> datetime:
    """Hora actual del negocio (naive, en la zona horaria configurada)."""
    return datetime.now(ZoneInfo(settings.business_timezone)).replace(tzinfo=None)


def to_local_naive(dt: datetime) -> datetime:
    """Convierte un datetime con zona a hora local naive; deja los naive igual."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo(settings.business_timezone)).replace(tzinfo=None)
    return dt
