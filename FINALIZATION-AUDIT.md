# GeoCooling — Finalization audit

Date: 2026-08-08

## Release candidate baseline

Current reference branch: `feature/geocooling-ui-v1`.

## Confirmed physical topology

The installation uses **two logical outputs** on the Waveshare controller:

- **EV** — electrovalve.
- **M11 + M13** — both circulators are commanded together by the same actuator/output.

Therefore the existing `valve + pump` software model already matches the real installation topology. No third independent relay is required.

## Remaining blocking gaps before real autonomous operation

1. **Hydraulic sequence must be hardened and certified on real hardware.**
   The existing sequence already opens EV, waits, starts the common M11+M13 output, supervises operation, then stops M11+M13 before closing EV. Feedback verification and safe-state rollback already exist. Final hardening must ensure a START is never accepted from `FAULT`, re-check thermal safety immediately before M11+M13 start, and preserve a deterministic safe state on every failure path.

2. **Condensation safety must fail closed on real hardware.**
   `GEOCOOLING_REQUIRE_THERMAL_SENSORS` currently defaults to false. For a real driver, missing indoor temperature / humidity / floor-surface temperature must block START and request a safe stop while running.

3. **Hardware readiness and certification must explicitly document EV + M11/M13.**
   Readiness and dry-run can retain their two-output model, but labels and certification criteria must reflect the real hydraulic wiring.

4. **Autonomous real-driver execution must remain disabled until field certification passes.**
   `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER` must remain false throughout finalization and commissioning.

## Closure sprints

### F1 — Physical topology validation — CLOSED
- Confirmed topology: EV on one output; M11 + M13 together on one output.
- Existing `valve + pump` driver topology retained.
- Fail-safe state remains: M11+M13 OFF, then EV CLOSED.
- No third actuator implementation required.

### F2 — Certified hydraulic sequence
- Retain the existing START sequence: EV OPEN -> feedback -> delay -> M11+M13 ON -> feedback -> RUNNING.
- Retain the existing STOP sequence: M11+M13 OFF -> feedback -> delay -> EV CLOSED -> feedback -> OFF.
- Reject START from `FAULT`; require explicit reset first.
- Re-evaluate thermal safety immediately before M11+M13 is energized.
- Guarantee best-effort safe rollback even if a feedback/write operation itself fails.
- Add focused regression tests for these hardening rules.

### F3 — Thermal safety fail-closed
- Require valid fresh temperature/humidity/surface data on real hardware.
- Block START on missing/stale/invalid thermal data.
- Trigger safe stop on condensation margin violation or sensor loss during RUNNING.
- Test dew-point margin and sensor-loss scenarios.

### F4 — Field certification and release
- Update readiness terminology for EV + M11/M13.
- Physical relay-by-relay commissioning with autonomous mode disabled.
- Validate Home Assistant live telemetry and UI states.
- Run complete regression suite.
- Merge release candidate to `main` only after field certification passes.

## Release rule

No new Brain, Digital Twin, prediction or UI feature work until F2–F4 are closed. The objective is operational completion and safety certification, not feature expansion.
