# RC3.3 — Shadow Journal

RC3.3 enregistre périodiquement le résultat de :

`GET /geocooling/rc3/shadow/live`

## Fichiers produits

Chaque session contient :

- `metadata.json`
- `shadow-comparisons.jsonl`
- `summary.csv`
- `errors.log` si nécessaire

## Commandes

```bash
./START_RC3_SHADOW_JOURNAL.sh
./STATUS_RC3_SHADOW_JOURNAL.sh
./STOP_RC3_SHADOW_JOURNAL.sh
```

L’intervalle est de 30 secondes par défaut :

```bash
GEOCOOLING_RC3_SHADOW_INTERVAL_SECONDS=60 \
./START_RC3_SHADOW_JOURNAL.sh
```

## Données suivies

- action legacy ;
- scénario legacy ;
- action RC3 ;
- scénario RC3 ;
- confiance RC3 ;
- correspondance des actions ;
- correspondance des scénarios ;
- autorisation Controller ;
- appels Controller et matériel.

## Garanties

- GET uniquement ;
- mode SHADOW ;
- aucune autorisation Controller ;
- aucun appel au Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture dans la base applicative.
