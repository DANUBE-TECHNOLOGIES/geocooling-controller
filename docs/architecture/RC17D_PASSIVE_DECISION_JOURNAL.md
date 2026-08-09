# RC1.7D — Passive Decision Journal

RC1.7D enregistre périodiquement le contexte produit par :

`GET /geocooling/decision-context/live`

## Données produites

Chaque session contient :

- `metadata.json`
- `contexts.jsonl`
- `summary.csv`
- `errors.log` si nécessaire

## Commandes

```bash
./START_DECISION_JOURNAL.sh
./STATUS_DECISION_JOURNAL.sh
./STOP_DECISION_JOURNAL.sh
```

L’intervalle est de 30 secondes par défaut. Il peut être modifié :

```bash
GEOCOOLING_DECISION_JOURNAL_INTERVAL_SECONDS=60 \
./START_DECISION_JOURNAL.sh
```

## Garanties

- HTTP GET uniquement ;
- aucune écriture matérielle ;
- aucune publication MQTT ;
- aucune écriture dans la base applicative ;
- aucun changement du Brain ;
- journalisation uniquement dans `decision-journal/`.
