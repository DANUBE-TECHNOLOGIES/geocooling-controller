from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)


def policy(state: str):
    return build_hardware_activation_policy({"state": state})


def test_early_commissioning_blocks_all_positive_hardware_paths():
    result = policy("MAPPING_INCOMPLETE")

    assert result["controller_start_allowed"] is False
    assert result["manual_arm_allowed"] is False
    assert result["manual_positive_commands_allowed"] is False
    assert result["commissioning_tests_allowed"] is False


def test_field_certification_stage_only_opens_certification_window():
    result = policy("FIELD_CERTIFICATION_REQUIRED")

    assert result["controller_start_allowed"] is False
    assert result["manual_arm_allowed"] is True
    assert result["manual_positive_commands_allowed"] is False
    assert result["commissioning_tests_allowed"] is True


def test_release_ready_opens_normal_positive_paths():
    result = policy("READY_FOR_RELEASE")

    assert result["controller_start_allowed"] is True
    assert result["manual_arm_allowed"] is True
    assert result["manual_positive_commands_allowed"] is True
    assert result["commissioning_tests_allowed"] is True


def test_safe_actions_are_never_blocked_by_commissioning_state():
    for state in (
        "UPSTREAM_NOT_READY",
        "IDENTIFICATION_REQUIRED",
        "MAPPING_INCOMPLETE",
        "FIELD_CERTIFICATION_REQUIRED",
        "READY_FOR_RELEASE",
        "UNKNOWN",
    ):
        result = policy(state)
        assert result["safe_stop_allowed"] is True
        assert result["pump_stop_allowed"] is True
        assert result["valve_close_allowed"] is True
        assert result["disarm_allowed"] is True
        assert result["hardware_touched"] is False
