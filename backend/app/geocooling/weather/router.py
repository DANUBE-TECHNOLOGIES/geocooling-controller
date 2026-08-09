from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.geocooling.weather.service import (
    WeatherConfigurationError,
    WeatherProviderError,
    weather_service,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(
    prefix="/geocooling/weather",
    tags=["GeoCooling Weather Intelligence"],
)


@router.get("")
async def get_weather(
    refresh: bool = Query(
        default=False,
        description="Force le rafraîchissement du cache fournisseur.",
    ),
) -> dict[str, Any]:
    """
    Conditions actuelles et prévisions météo normalisées.

    Cette route est strictement en lecture seule et ne déclenche aucune
    commande matérielle ni aucune décision du Brain.
    """

    try:
        return await weather_service.get_weather(
            force_refresh=refresh,
        )
    except WeatherConfigurationError as exc:
        LOGGER.error("Configuration météo invalide : %s", exc)

        raise HTTPException(
            status_code=503,
            detail={
                "code": "weather_configuration_error",
                "message": str(exc),
            },
        ) from exc
    except WeatherProviderError as exc:
        LOGGER.warning("Fournisseur météo indisponible : %s", exc)

        raise HTTPException(
            status_code=502,
            detail={
                "code": "weather_provider_error",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        LOGGER.exception("Erreur Weather Intelligence inattendue")

        raise HTTPException(
            status_code=500,
            detail={
                "code": "weather_internal_error",
                "message": str(exc),
            },
        ) from exc


@router.get("/health")
async def get_weather_health() -> JSONResponse:
    """
    État local du service météo.

    Ne contacte pas le fournisseur et ne modifie pas le cache.
    """

    return JSONResponse(
        content=weather_service.health(),
        headers={
            "Cache-Control": "no-store",
        },
    )
