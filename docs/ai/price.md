# IA 2 — Suggestion de prix (régression)

_Rapport généré automatiquement par `python manage.py evaluate_price` le 27/10/2026 à 15:41._

## Protocole

- Données : `data/ai/price_synth.csv`, **4000 trajets synthétiques** entre 27 villes
  tunisiennes (distance routière estimée = haversine × 1,25), poids 50 kg – 24 t, 9 types de marchandise,
  urgence 0–10 jours. Le prix « marché » suit une formule cachée (coût fixe + distance × charge taxable,
  multiplicateur par type, prime d'urgence) avec un bruit log-normal de 8 %.
- Variables du modèle : distance, poids, volume, type de marchandise, urgence.
- Modèle : `GradientBoostingRegressor` (400 arbres, profondeur 4) dans un pipeline scikit-learn
  (one-hot du type, log du poids/volume), cible apprise en log(prix).
- Découpage : 80 % entraînement / 20 % test (800 trajets), `random_state` fixé.

## Résultats (jeu de test)

| modèle | MAE (TND) | RMSE (TND) | R² | MAPE |
|---|---|---|---|---|
| Gradient Boosting | 38.660 | 74.450 | 0.968 | 7.7% |
| Référence : tarif médian / t·km | 799.430 | — | -14.851 | — |

## Interprétation

Le prix moyen du jeu de test est de 478 TND : une MAE de 39 TND correspond à une erreur
relative moyenne de 7.7%, proche du bruit irréductible de 8 % injecté dans les données. L'intervalle affiché à
l'utilisateur (±12 %) couvre donc la majorité des cas. Le modèle est sauvegardé dans
`data/ai/models/price.joblib` et ré-entraîné automatiquement s'il est absent.

## Latence

| appels | moyenne (ms) | p95 (ms) |
|---|---|---|
| 200 | 3.173 | 4.133 |

Mesurée sur l'inférence locale (sans réseau), un appel par exemple du jeu d'évaluation.
