# Répartition du travail — équipe CargoLink (4 membres)

| Membre | Périmètre | Branche(s) |
|---|---|---|
| **Ahmed Saidani** | **Toute l'intelligence artificielle** (5 IA + infrastructure asynchrone), comptes & rôles, contrôle d'accès, modération, intégration & déploiement | `member1/accounts-moderation-fraud-deploy` + fichiers IA des autres branches |
| **Fedi Ben Khalifa** | Annonces de fret, trajets & véhicules, recherche & filtres | `member2/shipments-smart-annonce`, `member3/trips-price` |
| **Farah Maiti** | Réservations & machine à états, messagerie | `member4/bookings-matching-messaging` |
| **Wissem Ferjani** | Avis, notifications, tableaux de bord, accueil & accessibilité | `member5/reviews-notifs-dashboard-sentiment` |

Chaque membre est **propriétaire** de son périmètre : il en connaît le code, le présente à la soutenance, répond aux
questions du jury dessus, relit les pull requests qui le touchent et y commite depuis **son propre compte Git**.

Le **socle commun** est partagé par les 4 membres : `config/` (settings, urls), `manage.py`, `apps/core/` (mixins,
`geo.py`, `choices.py`, `forms.py`, `views.py`, `urls.py`, `templatetags/`, `testing/factories.py`),
`templates/base.html`, `templates/partials/` génériques et `static/css/`. Toute modification du socle passe par une pull
request relue par un autre membre.

---

## Ahmed Saidani — Intelligence artificielle, comptes, modération, déploiement
Branche : `member1/accounts-moderation-fraud-deploy` (+ fichiers IA présents dans les autres branches)

| Domaine | Fichiers |
|---|---|
| **IA — infrastructure** | `apps/core/ai/llm_client.py` (client LLM multi-fournisseur), `apps/core/ai/registry.py`, `apps/core/models.py` (AIJob), `apps/core/tasks.py` (Celery, repli en thread), endpoints `/ai/` dans `apps/core/views.py`, `config/celery.py`, `apps/core/ai/evaluation.py`, `apps/core/management/commands/train_ai_models.py`, `static/js/app.js` (polling, spinner, erreurs) |
| **IA 1 — annonce intelligente** | `apps/shipments/ai.py`, `evaluate_smart_annonce`, `data/ai/smart_annonce_50.jsonl`, `docs/ai/smart_annonce.md` |
| **IA 2 — prix** | `apps/trips/pricing.py`, `apps/trips/ai.py`, `evaluate_price`, `data/ai/price_synth.csv`, `docs/ai/price.md` |
| **IA 3 — matching** | `apps/bookings/matching.py`, `apps/bookings/ai.py`, `evaluate_matching`, `data/ai/matching_labeled.json`, `docs/ai/matching.md` |
| **IA 4 — sentiment & réputation** | `apps/reviews/ai.py`, `apps/reviews/services.py` (score de réputation), `evaluate_sentiment`, `data/ai/reviews_sentiment_*.csv`, `docs/ai/sentiment.md` |
| **IA 5 — fraude / spam** | `apps/accounts/fraud.py`, `evaluate_fraud`, `data/ai/fraud_labeled.csv`, `docs/ai/fraud.md` |
| Comptes & profils | `apps/accounts/models.py`, `forms.py`, `views.py`, `urls.py`, `signals.py`, `admin.py`, `templates/accounts/*` |
| Groupes & accès | `apps/accounts/migrations/0002_create_groups.py`, `apps/core/mixins.py` |
| Modération | `ModerationView`, `ModerationActionView`, `templates/accounts/moderation.html`, `report_form.html` |
| Intégration & déploiement | `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`, `render.yaml`, `.github/workflows/ci.yml`, `config/settings/prod.py`, `.env.example`, `seed_demo` |
| Tests | `apps/accounts/tests/`, `apps/core/tests/test_permissions.py`, `test_ai_infra.py`, `test_evaluate_commands.py`, `apps/bookings/tests/test_matching.py`, tests IA des autres apps |

**Soutenance** : toutes les démonstrations IA (« Remplir avec l'IA », « Suggérer un budget », matching, réputation,
annonce signalée), commandes `evaluate_*`, worker Celery ; rôles, accès par URL directe (403), modération, admin Django,
docker compose, CI, Render.
**À maîtriser** : Celery + Redis, `202 Accepted` + polling, gestion des erreurs d'API et clé en variable
d'environnement ; Gradient Boosting, TF-IDF + régression logistique, forêt aléatoire, score pondéré ; MAE / RMSE / R²,
précision / rappel / F1, matrice de confusion, Precision@5 / NDCG@5, choix d'un seuil, biais d'évaluation ;
`AbstractUser`, mixins d'accès, CSRF, settings de production, Docker, Render.

---

## Fedi Ben Khalifa — Annonces, trajets & véhicules, recherche
Branches : `member2/shipments-smart-annonce` et `member3/trips-price`

| Domaine | Fichiers |
|---|---|
| Annonces de fret | `apps/shipments/models.py` (FreightRequest), `forms.py` (FreightRequestForm, SearchForm), `views.py`, `urls.py`, `admin.py` |
| Véhicules & trajets | `apps/trips/models.py` (Vehicle, Trip), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Recherche & filtres | `FreightSearchView`, `TripSearchView`, `templates/partials/search_form.html`, `templates/partials/pagination.html` |
| Référentiel géographique | `apps/core/geo.py` (villes tunisiennes, distances) |
| Templates | `templates/shipments/*`, `templates/trips/*`, `templates/partials/freight_card.html`, `templates/partials/trip_card.html` |
| Tests | `apps/shipments/tests/`, `apps/trips/tests/` (hors parties IA) |

**Soutenance** : CRUD complet d'une annonce, d'un trajet et d'un véhicule, erreurs de validation, recherche filtrée et
pagination.
**À maîtriser** : modèles et migrations, ModelForms, `clean()` vs `clean_<champ>()`, validation HTML5 + serveur, CBV
génériques (Create/Update/Delete/List/Detail), index et `select_related`, pagination.

---

## Farah Maiti — Réservations, machine à états, messagerie
Branche : `member4/bookings-matching-messaging`

| Domaine | Fichiers |
|---|---|
| Réservations | `apps/bookings/models.py` (BookingRequest, BookingStatusHistory), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Machine à états | `apps/bookings/services.py` |
| Messagerie | `apps/messaging/*`, `templates/messaging/*` |
| Templates | `templates/bookings/*`, `templates/partials/booking_row.html` |
| Tests | `apps/bookings/tests/test_status_machine.py`, `apps/messaging/tests/` |

**Soutenance** : demande depuis un trajet / offre depuis une annonce, accepter → démarrer → livrer, historique des
statuts, transition interdite par URL directe, messagerie.
**À maîtriser** : table `TRANSITIONS` et contrôle de l'acteur, `transaction.atomic` + `select_for_update`,
réservation / libération de capacité, refus automatique des offres concurrentes, contrôle d'accès objet, annotations
ORM (`Count`, `Max`).

---

## Wissem Ferjani — Avis, notifications, tableaux de bord, accessibilité
Branche : `member5/reviews-notifs-dashboard-sentiment`

| Domaine | Fichiers |
|---|---|
| Avis | `apps/reviews/models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `templates/reviews/*` |
| Notifications | `apps/notifications/*`, `templates/notifications/*` |
| Tableaux de bord | `apps/dashboard/*`, `templates/dashboard/*` |
| Accueil & accessibilité | `templates/core/home.html`, `templates/errors/*`, `docs/accessibility.md`, revue accessibilité du socle (`base.html`, `navbar.html`, `cargolink.css`) |
| Tests | `apps/reviews/tests/` (hors parties IA), `apps/notifications/tests/`, `apps/dashboard/tests/`, `apps/core/tests/test_core.py` |

**Soutenance** : page d'accueil, dépôt d'un avis, notifications, tableaux de bord PME / transporteur / admin,
démonstration clavier (lien d'évitement, focus, modale) et audit Lighthouse / axe.
**À maîtriser** : context processor, agrégations ORM (`Avg`, `Sum`, `Count`) ; WCAG AA : repères sémantiques, un seul
h1, `aria-describedby`, `aria-live`, contrastes 4,5:1, `:focus-visible`, piège de focus des modales.

---

## Commun à tous (QCM individuel)
Chacun doit pouvoir expliquer : le cycle requête → URL → vue → template, les modèles et migrations, l'ORM et
`select_related`, les CBV et mixins, les formulaires et la validation, CSRF et l'authentification, la structure des
settings, les tests (`pytest`, `manage.py test`, couverture), Docker / docker compose et, dans les grandes lignes, le
fonctionnement asynchrone de l'IA (Celery). Voir aussi `docs/JURY_QA.md`.

## Règles de contribution
1. Travailler sur sa branche, commits petits et conventionnels : `feat(scope): …`, `fix(scope): …`, `test(scope): …`,
   `docs(scope): …`, `refactor(scope): …`, `chore(scope): …`.
2. `ruff check . && ruff format --check . && pytest` avant chaque push.
3. Pull request vers `main`, CI verte, relecture par un autre membre, merge `--no-ff`.
4. Chacun commite avec **sa propre identité Git** (`git config user.name` / `user.email`).
