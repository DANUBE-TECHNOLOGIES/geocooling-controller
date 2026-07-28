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
