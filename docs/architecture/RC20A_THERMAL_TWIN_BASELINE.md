# RC2.0A — Thermal Twin Baseline

Cette première brique du jumeau thermique utilise les données du journal passif.

## Modèle

Le modèle estime :

- dérive médiane de la température intérieure par heure ;
- intervalle médian entre mesures ;
- couplage simplifié avec la température extérieure ;
- classe d’inertie du bâtiment ;
- prévisions à 30 min, 1 h, 2 h et 4 h.

## Commande

```bash
./BUILD_THERMAL_TWIN.sh
```

Pour fournir manuellement l’état initial :

```bash
./BUILD_THERMAL_TWIN.sh --indoor 25.4 --outdoor 30.1
```

## Résultats

Dans la session analysée :

```text
thermal-twin/
├── model.json
└── prediction.json
```

## Limites

Il s’agit d’un modèle de base passif. Il ne distingue pas encore :

- soleil ;
- occupation ;
- ouverture des fenêtres ;
- fonctionnement du rafraîchissement ;
- zones thermiques séparées.

Aucune commande matérielle n’est envoyée.
