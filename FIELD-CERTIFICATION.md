# GeoCooling — F4 Field Certification

Date: 2026-08-08
Branch: `feature/geocooling-ui-v1`

## Safety rule

Autonomous control of the real Waveshare driver MUST remain disabled during this procedure.
Do not set `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=true`.

The physical topology to certify is:

- EV: electrovalve, one Waveshare output.
- M11+M13: both circulators, one shared Waveshare output.
- Certified safe state: M11+M13 OFF, then EV CLOSED.

## Gate A — Static configuration

Pass only if all are true:

- driver is `waveshare_modbus`;
- Modbus connection is healthy;
- EV and M11+M13 map to two different relay numbers;
- write verification is enabled;
- hardware starts DISARMED after maintenance/restart;
- autonomous real-driver execution is disabled.

Record EV relay: ______
Record M11+M13 relay: ______

## Gate B — Safe state while DISARMED

1. Confirm controller state is OFF.
2. Keep hardware DISARMED.
3. Request SAFE_STOP.
4. Physically verify M11 is stopped.
5. Physically verify M13 is stopped.
6. Physically verify EV is closed.
7. Verify software feedback reports M11+M13 OFF and EV CLOSED.

Result: PASS / FAIL

## Gate C — Manual EV certification

1. Confirm M11+M13 are OFF.
2. Arm hardware using the explicit manual confirmation flow.
3. Command EV OPEN only.
4. Verify the expected relay changes and no other relay changes.
5. Physically verify EV opens.
6. Command EV CLOSED.
7. Physically verify EV closes.
8. DISARM and verify safe state again.

Result: PASS / FAIL

## Gate D — Manual M11+M13 certification

1. Arm hardware.
2. Open EV and verify it is physically open.
3. Command M11+M13 ON.
4. Verify both M11 and M13 run.
5. Verify no unrelated Waveshare relay changes.
6. Attempting to close EV while M11+M13 run must be refused.
7. Command M11+M13 OFF and verify both circulators stop.
8. Close EV and verify physical closure.
9. DISARM.

Result: PASS / FAIL

## Gate E — Thermal telemetry

With autonomous mode still disabled, verify live values are present and refresh continuously:

- indoor temperature;
- indoor relative humidity;
- floor surface temperature;
- floor supply temperature;
- floor return temperature;
- source inlet temperature;
- source outlet temperature;
- flow rate when available.

For the real driver, indoor temperature, humidity and floor surface temperature must never be treated as optional. Stale or missing mandatory values must make thermal safety unsafe.

Result: PASS / FAIL

## Gate F — Home Assistant / UI

Verify the displayed state matches the controller and physical installation for:

- GeoCooling available;
- simulation/real-driver mode;
- EV state;
- M11+M13 state;
- safety state;
- controller state OFF / STARTING / RUNNING / STOPPING / FAULT;
- thermal values and condensation safety information.

Result: PASS / FAIL

## Gate G — Controlled sequence

Only after Gates A-F pass:

1. Keep autonomous real-driver execution disabled.
2. Start one supervised controller cycle manually.
3. Verify order: EV OPEN -> feedback -> delay -> M11+M13 ON -> feedback -> RUNNING.
4. Request stop.
5. Verify order: M11+M13 OFF -> feedback -> drain delay -> EV CLOSED -> feedback -> OFF.
6. Verify a thermal safety loss produces a safe stop.
7. Verify a hardware readiness loss produces FAULT/safe rollback as designed.
8. Verify START from FAULT is refused until explicit reset.

Result: PASS / FAIL

## Gate H — Regression and release

Before merge to `main`:

- run the complete backend pytest suite;
- run F2/F3/F4 focused tests;
- record the exact commit SHA tested;
- confirm all field gates PASS;
- confirm no unresolved FAULT or relay mismatch exists;
- keep autonomous real-driver permission disabled unless a separate production-enable decision is explicitly made after certification.

Tested commit: ________________________________
Backend tests: PASS / FAIL
Field certification: PASS / FAIL
Certified by: _________________________________
Date/time: ____________________________________

## Release decision

`main` merge is forbidden while any gate is FAIL or untested.
