# IA 1 — Annonce intelligente (extraction de champs)

_Rapport généré automatiquement par `python manage.py evaluate_smart_annonce` le 27/10/2026 à 15:41._

## Protocole

- Jeu de test : `data/ai/smart_annonce_50.jsonl`, **50 textes libres annotés à la main**
  (une date de référence par exemple pour résoudre « mardi », « demain »…).
- Modèle évalué : l'extracteur local (règles françaises + référentiel des villes), utilisé en démo
  et en secours quand le LLM n'est pas configuré ou échoue. Avec `AI_API_KEY`, le même post-traitement
  (`normalize_fields`) s'applique à la sortie du LLM.
- Métrique : **précision par champ** = champs corrects / champs annotés. Nombres justes à ±5%,
  dates et villes exactes, `null` attendu ⇒ la prédiction doit être vide.
- Convention d'annotation : 1 palette ≈ 500 kg / 1,5 m³, 1 carton ≈ 15 kg / 0,06 m³, 1 sac ≈ 50 kg,
  sans date limite ⇒ enlèvement + 2 jours, sans date d'enlèvement ⇒ lendemain.

## Résultats

| champ | corrects | annotés | précision |
|---|---|---|---|
| merchandise_type | 48 | 50 | 0.960 |
| weight_kg | 41 | 42 | 0.976 |
| volume_m3 | 22 | 22 | 1.000 |
| origin | 49 | 50 | 0.980 |
| destination | 49 | 50 | 0.980 |
| pickup_date | 50 | 50 | 1.000 |
| delivery_deadline | 50 | 50 | 1.000 |
| budget | 50 | 50 | 1.000 |
| **micro-moyenne** | 359 | 364 | 0.986 |

Exemples entièrement corrects : **46/50** (92%).

## Erreurs observées

| exemple | champ | attendu | prédit |
|---|---|---|---|
| 7 | merchandise_type | alimentaire | agricole |
| 32 | origin | None | Tunis |
| 32 | destination | Tunis | None |
| 36 | merchandise_type | alimentaire | frais |
| 38 | weight_kg | 2000 | None |

## Analyse

Les erreurs restantes viennent de cas que des règles traitent mal : nombres avec séparateur de milliers
(« 2 000 kg »), villes hors référentiel (« La Marsa »), produits ambigus (« huile d'olive » classée agricole,
« lait UHT » classé frais). Ce sont précisément les cas où un LLM apporte un gain ; c'est pourquoi le client
IA essaie d'abord le fournisseur configuré, puis bascule sur ces règles.

## Latence

| appels | moyenne (ms) | p95 (ms) |
|---|---|---|
| 50 | 0.341 | 1.079 |

Mesurée sur l'inférence locale (sans réseau), un appel par exemple du jeu d'évaluation.
