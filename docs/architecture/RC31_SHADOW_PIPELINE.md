# RC3.1 — Shadow Pipeline

RC3.1 adapte les sorties actuelles vers les contrats RC3 et compare les
décisions en mode `SHADOW`.

## Adaptateurs

- `LegacyDecisionContextAdapter`
- `LegacyScenarioResultAdapter`

## Route

- `GET /geocooling/rc3/contract`
- `POST /geocooling/rc3/shadow/compare`

Le payload de comparaison contient :

```json
{
  "context": {},
  "scenario": {}
}
```

## Garanties

- aucune autorisation Controller ;
- aucun changement du Brain actuel ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture en base ;
- aucune activation du scénario sélectionné.
