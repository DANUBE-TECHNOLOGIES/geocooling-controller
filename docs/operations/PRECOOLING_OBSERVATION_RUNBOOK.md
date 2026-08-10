# GeoCooling — Runbook d'observation du pré-refroidissement

## Objectif

Observer le moteur RC3.5 de pré-refroidissement en mode SHADOW pendant 24 à 72 heures et mesurer sa qualité sans autoriser aucun actionnement matériel.

Le journal conserve uniquement des lectures HTTP GET issues du backend GeoCooling. Il n'autorise pas le contrôleur, n'écrit pas dans la base, ne publie pas sur MQTT et ne commande aucun relais.

## Préconditions

- Backend GeoCooling healthy.
- Service météo Open-Meteo configuré sur Chevannes.
- Weather/Inertia en `HOURLY_FORECAST` et `weather_degraded=false`.
- Télémétrie GeoCooling 5/5 prête.
- Tous les flags hardware/autopilot restent à `false`.

## Démarrer une campagne

```bash
cd /opt/stacks/smart-building-controller
bash scripts/rc3/start-precooling-journal.sh
```

Intervalle par défaut : 300 secondes. Pour une campagne plus dense :

```bash
GEOCOOLING_PRECOOL_JOURNAL_INTERVAL_SECONDS=120 \
  bash scripts/rc3/start-precooling-journal.sh
```

Ne pas descendre sous 60 secondes.

## Contrôler la campagne

```bash
bash scripts/rc3/status-precooling-journal.sh
```

Le statut doit confirmer que le collecteur tourne et que des snapshots sont ajoutés.

## Analyse descriptive pendant la campagne

```bash
bash scripts/rc3/analyze-precooling-journal.sh
```

Cette analyse résume notamment :

- états advisory rencontrés ;
- confiance moyenne ;
- avance moyenne recommandée ;
- scénarios conseillés ;
- gain thermique prévu.

## Arrêter la campagne

```bash
bash scripts/rc3/stop-precooling-journal.sh
```

## Calibration prédiction vs réel

Après plusieurs heures de données :

```bash
bash scripts/rc3/calibrate-precooling-journal.sh
```

Le calibrateur compare les températures `BASELINE` prédites à t0 avec les températures intérieures réellement observées plus tard. Il calcule pour chaque horizon :

- `MAE` : erreur absolue moyenne ;
- `bias` : biais signé (positif = modèle trop chaud, négatif = modèle trop froid) ;
- erreur absolue maximale ;
- nombre de prédictions réellement appariées.

## Interprétation du statut

### `INSUFFICIENT_DATA`

Moins de 12 prédictions ont pu être comparées à une observation future. Continuer la campagne avant toute conclusion.

### `WELL_CALIBRATED`

MAE globale <= 0,5 °C avec un nombre suffisant de comparaisons. Le modèle est suffisamment précis pour poursuivre l'étude du timing de pré-refroidissement.

### `USABLE_WITH_CAUTION`

MAE globale entre 0,5 °C et 1,0 °C. Les recommandations restent utiles en SHADOW mais ne doivent pas être promues vers un pilotage automatique.

### `RECALIBRATION_RECOMMENDED`

MAE globale > 1,0 °C. Il faut recalibrer le modèle thermique avant toute promotion du moteur de pré-refroidissement.

## Règles de décision

1. Aucune modification automatique des constantes thermiques à partir du journal.
2. Aucune promotion vers le contrôleur sur une seule journée d'observation.
3. Comparer plusieurs épisodes météo : journée chaude, nuit fraîche, forte variation de rayonnement si possible.
4. Examiner le biais par horizon avant la MAE globale : un modèle juste à 30 min mais faux à 6 h doit rester limité à l'horizon court.
5. Conserver `promotion_to_controller_allowed=false` jusqu'à commissioning terrain terminé ET calibration démontrée.

## Sécurité

Cette campagne est indépendante du commissioning EV / M11 / M13. Elle peut fonctionner avant leur raccordement, car elle ne réalise aucun write matériel.
