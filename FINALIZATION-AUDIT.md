# GeoCooling — Finalization audit

Date: 2026-08-09

## Release candidate baseline

Current reference branch: `feature/geocooling-ui-v1`.

GitHub is now the source of truth for RC1, RC2, RC3, F2, F3 and F4 code. Runtime-specific `.env` configuration is local and not versioned.

## Confirmed physical topology

The installation uses **two logical outputs** on the Waveshare controller:

- **EV** — electrovalve.
- **M11 + M13** — both circulators are commanded together by the same actuator/output.

Therefore the existing `valve + pump` software model matches the real installation topology. No third independent relay is required.

## Validation already completed

- Waveshare Modbus reachable on the deployed controller.
- Read-only relay status confirmed all eight relays OFF during commissioning baseline.
- Hardware kept DISARMED.
- Real hydraulic sequence kept disabled.
- Autonomous real-driver execution kept disabled.
- Backend rebuilt from the consolidated GitHub source and returned healthy.
- Runtime route validation for the consolidated RC1/RC2/RC3 stack completed.
- Focused RC1, RC2, RC3, F2, F3 and F4 regression groups were executed successfully during integration.
- Gate A / Gate B software and safe-state baseline completed.

## Remaining blocking gaps before real autonomous operation

1. **Physical actuator certification is deferred until wiring is complete.**
   EV and M11+M13 are not yet connected to their final actuators. Gate C/D/G physical commissioning therefore remains pending.

2. **Surface-temperature mapping is still missing in the deployed telemetry.**
   F3 correctly remains fail-closed without a fresh floor-surface temperature. `GEOCOOLING_SURFACE_SENSOR` must be mapped to the confirmed physical sensor before START can be certified.

3. **Hydraulic telemetry mapping must be completed.**
   Floor supply/return, source inlet/outlet and flow are supported by the thermal engine but depend on explicit sensor mappings. See `docs/TELEMETRY-MAPPING.md` and `scripts/audit/geocooling-telemetry-mapping.sh`.

4. **Home Assistant/UI must be validated with the completed telemetry.**
   The frontend snapshot model now exposes surface temperature, flow rate, dew point, condensation margin and safety reason in addition to the existing hydraulic temperatures.

5. **Autonomous real-driver execution must remain disabled until field certification passes.**
   `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER` must remain false throughout finalization and commissioning.

## Closure sprints

### F1 — Physical topology validation — CLOSED
- Confirmed topology: EV on one output; M11 + M13 together on one output.
- Existing `valve + pump` driver topology retained.
- Fail-safe state remains: M11+M13 OFF, then EV CLOSED.
- No third actuator implementation required.

### F2 — Certified hydraulic sequence — CODE + REGRESSION COMPLETE / FIELD CERTIFICATION PENDING
- START sequence: EV OPEN -> feedback -> delay -> M11+M13 ON -> feedback -> RUNNING.
- STOP sequence: M11+M13 OFF -> feedback -> delay -> EV CLOSED -> feedback -> OFF.
- START is rejected from `FAULT` and `EMERGENCY_STOP`; explicit reset required.
- Thermal safety is re-evaluated immediately before M11+M13 is energized.
- Fault handling performs best-effort safe rollback and forces deterministic `FAULT` state even if rollback telemetry/persistence also fails.
- Focused regression tests executed successfully during consolidation.
- Physical execution remains pending final actuator wiring.

### F3 — Thermal safety fail-closed — CODE + REGRESSION COMPLETE / SENSOR MAPPING PENDING
- Non-simulation drivers require a real thermal snapshot.
- Indoor temperature, indoor humidity and surface temperature are mandatory.
- Thermal freshness is enforced with `GEOCOOLING_THERMAL_MAX_AGE_SECONDS` (default 180 s, minimum 5 s).
- Missing, invalid, future-skewed or stale data blocks START and becomes unsafe during RUNNING.
- Dew-point margin is evaluated only when data is complete and fresh.
- Focused regression tests executed successfully during consolidation.
- Current deployed blocker: floor-surface sensor mapping not yet configured.

### F4 — Field certification and release — IN PROGRESS
- Readiness terminology updated for EV + M11/M13.
- Gate A/B baseline completed with real Waveshare connected and disarmed.
- Telemetry mapping contract/documentation added.
- Frontend thermal-safety snapshot contract expanded.
- Gate C/D/G physical actuator commissioning deferred until EV and M11/M13 are wired.
- Home Assistant/UI live validation remains pending completed telemetry.
- Merge to `main` remains forbidden until all physical certification gates pass.

## Release rule

No new Brain, Digital Twin, prediction or unrelated UI feature work until F2–F4 are closed. The objective is operational completion and safety certification, not feature expansion.
