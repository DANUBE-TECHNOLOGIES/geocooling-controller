import pytest

from app.geocooling.energy_model import GeoCoolingEnergyModel


def number(value):
    return None if value is None else float(value)


def evaluate(*, thermal=None, latest=None):
    return GeoCoolingEnergyModel().evaluate(
        thermal=thermal or {},
        latest=latest or {},
        number_parser=number,
    )


def test_estimates_floor_loop_power_from_flow_and_delta_t():
    result = evaluate(latest={
        "flow_rate_l_min": 20.0,
        "floor_supply_temperature_c": 18.0,
        "floor_return_temperature_c": 20.0,
    })

    assert result.available_power_kw == pytest.approx(2.791, abs=0.001)
    assert result.confidence == 85
    assert result.useful is True
    assert result.source == "floor_loop"


def test_measured_power_has_priority_over_theoretical_power():
    result = evaluate(
        thermal={"cooling_power_kw": 3.5},
        latest={
            "flow_rate_l_min": 20.0,
            "floor_supply_temperature_c": 18.0,
            "floor_return_temperature_c": 20.0,
        },
    )

    assert result.available_power_kw == 3.5
    assert result.measured_power_kw == 3.5
    assert result.theoretical_power_kw == pytest.approx(2.791, abs=0.001)
    assert result.confidence == 95


def test_missing_energy_data_is_neutral_not_zero_capacity():
    result = evaluate()

    assert result.available_power_kw is None
    assert result.useful is None
    assert result.score == 50
    assert result.confidence == 0


def test_low_power_is_explicitly_limited():
    result = evaluate(thermal={"cooling_power_kw": 0.4})

    assert result.useful is False
    assert "insuffisante" in result.limitation
