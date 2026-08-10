# GeoCooling — Finalization audit

Date: 2026-08-10

## Release candidate baseline

Current reference branch: `feature/geocooling-ui-v1`.

Software-finalization baseline commit before this audit update: `db44667d3e1ec0840589409982aec228e8d877c2`.

GitHub is the source of truth for the consolidated RC1, RC2, RC3, F2, F3 and F4 software stack. Runtime-specific `.env` configuration remains local and is not versioned.

## Final software status

**SOFTWARE FINALIZATION: COMPLETE**

The repository is now considered functionally closed for the current GeoCooling scope. No additional Brain, Digital Twin, prediction, UI expansion or unrelated feature development is required before field certification.

The remaining blockers are intentionally external to software completion:

- final physical wiring of EV and M11+M13;
- confirmation of real relay assignments;
- completion of live hydraulic/surface telemetry mappings;
- Home Assistant/UI live verification with the final sensor mappings;
- supervised physical Gates C through G;
- final Gate H full-regression run on the exact field-certified commit.

Until those gates pass, real autonomous execution remains forbidden and the system must remain fail-closed.

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
- Real-driver START path remains protected by commissioning readiness.
- Real-driver thermal safety remains fail-closed on missing, stale, future-skewed or invalid mandatory telemetry.
- Hydraulic role mapping remains explicit; automatic physical-role assignment is forbidden.
- Surface safety supports a real surface sensor or the explicitly selected conservative floor-loop estimate path.

## Remaining field-certification blockers

1. **Physical actuator certification is deferred until wiring is complete.**
   EV and M11+M13 are not yet connected to their final actuators. Gate C/D/G physical commissioning therefore remains pending.

2. **Surface-temperature mapping must be confirmed in deployed telemetry.**
   F3 correctly remains fail-closed without a fresh floor-surface reference. Use either the confirmed physical sensor through `GEOCOOLING_SURFACE_SENSOR` or the explicitly selected conservative `floor_loop_estimate` mode once floor supply/return telemetry is certified.

3. **Hydraulic telemetry mapping must be completed.**
   Floor supply/return, source inlet/outlet and optional flow depend on explicit sensor mappings. See `docs/TELEMETRY-MAPPING.md` and `scripts/audit/geocooling-telemetry-mapping.sh`.

4. **Home Assistant/UI must be validated with the completed telemetry.**
   The frontend snapshot model exposes surface temperature, flow rate, dew point, condensation margin and safety reason in addition to the hydraulic temperatures.

5. **Autonomous real-driver execution must remain disabled until field certification passes.**
   `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER` must remain false throughout finalization and commissioning.

## Closure sprints

### F1 — Physical topology validation — CLOSED
- Confirmed topology: EV on one output; M11 + M13 together on one output.
- Existing `valve + pump` driver topology retained.
- Fail-safe state remains: M11+M13 OFF, then EV CLOSED.
- No third actuator implementation required.

### F2 — Certified hydraulic sequence — SOFTWARE CLOSED / FIELD CERTIFICATION PENDING
- START sequence: EV OPEN -> feedback -> delay -> M11+M13 ON -> feedback -> RUNNING.
- STOP sequence: M11+M13 OFF -> feedback -> delay -> EV CLOSED -> feedback -> OFF.
- START is rejected from `FAULT` and `EMERGENCY_STOP`; explicit reset required.
- Thermal safety is re-evaluated immediately before M11+M13 is energized.
- Fault handling performs best-effort safe rollback and forces deterministic `FAULT` state even if rollback telemetry/persistence also fails.
- Focused regression tests executed successfully during consolidation.
- Physical execution remains pending final actuator wiring.

### F3 — Thermal safety fail-closed — SOFTWARE CLOSED / SENSOR MAPPING PENDING
- Non-simulation drivers require a real thermal snapshot.
- Indoor temperature, indoor humidity and a valid surface reference are mandatory.
- Thermal freshness is enforced with `GEOCOOLING_THERMAL_MAX_AGE_SECONDS` (default 180 s, minimum 5 s).
- Missing, invalid, future-skewed or stale data blocks START and becomes unsafe during RUNNING.
- Dew-point margin is evaluated only when data is complete and fresh.
- Telemetry health classifies explicit hydraulic roles and never auto-assigns physical sensors.
- Focused regression tests executed successfully during consolidation.

### F4 — Field certification and release — SOFTWARE PREPARATION CLOSED / FIELD EXECUTION PENDING
- Readiness terminology aligned with EV + M11/M13.
- Gate A/B baseline completed with real Waveshare connected and disarmed.
- Telemetry mapping contract/documentation added.
- Frontend thermal-safety snapshot contract expanded.
- Gate C/D/G physical actuator commissioning deferred until EV and M11/M13 are wired.
- Home Assistant/UI live validation remains pending completed telemetry.
- Gate H remains pending the exact field-certified commit and full regression run.
- Merge to `main` remains forbidden until all physical certification gates pass.

## Operational freeze rule

From this point until field certification is complete:

- do not add unrelated features;
- do not enable autonomous real-driver execution;
- do not weaken telemetry freshness or condensation safety checks;
- do not bypass commissioning readiness;
- do not infer physical sensor roles automatically;
- only accept changes required to correct a verified certification defect.

## Release rule

The software scope is finalized, but production release is **not** certified yet.

Merge to `main` and autonomous real-driver enablement are forbidden until FIELD-CERTIFICATION.md Gates A-H are all PASS and the exact tested commit SHA is recorded.
