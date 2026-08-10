# GeoCooling — Software Freeze Candidate

## Decision

The `feature/geocooling-ui-v1` branch is a **software freeze candidate** once the release-candidate workflow is green after the hardware-command-path audit.

This does **not** mean the installation is commissioned. It means further software feature work should stop unless field testing reveals a defect.

## What is frozen

The candidate contains:

- RC1 / RC2 / RC3 decision, scenario and prediction stack;
- F2 hydraulic sequencing hardening;
- F3 condensation/thermal fail-closed safety;
- F4 device readiness;
- Waveshare Modbus driver with EV + shared M11/M13 topology;
- telemetry-health classification and sensor mapping diagnostics;
- commissioning readiness gate;
- hardware activation policy;
- normal START commissioning gate;
- manual hardware commissioning gate;
- physical commissioning-test gate;
- arbitrary direct-relay activation gate;
- Home Assistant fail-safe telemetry bridge;
- Commissioning and Telemetry UI;
- consolidated release-readiness endpoint;
- final field-release procedure.

## Positive hardware paths now covered

1. normal controller START;
2. Brain command bridge START;
3. manual command-manager START;
4. manual EV OPEN;
5. manual M11/M13 START;
6. physical EV commissioning test;
7. physical M11/M13 commissioning test;
8. arbitrary Waveshare relay ON endpoint.

Every positive path is blocked until the appropriate commissioning stage. Safety-state paths remain available.

## Verified historical paths

- Brain command bridge delegates to controller methods and therefore inherits the central START gate.
- Manual command execution delegates START to `request_start()`.
- Execution Supervisor is event-observation only.
- Water Test Framework is simulation-only.
- Industrial Hardening is passive and may only drive the system toward a safer state (for example disarm).

## Known physical blockers

Software freeze must not be confused with operational readiness. The remaining blockers are physical/runtime:

1. WT32 / ESPHome DS18B20 telemetry is not currently visible in MQTT ingestion.
2. Hydraulic sensor identities are not yet physically confirmed.
3. The six telemetry roles are not yet all mapped and `OK`.
4. EV is not yet field-certified.
5. M11/M13 are not yet field-certified through their shared actuator path.
6. Field safe-stop behavior has not yet been observed on the real installation.

## Change policy after freeze

After software freeze, changes should be limited to:

- defects demonstrated by field testing;
- missing telemetry adapter needed for the actual WT32 topics;
- safety defects;
- deployment/runtime compatibility fixes.

Do not add new control features, automation strategies or UI scope before completing field commissioning.

## Release transition

Follow `FINAL_RELEASE_PLAN.md`.

The final runtime gate is:

`/geocooling/brain-v2/integration/home-assistant/release-readiness`

A deployable release requires `READY_FOR_DEPLOYMENT` with no blockers and safe runtime defaults.
