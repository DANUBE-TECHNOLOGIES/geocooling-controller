from app.geocooling.rc3.precooling_advisor import PreCoolingAdvisor


def prediction(points, *, degraded=False):
    return {
        "generated_at": "2026-08-10T15:00:00+00:00",
        "weather_input": {"degraded": degraded},
        "trajectories": points,
    }


def trajectories(baseline, soft, full):
    def rows(values):
        return [
            {
                "horizon_minutes": horizon,
                "predicted_indoor_temperature_c": temperature,
                "confidence": confidence,
            }
            for horizon, temperature, confidence in values
        ]

    return [
        {"scenario": "BASELINE", "points": rows(baseline)},
        {"scenario": "SOFT_COOLING", "points": rows(soft)},
        {"scenario": "FULL_COOLING", "points": rows(full)},
    ]


def test_no_precooling_when_comfort_limit_not_crossed() -> None:
    advisor = PreCoolingAdvisor(comfort_target_c=24.0, comfort_max_c=25.0)
    payload = prediction(
        trajectories(
            [(60, 24.2, 0.8), (240, 24.7, 0.7)],
            [(60, 23.9, 0.8), (240, 24.0, 0.7)],
            [(60, 23.7, 0.8), (240, 23.5, 0.7)],
        )
    )

    result = advisor.advise(payload)

    assert result["state"] == "NO_PRECOOL_NEEDED"
    assert result["recommendation"]["start_at"] is None
    assert result["safety"]["controller_authorized"] is False
    assert result["safety"]["promotion_to_controller_allowed"] is False


def test_precooling_window_is_identified_with_good_confidence() -> None:
    advisor = PreCoolingAdvisor(
        comfort_target_c=24.0,
        comfort_max_c=25.0,
        minimum_confidence=0.45,
    )
    payload = prediction(
        trajectories(
            [(60, 24.5, 0.75), (240, 25.6, 0.65), (360, 26.2, 0.55)],
            [(60, 24.2, 0.75), (240, 24.4, 0.65), (360, 24.8, 0.55)],
            [(60, 24.0, 0.75), (240, 23.8, 0.65), (360, 24.0, 0.55)],
        )
    )

    result = advisor.advise(payload)

    assert result["state"] in {"PRECOOL_WINDOW_IDENTIFIED", "PRECOOL_NOW_ADVISORY"}
    assert result["forecast"]["first_limit_crossing_horizon_minutes"] == 240
    assert result["recommendation"]["scenario"] in {"SOFT_COOLING", "FULL_COOLING"}
    assert result["recommendation"]["lead_minutes"] >= 30
    assert result["recommendation"]["start_at"] is not None
    assert result["safety"]["hardware_write"] is False


def test_low_confidence_never_promotes_recommendation() -> None:
    advisor = PreCoolingAdvisor(
        comfort_target_c=24.0,
        comfort_max_c=25.0,
        minimum_confidence=0.6,
    )
    payload = prediction(
        trajectories(
            [(120, 25.4, 0.4)],
            [(120, 24.5, 0.4)],
            [(120, 24.0, 0.4)],
        )
    )

    result = advisor.advise(payload)

    assert result["state"] == "LOW_CONFIDENCE"
    assert result["forecast"]["confidence_at_crossing"] == 0.4
    assert result["safety"]["promotion_to_controller_allowed"] is False


def test_degraded_weather_is_explicit() -> None:
    advisor = PreCoolingAdvisor(comfort_target_c=24.0, comfort_max_c=25.0)
    payload = prediction(
        trajectories(
            [(120, 25.4, 0.8)],
            [(120, 24.5, 0.8)],
            [(120, 24.0, 0.8)],
        ),
        degraded=True,
    )

    result = advisor.advise(payload)

    assert result["state"] == "WEATHER_DEGRADED"
    assert result["forecast"]["weather_degraded"] is True
    assert result["safety"]["controller_called"] is False
