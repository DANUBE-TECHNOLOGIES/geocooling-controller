from app.geocooling.commissioning_readiness import build_commissioning_readiness


def health(*, upstream="OBSERVED", configured=6, ready=True):
    return {
        "upstream_state": upstream,
        "configured_role_count": configured,
        "ready": ready,
        "roles": {f"role_{i}": {} for i in range(6)},
    }


def test_upstream_must_be_restored_first():
    result = build_commissioning_readiness(
        health(upstream="UPSTREAM_EMPTY", configured=0, ready=False)
    )
    assert result["state"] == "UPSTREAM_NOT_READY"
    assert result["ready_for_release"] is False


def test_observed_sources_still_require_physical_identification():
    result = build_commissioning_readiness(
        health(configured=0, ready=False)
    )
    assert result["state"] == "IDENTIFICATION_REQUIRED"
    assert result["automatic_hardware_enable"] is False


def test_confirmed_identification_requires_complete_mapping():
    result = build_commissioning_readiness(
        health(configured=4, ready=False),
        physical_identification_confirmed=True,
    )
    assert result["state"] == "MAPPING_INCOMPLETE"


def test_complete_mapping_with_unhealthy_role_stays_incomplete():
    result = build_commissioning_readiness(
        health(configured=6, ready=False),
        physical_identification_confirmed=True,
    )
    assert result["state"] == "MAPPING_INCOMPLETE"


def test_healthy_telemetry_requires_field_certification():
    result = build_commissioning_readiness(
        health(configured=6, ready=True),
        physical_identification_confirmed=True,
    )
    assert result["state"] == "FIELD_CERTIFICATION_REQUIRED"
    assert result["telemetry_ready"] is True


def test_release_ready_requires_both_human_confirmations():
    result = build_commissioning_readiness(
        health(configured=6, ready=True),
        physical_identification_confirmed=True,
        field_certification_confirmed=True,
    )
    assert result["state"] == "READY_FOR_RELEASE"
    assert result["ready_for_release"] is True
    assert result["hardware_touched"] is False
