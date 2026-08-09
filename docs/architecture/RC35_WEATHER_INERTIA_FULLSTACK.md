# RC3.5 — Weather/Inertia Predictor Fullstack

RC3.5 réutilise le Decision Context, le service météo et l’architecture RC3
pour produire des trajectoires thermiques jusqu’à 48 heures.

## Horizons

- 30 min
- 1 h
- 2 h
- 4 h
- 6 h
- 12 h
- 24 h
- 48 h

## Trajectoires

- `BASELINE`
- `SOFT_COOLING`
- `FULL_COOLING`

## Modèle

Le modèle comprend deux dynamiques :

- inertie rapide de l’air et des apports solaires ;
- inertie lente de la dalle et de la masse du bâtiment.

Les paramètres initiaux restent conservateurs et seront ajustés par les
données déjà enregistrées dans les journaux thermiques.

## API

- `GET /geocooling/rc3/weather-inertia/contract`
- `GET /geocooling/rc3/weather-inertia/live`

## Frontend

- `/geocooling/weather-inertia`

La page affiche :

- état thermique actuel ;
- courbes des trois trajectoires ;
- prévisions jusqu’à 48 h ;
- confiance et incertitude ;
- paramètres d’inertie utilisés.

## Sécurité

- mode SHADOW ;
- aucune autorisation Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune activation automatique.
