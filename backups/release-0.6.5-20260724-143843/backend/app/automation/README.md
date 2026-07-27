# Automation Engine — Sprint 006.3

Orchestrateur d'exécution pour le géocooling.

- mode `simulation` : exécute le contrôleur GeoCooling en simulation, même si l'ESP32 est hors ligne ;
- mode `real` : refus automatique tant que `geocooling-controller` n'est pas en ligne ;
- persistance PostgreSQL ;
- publication des transitions dans l'Event Bus ;
- cycle de vie : pending → validating → approved → executing → success/failed/rejected.

Routes :
- `GET /automation/diagnostics`
- `GET /automation/executions`
- `GET /automation/executions/{id}`
- `POST /automation/execute`
- `POST /automation/simulate`
- `POST /automation/executions/{id}/cancel`
