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

1. **F2 hydraulic hardening is code-complete but still requires executed regression and field certification.**
   START now requires `OFF`, `FAULT` and `EMERGENCY_STOP` require an explicit reset, thermal safety is re-checked immediately before M11+M13 are energized, and failure paths force a deterministic in-memory `FAULT` after best-effort hardware rollback.

2. **F3 condensation fail-closed is code-complete but still requires executed regression and field certification.**
   Real drivers now require a fresh thermal snapshot containing indoor temperature, indoor humidity and floor-surface temperature. Missing, invalid or stale data blocks START and becomes unsafe during RUNNING.

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

### F2 — Certified hydraulic sequence — CODE COMPLETE / CERTIFICATION PENDING
- START sequence retained: EV OPEN -> feedback -> delay -> M11+M13 ON -> feedback -> RUNNING.
- STOP sequence retained: M11+M13 OFF -> feedback -> delay -> EV CLOSED -> feedback -> OFF.
- START is rejected from `FAULT` and `EMERGENCY_STOP`; explicit reset required.
- Controller lock is retained through the final START delegation to close the OFF-to-FAULT race window.
- Thermal safety is re-evaluated immediately before M11+M13 is energized.
- Fault handling performs best-effort safe rollback and forces deterministic `FAULT` state even if rollback telemetry/persistence also fails.
- Focused regression tests added in `backend/tests/test_f2_controller_hydraulic_hardening.py` plus existing C019/Waveshare tests.
- GitHub Actions workflow added for the F2/F3 regression suite, but no run is currently visible through the connected GitHub integration; executed validation remains pending.

### F3 — Thermal safety fail-closed — CODE COMPLETE / CERTIFICATION PENDING
- Non-simulation drivers require a real thermal snapshot.
- Indoor temperature, indoor humidity and surface temperature are mandatory.
- Thermal freshness is enforced with `GEOCOOLING_THERMAL_MAX_AGE_SECONDS` (default 180 s, minimum 5 s).
- Missing, invalid, future-skewed or stale data returns an unsafe decision and blocks START.
- Dew-point margin continues to be evaluated by `GeoCoolingSafetyManager` once data is complete and fresh.
- During RUNNING, sensor loss/staleness or condensation risk enters the existing safe STOP sequence.
- Focused regression tests added in `backend/tests/test_f3_thermal_fail_closed.py`.
- Executed regression and physical validation remain pending.

### F4 — Field certification and release — IN PROGRESS
- Update readiness terminology for EV + M11/M13.
- Physical relay-by-relay commissioning with autonomous mode disabled.
- Validate Home Assistant live telemetry and UI states.
- Run complete regression suite.
- Merge release candidate to `main` only after field certification passes.

## Release rule

No new Brain, Digital Twin, prediction or UI feature work until F2–F4 are closed. The objective is operational completion and safety certification, not feature expansion.
