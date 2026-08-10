import pytest

from app.geocooling.commissioning_test_gate import (
    CommissioningTestGateError,
    validate_commissioning_test_readiness,
    validate_commissioning_test_with_provider,
)


@pytest.mark.parametrize(
    "state",
    [
        "UPSTREAM_NOT_READY",
        "IDENTIFICATION_REQUIRED",
        "MAPPING_INCOMPLETE",
        "UNKNOWN",
    ],
)
def test_physical_commissioning_test_fails_closed_before_field_stage(state):
    with pytest.raises(CommissioningTestGateError):
        validate_commissioning_test_readiness({"state": state})


@pytest.mark.parametrize(
    "state",
    ["FIELD_CERTIFICATION_REQUIRED", "READY_FOR_RELEASE"],
)
def test_physical_commissioning_test_allowed_in_certification_window(state):
    result = validate_commissioning_test_readiness({"state": state})

    assert result["allowed"] is True
    assert result["readiness_state"] == state
    assert result["hardware_touched"] is False


def test_provider_failure_fails_closed():
    def broken_provider():
        raise RuntimeError("telemetry unavailable")

    with pytest.raises(CommissioningTestGateError):
        validate_commissioning_test_with_provider(broken_provider)


def test_invalid_provider_report_fails_closed():
    with pytest.raises(CommissioningTestGateError):
        validate_commissioning_test_with_provider(lambda: None)
