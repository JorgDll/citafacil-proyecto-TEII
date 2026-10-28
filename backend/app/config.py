"""Configuración de la aplicación mediante variables de entorno.

Todas las opciones se pueden sobreescribir con variables de entorno o con un
archivo `.env` (ver `.env.example`). Así el mismo código corre en local (SQLite)
y en producción (PostgreSQL en Render) sin tocar nada.
"""
from __future__ import annotations

import phonenumbers
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Negocio / marca ---
    business_name: str = "Barbería Don Lucho"
    business_timezone: str = "America/Santiago"
    currency: str = "CLP"
    # País base (ISO 3166-1 alpha-2): interpreta números sin "+" y preselecciona el selector.
    default_country: str = "CL"
    open_hour: int = 10          # apertura (hora local, 24h)
    close_hour: int = 20         # cierre (hora local, 24h)
    slot_interval_minutes: int = 30
    # Días cerrados: 0=lunes ... 6=domingo. Por defecto cierra domingo.
    closed_weekdays: str = "6"

    # --- Base de datos ---
    # En local: SQLite. En producción, define DATABASE_URL (PostgreSQL).
    database_url: str = "sqlite:///./citafacil.db"

    # --- Seguridad ---
    admin_token: str = "cambia-este-token-admin"
    cors_origins: str = "*"      # separado por comas, o "*" para todos

    # --- Cuentas del panel de administración (HU-6) ---
    staff_cookie_name: str = "citafacil_admin"
    session_hours: int = 12             # duración fija de la sesión
    login_max_attempts: int = 5         # fallos seguidos antes de bloquear la cuenta
    login_lock_minutes: int = 15
    password_min_length: int = 10

    # --- Autogestión de la cita por el cliente (HU-5) ---
    # URL pública de la app: base del enlace que llega por WhatsApp.
    public_base_url: str = "http://localhost:8000"
    manage_cutoff_hours: int = 2        # anticipación mínima para cancelar/reprogramar
    manage_max_reschedules: int = 2     # reprogramaciones permitidas por cita

    # --- Dispositivo recordado (cookie HttpOnly) ---
    device_cookie_name: str = "citafacil_device"
    device_cookie_days: int = 365
    cookie_secure: bool = False   # true solo si se sirve por HTTPS

    # --- Twilio / WhatsApp ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""      # ej: "whatsapp:+14155238886"
    reminder_hours_before: int = 24     # cuántas horas antes recordar
    reminder_poll_minutes: int = 15     # cada cuánto revisa el programador

    @field_validator("default_country")
    @classmethod
    def _valid_country(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in phonenumbers.SUPPORTED_REGIONS:
            raise ValueError(f"DEFAULT_COUNTRY inválido: {v!r}. Usa un código ISO de país (ej. PA, CL, US).")
        return v

    # --- Helpers derivados ---
    @property
    def closed_weekdays_set(self) -> set[int]:
        return {int(x) for x in self.closed_weekdays.split(",") if x.strip() != ""}

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def twilio_enabled(self) -> bool:
        """True solo si están las 3 credenciales de Twilio."""
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_whatsapp_from
        )


settings = Settings()
