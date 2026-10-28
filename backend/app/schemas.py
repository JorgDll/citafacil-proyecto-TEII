"""Esquemas Pydantic (validación de entrada/salida de la API)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import VALID_STATUSES
from .utils import PhoneError, normalize_phone, phone_parts, to_local_naive


# ---------- Servicios ----------
class ServiceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    duration_min: int = Field(30, ge=5, le=480)
    price: int = Field(0, ge=0)
    active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    duration_min: Optional[int] = Field(None, ge=5, le=480)
    price: Optional[int] = Field(None, ge=0)
    active: Optional[bool] = None


class ServiceOut(ServiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Citas ----------
class AppointmentCreate(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=120)
    customer_phone: str = Field(..., examples=["+56 9 4291 6570"])
    service_id: int
    start_at: datetime = Field(..., description="Inicio de la cita (ISO 8601)")
    notes: str = Field("", max_length=300)

    @field_validator("customer_phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except PhoneError as e:
            raise ValueError(str(e))

    @field_validator("start_at")
    @classmethod
    def _naive_local(cls, v: datetime) -> datetime:
        return to_local_naive(v)


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_name: str
    customer_phone: str
    service_id: int
    start_at: datetime
    end_at: datetime
    status: str
    notes: str
    reminder_sent: bool
    created_at: datetime
    service: Optional[ServiceOut] = None


# ---------- Dispositivo recordado (HU-1) ----------
class DeviceProfileIn(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=120)
    customer_phone: str = Field(..., examples=["+56 9 4291 6570"])

    @field_validator("customer_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("customer_phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except PhoneError as e:
            raise ValueError(str(e))


class DeviceProfileOut(BaseModel):
    known: bool
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    phone_country: Optional[str] = None     # ISO del país del celular (repuebla el selector)
    phone_national: Optional[str] = None    # número sin código de país
    detail: Optional[str] = None

    @model_validator(mode="after")
    def _split_phone(self):
        if self.customer_phone and not self.phone_country:
            self.phone_country, self.phone_national = phone_parts(self.customer_phone)
        return self


class AppointmentCreatedOut(AppointmentOut):
    """Respuesta de crear una cita: añade el enlace personal (sólo se conoce en este momento)."""

    manage_url: Optional[str] = None


# ---------- Autogestión de la cita (HU-5) ----------
CANCEL_PHRASE = "cancelar cita"


class ManageOut(BaseModel):
    business_name: str
    service_name: str
    service_duration_min: int
    service_price: int
    start_at: datetime
    end_at: datetime
    status: str
    customer_first_name: str
    can_cancel: bool
    can_reschedule: bool
    reason: Optional[str] = None
    reschedules_left: int
    cutoff_hours: int


class RescheduleIn(BaseModel):
    start_at: datetime = Field(..., description="Nuevo inicio de la cita (ISO 8601)")

    @field_validator("start_at")
    @classmethod
    def _naive_local(cls, v: datetime) -> datetime:
        return to_local_naive(v)


class CancelIn(BaseModel):
    # Obligatorio (sin valor por defecto): los validadores no corren sobre defaults, así
    # que un cuerpo vacío `{}` habría saltado la confirmación.
    confirmation: str = Field(..., description='Debe ser el texto "Cancelar cita"')

    @field_validator("confirmation")
    @classmethod
    def _must_type_phrase(cls, v: str) -> str:
        # Sin distinguir mayúsculas ni espacios sobrantes, pero el texto debe coincidir.
        if " ".join((v or "").split()).casefold() != CANCEL_PHRASE:
            raise ValueError("Escribe «Cancelar cita» para confirmar.")
        return v


class AppointmentStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"Estado inválido. Debe ser uno de: {sorted(VALID_STATUSES)}")
        return v


# ---------- Disponibilidad (HU-2) ----------
class SlotOut(BaseModel):
    time: str
    available: bool
    reason: Optional[str] = None   # None | "past" | "booked"


class DayOut(BaseModel):
    date: str
    status: str                    # past | closed | full | available
    free: int


# ---------- Análisis de demanda (HU-3) ----------
class ServiceCountOut(BaseModel):
    service_id: int
    name: str
    count: int


class ServiceCountsOut(BaseModel):
    start: str
    end: str
    total: int
    items: list[ServiceCountOut]


class SeriesOut(BaseModel):
    service_id: int
    name: str
    counts: list[int]


class TrendOut(BaseModel):
    start: str
    end: str
    group_by: str
    labels: list[str]
    series: list[SeriesOut]


class HistoryPoint(BaseModel):
    date: str
    count: int


class ForecastPoint(BaseModel):
    date: str
    expected: float
    lower: float
    upper: float


class ForecastOut(BaseModel):
    enough_data: bool
    message: Optional[str] = None
    horizon: int
    method: str
    trend_per_week: float
    expected_total: float
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]


# ---------- Cuentas del panel y actividad (HU-6) ----------
import re as _re  # noqa: E402

_USERNAME_RE = _re.compile(r"^[a-z0-9._-]{3,32}$")


def _clean_username(v: str) -> str:
    v = (v or "").strip().lower()
    if not _USERNAME_RE.match(v):
        raise ValueError("Usuario inválido: 3 a 32 caracteres entre letras minúsculas, números, punto, guion y guion bajo.")
    return v


class LoginIn(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=200)


class SetupIn(BaseModel):
    setup_token: str = Field(..., max_length=200)
    username: str
    display_name: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., max_length=200)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return _clean_username(v)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(..., max_length=200)


class MeOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    role_label: str
    permissions: list[str]
    must_change_password: bool


class StaffUserOut(MeOut):
    active: bool
    locked: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class StaffUserCreate(BaseModel):
    username: str
    display_name: str = Field(..., min_length=2, max_length=80)
    role: str
    permissions: Optional[list[str]] = None      # None = los del rol
    password: str = Field(..., max_length=200)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return _clean_username(v)


class StaffUserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=80)
    role: Optional[str] = None
    permissions: Optional[list[str]] = None
    active: Optional[bool] = None


class AuditItemOut(BaseModel):
    id: int
    created_at: datetime
    actor_type: str
    user_id: Optional[int] = None
    actor_name: str
    action: str
    entity: str
    entity_id: Optional[int] = None
    detail: dict
    ip: str


class AuditPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditItemOut]


# ---------- Otros ----------
class CountryOut(BaseModel):
    iso: str
    dial_code: str
    example: str = ""


class ConfigOut(BaseModel):
    business_name: str
    default_country: str
    timezone: str
    currency: str
    open_hour: int
    close_hour: int
    slot_interval_minutes: int
    closed_weekdays: list[int]


class StatsOut(BaseModel):
    total: int
    pending: int
    confirmed: int
    cancelled: int
    done: int
    upcoming: int


class MessageOut(BaseModel):
    detail: str
