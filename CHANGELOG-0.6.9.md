# Smart Building Controller 0.6.9

## GeoCooling Thermal Core

- Ajout du moteur `ThermalEstimator`.
- Acquisition étendue : intérieur, humidité, surface, départ/retour plancher, entrée/sortie source, extérieur.
- Calculs : point de rosée, marge, ΔT plancher, ΔT source, tendances horaires, état thermique.
- Détection d'échange frigorifique.
- Nouveau endpoint `GET /geocooling/thermal`.
- Enrichissement de `PUT /geocooling/thermal-snapshot`, du statut et des diagnostics.
