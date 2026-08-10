from app.geocooling.surface_estimation import estimate_floor_surface_temperature


def test_estimate_uses_supply_and_return_mean_with_negative_bias():
    result = estimate_floor_surface_temperature(18.0, 20.0, bias_c=-0.5)

    assert result.available is True
    assert result.mean_water_temperature_c == 19.0
    assert result.temperature_c == 18.5
    assert result.bias_c == -0.5
    assert result.method == "floor_supply_return_mean_conservative"


def test_positive_bias_is_never_allowed():
    result = estimate_floor_surface_temperature(18.0, 20.0, bias_c=2.0)

    assert result.available is True
    assert result.bias_c == 0.0
    assert result.temperature_c == 19.0


def test_missing_floor_temperature_is_fail_closed():
    result = estimate_floor_surface_temperature(18.0, None, bias_c=-0.5)

    assert result.available is False
    assert result.temperature_c is None


def test_order_of_floor_temperatures_does_not_change_mean():
    first = estimate_floor_surface_temperature(18.0, 20.0, bias_c=-0.5)
    second = estimate_floor_surface_temperature(20.0, 18.0, bias_c=-0.5)

    assert first.temperature_c == second.temperature_c == 18.5
