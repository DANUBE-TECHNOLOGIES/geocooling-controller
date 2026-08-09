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

## Telemetry health states

`backend/app/geocooling/telemetry_health.py` provides a fail-closed classification for every GeoCooling telemetry role:

- `UNSET`: the role has no configured sensor name;
- `SOURCE_ABSENT`: a sensor name is configured but that source has never been observed;
- `METRIC_ABSENT`: the source exists but does not expose the required `temperature` or `flow` metric;
- `STALE`: the metric exists but is older than the configured freshness threshold;
- `OK`: the required metric is present and fresh.

The aggregate report also uses `UPSTREAM_EMPTY` when `/sensors/latest` contains no hydraulic, surface or flow candidate at all. This distinction is important: changing `.env` mappings cannot repair `UPSTREAM_EMPTY`; the WT32/ESPHome -> MQTT path must first be restored.

All non-`OK` states remain fail-closed for autonomous real-driver operation.

## Discovery workflow

Run `scripts/audit/geocooling-telemetry-mapping.sh` on a deployed controller. The script only calls `/sensors/latest`; it does not publish MQTT messages and does not command the Waveshare.

The script first reports upstream health. If it reports `UPSTREAM_EMPTY`, run `scripts/audit/geocooling-esphome-mqtt-diagnostic.sh`. That diagnostic is also passive: it inspects running containers and ESPHome logs and subscribes to MQTT for a short observation window. It never publishes MQTT, writes Modbus, or commands a relay.

Only after upstream telemetry is visible should sensor roles be mapped. The mapping audit lists observed sensor names and proposes candidates only when names contain clear role hints. Candidate output is advisory. Confirm the physical sensor before setting any mapping.

## Flow fallback

`GEOCOOLING_FLOW_RATE_L_MIN` may define a fixed fallback flow when no real flow measurement is available. The safe default is `0`, which means cooling power and transferred energy remain unknown rather than fabricated.

## Release gate

Before autonomous real-driver operation:

1. restore and verify WT32/ESPHome -> MQTT telemetry;
2. confirm the physical identity of the surface sensor;
3. confirm the floor supply/return identities;
4. confirm source inlet/outlet identities;
5. configure a real flow sensor or explicitly accept that cooling power cannot be measured;
6. verify every required telemetry role is `OK` and fresh;
7. verify `/geocooling/status` reports fresh non-null values for every configured sensor;
8. verify condensation safety reports a real dew point and margin;
9. keep `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false` until field certification is complete.
