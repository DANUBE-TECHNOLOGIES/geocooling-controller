# RC3.0 — Architecture Freeze

RC3.0 définit l’architecture cible du Brain prédictif sans modifier le
comportement actuel.

## Contrats versionnés

- `DecisionInput`
- `MeasurementSet`
- `ForecastPoint`
- `ConstraintViolation`
- `ScenarioScore`
- `DecisionOutput`

## Ports

- `ContextProvider`
- `ScenarioGenerator`
- `ScenarioEvaluator`
- `ScenarioRanker`
- `DecisionExplainer`
- `SafetyPolicy`
- `DecisionObserver`
- `DecisionSink`
- `LegacyContextAdapter`

## Pipeline unique

```text
ContextProvider
      ↓
ScenarioGenerator
      ↓
ScenarioEvaluator
      ↓
ScenarioRanker
      ↓
SafetyPolicy
      ↓
DecisionExplainer
      ↓
DecisionOutput
      ↓
Observers
```

## Modes

- `PASSIVE` : aucune autorisation Controller ;
- `SHADOW` : comparaison avec le Brain actuel ;
- `ACTIVE` : futur mode autorisant le Controller après validation.

RC3.0 ne fournit aucun composant actif.

## Stratégie de migration

1. adapter le Decision Context existant vers `DecisionInput` ;
2. adapter le Scenario Engine existant vers les ports RC3 ;
3. exécuter RC3 en mode `SHADOW` ;
4. comparer RC3 au Brain actuel ;
5. activer progressivement après validation terrain.

## Garanties

- aucun changement du Brain actuel ;
- aucun raccordement au Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucune API ajoutée ;
- aucun redémarrage nécessaire.
