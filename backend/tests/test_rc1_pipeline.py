from app.geocooling.rc1_pipeline import pipeline_status
from app.geocooling.rc1_router import get_rc1_readiness


def test_pipeline_status_is_read_only() -> None:
    status = pipeline_status()

    assert status["mode"] == "read_only"
    assert status["safety"] == {
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "service_start": False,
    }


def test_pipeline_contains_all_canonical_roles() -> None:
    status = pipeline_status()
    roles = {item["role"] for item in status["checks"]}

    assert roles == {
        "sensors",
        "historian",
        "weather",
        "learning",
        "thermal_engine",
        "prediction",
        "brain",
        "safety",
        "controller",
        "hardware",
    }


def test_readiness_payload_is_consistent() -> None:
    readiness = get_rc1_readiness()

    assert readiness["ready"] == (
        readiness["architecture_ready"]
        and readiness["pipeline_ready"]
    )
