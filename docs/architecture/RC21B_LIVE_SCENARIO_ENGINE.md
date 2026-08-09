# RC2.1B — Live Passive Scenario Engine

Cette brique relie :

1. le `LiveDecisionContextService` ;
2. le `ScenarioEngine` ;
3. une API de lecture passive.

## Routes

- `GET /geocooling/scenario-engine/live`
- `GET /geocooling/scenario-engine/live/health`

La route `/live` construit le contexte réel, évalue les cinq scénarios et
retourne le classement complet.

## Pondérations

Elles peuvent être ajustées par paramètres de requête :

```text
comfort_weight
safety_weight
energy_weight
stability_weight
learning_weight
```

## Garanties

- aucun scénario activé ;
- aucun appel au Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture en base ;
- appels internes limités aux routes GET déjà utilisées par le contexte live.
