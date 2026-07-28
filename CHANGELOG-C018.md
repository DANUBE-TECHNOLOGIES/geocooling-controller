# PATCH C018 — Waveshare Modbus TCP

## Objectif

Intégrer la couche matérielle du relais Waveshare 8 canaux sans relier le Brain aux actionneurs.

## Matériel validé

- Hôte : `192.168.10.122`
- Port : `502`
- Unit ID : `1`
- Coils : adresses `0` à `7`
- Protocole : Modbus TCP

## Modifications

- Client Modbus TCP natif sans dépendance supplémentaire.
- Lecture groupée des huit coils (`0x01`).
- Écriture individuelle (`0x05`) et arrêt global (`0x0F`).
- Retry/reconnexion configurable, contrôle MBAP et validation des réponses.
- Vérification de l'état après écriture.
- Armement obligatoire pour toute commande ON ; OFF toujours autorisé.
- État sûr hydraulique : circulateur OFF puis vanne OFF.
- Métriques de communication et exposition de l'état des huit relais.
- API de diagnostic :
  - `GET /geocooling/relay/status`
  - `POST /geocooling/relay/{relay_id}/on`
  - `POST /geocooling/relay/{relay_id}/off`
  - `POST /geocooling/relay/all/off`

## Sécurité

- `GEOCOOLING_HARDWARE_ARMED=false` par défaut.
- Aucune intégration automatique au Brain dans C018.
- Le contrôleur reste en simulation tant que `GEOCOOLING_DRIVER` n'est pas explicitement modifié.
