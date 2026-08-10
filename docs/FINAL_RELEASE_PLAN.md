# GeoCooling — Final Release Plan

This document is the release path for the GeoCooling controller after the RC1/RC2/RC3 consolidation and safety hardening.

## 1. Current software baseline

The release candidate must remain green on:

- RC1 / RC2 / RC3 regression suite;
- F2 hydraulic hardening;
- F3 thermal fail-closed safety;
- F4 device readiness;
- telemetry-health classification;
- commissioning readiness;
- hardware activation policy;
- manual hardware commissioning gate;
- physical commissioning-test manager gate;
- Home Assistant fail-safe bridge;
- frontend lint and production build.

No release decision may be based only on the software CI. Physical commissioning is a distinct gate.

## 2. Mandatory safe defaults before field work

The VM must start with these values disabled:

```env
GEOCOOLING_HARDWARE_ARMED=false
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
GEOCOOLING_AUTOPILOT_ENABLED=false
GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false
GEOCOOLING_COMMISSIONING_TESTS_ENABLED=false
GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED=false
GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED=false
```

The release-readiness endpoint treats active positive-control flags as a deployment blocker.

## 3. Restore the sensor upstream chain

Before any physical actuator test:

1. WT32 / ESPHome must be online.
2. DS18B20 measurements must be visible on MQTT.
3. `/sensors/latest` must contain the hydraulic sensor measurements.
4. `/geocooling/brain-v2/integration/home-assistant/telemetry-health` must no longer report `UPSTREAM_EMPTY`.

Use only passive diagnostics during this phase.

## 4. Physically identify sensors

No sensor may be auto-assigned from temperature alone.

Confirm the physical identity of each role:

- surface temperature;
- floor supply;
- floor return;
- source inlet;
- source outlet;
- flow.

Then configure the matching `GEOCOOLING_*_SENSOR` values and confirm:

```env
GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED=true
```

The telemetry-health endpoint must report all six roles `OK` and the commissioning state must reach `FIELD_CERTIFICATION_REQUIRED`.

## 5. Open the physical commissioning window

Only when the commissioning state is `FIELD_CERTIFICATION_REQUIRED`:

1. Keep the normal controller start blocked.
2. Keep autopilot disabled.
3. Enable temporary commissioning tests only:

```env
GEOCOOLING_COMMISSIONING_TESTS_ENABLED=true
```

4. Arm the Waveshare through the explicitly confirmed manual-arm path.
5. Run a short EV test first.
6. Return EV to the safe state.
7. Run the M11/M13 test only with EV confirmed open by the driver interlock.
8. Cancel or safe-stop immediately on any mismatch.
9. Disarm the hardware again after the tests.

The commissioning-test manager and manual hardware control are both policy-gated. Safety stop actions remain available regardless of commissioning state.

## 6. Field certification

Field certification is a human confirmation after observing correct physical behavior:

- EV direction is correct;
- EV closes on stop;
- M11/M13 run only after EV opening;
- M11/M13 stop before EV closure;
- feedback/status is coherent;
- no unexpected relay is energized;
- thermal telemetry remains valid during the test;
- emergency/safe stop returns all outputs to OFF.

Only after those checks:

```env
GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED=true
```

The commissioning endpoint must then report `READY_FOR_RELEASE`.

## 7. Return to safe deployment defaults

Before deploying the final release, return positive runtime-control flags to false:

```env
GEOCOOLING_HARDWARE_ARMED=false
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
GEOCOOLING_AUTOPILOT_ENABLED=false
GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false
GEOCOOLING_COMMISSIONING_TESTS_ENABLED=false
```

The endpoint:

`/geocooling/brain-v2/integration/home-assistant/release-readiness`

must report:

- `commissioning_state = READY_FOR_RELEASE`;
- `runtime_safe_defaults = true`;
- `deployment_ready = true`;
- `state = READY_FOR_DEPLOYMENT`;
- no blockers.

## 8. Final deployment

After the release is deployed and revalidated with hardware still safe/disarmed, runtime activation may be performed deliberately according to the normal operating procedure.

Never combine deployment, hardware arming and autopilot activation into one uncontrolled step.

## 9. Rollback rule

Any regression in telemetry, driver readiness, condensation safety, relay feedback or commissioning status requires:

1. autopilot OFF;
2. pump OFF;
3. EV closed;
4. hardware disarmed;
5. return to diagnostic mode;
6. no reactivation until the failing gate is green again.
