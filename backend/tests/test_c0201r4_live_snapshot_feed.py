from pathlib import Path

TARGET = Path("backend/app/geocooling/api.py")
MARKER = "C020.1R4 DIGITAL TWIN LIVE FEED"


def _thermal_snapshot_section(source: str) -> str:
    start = source.index(
        "def put_thermal_snapshot(payload: dict[str, Any] = Body(...)) -> dict:"
    )
    end = source.find("\n@router.", start)
    return source[start:] if end == -1 else source[start:end]


def _helper_section(source: str) -> str:
    start = source.index(f"# {MARKER}")
    end = source.index(
        "def put_thermal_snapshot(payload: dict[str, Any] = Body(...)) -> dict:",
        start,
    )
    return source[start:end]


def test_c0201r4_helper_exists_once():
    source = TARGET.read_text(encoding="utf-8")
    assert source.count("def _c020_digital_twin_snapshot_payload") == 1


def test_c0201r4_feed_updates_after_ingestion():
    source = TARGET.read_text(encoding="utf-8")
    route = _thermal_snapshot_section(source)

    ingest = route.index("controller.ingest_thermal_snapshot(payload)")
    update = route.index("industrial_platform.digital_twin.update(")
    returned = route.index("return result")

    assert ingest < update < returned
    assert "_c020_digital_twin_snapshot_payload(payload)" in route


def test_c0201r4_added_sections_contain_no_hardware_write():
    source = TARGET.read_text(encoding="utf-8")
    added_code = _helper_section(source) + _thermal_snapshot_section(source)

    for forbidden in (
        "mqtt.publish",
        "write_coil",
        "set_relay",
        "command_relay",
        "driver.activate",
    ):
        assert forbidden not in added_code
