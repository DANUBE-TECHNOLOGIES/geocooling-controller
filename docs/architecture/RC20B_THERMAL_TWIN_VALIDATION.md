# RC2.0B — Thermal Twin Validation

Cette brique compare les prévisions générées par RC2.0A aux températures
réellement observées dans le journal passif.

## Indicateurs

- MAE ;
- RMSE ;
- biais ;
- erreur absolue maximale ;
- qualité globale ;
- qualité par horizon.

## Commande

```bash
./VALIDATE_THERMAL_TWIN.sh
```

Pour une session précise :

```bash
./VALIDATE_THERMAL_TWIN.sh \
  --session session-20260803-120000
```

## Prérequis

La session doit contenir :

- `contexts.jsonl`
- `thermal-twin/prediction.json`

## Résultats

```text
thermal-twin/validation/
├── VALIDATION.md
├── validation.json
└── matches.csv
```

## Sécurité

Analyse locale uniquement, sans API ni commande matérielle.
