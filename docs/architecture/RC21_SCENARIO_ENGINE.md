# RC2.1 — Passive Scenario Engine

Le Scenario Engine compare cinq stratégies :

- `WAIT`
- `PRECOOL_30`
- `PRECOOL_60`
- `COOL_NOW`
- `SOFT_COOLING`

## Évaluation

Chaque stratégie reçoit les scores suivants :

- confort ;
- sécurité ;
- énergie ;
- stabilité ;
- qualité d’apprentissage.

Les pondérations par défaut sont :

- confort : 40 % ;
- sécurité : 25 % ;
- énergie : 20 % ;
- stabilité : 10 % ;
- apprentissage : 5 %.

## API

- `GET /geocooling/scenario-engine/contract`
- `POST /geocooling/scenario-engine/evaluate`

La route `POST` effectue uniquement un calcul pur à partir du contexte fourni.

## Garanties

- aucune modification du Brain existant ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucun appel HTTP sortant ;
- aucune activation automatique du scénario sélectionné.
