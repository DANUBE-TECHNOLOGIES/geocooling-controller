# RC1.3 — Pipeline Status

Ce lot expose une vue en lecture seule du pipeline canonique RC1.

## Routes

- `GET /geocooling/rc1/architecture`
- `GET /geocooling/rc1/pipeline`
- `GET /geocooling/rc1/readiness`

## Garanties

- aucune écriture matérielle ;
- aucune publication MQTT ;
- aucune mutation de base de données ;
- aucun démarrage automatique de service ;
- aucune suppression des anciennes générations de Brain.

Le lot vérifie uniquement que les modules et symboles désignés par le contrat
RC1 sont importables.
