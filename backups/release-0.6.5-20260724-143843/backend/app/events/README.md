# Event Bus — Sprint 006.2C

Bus interne asynchrone avec file bornée, abonnements par motif (`safety.*`, `device.*`, `*`),
persistance PostgreSQL et historique mémoire.

Routes :
- `GET /events/diagnostics`
- `GET /events/recent`
- `GET /events/types`
- `POST /events/publish`

Exemple Python :

```python
event_bus.subscribe("device.*", handler)
event_bus.publish("device.offline", "device_manager", {"device_id": "geocooling-controller"})
```
