"""Análisis de demanda para el panel admin (HU-3): barras, líneas y proyección."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import analytics, schemas
from ..auth import require_permission
from ..database import get_db

router = APIRouter(
    prefix="/api/admin/analytics",
    tags=["Análisis"],
    dependencies=[Depends(require_permission("analytics.view"))],
)


def _ids(raw: Optional[str]) -> Optional[list[int]]:
    if not raw or not raw.strip():
        return None
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="service_ids debe ser una lista de enteros separada por comas.")


def _range(
    preset: Optional[str] = Query(None, alias="range", description="7d, 14d, 30d, 90d, 180d o 365d"),
    date_from: Optional[date] = Query(None, alias="from", description="Inicio (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, alias="to", description="Fin (YYYY-MM-DD)"),
) -> tuple[date, date]:
    try:
        return analytics.resolve_range(preset, date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/services", response_model=schemas.ServiceCountsOut, summary="Reservas por servicio (barras)")
def services_chart(
    rng: tuple[date, date] = Depends(_range),
    service_ids: Optional[str] = Query(None, description="IDs separados por comas; vacío = todos"),
    db: Session = Depends(get_db),
):
    return analytics.counts_by_service(db, rng[0], rng[1], _ids(service_ids))


@router.get("/trend", response_model=schemas.TrendOut, summary="Reservas en el tiempo por servicio (líneas)")
def trend_chart(
    rng: tuple[date, date] = Depends(_range),
    service_ids: Optional[str] = Query(None, description="IDs separados por comas; vacío = todos"),
    group_by: Optional[str] = Query(None, description="day, week o month (por defecto según el rango)"),
    db: Session = Depends(get_db),
):
    try:
        return analytics.trend(db, rng[0], rng[1], _ids(service_ids), group_by)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/forecast", response_model=schemas.ForecastOut, summary="Proyección de la demanda")
def forecast_chart(
    horizon: int = Query(30, description="Días a proyectar: 14, 30 o 90"),
    service_ids: Optional[str] = Query(None, description="IDs separados por comas; vacío = todos"),
    db: Session = Depends(get_db),
):
    if horizon not in analytics.HORIZONS:
        raise HTTPException(status_code=422, detail=f"horizon debe ser uno de {list(analytics.HORIZONS)}.")
    return analytics.forecast(db, horizon, _ids(service_ids))
