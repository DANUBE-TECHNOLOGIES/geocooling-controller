# RC3.7 — Prediction Validation Fullstack

RC3.7 crée la donnée qui manquait à RC3.6 : la comparaison réelle entre une
prévision passée et la température intérieure mesurée lorsque son horizon est
atteint.

## Collecte

Toutes les cinq minutes, le collecteur enregistre :

- la prévision RC3.5 complète ;
- le Decision Context réel ;
- l’heure exacte de capture.

## Validation

Le moteur associe ensuite chaque point prévu à la mesure réelle la plus proche.

Il calcule :

- MAE ;
- RMSE ;
- biais ;
- précision par horizon.

## API

- `GET /geocooling/rc3/prediction-validation/contract`
- `GET /geocooling/rc3/prediction-validation/report`

## Frontend

- `/geocooling/prediction-validation`

## Commandes

```bash
./START_RC3_PREDICTION_JOURNAL.sh
./STATUS_RC3_PREDICTION_JOURNAL.sh
./STOP_RC3_PREDICTION_JOURNAL.sh
```

## Sécurité

Mode Shadow uniquement. Aucun pilotage matériel.
