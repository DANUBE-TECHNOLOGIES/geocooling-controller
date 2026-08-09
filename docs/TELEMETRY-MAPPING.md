# GeoCooling telemetry mapping

## Purpose

The controller stores generic MQTT measurements in `sensor_measurements` and builds a GeoCooling thermal snapshot every aggregation cycle.

Indoor temperature/humidity and outdoor temperature are derived by the existing building aggregation. Hydraulic and condensation-critical measurements are deliberately mapped explicitly so a sensor can never be assigned to the wrong physical role only because its value looks plausible.

## Required safety mapping

`GEOCOOLING_SURFACE_SENSOR` identifies the floor/surface temperature used by condensation safety.

For a real driver this measurement is mandatory. Missing or stale surface temperature keeps thermal safety fail-closed and blocks START.

## Hydraulic mappings

- `GEOCOOLING_FLOOR_SUPPLY_SENSOR`: floor-loop supply temperature.
- `GEOCOOLING_FLOOR_RETURN_SENSOR`: floor-loop return temperature.
- `GEOCOOLING_SOURCE_INLET_SENSOR`: source/well inlet temperature.
- `GEOCOOLING_SOURCE_OUTLET_SENSOR`: source/well outlet temperature.
- `GEOCOOLING_FLOW_SENSOR`: hydraulic flow sensor exposing the `flow` metric.

Each value must equal the exact `sensor_name` stored by the MQTT collector. The read-only endpoint `/sensors/latest` exposes the observed names, metrics, values and MQTT topics.

## Discovery workflow

Run `scripts/audit/geocooling-telemetry-mapping.sh` on a deployed controller. The script only calls `/sensors/latest`; it does not publish MQTT messages and does not command the Waveshare.

The script lists all observed sensor names and proposes candidates only when names contain clear role hints. Candidate output is advisory. Confirm the physical sensor before setting any mapping.

## Flow fallback

`GEOCOOLING_FLOW_RATE_L_MIN` may define a fixed fallback flow when no real flow measurement is available. The safe default is `0`, which means cooling power and transferred energy remain unknown rather than fabricated.

## Release gate

Before autonomous real-driver operation:

1. confirm the physical identity of the surface sensor;
2. confirm the floor supply/return identities;
3. confirm source inlet/outlet identities;
4. configure a real flow sensor or explicitly accept that cooling power cannot be measured;
5. verify `/geocooling/status` reports fresh non-null values for every configured sensor;
6. verify condensation safety reports a real dew point and margin;
7. keep `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false` until field certification is complete.
