# GeoCooling — Hardware Command Path Audit

## Objective

Verify that every path capable of producing a positive physical command is controlled by the commissioning policy and that safe-state actions can never be blocked by a degraded readiness state.

## Audited command paths

### 1. Normal controller START

Path:

`API / Brain / manual command -> GeoCoolingController.request_start()`

Status: **GATED**

Real drivers are rejected unless the Commissioning Gate is `READY_FOR_RELEASE`. Simulation remains available. A commissioning/DB failure is fail-closed before EV is opened.

### 2. Brain command bridge

Path:

`brain decision -> GeoCoolingControllerCommandBridge -> controller.request_start()`

Status: **GATED THROUGH CONTROLLER**

The bridge maps positive Brain decisions to `request_start`. It does not call the Waveshare driver directly. The bridge is additionally disarmed by default.

### 3. Manual EV / pump control

Path:

`/geocooling/manual/valve/open` or `/manual/pump/start` -> HardwareManualControl`

Status: **GATED**

- manual arm: allowed only from `FIELD_CERTIFICATION_REQUIRED`;
- positive manual EV/pump commands: allowed only at `READY_FOR_RELEASE`;
- pump stop, valve close, safe-stop and disarm: always available.

### 4. Physical commissioning tests

Path:

`/geocooling/commissioning/test/* -> GeoCoolingCommissioningTestManager`

Status: **GATED**

A real test requires all historical interlocks plus the central activation policy. The commissioning-test window opens only at `FIELD_CERTIFICATION_REQUIRED` or `READY_FOR_RELEASE`. Any readiness-service failure blocks the test. Simulation does not depend on this gate.

### 5. Arbitrary Waveshare relay ON diagnostic route

Path:

`/geocooling/relay/{relay_id}/on -> WaveshareModbusDriver.set_relay(..., True)`

Status: **GATED**

This historical route was a direct bypass because it did not use `HardwareManualControl` or `request_start`. `set_relay(..., True)` is now policy-gated and requires `READY_FOR_RELEASE`. Arbitrary relay OFF remains available regardless of gate state.

Dedicated EV and M11/M13 methods are not affected by the arbitrary-relay gate because they are required by the controlled field-certification path.

### 6. All-relays OFF / safe-state routes

Paths include:

- `set_relay(..., False)`;
- `all_off()`;
- `force_safe_state()`;
- pump stop;
- EV close;
- manual disarm.

Status: **ALWAYS AVAILABLE BY POLICY**

A failed commissioning/readiness dependency must never prevent a shutdown.

### 7. Water Test Framework

Status: **SIMULATION ONLY**

The framework declares `physical_commands_allowed = false`, uses digital-twin simulation actions and requires the controller command bridge to remain disarmed. No physical command path was found in this framework.

### 8. Execution Supervisor

Status: **PASSIVE**

The supervisor consumes `controller.action` events and builds execution lifecycle/history. It does not execute physical commands.

### 9. Industrial Hardening

Status: **PASSIVE / SAFE-STATE ONLY**

The hardening layer probes component state, maintains lifecycle/heartbeat data and may disarm hardware when critical conditions are detected. It does not arm hardware or issue positive actuator commands.

## Central policy matrix

| Path | Before field certification | FIELD_CERTIFICATION_REQUIRED | READY_FOR_RELEASE |
|---|---:|---:|---:|
| Normal controller START | Blocked | Blocked | Allowed |
| Manual arm | Blocked | Allowed | Allowed |
| Manual EV/pump ON | Blocked | Blocked | Allowed |
| Physical commissioning tests | Blocked | Allowed | Allowed |
| Arbitrary relay ON | Blocked | Blocked | Allowed |
| STOP / safe-state actions | Allowed | Allowed | Allowed |

## Fail-closed requirements

Positive commands must be rejected when any of the following cannot be determined:

- commissioning readiness;
- telemetry readiness required by commissioning;
- policy state;
- device readiness for commissioning tests.

Shutdown paths must remain available under the same failures.

## Software freeze criteria

The software can be considered freeze-ready when:

1. RC1/RC2/RC3 regression is green;
2. F2/F3/F4 safety regression is green;
3. telemetry, commissioning, activation-policy and release-readiness tests are green;
4. manual-control, commissioning-test and arbitrary-relay bypass tests are green;
5. frontend lint and production build are green;
6. no newly discovered positive hardware route bypasses these gates.

## Remaining non-software blockers

The software audit does not replace field commissioning. The known blockers are:

- restore WT32/ESPHome -> MQTT DS18B20 telemetry;
- physically identify the hydraulic sensors;
- configure and validate all six telemetry roles;
- certify EV direction and safe closure;
- certify shared M11/M13 actuation and interlock with EV;
- confirm safe-stop behavior on the real installation;
- mark field certification complete only after observation.

See `FINAL_RELEASE_PLAN.md` for the exact field sequence.
