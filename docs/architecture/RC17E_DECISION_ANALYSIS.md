# RC1.7E — Decision Journal Analysis

RC1.7E analyse les sessions produites par RC1.7D.

## Fichiers générés

Dans `decision-journal/session-.../analysis/` :

- `ANALYSIS.md`
- `analysis.json`
- `samples-flat.csv`

## Indicateurs

- répartition des décisions ;
- confiance moyenne ;
- taux de blocage ;
- fréquence des risques ;
- disponibilité Weather/Historian/Learning/Prediction/Hardware ;
- qualité des données ;
- statistiques des températures, humidité, point de rosée et marge de condensation.

## Commande

```bash
./ANALYZE_DECISION_JOURNAL.sh
```

Pour une session précise :

```bash
./ANALYZE_DECISION_JOURNAL.sh \
  --session session-20260803-120000
```

## Sécurité

L’analyseur lit uniquement les fichiers locaux du journal. Il n’appelle aucune
API et n’envoie aucune commande.
