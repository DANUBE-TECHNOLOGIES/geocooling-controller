import time
from app.geocooling.runtime_profiler import GeoCoolingRuntimeProfiler

class Target:
    def ok(self):
        time.sleep(0.001)
        return 42
    def fail(self):
        raise ValueError("boom")

def test_instrument_records_success(tmp_path):
    profiler = GeoCoolingRuntimeProfiler(data_dir=str(tmp_path), warning_ms=100)
    target = Target()
    assert profiler.instrument(target, "ok", component="target") is True
    assert target.ok() == 42
    snap = profiler.snapshot()
    assert snap["sample_count"] == 1
    assert snap["operations"][0]["operation"] == "target.ok"

def test_failure_is_recorded(tmp_path):
    profiler = GeoCoolingRuntimeProfiler(data_dir=str(tmp_path))
    target = Target()
    profiler.instrument(target, "fail", component="target")
    try:
        target.fail()
    except ValueError:
        pass
    assert profiler.status()["summary"]["failures"] == 1

def test_persistence_reload(tmp_path):
    p1 = GeoCoolingRuntimeProfiler(data_dir=str(tmp_path))
    p1.record("brain", "evaluate", 12.5)
    p2 = GeoCoolingRuntimeProfiler(data_dir=str(tmp_path))
    assert p2.history(1)[0]["duration_ms"] == 12.5

def test_thresholds(tmp_path):
    profiler = GeoCoolingRuntimeProfiler(data_dir=str(tmp_path), warning_ms=10, critical_ms=20)
    assert profiler.record("x", "a", 15)["severity"] == "WARNING"
    assert profiler.record("x", "b", 25)["severity"] == "CRITICAL"
