# Smart Building Controller 0.6.7

## GeoCooling Runtime

- anti-court-cycle avec durée minimale d'arrêt configurable ;
- durée minimale de marche configurable ;
- watchdog matériel pendant le fonctionnement ;
- sécurité anti-condensation avec calcul du point de rosée ;
- arrêt de sécurité en cas de perte du matériel ou de marge thermique insuffisante ;
- diagnostics enrichis ;
- endpoints `GET /geocooling/diagnostics` et `GET /geocooling/safety` ;
- correction du champ `simulation` dans l'historique ;
- tests unitaires du Safety Manager.

## Variables d'environnement

- `GEOCOOLING_MIN_ON_SECONDS` (défaut : 180)
- `GEOCOOLING_MIN_OFF_SECONDS` (défaut : 300)
- `GEOCOOLING_WATCHDOG_INTERVAL_SECONDS` (défaut : 5)
- `GEOCOOLING_MIN_DEW_POINT_MARGIN_C` (défaut : 3.0)
- `GEOCOOLING_REQUIRE_THERMAL_SENSORS` (défaut : false)
