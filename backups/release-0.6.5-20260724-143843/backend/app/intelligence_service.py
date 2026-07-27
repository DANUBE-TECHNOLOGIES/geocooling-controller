import json
import logging
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


logger = logging.getLogger("sbc.intelligence")


INTELLIGENCE_REFRESH_SECONDS = max(
    60,
    int(
        os.getenv(
            "INTELLIGENCE_REFRESH_SECONDS",
            "300",
        )
    ),
)

COMFORT_TARGET_TEMPERATURE = float(
    os.getenv(
        "COMFORT_TARGET_TEMPERATURE",
        "22.5",
    )
)

COMFORT_MAX_TEMPERATURE = float(
    os.getenv(
        "COMFORT_MAX_TEMPERATURE",
        "24.0",
    )
)

COMFORT_MIN_TEMPERATURE = float(
    os.getenv(
        "COMFORT_MIN_TEMPERATURE",
        "20.0",
    )
)

CONDENSATION_MARGIN_C = float(
    os.getenv(
        "CONDENSATION_MARGIN_C",
        "2.0",
    )
)

GECOOLING_ESTIMATED_RATE = float(
    os.getenv(
        "GECOOLING_ESTIMATED_RATE",
        "-0.35",
    )
)

THERMAL_MODEL_MIN_SAMPLES = max(
    12,
    int(
        os.getenv(
            "THERMAL_MODEL_MIN_SAMPLES",
            "36",
        )
    ),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def average(values: list[float | None]) -> float | None:
    usable = [
        float(value)
        for value in values
        if value is not None
    ]

    if not usable:
        return None

    return sum(usable) / len(usable)


def calculate_dew_point(
    temperature: float | None,
    humidity: float | None,
) -> float | None:
    if (
        temperature is None
        or humidity is None
        or humidity <= 0
        or humidity > 100
    ):
        return None

    a = 17.62
    b = 243.12

    gamma = (
        math.log(humidity / 100.0)
        + (a * temperature)
        / (b + temperature)
    )

    result = (b * gamma) / (a - gamma)

    return round(result, 3)


def solve_linear_system(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float] | None:
    size = len(vector)

    augmented = [
        matrix[row][:] + [vector[row]]
        for row in range(size)
    ]

    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(
                augmented[row][column]
            ),
        )

        if abs(augmented[pivot][column]) < 1e-12:
            return None

        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column],
        )

        divisor = augmented[column][column]

        augmented[column] = [
            value / divisor
            for value in augmented[column]
        ]

        for row in range(size):
            if row == column:
                continue

            factor = augmented[row][column]

            augmented[row] = [
                augmented[row][index]
                - factor * augmented[column][index]
                for index in range(size + 1)
            ]

    return [
        augmented[index][-1]
        for index in range(size)
    ]


def ridge_regression(
    features: list[list[float]],
    targets: list[float],
    ridge: float = 0.05,
) -> list[float] | None:
    if not features or not targets:
        return None

    columns = len(features[0])

    xtx = [
        [0.0 for _ in range(columns)]
        for _ in range(columns)
    ]

    xty = [0.0 for _ in range(columns)]

    for row, target in zip(features, targets):
        for i in range(columns):
            xty[i] += row[i] * target

            for j in range(columns):
                xtx[i][j] += row[i] * row[j]

    for index in range(columns):
        xtx[index][index] += ridge

    return solve_linear_system(xtx, xty)


class IntelligenceService:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.stop_event = threading.Event()

        self.running = False
        self.last_run_at: str | None = None
        self.last_error: str | None = None
        self.run_count = 0

        self.model_ready = False
        self.model_sample_count = 0
        self.model_confidence = 0.0
        self.latest_recommendation: dict[str, Any] | None = None

    def initialize_database(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS building_state (
                id BIGSERIAL PRIMARY KEY,
                calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                salon_temperature DOUBLE PRECISION,
                etage_temperature DOUBLE PRECISION,
                indoor_temperature DOUBLE PRECISION,
                indoor_humidity DOUBLE PRECISION,
                indoor_dew_point DOUBLE PRECISION,

                outdoor_temperature DOUBLE PRECISION,
                outdoor_humidity DOUBLE PRECISION,
                outdoor_cloud_cover DOUBLE PRECISION,
                outdoor_solar_radiation DOUBLE PRECISION,

                forecast_temperature_h1 DOUBLE PRECISION,
                forecast_temperature_h3 DOUBLE PRECISION,
                forecast_temperature_h6 DOUBLE PRECISION,
                forecast_temperature_h12 DOUBLE PRECISION,

                forecast_solar_h3 DOUBLE PRECISION,
                forecast_solar_h6 DOUBLE PRECISION,

                indoor_outdoor_delta DOUBLE PRECISION,
                temperature_slope_1h DOUBLE PRECISION,
                temperature_slope_3h DOUBLE PRECISION,

                condensation_limit DOUBLE PRECISION,

                geocooling_active BOOLEAN,
                circulation_active BOOLEAN,
                heat_pump_active BOOLEAN,

                data_quality TEXT NOT NULL,
                raw_state JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_building_state_calculated_at
            ON building_state (
                calculated_at DESC
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS thermal_model (
                id BIGSERIAL PRIMARY KEY,
                trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                model_version TEXT NOT NULL,
                sample_count INTEGER NOT NULL,

                intercept DOUBLE PRECISION NOT NULL,
                coefficient_indoor_outdoor_delta
                    DOUBLE PRECISION NOT NULL,
                coefficient_solar_radiation
                    DOUBLE PRECISION NOT NULL,
                coefficient_previous_slope
                    DOUBLE PRECISION NOT NULL,
                coefficient_geocooling
                    DOUBLE PRECISION NOT NULL,

                mean_absolute_error DOUBLE PRECISION,
                confidence DOUBLE PRECISION NOT NULL,

                details JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_thermal_model_trained_at
            ON thermal_model (
                trained_at DESC
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS thermal_predictions (
                id BIGSERIAL PRIMARY KEY,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                horizon_hours INTEGER NOT NULL,

                predicted_temperature_free
                    DOUBLE PRECISION,
                predicted_temperature_geocooling
                    DOUBLE PRECISION,

                comfort_target DOUBLE PRECISION NOT NULL,
                overheating_risk DOUBLE PRECISION NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,

                model_source TEXT NOT NULL,
                details JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_thermal_predictions_generated
            ON thermal_predictions (
                generated_at DESC
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS control_recommendations (
                id BIGSERIAL PRIMARY KEY,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                subsystem TEXT NOT NULL,
                action TEXT NOT NULL,
                priority INTEGER NOT NULL,

                recommended_start_at TIMESTAMPTZ,
                recommended_duration_minutes INTEGER,

                reason TEXT NOT NULL,
                risk_level TEXT NOT NULL,

                automatic_execution BOOLEAN
                    NOT NULL DEFAULT FALSE,

                details JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_control_recommendations_generated
            ON control_recommendations (
                generated_at DESC
            )
            """,
        ]

        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def latest_sensor_value(
        self,
        connection: Any,
        sensor_names: list[str],
        metric: str,
        max_age_minutes: int = 180,
    ) -> float | None:
        row = connection.execute(
            text(
                """
                SELECT value
                FROM sensor_measurements
                WHERE sensor_name = ANY(:sensor_names)
                  AND metric = :metric
                  AND measured_at >=
                      NOW()
                      - (
                          :max_age_minutes
                          * INTERVAL '1 minute'
                      )
                ORDER BY measured_at DESC
                LIMIT 1
                """
            ),
            {
                "sensor_names": sensor_names,
                "metric": metric,
                "max_age_minutes":
                    max_age_minutes,
            },
        ).scalar_one_or_none()

        return safe_float(row)

    def current_weather(
        self,
        connection: Any,
    ) -> dict[str, float | None]:
        row = connection.execute(
            text(
                """
                SELECT
                    temperature,
                    humidity,
                    cloud_cover
                FROM weather_observations
                ORDER BY observed_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()

        if not row:
            return {
                "temperature": None,
                "humidity": None,
                "cloud_cover": None,
            }

        solar = connection.execute(
            text(
                """
                SELECT shortwave_radiation
                FROM weather_forecasts
                WHERE forecast_at >=
                    DATE_TRUNC('hour', NOW())
                ORDER BY forecast_at
                LIMIT 1
                """
            )
        ).scalar_one_or_none()

        return {
            "temperature":
                safe_float(row["temperature"]),
            "humidity":
                safe_float(row["humidity"]),
            "cloud_cover":
                safe_float(row["cloud_cover"]),
            "solar_radiation":
                safe_float(solar),
        }

    def forecast_value(
        self,
        connection: Any,
        hours: int,
        column: str,
    ) -> float | None:
        allowed_columns = {
            "temperature",
            "shortwave_radiation",
        }

        if column not in allowed_columns:
            raise ValueError(
                f"Colonne météo interdite : {column}"
            )

        query = text(
            f"""
            SELECT {column}
            FROM weather_forecasts
            WHERE forecast_at >=
                NOW() + (
                    :hours
                    * INTERVAL '1 hour'
                )
            ORDER BY forecast_at
            LIMIT 1
            """
        )

        value = connection.execute(
            query,
            {"hours": hours},
        ).scalar_one_or_none()

        return safe_float(value)

    def average_forecast_solar(
        self,
        connection: Any,
        hours: int,
    ) -> float | None:
        value = connection.execute(
            text(
                """
                SELECT AVG(shortwave_radiation)
                FROM weather_forecasts
                WHERE forecast_at BETWEEN
                    NOW()
                    AND NOW()
                        + (
                            :hours
                            * INTERVAL '1 hour'
                        )
                """
            ),
            {"hours": hours},
        ).scalar_one_or_none()

        return safe_float(value)

    def historical_indoor_temperature(
        self,
        connection: Any,
        hours_ago: int,
    ) -> float | None:
        value = connection.execute(
            text(
                """
                SELECT indoor_temperature
                FROM building_state
                WHERE calculated_at <=
                    NOW()
                    - (
                        :hours_ago
                        * INTERVAL '1 hour'
                    )
                  AND indoor_temperature IS NOT NULL
                ORDER BY calculated_at DESC
                LIMIT 1
                """
            ),
            {"hours_ago": hours_ago},
        ).scalar_one_or_none()

        return safe_float(value)

    def calculate_slope(
        self,
        current: float | None,
        previous: float | None,
        duration_hours: float,
    ) -> float | None:
        if (
            current is None
            or previous is None
            or duration_hours <= 0
        ):
            return None

        return round(
            (current - previous)
            / duration_hours,
            5,
        )

    def relay_state(
        self,
        connection: Any,
        search_terms: list[str],
    ) -> bool | None:
        rows = connection.execute(
            text(
                """
                SELECT
                    sensor_name,
                    metric,
                    value
                FROM sensor_measurements
                WHERE measured_at >=
                    NOW() - INTERVAL '30 minutes'
                  AND (
                      metric IN (
                          'state',
                          'switch',
                          'running',
                          'on'
                      )
                      OR metric LIKE '%state%'
                  )
                ORDER BY measured_at DESC
                LIMIT 100
                """
            )
        ).mappings().all()

        for row in rows:
            name = str(
                row["sensor_name"]
            ).lower()

            if any(
                term in name
                for term in search_terms
            ):
                value = safe_float(row["value"])

                if value is not None:
                    return value >= 0.5

        return None

    def collect_state(
        self,
        connection: Any,
    ) -> dict[str, Any]:
        salon_temperature = self.latest_sensor_value(
            connection,
            [
                "gc_temp_salon",
                "temp_salon",
                "salon",
            ],
            "temperature",
        )

        etage_temperature = self.latest_sensor_value(
            connection,
            [
                "gc_temp_etage",
                "temp_etage",
                "etage",
            ],
            "temperature",
        )

        indoor_temperature = average(
            [
                salon_temperature,
                etage_temperature,
            ]
        )

        salon_humidity = self.latest_sensor_value(
            connection,
            [
                "gc_temp_salon",
                "gc_humidite_salon",
                "salon",
            ],
            "humidity",
        )

        etage_humidity = self.latest_sensor_value(
            connection,
            [
                "gc_temp_etage",
                "gc_humidite_etage",
                "etage",
            ],
            "humidity",
        )

        indoor_humidity = average(
            [
                salon_humidity,
                etage_humidity,
            ]
        )

        indoor_dew_point = calculate_dew_point(
            indoor_temperature,
            indoor_humidity,
        )

        weather = self.current_weather(
            connection
        )

        outdoor_temperature = weather.get(
            "temperature"
        )

        previous_1h = (
            self.historical_indoor_temperature(
                connection,
                1,
            )
        )

        previous_3h = (
            self.historical_indoor_temperature(
                connection,
                3,
            )
        )

        slope_1h = self.calculate_slope(
            indoor_temperature,
            previous_1h,
            1,
        )

        slope_3h = self.calculate_slope(
            indoor_temperature,
            previous_3h,
            3,
        )

        indoor_outdoor_delta = None

        if (
            indoor_temperature is not None
            and outdoor_temperature is not None
        ):
            indoor_outdoor_delta = round(
                indoor_temperature
                - outdoor_temperature,
                4,
            )

        condensation_limit = None

        if indoor_dew_point is not None:
            condensation_limit = round(
                indoor_dew_point
                + CONDENSATION_MARGIN_C,
                3,
            )

        geocooling_active = self.relay_state(
            connection,
            [
                "geocooling",
                "geo_cooling",
                "geo-cooling",
            ],
        )

        circulation_active = self.relay_state(
            connection,
            [
                "circulateur",
                "circulation",
                "pump",
                "pompe",
            ],
        )

        heat_pump_active = self.relay_state(
            connection,
            [
                "pac",
                "heatpump",
                "heat_pump",
            ],
        )

        forecast_temperature_h1 = (
            self.forecast_value(
                connection,
                1,
                "temperature",
            )
        )

        forecast_temperature_h3 = (
            self.forecast_value(
                connection,
                3,
                "temperature",
            )
        )

        forecast_temperature_h6 = (
            self.forecast_value(
                connection,
                6,
                "temperature",
            )
        )

        forecast_temperature_h12 = (
            self.forecast_value(
                connection,
                12,
                "temperature",
            )
        )

        forecast_solar_h3 = (
            self.average_forecast_solar(
                connection,
                3,
            )
        )

        forecast_solar_h6 = (
            self.average_forecast_solar(
                connection,
                6,
            )
        )

        required_values = [
            indoor_temperature,
            outdoor_temperature,
            forecast_temperature_h3,
        ]

        available_count = sum(
            value is not None
            for value in required_values
        )

        if available_count == len(required_values):
            data_quality = "good"
        elif available_count >= 2:
            data_quality = "partial"
        else:
            data_quality = "insufficient"

        return {
            "salon_temperature":
                salon_temperature,
            "etage_temperature":
                etage_temperature,
            "indoor_temperature":
                indoor_temperature,
            "indoor_humidity":
                indoor_humidity,
            "indoor_dew_point":
                indoor_dew_point,

            "outdoor_temperature":
                outdoor_temperature,
            "outdoor_humidity":
                weather.get("humidity"),
            "outdoor_cloud_cover":
                weather.get("cloud_cover"),
            "outdoor_solar_radiation":
                weather.get("solar_radiation"),

            "forecast_temperature_h1":
                forecast_temperature_h1,
            "forecast_temperature_h3":
                forecast_temperature_h3,
            "forecast_temperature_h6":
                forecast_temperature_h6,
            "forecast_temperature_h12":
                forecast_temperature_h12,

            "forecast_solar_h3":
                forecast_solar_h3,
            "forecast_solar_h6":
                forecast_solar_h6,

            "indoor_outdoor_delta":
                indoor_outdoor_delta,
            "temperature_slope_1h":
                slope_1h,
            "temperature_slope_3h":
                slope_3h,

            "condensation_limit":
                condensation_limit,

            "geocooling_active":
                geocooling_active,
            "circulation_active":
                circulation_active,
            "heat_pump_active":
                heat_pump_active,

            "data_quality":
                data_quality,
        }

    def store_state(
        self,
        connection: Any,
        state: dict[str, Any],
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO building_state (
                    salon_temperature,
                    etage_temperature,
                    indoor_temperature,
                    indoor_humidity,
                    indoor_dew_point,

                    outdoor_temperature,
                    outdoor_humidity,
                    outdoor_cloud_cover,
                    outdoor_solar_radiation,

                    forecast_temperature_h1,
                    forecast_temperature_h3,
                    forecast_temperature_h6,
                    forecast_temperature_h12,

                    forecast_solar_h3,
                    forecast_solar_h6,

                    indoor_outdoor_delta,
                    temperature_slope_1h,
                    temperature_slope_3h,

                    condensation_limit,

                    geocooling_active,
                    circulation_active,
                    heat_pump_active,

                    data_quality,
                    raw_state
                )
                VALUES (
                    :salon_temperature,
                    :etage_temperature,
                    :indoor_temperature,
                    :indoor_humidity,
                    :indoor_dew_point,

                    :outdoor_temperature,
                    :outdoor_humidity,
                    :outdoor_cloud_cover,
                    :outdoor_solar_radiation,

                    :forecast_temperature_h1,
                    :forecast_temperature_h3,
                    :forecast_temperature_h6,
                    :forecast_temperature_h12,

                    :forecast_solar_h3,
                    :forecast_solar_h6,

                    :indoor_outdoor_delta,
                    :temperature_slope_1h,
                    :temperature_slope_3h,

                    :condensation_limit,

                    :geocooling_active,
                    :circulation_active,
                    :heat_pump_active,

                    :data_quality,
                    CAST(:raw_state AS JSONB)
                )
                """
            ),
            {
                **state,
                "raw_state": json.dumps(
                    state,
                    ensure_ascii=False,
                    default=str,
                ),
            },
        )

    def training_rows(
        self,
        connection: Any,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                """
                WITH paired AS (
                    SELECT
                        current_state.calculated_at,

                        current_state.indoor_temperature
                            AS current_temperature,

                        future_state.indoor_temperature
                            AS future_temperature,

                        current_state.indoor_outdoor_delta,
                        current_state.outdoor_solar_radiation,
                        current_state.temperature_slope_1h,

                        CASE
                            WHEN
                                COALESCE(
                                    current_state.geocooling_active,
                                    FALSE
                                )
                                OR COALESCE(
                                    current_state.circulation_active,
                                    FALSE
                                )
                            THEN 1.0
                            ELSE 0.0
                        END AS geocooling_active

                    FROM building_state current_state

                    JOIN LATERAL (
                        SELECT indoor_temperature
                        FROM building_state candidate
                        WHERE candidate.calculated_at >=
                            current_state.calculated_at
                            + INTERVAL '55 minutes'
                          AND candidate.calculated_at <=
                            current_state.calculated_at
                            + INTERVAL '75 minutes'
                          AND candidate.indoor_temperature
                              IS NOT NULL
                        ORDER BY
                            ABS(
                                EXTRACT(
                                    EPOCH FROM (
                                        candidate.calculated_at
                                        - current_state.calculated_at
                                        - INTERVAL '1 hour'
                                    )
                                )
                            )
                        LIMIT 1
                    ) future_state
                    ON TRUE

                    WHERE
                        current_state.indoor_temperature
                            IS NOT NULL
                        AND current_state.indoor_outdoor_delta
                            IS NOT NULL
                        AND current_state.outdoor_solar_radiation
                            IS NOT NULL
                )

                SELECT *
                FROM paired
                ORDER BY calculated_at DESC
                LIMIT 2016
                """
            )
        ).mappings().all()

        return [
            dict(row)
            for row in rows
        ]

    def train_model(
        self,
        connection: Any,
    ) -> dict[str, Any] | None:
        rows = self.training_rows(connection)

        self.model_sample_count = len(rows)

        if len(rows) < THERMAL_MODEL_MIN_SAMPLES:
            self.model_ready = False
            self.model_confidence = min(
                0.45,
                len(rows)
                / THERMAL_MODEL_MIN_SAMPLES
                * 0.45,
            )
            return None

        features: list[list[float]] = []
        targets: list[float] = []

        for row in rows:
            current_temperature = safe_float(
                row["current_temperature"]
            )
            future_temperature = safe_float(
                row["future_temperature"]
            )
            delta = safe_float(
                row["indoor_outdoor_delta"]
            )
            solar = safe_float(
                row["outdoor_solar_radiation"]
            )
            previous_slope = safe_float(
                row["temperature_slope_1h"]
            )
            geocooling = safe_float(
                row["geocooling_active"]
            )

            if (
                current_temperature is None
                or future_temperature is None
                or delta is None
                or solar is None
                or geocooling is None
            ):
                continue

            if previous_slope is None:
                previous_slope = 0.0

            features.append(
                [
                    1.0,
                    delta,
                    solar / 1000.0,
                    previous_slope,
                    geocooling,
                ]
            )

            targets.append(
                future_temperature
                - current_temperature
            )

        if len(features) < THERMAL_MODEL_MIN_SAMPLES:
            self.model_ready = False
            return None

        coefficients = ridge_regression(
            features,
            targets,
        )

        if coefficients is None:
            self.model_ready = False
            return None

        errors: list[float] = []

        for feature_row, target in zip(
            features,
            targets,
        ):
            prediction = sum(
                coefficient * value
                for coefficient, value in zip(
                    coefficients,
                    feature_row,
                )
            )

            errors.append(
                abs(target - prediction)
            )

        mean_absolute_error = (
            sum(errors) / len(errors)
            if errors
            else None
        )

        sample_confidence = min(
            1.0,
            len(features) / 500.0,
        )

        error_confidence = (
            max(
                0.0,
                1.0
                - (
                    mean_absolute_error / 1.5
                ),
            )
            if mean_absolute_error is not None
            else 0.0
        )

        confidence = round(
            sample_confidence
            * error_confidence,
            4,
        )

        model = {
            "intercept": coefficients[0],
            "coefficient_indoor_outdoor_delta":
                coefficients[1],
            "coefficient_solar_radiation":
                coefficients[2],
            "coefficient_previous_slope":
                coefficients[3],
            "coefficient_geocooling":
                coefficients[4],
            "sample_count": len(features),
            "mean_absolute_error":
                mean_absolute_error,
            "confidence": confidence,
        }

        connection.execute(
            text(
                """
                INSERT INTO thermal_model (
                    model_version,
                    sample_count,

                    intercept,
                    coefficient_indoor_outdoor_delta,
                    coefficient_solar_radiation,
                    coefficient_previous_slope,
                    coefficient_geocooling,

                    mean_absolute_error,
                    confidence,
                    details
                )
                VALUES (
                    'ridge-v1',
                    :sample_count,

                    :intercept,
                    :coefficient_indoor_outdoor_delta,
                    :coefficient_solar_radiation,
                    :coefficient_previous_slope,
                    :coefficient_geocooling,

                    :mean_absolute_error,
                    :confidence,
                    CAST(:details AS JSONB)
                )
                """
            ),
            {
                **model,
                "details": json.dumps(
                    model,
                    ensure_ascii=False,
                ),
            },
        )

        self.model_ready = True
        self.model_confidence = confidence

        return model

    def latest_model(
        self,
        connection: Any,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            text(
                """
                SELECT
                    model_version,
                    sample_count,
                    intercept,
                    coefficient_indoor_outdoor_delta,
                    coefficient_solar_radiation,
                    coefficient_previous_slope,
                    coefficient_geocooling,
                    mean_absolute_error,
                    confidence,
                    trained_at
                FROM thermal_model
                ORDER BY trained_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()

        return dict(row) if row else None

    def hourly_temperature_change(
        self,
        state: dict[str, Any],
        model: dict[str, Any] | None,
        geocooling_active: bool,
    ) -> tuple[float, str, float]:
        indoor_outdoor_delta = (
            safe_float(
                state.get(
                    "indoor_outdoor_delta"
                )
            )
            or 0.0
        )

        solar_radiation = (
            safe_float(
                state.get(
                    "outdoor_solar_radiation"
                )
            )
            or 0.0
        )

        previous_slope = (
            safe_float(
                state.get(
                    "temperature_slope_1h"
                )
            )
            or 0.0
        )

        if model is not None:
            change = (
                float(model["intercept"])
                + float(
                    model[
                        "coefficient_indoor_outdoor_delta"
                    ]
                )
                * indoor_outdoor_delta
                + float(
                    model[
                        "coefficient_solar_radiation"
                    ]
                )
                * (solar_radiation / 1000.0)
                + float(
                    model[
                        "coefficient_previous_slope"
                    ]
                )
                * previous_slope
                + float(
                    model[
                        "coefficient_geocooling"
                    ]
                )
                * (
                    1.0
                    if geocooling_active
                    else 0.0
                )
            )

            return (
                max(-2.0, min(2.0, change)),
                "learned_model",
                float(model["confidence"]),
            )

        outdoor_temperature = safe_float(
            state.get("outdoor_temperature")
        )

        indoor_temperature = safe_float(
            state.get("indoor_temperature")
        )

        passive_change = 0.0

        if (
            outdoor_temperature is not None
            and indoor_temperature is not None
        ):
            passive_change = (
                outdoor_temperature
                - indoor_temperature
            ) * 0.025

        solar_change = (
            solar_radiation / 1000.0
        ) * 0.12

        inertia_change = previous_slope * 0.45

        geocooling_change = (
            GECOOLING_ESTIMATED_RATE
            if geocooling_active
            else 0.0
        )

        change = (
            passive_change
            + solar_change
            + inertia_change
            + geocooling_change
        )

        return (
            max(-1.5, min(1.5, change)),
            "initial_physical_estimate",
            min(
                0.45,
                self.model_sample_count
                / THERMAL_MODEL_MIN_SAMPLES
                * 0.45,
            ),
        )

    def generate_predictions(
        self,
        connection: Any,
        state: dict[str, Any],
        model: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        indoor_temperature = safe_float(
            state.get("indoor_temperature")
        )

        if indoor_temperature is None:
            return []

        predictions: list[dict[str, Any]] = []

        for horizon in (1, 3, 6, 12):
            free_temperature = indoor_temperature
            cooled_temperature = indoor_temperature

            model_source = (
                "learned_model"
                if model
                else "initial_physical_estimate"
            )

            confidence = (
                safe_float(
                    model.get("confidence")
                )
                if model
                else self.model_confidence
            ) or 0.0

            for step in range(horizon):
                free_change, _, _ = (
                    self.hourly_temperature_change(
                        state,
                        model,
                        geocooling_active=False,
                    )
                )

                cooled_change, _, _ = (
                    self.hourly_temperature_change(
                        state,
                        model,
                        geocooling_active=True,
                    )
                )

                forecast_key = (
                    "forecast_temperature_h1"
                    if step < 2
                    else "forecast_temperature_h3"
                    if step < 5
                    else "forecast_temperature_h6"
                    if step < 10
                    else "forecast_temperature_h12"
                )

                forecast_temperature = safe_float(
                    state.get(forecast_key)
                )

                if forecast_temperature is not None:
                    free_change += (
                        forecast_temperature
                        - free_temperature
                    ) * 0.01

                    cooled_change += (
                        forecast_temperature
                        - cooled_temperature
                    ) * 0.01

                free_temperature += free_change
                cooled_temperature += cooled_change

            overheating_risk = max(
                0.0,
                min(
                    1.0,
                    (
                        free_temperature
                        - COMFORT_MAX_TEMPERATURE
                    ) / 3.0,
                ),
            )

            prediction = {
                "horizon_hours": horizon,
                "predicted_temperature_free":
                    round(
                        free_temperature,
                        3,
                    ),
                "predicted_temperature_geocooling":
                    round(
                        cooled_temperature,
                        3,
                    ),
                "comfort_target":
                    COMFORT_TARGET_TEMPERATURE,
                "overheating_risk":
                    round(
                        overheating_risk,
                        4,
                    ),
                "confidence":
                    round(confidence, 4),
                "model_source":
                    model_source,
            }

            connection.execute(
                text(
                    """
                    INSERT INTO thermal_predictions (
                        horizon_hours,
                        predicted_temperature_free,
                        predicted_temperature_geocooling,
                        comfort_target,
                        overheating_risk,
                        confidence,
                        model_source,
                        details
                    )
                    VALUES (
                        :horizon_hours,
                        :predicted_temperature_free,
                        :predicted_temperature_geocooling,
                        :comfort_target,
                        :overheating_risk,
                        :confidence,
                        :model_source,
                        CAST(:details AS JSONB)
                    )
                    """
                ),
                {
                    **prediction,
                    "details": json.dumps(
                        prediction,
                        ensure_ascii=False,
                    ),
                },
            )

            predictions.append(prediction)

        return predictions

    def generate_recommendation(
        self,
        connection: Any,
        state: dict[str, Any],
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        indoor_temperature = safe_float(
            state.get("indoor_temperature")
        )

        condensation_limit = safe_float(
            state.get("condensation_limit")
        )

        forecast_h6 = next(
            (
                prediction
                for prediction in predictions
                if prediction["horizon_hours"] == 6
            ),
            None,
        )

        action = "WAIT"
        priority = 20
        risk_level = "low"
        reason = (
            "Données en cours d'analyse ; "
            "aucune action immédiate nécessaire."
        )
        duration_minutes = 0

        if indoor_temperature is None:
            action = "NO_DATA"
            priority = 100
            risk_level = "high"
            reason = (
                "Température intérieure indisponible. "
                "Le pilotage automatique doit rester désactivé."
            )

        elif forecast_h6 is not None:
            predicted_free = float(
                forecast_h6[
                    "predicted_temperature_free"
                ]
            )

            predicted_cooled = float(
                forecast_h6[
                    "predicted_temperature_geocooling"
                ]
            )

            if predicted_free >= COMFORT_MAX_TEMPERATURE:
                required_reduction = max(
                    0.0,
                    predicted_free
                    - COMFORT_TARGET_TEMPERATURE,
                )

                cooling_rate = max(
                    0.10,
                    abs(
                        predicted_free
                        - predicted_cooled
                    ) / 6.0,
                )

                duration_minutes = min(
                    360,
                    max(
                        30,
                        int(
                            required_reduction
                            / cooling_rate
                            * 60
                        ),
                    ),
                )

                action = "PRECOOL"
                priority = 80
                risk_level = (
                    "high"
                    if predicted_free
                    >= COMFORT_MAX_TEMPERATURE + 2
                    else "medium"
                )

                reason = (
                    f"Température intérieure prévue "
                    f"à H+6 : {predicted_free:.1f} °C. "
                    f"Pré-refroidissement recommandé "
                    f"pendant environ "
                    f"{duration_minutes} minutes."
                )

            elif (
                predicted_free
                >= COMFORT_MAX_TEMPERATURE - 0.5
            ):
                action = "MONITOR"
                priority = 50
                risk_level = "medium"
                reason = (
                    f"Risque modéré de surchauffe : "
                    f"{predicted_free:.1f} °C prévu "
                    f"à H+6."
                )

            elif (
                indoor_temperature
                > COMFORT_TARGET_TEMPERATURE
                and predicted_free
                < indoor_temperature - 0.5
            ):
                action = "WAIT_FOR_NATURAL_COOLING"
                priority = 30
                risk_level = "low"
                reason = (
                    "La météo devrait refroidir "
                    "naturellement le bâtiment. "
                    "Le géocooling n'est pas prioritaire."
                )

        if (
            condensation_limit is not None
            and condensation_limit >= 17.0
        ):
            reason += (
                f" Température minimale de surface "
                f"conseillée : "
                f"{condensation_limit:.1f} °C."
            )

        recommendation = {
            "subsystem": "geocooling",
            "action": action,
            "priority": priority,
            "recommended_start_at": (
                utc_now()
                if action == "PRECOOL"
                else None
            ),
            "recommended_duration_minutes":
                duration_minutes,
            "reason": reason,
            "risk_level": risk_level,
            "automatic_execution": False,
            "details": {
                "simulation_only": True,
                "comfort_target":
                    COMFORT_TARGET_TEMPERATURE,
                "comfort_max":
                    COMFORT_MAX_TEMPERATURE,
                "condensation_limit":
                    condensation_limit,
                "model_ready":
                    self.model_ready,
                "model_confidence":
                    self.model_confidence,
            },
        }

        connection.execute(
            text(
                """
                INSERT INTO control_recommendations (
                    subsystem,
                    action,
                    priority,
                    recommended_start_at,
                    recommended_duration_minutes,
                    reason,
                    risk_level,
                    automatic_execution,
                    details
                )
                VALUES (
                    :subsystem,
                    :action,
                    :priority,
                    :recommended_start_at,
                    :recommended_duration_minutes,
                    :reason,
                    :risk_level,
                    FALSE,
                    CAST(:details AS JSONB)
                )
                """
            ),
            {
                **recommendation,
                "details": json.dumps(
                    recommendation["details"],
                    ensure_ascii=False,
                    default=str,
                ),
            },
        )

        recommendation["generated_at"] = (
            utc_now().isoformat()
        )

        self.latest_recommendation = recommendation

        return recommendation

    def cleanup(self, connection: Any) -> None:
        connection.execute(
            text(
                """
                DELETE FROM thermal_predictions
                WHERE generated_at <
                    NOW() - INTERVAL '30 days'
                """
            )
        )

        connection.execute(
            text(
                """
                DELETE FROM control_recommendations
                WHERE generated_at <
                    NOW() - INTERVAL '90 days'
                """
            )
        )

    def run_once(self) -> None:
        with self.engine.begin() as connection:
            state = self.collect_state(connection)
            self.store_state(connection, state)

            model = self.train_model(connection)

            if model is None:
                model = self.latest_model(connection)

                if model is not None:
                    self.model_ready = (
                        int(model["sample_count"])
                        >= THERMAL_MODEL_MIN_SAMPLES
                    )
                    self.model_confidence = float(
                        model["confidence"]
                    )

            predictions = self.generate_predictions(
                connection,
                state,
                model,
            )

            self.generate_recommendation(
                connection,
                state,
                predictions,
            )

            self.cleanup(connection)

        self.last_run_at = utc_now().isoformat()
        self.last_error = None
        self.run_count += 1

        logger.info(
            "Cycle intelligence terminé : "
            "qualité=%s modèle=%s échantillons=%s",
            state["data_quality"],
            self.model_ready,
            self.model_sample_count,
        )

    def start(self) -> None:
        self.initialize_database()
        self.running = True

        def worker() -> None:
            while not self.stop_event.is_set():
                try:
                    self.run_once()
                except Exception as exc:
                    self.last_error = str(exc)

                    logger.exception(
                        "Erreur du moteur "
                        "d'intelligence thermique"
                    )

                self.stop_event.wait(
                    INTELLIGENCE_REFRESH_SECONDS
                )

            self.running = False

        threading.Thread(
            target=worker,
            daemon=True,
            name="intelligence-worker",
        ).start()

    def stop(self) -> None:
        self.stop_event.set()
        self.running = False

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "mode": "simulation",
            "automatic_execution": False,
            "refresh_seconds":
                INTELLIGENCE_REFRESH_SECONDS,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "model_ready": self.model_ready,
            "model_sample_count":
                self.model_sample_count,
            "model_minimum_samples":
                THERMAL_MODEL_MIN_SAMPLES,
            "model_confidence":
                self.model_confidence,
            "comfort": {
                "target_temperature":
                    COMFORT_TARGET_TEMPERATURE,
                "maximum_temperature":
                    COMFORT_MAX_TEMPERATURE,
                "minimum_temperature":
                    COMFORT_MIN_TEMPERATURE,
                "condensation_margin":
                    CONDENSATION_MARGIN_C,
            },
            "latest_recommendation":
                self.latest_recommendation,
        }
