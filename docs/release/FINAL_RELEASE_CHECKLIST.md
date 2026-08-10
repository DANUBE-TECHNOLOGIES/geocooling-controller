# GeoCooling — Final Release Checklist

## Objectif

Fermer le projet logiciel sans masquer les dépendances physiques encore non réalisées. Aucun état `READY` ne doit être forcé.

## 1. Logiciel — doit être vert avant terrain

- Backend healthy.
- CI RC1 / RC2 / RC3 verte.
- Régressions F2 / F3 / F4 vertes.
- Télémétrie 5/5 prête.
- Surface plancher dérivée en `floor_loop_estimate` avec biais conservateur.
- Débit déclaré optionnel tant qu'aucun débitmètre n'est installé.
- Humidité intérieure disponible dans le Decision Context.
- Températures source entrée / sortie disponibles dans le Decision Context.
- Open-Meteo localisé explicitement sur Chevannes.
- Weather/Inertia en `HOURLY_FORECAST`, non dégradé.
- Pré-refroidissement en mode SHADOW uniquement.
- Journal et calibration offline disponibles.
- Tous les flags hardware/autopilot à `false` par défaut.
- `release-readiness` refuse tout déploiement si un flag dangereux est actif.

Audit unique :

```bash
cd /opt/stacks/smart-building-controller
bash scripts/release/geocooling-final-readiness-audit.sh
```

Avant raccordement terrain, l'état attendu est :

```text
FINAL_STATE=SOFTWARE_COMPLETE_FIELD_CERTIFICATION_REQUIRED
```

## 2. Dépendances physiques restantes

Ces tâches ne peuvent pas être validées par le logiciel seul :

- raccorder électriquement l'EV au relais prévu ;
- raccorder M11 ;
- raccorder M13 ;
- confirmer physiquement l'affectation relais -> équipement ;
- vérifier les états de repos ;
- effectuer les tests temporisés de commissioning ;
- vérifier la séquence hydraulique EV avant pompes ;
- vérifier le safe-stop pompes puis EV ;
- confirmer le comportement réel en cas de coupure / erreur ;
- valider la certification terrain.

Ne jamais modifier `GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED=true` sans ces vérifications.

## 3. Certification terrain

Utiliser :

```bash
bash scripts/commissioning/field-certification-preflight.sh
```

Puis suivre :

`docs/commissioning/FIELD_CERTIFICATION_RUNBOOK.md`

L'état attendu après certification réussie est :

```text
commissioning_state=READY_FOR_RELEASE
```

## 4. Gate release final

Après certification, conserver les defaults sûrs :

```text
GEOCOOLING_HARDWARE_ARMED=false
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
GEOCOOLING_AUTOPILOT_ENABLED=false
GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER=false
```

Puis relancer :

```bash
bash scripts/release/geocooling-final-readiness-audit.sh
```

L'état final attendu est :

```text
FINAL_STATE=READY_FOR_DEPLOYMENT
```

## 5. Activation opérationnelle

`READY_FOR_DEPLOYMENT` ne signifie pas que l'autopilot doit être activé immédiatement. L'activation réelle doit être une action séparée, contrôlée, réversible et documentée.

Le moteur de pré-refroidissement reste `promotion_to_controller_allowed=false` tant que sa calibration terrain n'a pas été jugée suffisante.

## 6. Critère de fermeture du projet

Le développement logiciel est considéré terminé lorsque :

1. la CI est verte ;
2. l'audit final renvoie `SOFTWARE_COMPLETE_FIELD_CERTIFICATION_REQUIRED` avant le terrain ;
3. aucune anomalie logicielle bloquante n'est ouverte ;
4. les seules tâches restantes sont les raccordements et la certification physique.

Le projet global est considéré prêt au déploiement lorsque l'audit final renvoie `READY_FOR_DEPLOYMENT` après certification terrain.
