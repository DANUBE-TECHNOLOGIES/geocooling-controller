from pathlib import Path

from app.geocooling.industrial_hardening import (
    GeoCoolingHeartbeatRegistry,
    GeoCoolingSafeMode,
    GeoCoolingTransactionManager,
    TransactionStep,
)


def test_transaction_commits_in_order():
    events = []
    manager = GeoCoolingTransactionManager()
    result = manager.execute("ok", [
        TransactionStep("one", lambda: events.append("one")),
        TransactionStep("two", lambda: events.append("two")),
    ])
    assert result["status"] == "COMMITTED"
    assert events == ["one", "two"]


def test_transaction_rolls_back_in_reverse_order():
    events = []
    manager = GeoCoolingTransactionManager()

    def fail():
        raise RuntimeError("boom")

    result = manager.execute("rollback", [
        TransactionStep("one", lambda: events.append("one"), lambda: events.append("undo-one")),
        TransactionStep("two", lambda: events.append("two"), lambda: events.append("undo-two")),
        TransactionStep("fail", fail),
    ])
    assert result["status"] == "ROLLED_BACK"
    assert events == ["one", "two", "undo-two", "undo-one"]


def test_dry_run_executes_no_action():
    events = []
    manager = GeoCoolingTransactionManager()
    result = manager.execute("dry", [TransactionStep("one", lambda: events.append("one"))], dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert events == []


def test_heartbeat_registry_reports_healthy():
    registry = GeoCoolingHeartbeatRegistry(stale_after_seconds=60)
    registry.beat("brain")
    snapshot = registry.snapshot()
    assert snapshot["healthy"] is True
    assert snapshot["components"][0]["component"] == "brain"


def test_safe_mode_persists(tmp_path: Path):
    path = tmp_path / "safe.json"
    first = GeoCoolingSafeMode(str(path))
    first.activate("test", "pytest")
    second = GeoCoolingSafeMode(str(path))
    assert second.status()["active"] is True
    second.clear("pytest")
    assert second.status()["active"] is False

from app.geocooling.industrial_hardening import GeoCoolingLifecycleRegistry


def test_transaction_history_persists(tmp_path: Path):
    path = tmp_path / "transactions.jsonl"
    first = GeoCoolingTransactionManager(path=str(path))
    first.execute("persisted", [TransactionStep("one", lambda: None)])
    second = GeoCoolingTransactionManager(path=str(path))
    assert second.status()["transactions"] == 1
    assert second.history()[0]["name"] == "persisted"


def test_lifecycle_transitions_and_persists(tmp_path: Path):
    path = tmp_path / "lifecycle.json"
    first = GeoCoolingLifecycleRegistry(str(path))
    first.transition("controller", "INIT", reason="boot")
    first.transition("controller", "READY", reason="ok")
    snapshot = first.snapshot()
    assert snapshot["components"][0]["state"] == "READY"
    second = GeoCoolingLifecycleRegistry(str(path))
    assert second.snapshot()["restart_detected"] is True
    assert second.snapshot()["components"][0]["state"] == "READY"


def test_lifecycle_rejects_unknown_state(tmp_path: Path):
    registry = GeoCoolingLifecycleRegistry(str(tmp_path / "lifecycle.json"))
    try:
        registry.transition("controller", "UNKNOWN", reason="bad")
    except ValueError as exc:
        assert "Unsupported lifecycle state" in str(exc)
    else:
        raise AssertionError("ValueError expected")
