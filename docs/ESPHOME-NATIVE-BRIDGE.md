# ESPHome Native API telemetry bridge

## Purpose

The WT32 (`sbc-core`, currently `192.168.10.105`) already exposes the four
hydraulic DS18B20 sensors through the encrypted ESPHome Native API on TCP/6053.
The firmware is healthy and must not be changed merely to satisfy the server
telemetry pipeline.

The `esphome-bridge` service therefore subscribes read-only to ESPHome entity
states and writes approved measurements into the existing
`sensor_measurements` table.

## Confirmed physical sensors

| ESPHome entity | DS18B20 address | Canonical sensor_name |
|---|---|---|
| GeoCooling - Arrivée Forage | `0x6b0000001289f028` | `gc_source_inlet` |
| GeoCooling - Retour Forage | `0x7c00000014ab2828` | `gc_source_outlet` |
| GeoCooling - Départ Plancher | `0xeb000000229bf128` | `gc_floor_supply` |
| GeoCooling - Retour Plancher | `0xf50000006fff6528` | `gc_floor_return` |

These four identities were confirmed from the deployed ESPHome configuration
and live logs. They are not inferred from temperature values.

## Safety properties

The bridge:

- uses `aioesphomeapi.APIClient` only for connection, entity listing and state
  subscription;
- exposes no service/button/switch command method;
- accepts only the four exact entity names above;
- accepts only finite numeric states;
- writes only `metric=temperature` rows;
- never publishes MQTT;
- never writes controller state;
- never touches Waveshare, EV, M11 or M13;
- reconnects automatically after API loss.

The synthetic `mqtt_topic` database field is populated with an
`esphome-native://...` URI because the legacy schema requires a non-null source
identifier even for non-MQTT telemetry.

## Runtime configuration

Required local `.env` values:

```text
ESPHOME_BRIDGE_HOST=192.168.10.105
ESPHOME_BRIDGE_PORT=6053
ESPHOME_BRIDGE_NOISE_PSK=<local sbc_api_key secret>
ESPHOME_BRIDGE_RECONNECT_SECONDS=5

GEOCOOLING_SOURCE_INLET_SENSOR=gc_source_inlet
GEOCOOLING_SOURCE_OUTLET_SENSOR=gc_source_outlet
GEOCOOLING_FLOOR_SUPPLY_SENSOR=gc_floor_supply
GEOCOOLING_FLOOR_RETURN_SENSOR=gc_floor_return
```

Do not commit the Noise PSK. The rollout helper reads it from the existing local
ESPHome `secrets.yaml` and writes it only to the local, unversioned `.env`.

## Deployment

From the repository on the GeoCooling VM:

```bash
bash scripts/deploy/enable-esphome-native-bridge.sh
```

The helper:

1. backs up `.env`;
2. extracts `sbc_api_key` without printing it;
3. configures only the four confirmed mappings;
4. preserves all commissioning/hardware safety flags;
5. builds and starts `backend` + `esphome-bridge`;
6. waits for telemetry;
7. requires all four canonical temperature sensors to appear in
   `/sensors/latest`.

## Deliberately unresolved roles

`GEOCOOLING_SURFACE_SENSOR` and `GEOCOOLING_FLOW_SENSOR` remain empty. There is
currently no confirmed floor-surface sensor or flowmeter source in this bridge.
The project must therefore not report six-of-six telemetry readiness based only
on the four DS18B20 sensors.
