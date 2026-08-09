# RC2.1D — Scenario Journal Analysis

RC2.1D analyse les sessions produites par RC2.1C.

## Indicateurs

- répartition des scénarios sélectionnés ;
- score du scénario retenu ;
- confiance ;
- écart entre le premier et le deuxième scénario ;
- nombre de changements de scénario ;
- transitions les plus fréquentes ;
- alignement entre Scenario Engine et Decision Context ;
- taux de décisions ambiguës ;
- énergie et durée de fonctionnement estimées.

## Commande

```bash
./ANALYZE_SCENARIO_JOURNAL.sh
```

Pour une session précise :

```bash
./ANALYZE_SCENARIO_JOURNAL.sh \
  --session session-20260803-130000
```

## Résultats

```text
scenario-journal/session-.../analysis/
├── ANALYSIS.md
├── analysis.json
└── samples-flat.csv
```

## Sécurité

Analyse locale uniquement, sans API et sans commande matérielle.
