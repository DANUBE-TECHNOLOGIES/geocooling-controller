from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)
from app.geocooling.release_readiness import build_release_readiness


def commissioning(state: str, next_action: str = "finish commissioning"):
    return {"state": state, "next_action": next_action}


def safe_flags():
    return {
        "hardware_armed": False,
        "hardware_sequence_enabled": False,
        "autopilot_enabled": False,
        "autopilot_allow_real_driver": False,
    }


def test_release_is_blocked_until_commissioning_is_complete():
    c = commissioning("FIELD_CERTIFICATION_REQUIRED")
    result = build_release_readiness(
        c,
        build_hardware_activation_policy(c),
        safe_flags(),
    )

    assert result["state"] == "COMMISSIONING_BLOCKED"
    assert result["deployment_ready"] is False
    assert result["runtime_safe_defaults"] is True
    assert result["blockers"] == ["finish commissioning"]


def test_release_requires_safe_runtime_defaults_even_after_certification():
    c = commissioning("READY_FOR_RELEASE")
    flags = safe_flags()
    flags["hardware_armed"] = True

    result = build_release_readiness(
        c,
        build_hardware_activation_policy(c),
        flags,
    )

    assert result["state"] == "CONFIG_REVIEW_REQUIRED"
    assert result["deployment_ready"] is False
    assert result["active_dangerous_flags"] == ["hardware_armed"]


def test_release_is_ready_only_when_commissioning_and_safe_defaults_are_green():
    c = commissioning("READY_FOR_RELEASE")
    result = build_release_readiness(
        c,
        build_hardware_activation_policy(c),
        safe_flags(),
    )

    assert result["state"] == "READY_FOR_DEPLOYMENT"
    assert result["deployment_ready"] is True
    assert result["runtime_safe_defaults"] is True
    assert result["blockers"] == []
    assert result["hardware_touched"] is False
    assert result["mqtt_publish"] is False
