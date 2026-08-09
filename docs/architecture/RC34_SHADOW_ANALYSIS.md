# RC3.4 — Shadow Analysis

RC3.4 analyse les sessions produites par RC3.3.

## Indicateurs

- taux de correspondance des actions ;
- taux de correspondance des scénarios ;
- confiance RC3 ;
- matrices Legacy → RC3 ;
- détection de toute autorisation ou commande interdite ;
- critères de passage vers l’étape suivante.

## Seuils initiaux

- au moins 100 échantillons ;
- correspondance des actions ≥ 95 % ;
- correspondance des scénarios ≥ 90 % ;
- confiance moyenne ≥ 0,70 ;
- aucun incident de sécurité.

## Commande

```bash
./ANALYZE_RC3_SHADOW_JOURNAL.sh
```

Pour une session précise :

```bash
./ANALYZE_RC3_SHADOW_JOURNAL.sh \
  --session session-20260803-140000
```

## Résultats

```text
rc3-shadow-journal/session-.../analysis/
├── ANALYSIS.md
├── analysis.json
└── samples-flat.csv
```

## Sécurité

Analyse locale uniquement, sans API, sans Controller et sans matériel.
