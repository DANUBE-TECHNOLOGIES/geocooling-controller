# GeoCooling — Physical sensor identification

## Goal

Map the six GeoCooling telemetry roles to the real physical probes without ever inferring identity from temperature alone.

Roles:

- `GEOCOOLING_SURFACE_SENSOR` — floor surface temperature;
- `GEOCOOLING_FLOOR_SUPPLY_SENSOR` — floor-loop supply;
- `GEOCOOLING_FLOOR_RETURN_SENSOR` — floor-loop return;
- `GEOCOOLING_SOURCE_INLET_SENSOR` — source/well inlet;
- `GEOCOOLING_SOURCE_OUTLET_SENSOR` — source/well outlet;
- `GEOCOOLING_FLOW_SENSOR` — hydraulic flow sensor exposing `flow`.

## Safety rules

1. Keep `GEOCOOLING_HARDWARE_ARMED=false`.
2. Keep `GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false`.
3. Keep `GEOCOOLING_AUTOPILOT_ENABLED=false`.
4. Keep `GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false`.
5. Do not energize EV, M11 or M13 during identification.
6. Do not assign a role only because a probe value looks plausible.
7. Record the physical cable/probe identity before editing `.env`.

The telemetry-health API explicitly reports `auto_assignment_allowed=false` and `physical_confirmation_required=true`.

## Step 1 — restore upstream telemetry

The endpoint

`/geocooling/brain-v2/integration/home-assistant/telemetry-health`

must report `upstream_state=OBSERVED` and at least one `candidate_sensors` entry before mapping begins.

If it reports `UPSTREAM_EMPTY`, repair WT32/ESPHome -> MQTT first. Changing `.env` cannot repair an absent upstream source.

## Step 2 — establish the candidate matrix

For every item in `candidate_sensors`, record:

- `sensor_name`;
- metric (`temperature` or `flow`);
- MQTT topic;
- physical cable / probe label if known.

No candidate is assigned automatically.

## Step 3 — identify one probe at a time

Use a passive physical perturbation that cannot affect the hydraulic installation, for example briefly warming only the accessible probe body/cable end with a hand when safe and practical. Observe which candidate changes while the other candidates remain stable.

Do not heat pipework, operate valves, start pumps, disconnect live electrical equipment, or alter the heat-pump controller as part of identification.

Repeat independently for each accessible probe and record the correspondence.

## Step 4 — configure one role at a time

After physical confirmation, set exactly one corresponding environment variable to the confirmed `sensor_name`. Restart/redeploy only the backend if required by the deployment method.

Then verify the role state becomes `OK` in telemetry health. If it becomes:

- `SOURCE_ABSENT`: the configured name is not observed;
- `METRIC_ABSENT`: the source exists but does not expose the required metric;
- `STALE`: the last measurement exceeds `GEOCOOLING_SENSOR_STALE_SECONDS`;
- `UNSET`: the environment variable was not loaded;
- `OK`: source, metric and freshness are valid.

Do not configure the next role until the current one behaves as expected.

## Step 5 — final six-role gate

Before any real hydraulic commissioning, require:

- `ready=true`;
- `fail_closed=false`;
- `configured_role_count=6`;
- all six role states equal `OK`;
- `physical_confirmation_required=true` remains part of the API contract;
- hardware and autopilot safety flags remain disabled until the separate actuator certification.

## Flow sensor

A temperature probe can never satisfy the `flow` role. `GEOCOOLING_FLOW_SENSOR` must point to a source exposing the `flow` metric. If no real flow sensor is installed, leave the role unmapped and keep `GEOCOOLING_FLOW_RATE_L_MIN=0`; transferred power/energy must remain unknown rather than fabricated.
