# GeoCooling RC1 — Architecture Freeze

Autorité opérationnelle RC1 :

- Brain : `app.geocooling.brain.GeoCoolingBrain`
- Contrôleur : `app.geocooling.controller`
- Matériel : `app.geocooling.waveshare_modbus_driver`
- Météo : `app.weather_service.WeatherService`

Pipeline : Sensors → Historian → Weather → Learning → Thermal Engine → Prediction → Brain → Safety → Controller → Hardware.

`brain_v2`, `brain_v4` et `brain_v5` restent présents mais ne sont pas l’autorité d’actionnement RC1. Aucune suppression n’est réalisée dans ce lot.
