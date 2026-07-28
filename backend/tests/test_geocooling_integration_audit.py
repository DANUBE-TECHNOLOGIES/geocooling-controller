import importlib.util
from pathlib import Path

from app.geocooling.integration_audit import GeoCoolingIntegrationAudit


class Manual:
    def status(self):
        return {"armed": False, "ready": False}


class Dashboard:
    def snapshot(self):
        return {"status": "ok"}


class Controller:
    driver_name = "simulation"
    autopilot_enabled = False
    autopilot_allow_real_driver = False


def build(monkeypatch, tmp_path, routes=None):
    monkeypatch.setenv("GEOCOOLING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "GEOCOOLING_BRAIN_JOURNAL_PATH",
        str(tmp_path / "brain-decisions.jsonl"),
    )
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    return GeoCoolingIntegrationAudit(
        Controller(), Manual(), Dashboard(),
        route_provider=lambda: list(routes if routes is not None else GeoCoolingIntegrationAudit.REQUIRED_ROUTES),
    )


def test_audit_ready(monkeypatch, tmp_path):
    audit = build(monkeypatch, tmp_path)
    report = audit.evaluate()
    assert report["version"] == "C024.2"
    assert report["verdict"] == "READY_FOR_COMMISSIONING"
    assert not (tmp_path / ".geocooling-write-probe").exists()


def test_audit_missing_route_blocks(monkeypatch, tmp_path):
    audit = build(monkeypatch, tmp_path, routes=[])
    assert audit.evaluate()["verdict"] == "NOT_READY"


def test_real_driver_autopilot_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOCOOLING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEOCOOLING_BRAIN_JOURNAL_PATH", str(tmp_path / "brain-decisions.jsonl"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    c = Controller()
    c.driver_name = "waveshare_modbus"
    c.autopilot_enabled = True
    c.autopilot_allow_real_driver = True
    audit = GeoCoolingIntegrationAudit(
        c, Manual(), Dashboard(),
        route_provider=lambda: list(GeoCoolingIntegrationAudit.REQUIRED_ROUTES),
    )
    report = audit.evaluate()
    assert any(x["id"] == "runtime:autopilot-safe" and x["status"] == "FAIL" for x in report["checks"])


def test_unwritable_data_directory_blocks(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked-file"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("GEOCOOLING_DATA_DIR", str(blocked / "geocooling"))
    monkeypatch.setenv("GEOCOOLING_BRAIN_JOURNAL_PATH", str(blocked / "geocooling" / "brain-decisions.jsonl"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    audit = GeoCoolingIntegrationAudit(
        Controller(), Manual(), Dashboard(),
        route_provider=lambda: list(GeoCoolingIntegrationAudit.REQUIRED_ROUTES),
    )
    report = audit.evaluate()
    assert report["verdict"] == "NOT_READY"
    assert any(x["id"] == "persistence:writable" and x["status"] == "FAIL" for x in report["checks"])


def test_journal_outside_data_dir_is_warning(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOCOOLING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEOCOOLING_BRAIN_JOURNAL_PATH", "/var/lib/geocooling/brain-decisions.jsonl")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    audit = GeoCoolingIntegrationAudit(
        Controller(), Manual(), Dashboard(),
        route_provider=lambda: list(GeoCoolingIntegrationAudit.REQUIRED_ROUTES),
    )
    report = audit.evaluate()
    assert report["verdict"] == "READY_FOR_COMMISSIONING"
    assert any(x["id"] == "persistence:journal-location" and x["status"] == "FAIL" for x in report["warnings"])
