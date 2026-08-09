# RC2.0C — Thermal Twin Calibration

RC2.0C ajuste prudemment le modèle RC2.0A à partir des résultats RC2.0B.

## Principe

Le biais moyen de prédiction corrige progressivement :

- la dérive intérieure par heure ;
- le couplage à la température extérieure.

Le taux d’apprentissage par défaut est volontairement limité à `0.25`.

## Commande

```bash
./CALIBRATE_THERMAL_TWIN.sh
```

Pour ralentir encore l’apprentissage :

```bash
./CALIBRATE_THERMAL_TWIN.sh \
  --learning-rate 0.10
```

## Résultats

```text
thermal-twin/calibration/
├── calibration.json
└── calibrated-model.json
```

## Important

Le modèle calibré n’est pas automatiquement activé. Il est produit pour revue
et comparaison. L’activation dans le Brain fera l’objet d’une étape séparée
après plusieurs cycles de validation.

## Sécurité

Analyse locale uniquement. Aucune API ni commande matérielle.
