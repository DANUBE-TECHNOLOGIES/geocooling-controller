# RC3.2 — Live Shadow Runner

RC3.2 automatise la comparaison RC3 en utilisant directement :

- `GET /geocooling/decision-context/live`
- `GET /geocooling/scenario-engine/live`

## Routes

- `GET /geocooling/rc3/shadow/live`
- `GET /geocooling/rc3/shadow/live/health`

## Résultat

La réponse contient :

- le résultat RC3 en mode SHADOW ;
- l’action legacy ;
- le scénario legacy ;
- `action_match` ;
- `scenario_match` ;
- les garanties de non-activation.

## Garanties

- HTTP GET uniquement ;
- aucune autorisation Controller ;
- aucun appel au Controller ;
- aucun scénario activé ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture en base.
