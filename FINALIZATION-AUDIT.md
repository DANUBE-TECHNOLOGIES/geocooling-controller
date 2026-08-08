# GeoCooling — Finalization audit

Date: 2026-08-08

## Release candidate baseline

Current reference branch: `feature/geocooling-ui-v1`.

## Blocking gaps before real autonomous operation

1. **Physical actuator model does not match the installation.**
   The current Waveshare driver models only two outputs (`valve` + `pump`). The real installation requires three independently mapped outputs: **EV**, **M11** (floor-heating loop circulator), and **M13** (buffer-tank circulator).

2. **Real sequence is still guarded / not certified for the 3-output hydraulic topology.**
   Hardware arming and Modbus write verification exist, but the production start/stop sequence must be updated and tested for EV + M11 + M13 before autonomous mode is enabled.

3. **Condensation safety must fail closed on real hardware.**
   `GEOCOOLING_REQUIRE_THERMAL_SENSORS` currently defaults to false. For a real driver, missing indoor temperature / humidity / floor-surface temperature must block START and request a safe stop while running.

4. **Hardware readiness still validates only valve + pump.**
   Readiness, dry-run sequence, manual control, status payloads and certification tests must all be upgraded to the three-actuator topology.

5. **Autonomous real-driver execution must remain disabled until field certification passes.**
   `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER` must remain false throughout finalization and commissioning.

## Closure sprints

### F1 — Physical topology EV / M11 / M13
- Add explicit relay mapping for EV, M11 and M13.
- Extend driver status and manual control.
- Define fail-safe state: M11 OFF, M13 OFF, EV CLOSED.
- Add unit tests for mapping, interlocks and all-off behavior.

### F2 — Certified hydraulic sequence
- Implement real START sequence with feedback checks and configurable delays.
- Implement STOP / emergency sequence with deterministic safe ordering.
- Abort and rollback to safe state on any write/readback failure.
- Add sequence integration tests.

### F3 — Thermal safety fail-closed
- Require valid fresh temperature/humidity/surface data on real hardware.
- Block START on missing/stale/invalid thermal data.
- Trigger safe stop on condensation margin violation during RUNNING.
- Test dew-point margin and sensor-loss scenarios.

### F4 — Field certification and release
- Upgrade hardware readiness and dry-run for EV/M11/M13.
- Physical relay-by-relay commissioning with autonomous mode disabled.
- Validate Home Assistant live telemetry and UI states.
- Run complete regression suite.
- Merge release candidate to `main` only after field certification passes.

## Release rule

No new Brain, Digital Twin, prediction or UI feature work until F1–F4 are closed. The objective is now operational completion and safety certification, not feature expansion.
