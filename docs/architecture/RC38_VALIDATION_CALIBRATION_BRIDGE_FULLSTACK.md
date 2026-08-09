# RC3.8 — Validation/Calibration Bridge

Relie les correspondances RC3.7 au moteur de calibration RC3.6.

Pipeline :

```text
Prévision → mesure réelle → erreur → proposition de calibration
```

API :

- `GET /geocooling/rc3/learning/contract`
- `GET /geocooling/rc3/learning/report`

Frontend :

- `/geocooling/learning`

Aucune activation automatique.
