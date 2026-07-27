# Device Framework — Sprint 006.2B

Le Device Manager exploite l'historien MQTT déjà alimenté par `MQTTCollector`.
Il ne crée pas un second collecteur global et n'interfère pas avec les commandes GeoCooling.

Topics GeoCooling attendus :

- `geocooling/status/device`
- `geocooling/status/heartbeat`
- `geocooling/status/availability`

Exemple de payload `status/device` :

```json
{
  "device_id": "geocooling-controller",
  "name": "ESP32 GeoCooling",
  "firmware_version": "0.1.0",
  "ip": "192.168.1.50",
  "mac": "AA:BB:CC:DD:EE:FF",
  "rssi": -61,
  "uptime_seconds": 120,
  "components": [
    {"id": "valve", "type": "relay", "name": "Electrovanne", "available": true, "required": true},
    {"id": "pump", "type": "relay", "name": "Circulateur", "available": true, "required": true}
  ]
}
```
