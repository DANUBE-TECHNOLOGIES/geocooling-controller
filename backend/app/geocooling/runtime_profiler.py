"""C024.3 — Profilage runtime non intrusif GeoCooling."""
from __future__ import annotations

import functools
import json
import math
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 3)


class GeoCoolingRuntimeProfiler:
    PATCH_VERSION = "C024.3"

    def __init__(self, *, data_dir: str | None = None, history_capacity: int = 2000,
                 warning_ms: float = 100.0, critical_ms: float = 500.0) -> None:
        root = data_dir or os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling")
        self.path = Path(root) / "runtime-profile.jsonl"
        self.history_capacity = max(100, int(history_capacity))
        self.warning_ms = max(1.0, float(warning_ms))
        self.critical_ms = max(self.warning_ms, float(critical_ms))
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=self.history_capacity)
        self._started_at = _utc_now()
        self._instrumented: set[str] = set()
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            lines = self.path.read_text(encoding="utf-8").splitlines()[-self.history_capacity:]
            for line in lines:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        self._events.append(item)
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            return

    def _persist(self, event: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def record(self, component: str, operation: str, duration_ms: float,
               *, success: bool = True, error: str | None = None) -> dict[str, Any]:
        duration_ms = round(max(0.0, float(duration_ms)), 3)
        severity = "CRITICAL" if duration_ms >= self.critical_ms else (
            "WARNING" if duration_ms >= self.warning_ms else "OK"
        )
        if not success:
            severity = "ERROR"
        event = {
            "recorded_at": _utc_now(), "component": str(component),
            "operation": str(operation), "duration_ms": duration_ms,
            "success": bool(success), "severity": severity, "error": error,
        }
        with self._lock:
            self._events.append(event)
            self._persist(event)
        return event

    def instrument(self, target: Any, method_name: str, *, component: str | None = None) -> bool:
        key = f"{id(target)}:{method_name}"
        with self._lock:
            if key in self._instrumented:
                return False
        original = getattr(target, method_name, None)
        if not callable(original):
            return False
        profiler = self
        component_name = component or type(target).__name__

        @functools.wraps(original)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                result = original(*args, **kwargs)
            except Exception as exc:
                profiler.record(component_name, method_name,
                    (time.perf_counter() - started) * 1000.0,
                    success=False, error=f"{type(exc).__name__}: {exc}")
                raise
            profiler.record(component_name, method_name,
                (time.perf_counter() - started) * 1000.0)
            return result

        setattr(target, method_name, wrapped)
        with self._lock:
            self._instrumented.add(key)
        return True

    def history(self, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), self.history_capacity))
        with self._lock:
            return list(self._events)[-limit:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            groups[f"{event['component']}.{event['operation']}"].append(event)
        operations = []
        for name, items in sorted(groups.items()):
            durations = [float(item["duration_ms"]) for item in items]
            failures = sum(not bool(item.get("success")) for item in items)
            warnings = sum(item.get("severity") in {"WARNING", "CRITICAL"} for item in items)
            operations.append({
                "operation": name, "samples": len(items), "failures": failures,
                "slow_calls": warnings, "minimum_ms": round(min(durations), 3),
                "average_ms": round(sum(durations) / len(durations), 3),
                "p95_ms": _p95(durations), "maximum_ms": round(max(durations), 3),
                "last_ms": durations[-1], "last_at": items[-1].get("recorded_at"),
            })
        all_durations = [float(event["duration_ms"]) for event in events]
        failures = sum(not bool(event.get("success")) for event in events)
        slow = sum(event.get("severity") in {"WARNING", "CRITICAL"} for event in events)
        overall = "DEGRADED" if failures or slow else ("OK" if events else "NO_DATA")
        return {
            "overall": overall, "patch_version": self.PATCH_VERSION,
            "started_at": self._started_at, "sample_count": len(events),
            "instrumented_count": len(self._instrumented),
            "thresholds_ms": {"warning": self.warning_ms, "critical": self.critical_ms},
            "summary": {
                "failures": failures, "slow_calls": slow,
                "minimum_ms": round(min(all_durations), 3) if all_durations else None,
                "average_ms": round(sum(all_durations)/len(all_durations), 3) if all_durations else None,
                "p95_ms": _p95(all_durations),
                "maximum_ms": round(max(all_durations), 3) if all_durations else None,
            },
            "operations": operations,
            "latest": events[-1] if events else None,
        }

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "overall": snap["overall"], "patch_version": self.PATCH_VERSION,
            "running": True, "path": str(self.path),
            "path_exists": self.path.exists(), "sample_count": snap["sample_count"],
            "instrumented_count": snap["instrumented_count"],
            "thresholds_ms": snap["thresholds_ms"], "summary": snap["summary"],
        }
