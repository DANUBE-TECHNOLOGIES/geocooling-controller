# Sprint UI-001 — Connexion temps réel du dashboard

## Livré
- Suppression de l’utilisation de `mockSnapshot` sur la page principale.
- Proxy serveur Next.js vers `GET /geocooling/home-assistant`.
- Normalisation stricte de la réponse backend snake_case vers le modèle UI.
- Polling automatique toutes les 2 secondes.
- Gestion des délais, erreurs, reconnexion et actualisation manuelle.
- Indicateurs Backend/Mode dynamiques dans la barre supérieure.
- Affichage robuste des sondes absentes avec `—`.

## Variable requise
Le conteneur/frontend doit disposer de :

```env
GEOCOOLING_API_URL=http://backend:8000
```

Adapter le nom d’hôte et le port à la configuration Docker existante.
