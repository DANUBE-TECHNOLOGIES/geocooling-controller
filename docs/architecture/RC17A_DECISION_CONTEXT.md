# RC1.7A — Decision Context

RC1.7A introduit le contrat de données unique utilisé lors des étapes suivantes
pour alimenter le Brain opérationnel.

## Garanties

- aucun changement du comportement de `GeoCoolingBrain` ;
- aucune commande envoyée au Waveshare ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucun nouveau thread ou service ;
- sérialisation JSON stable et testée.

## Structure

Le contexte regroupe :

- mesures thermiques et hydrauliques ;
- configuration de confort et de condensation ;
- disponibilité des sous-systèmes ;
- qualité des capteurs, de la météo, de l’apprentissage et de la prédiction ;
- prévisions thermiques ;
- risques structurés ;
- raisons explicatives ;
- recommandation, confiance et résultats attendus.

## Étape suivante

RC1.7B construira ce contexte à partir du snapshot réel et l’exposera en lecture
seule, sans modifier encore la décision opérationnelle du Brain.
