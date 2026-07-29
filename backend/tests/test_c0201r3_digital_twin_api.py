from pathlib import Path

TARGET = Path("backend/app/geocooling/api.py")
ROUTE = "/geocooling/industrial-platform/digital-twin"


def test_c0201r3_api_route_exists():
    source = TARGET.read_text(encoding="utf-8")
    assert ROUTE in source
    assert "industrial_platform.digital_twin.status()" in source


def test_c0201r3_api_route_is_get_only():
    source = TARGET.read_text(encoding="utf-8")
    assert f'@router.get("{ROUTE}")' in source
    assert f'@router.post("{ROUTE}")' not in source
    assert f'@router.put("{ROUTE}")' not in source
    assert f'@router.delete("{ROUTE}")' not in source
