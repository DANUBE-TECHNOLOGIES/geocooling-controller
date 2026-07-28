# PATCH C019 — Séquencement hydraulique réel sécurisé

## Objectif

Relier le contrôleur d'états existant au pilote Waveshare C018 sans autoriser
accidentellement un cycle hydraulique réel.

## Sécurité ajoutée

- nouvelle barrière indépendante `GEOCOOLING_HARDWARE_SEQUENCE_ENABLED` ;
- valeur par défaut `false` ;
- l'armement C018 autorise les commandes unitaires, mais ne suffit pas à lancer
  automatiquement un cycle complet ;
- confirmation Modbus après ouverture de vanne, démarrage de pompe, arrêt de
  pompe et fermeture de vanne ;
- défaut de confirmation => exception, état sûr puis état `FAULT` ;
- ordre hydraulique conservé : vanne ON, délai, pompe ON ; pompe OFF, délai,
  vanne OFF ;
- arrêt d'urgence inchangé : pompe OFF puis vanne OFF immédiatement.

## Variables

```env
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
GEOCOOLING_SEQUENCE_VERIFY_FEEDBACK=true
GEOCOOLING_SEQUENCE_FEEDBACK_TIMEOUT_SECONDS=3
GEOCOOLING_SEQUENCE_FEEDBACK_POLL_SECONDS=0.2
GEOCOOLING_VALVE_OPEN_DELAY=5
GEOCOOLING_VALVE_CLOSE_DELAY=2
```

## Mise en service prévue

C019 doit d'abord être installé avec :

```env
GEOCOOLING_HARDWARE_ARMED=false
GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=false
```

Puis les relais vanne et pompe sont testés séparément. L'activation du cycle
complet ne doit intervenir qu'après validation du câblage et du sens de marche.
