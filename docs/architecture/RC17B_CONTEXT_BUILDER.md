# RC1.7B — Passive Decision Context Builder

RC1.7B ajoute un constructeur passif et déterministe du `DecisionContext`.

## Sources acceptées

- thermal ;
- weather ;
- prediction ;
- learning ;
- historian ;
- hardware ;
- runtime ;
- configuration.

## Garanties

- aucune modification de `GeoCoolingBrain` ;
- aucune écriture matérielle ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucun démarrage de thread ;
- `pytest` facultatif ;
- installation idempotente ;
- sauvegarde de `backend/app/main.py`.

## API

- `GET /geocooling/decision-context/contract`
- `POST /geocooling/decision-context/build`

La route POST est une transformation pure : elle reçoit des payloads et renvoie
un contexte normalisé. Elle n'exécute aucune action.

## Étape suivante

RC1.7C ajoutera un agrégateur en lecture seule des services existants afin de
construire automatiquement ce contexte à partir du runtime réel.
