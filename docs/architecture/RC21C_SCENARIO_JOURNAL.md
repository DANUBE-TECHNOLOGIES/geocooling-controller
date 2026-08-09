# RC2.1C — Passive Scenario Journal

RC2.1C enregistre périodiquement le résultat de :

`GET /geocooling/scenario-engine/live`

## Fichiers produits

Chaque session contient :

- `metadata.json`
- `scenario-decisions.jsonl`
- `summary.csv`
- `errors.log` si nécessaire

## Commandes

```bash
./START_SCENARIO_JOURNAL.sh
./STATUS_SCENARIO_JOURNAL.sh
./STOP_SCENARIO_JOURNAL.sh
```

L’intervalle est de 30 secondes par défaut :

```bash
GEOCOOLING_SCENARIO_JOURNAL_INTERVAL_SECONDS=60 \
./START_SCENARIO_JOURNAL.sh
```

## Garanties

- GET uniquement ;
- aucun scénario activé ;
- aucun appel au Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture dans la base applicative.
