# IA 3 — Matching intelligent annonces ↔ trajets

_Rapport généré automatiquement par `python manage.py evaluate_matching` le 27/10/2026 à 15:41._

## Protocole

- Jeu annoté : `data/ai/matching_labeled.json`, **40 annonces** × 15 trajets candidats
  (600 paires), tels qu'ils sortent du pré-filtre de l'application (fenêtre de dates ±5 jours). Pertinence 0–3 attribuée par une **grille d'annotation indépendante** des poids du score
  (capacité, froid, détour ≤ 60/150 km, écart de date, prix vs budget, note du transporteur) avec 10 % de
  désaccord simulé entre annotateurs.
- Distribution des pertinences 0/1/2/3 : 348, 156, 67, 29.
- Score évalué : `0,35·trajet + 0,25·date + 0,15·capacité + 0,15·prix + 0,10·note`, ×0,1 si contrainte dure violée
  (capacité ou réfrigération).
- Métriques : **Precision@5** (pertinence ≥ 2 = pertinent) et **NDCG@5** (gain 2^rel − 1), moyennées par requête.

## Résultats

| classement | Precision@5 | NDCG@5 |
|---|---|---|
| Matching CargoLink (score pondéré) | 0.445 | 0.917 |
| Référence : même trajet d'abord | 0.350 | 0.625 |
| Référence : ordre aléatoire | 0.145 | 0.290 |
| Borne supérieure (classement parfait) | 0.480 | 1.000 |

## Interprétation

Le score pondéré dépasse nettement les deux références : il remonte les trajets voisins (détour faible) et
écarte les trajets incompatibles (capacité, froid). La Precision@5 est plafonnée par le nombre de candidats
pertinents par requête (souvent moins de 5) : il faut la comparer à la borne supérieure du tableau. Le même score sert dans les deux sens (annonce → trajets et
trajet → annonces).

## Latence

| appels | moyenne (ms) | p95 (ms) |
|---|---|---|
| 40 | 0.209 | 0.264 |

Mesurée sur l'inférence locale (sans réseau), un appel par exemple du jeu d'évaluation.
