# RC1.7C — Live Passive Decision Context

RC1.7C agrège les données réelles disponibles via les routes GET locales du
backend, puis les transmet au `PassiveDecisionContextBuilder`.

## Sources recherchées

- thermal ;
- weather ;
- prediction ;
- learning ;
- historian ;
- hardware ;
- runtime.

Chaque source dispose de plusieurs routes candidates. Une source absente ne
fait pas échouer la construction : elle dégrade la qualité et ajoute un risque.

## Sécurité

- HTTP sortant limité à GET ;
- aucune route d’actionnement appelée ;
- aucune commande au Waveshare ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucune modification de `GeoCoolingBrain`.

## Routes

- `GET /geocooling/decision-context/live`
- `GET /geocooling/decision-context/live/sources`

## Étape suivante

RC1.7D enregistrera passivement les contextes pour la campagne d’observation,
sans modifier l’autorité opérationnelle du Brain.
