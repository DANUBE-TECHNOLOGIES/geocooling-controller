# RC3.6 — Auto-calibration Fullstack

RC3.6 exploite les journaux déjà présents pour proposer des ajustements du
modèle RC3.5.

## Paramètres proposés

- inertie rapide ;
- inertie lente ;
- couplage de la masse thermique ;
- gain solaire ;
- efficacité du rafraîchissement modéré ;
- efficacité du rafraîchissement nominal ;
- confiance du modèle.

## API

- `GET /geocooling/rc3/calibration/contract`
- `GET /geocooling/rc3/calibration/proposal`

## Frontend

- `/geocooling/calibration`

## Sécurité

La proposition n’est jamais activée automatiquement. Elle nécessite une revue
humaine et ne touche ni au Controller ni au matériel.
