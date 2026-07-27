from app.geocooling.capabilities import (
    GeoCoolingCapabilities,
)


def number_parser(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def capabilities(**values):
    return GeoCoolingCapabilities.from_latest(
        values,
        number_parser=number_parser,
    )


def test_building_only_mode():
    result = capabilities(
        indoor_temperature_c=25.1,
        indoor_humidity_percent=46.3,
        outdoor_temperature_c=26.8,
    )

    assert result.building.complete is True
    assert result.hydraulic.available_count == 0
    assert result.operating_mode == "BUILDING_ONLY"
    assert result.data_quality == 70.0


def test_full_mode_with_four_hydraulic_measurements():
    result = capabilities(
        indoor_temperature_c=25.1,
        indoor_humidity_percent=46.3,
        outdoor_temperature_c=26.8,
        surface_temperature_c=22.4,
        floor_supply_temperature_c=18.0,
        floor_return_temperature_c=20.5,
        source_inlet_temperature_c=12.3,
    )

    assert result.building.complete is True
    assert result.hydraulic.available_count == 4
    assert result.operating_mode == "FULL"
    assert result.data_quality == 90.0


def test_limited_mode_with_two_building_measurements():
    result = capabilities(
        indoor_temperature_c=25.1,
        indoor_humidity_percent=46.3,
    )

    assert result.building.available_count == 2
    assert result.operating_mode == "LIMITED"


def test_insufficient_data_mode():
    result = capabilities(
        indoor_temperature_c=25.1,
    )

    assert result.building.available_count == 1
    assert result.operating_mode == "INSUFFICIENT_DATA"


def test_zero_is_a_valid_measurement():
    result = capabilities(
        indoor_temperature_c=0,
        indoor_humidity_percent=0,
        outdoor_temperature_c=0,
    )

    assert result.building.complete is True
    assert result.operating_mode == "BUILDING_ONLY"


def test_invalid_strings_are_not_available():
    result = capabilities(
        indoor_temperature_c="invalid",
        indoor_humidity_percent="46.3",
        outdoor_temperature_c="26.8",
    )

    assert result.building.available_count == 2
    assert result.operating_mode == "LIMITED"


def test_capabilities_serialization():
    result = capabilities(
        indoor_temperature_c=25.1,
        indoor_humidity_percent=46.3,
        outdoor_temperature_c=26.8,
    )

    payload = result.as_dict()

    assert payload["building"]["indoor_temperature"] is True
    assert payload["hydraulic"]["flow_meter"] is False
    assert payload["summary"]["operating_mode"] == "BUILDING_ONLY"
    assert payload["summary"]["data_quality"] == 70.0
