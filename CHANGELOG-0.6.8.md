# Smart Building Controller 0.6.8

- Anti-court-cycle avec durée minimale d'arrêt configurable.
- Durée minimale de marche configurable.
- Watchdog matériel en fonctionnement.
- Arrêt immédiat de sécurité en cas de perte ESP32/MQTT.
- Contrôle anti-condensation avant démarrage et pendant le fonctionnement.
- API `PUT /geocooling/thermal-snapshot`.
- API `GET /geocooling/safety` et `GET /geocooling/diagnostics`.
- Tests unitaires des temporisations Runtime.
