# Répartition du travail — équipe CargoLink (4 membres)

| Membre | Périmètre | IA | Branche(s) |
|---|---|---|---|
| **Ahmed Saidani** | Comptes & rôles, contrôle d'accès, modération, intégration & déploiement | IA 5 — fraude / spam | `member1/accounts-moderation-fraud-deploy` |
| **Fedi Ben Khalifa** | Annonces de fret, trajets & véhicules, recherche & filtres | IA 1 — annonce intelligente · IA 2 — prix | `member2/shipments-smart-annonce`, `member3/trips-price` |
| **Farah Maiti** | Réservations & machine à états, messagerie, infrastructure IA asynchrone | IA 3 — matching | `member4/bookings-matching-messaging` |
| **Wissem Ferjani** | Avis & réputation, notifications, tableaux de bord, accueil & accessibilité | IA 4 — sentiment | `member5/reviews-notifs-dashboard-sentiment` |

Chaque membre est **propriétaire** de son périmètre : il en connaît le code, le présente à la soutenance, répond aux
questions du jury dessus, relit les pull requests qui le touchent et y commite depuis **son propre compte Git**.

Le **socle commun** est partagé par les 4 membres : `config/` (settings, urls), `manage.py`, `apps/core/` (mixins,
`geo.py`, `choices.py`, `forms.py`, `views.py`, `urls.py`, `templatetags/`, `testing/factories.py`),
`templates/base.html`, `templates/partials/` génériques et `static/`. Toute modification du socle passe par une pull
request relue par un autre membre.

---

## Ahmed Saidani — Comptes, modération, IA fraude, déploiement
Branche : `member1/accounts-moderation-fraud-deploy`

| Domaine | Fichiers |
|---|---|
| Comptes & profils | `apps/accounts/models.py` (User, CompanyProfile, CarrierProfile, Report), `forms.py`, `views.py`, `urls.py`, `signals.py`, `admin.py` |
| Groupes & permissions | `apps/accounts/migrations/0002_create_groups.py` |
| Contrôle d'accès | `apps/core/mixins.py` (RoleRequiredMixin, OwnerRequiredMixin) |
| Modération | `ModerationView`, `ModerationActionView`, `templates/accounts/moderation.html`, `report_form.html` |
| **IA 5 — fraude/spam** | `apps/accounts/fraud.py`, `apps/accounts/management/commands/evaluate_fraud.py`, `data/ai/fraud_labeled.csv`, `docs/ai/fraud.md` |
| Intégration & déploiement | `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`, `render.yaml`, `.github/workflows/ci.yml`, `config/settings/prod.py`, `.env.example` |
| Données de démo | `apps/core/management/commands/seed_demo.py` |
| Templates | `templates/accounts/*` |
| Tests | `apps/accounts/tests/`, `apps/core/tests/test_permissions.py` |

**Soutenance** : inscription par rôle, connexion, verrouillage après 5 échecs, modération (annonce signalée par
l'IA → masquer), admin Django, `docker compose up`, CI GitHub Actions, déploiement Render.
**À maîtriser** : `AbstractUser` et pourquoi avant la 1re migration, groupes/permissions par migration de données,
mixins d'accès et test de la matrice de permissions, CSRF, hachage des mots de passe, django-axes, settings de prod
(HSTS, cookies `Secure`, `check --deploy`), WhiteNoise, gunicorn, Celery worker, forêt aléatoire, précision / rappel /
F1 / matrice de confusion, choix du seuil.

---

## Fedi Ben Khalifa — Annonces, trajets & véhicules, IA annonce intelligente et prix
Branches : `member2/shipments-smart-annonce` et `member3/trips-price`

| Domaine | Fichiers |
|---|---|
| Annonces de fret | `apps/shipments/models.py` (FreightRequest), `forms.py` (FreightRequestForm, SearchForm), `views.py`, `urls.py`, `admin.py` |
| Véhicules & trajets | `apps/trips/models.py` (Vehicle, Trip), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Recherche & filtres | `FreightSearchView`, `TripSearchView`, `templates/partials/search_form.html`, `templates/partials/pagination.html` |
| Référentiel géographique | `apps/core/geo.py` (villes tunisiennes, distances) |
| **IA 1 — annonce intelligente** | `apps/shipments/ai.py`, `apps/shipments/management/commands/evaluate_smart_annonce.py`, `data/ai/smart_annonce_50.jsonl`, `docs/ai/smart_annonce.md`, partie « smart annonce » de `static/js/app.js` |
| Client LLM | `apps/core/ai/llm_client.py` |
| **IA 2 — prix** | `apps/trips/pricing.py`, `apps/trips/ai.py`, `apps/trips/management/commands/evaluate_price.py`, `data/ai/price_synth.csv`, `docs/ai/price.md`, partie « prix » de `static/js/app.js` |
| Entraînement des modèles | `apps/core/management/commands/train_ai_models.py` |
| Templates | `templates/shipments/*`, `templates/trips/*`, `templates/partials/freight_card.html`, `templates/partials/trip_card.html` |
| Tests | `apps/shipments/tests/`, `apps/trips/tests/` |

**Soutenance** : CRUD complet d'une annonce et d'un trajet, validations (date limite, poids, capacité du véhicule),
recherche avec filtres et pagination, annonce intelligente (texte libre → formulaire pré-rempli), suggestion de prix.
**À maîtriser** : ModelForms, `clean()` vs `clean_<champ>()`, validation HTML5 + serveur, CBV génériques
(Create/Update/Delete/List/Detail), index et `select_related`, pagination ; client LLM (timeout, retries, repli local),
précision par champ ; régression GradientBoosting, MAE / RMSE / R², données synthétiques et leurs limites.

---

## Farah Maiti — Réservations, machine à états, messagerie, IA matching
Branche : `member4/bookings-matching-messaging`

| Domaine | Fichiers |
|---|---|
| Réservations | `apps/bookings/models.py` (BookingRequest, BookingStatusHistory), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Machine à états | `apps/bookings/services.py` |
| Messagerie | `apps/messaging/*`, `templates/messaging/*` |
| Infrastructure IA asynchrone | `apps/core/models.py` (AIJob), `apps/core/tasks.py`, `apps/core/ai/registry.py`, `config/celery.py`, polling dans `static/js/app.js` |
| **IA 3 — matching** | `apps/bookings/matching.py`, `apps/bookings/ai.py`, `apps/bookings/management/commands/evaluate_matching.py`, `data/ai/matching_labeled.json`, `docs/ai/matching.md`, partie « matching » de `static/js/app.js` |
| Templates | `templates/bookings/*`, `templates/partials/booking_row.html` |
| Tests | `apps/bookings/tests/`, `apps/messaging/tests/`, `apps/core/tests/test_ai_infra.py` |

**Soutenance** : demande depuis un trajet / offre depuis une annonce, accepter → démarrer → livrer, historique des
statuts, transition interdite par URL directe, messagerie, matching IA avec le détail du score.
**À maîtriser** : table `TRANSITIONS` et contrôle de l'acteur, `transaction.atomic` + `select_for_update`,
réservation / libération de capacité, refus automatique des offres concurrentes ; Celery + Redis, `AIJob`,
`202 Accepted` + polling, repli en thread sans broker ; score pondéré, Precision@5, NDCG@5.

---

## Wissem Ferjani — Avis, notifications, tableaux de bord, accessibilité, IA sentiment
Branche : `member5/reviews-notifs-dashboard-sentiment`

| Domaine | Fichiers |
|---|---|
| Avis & réputation | `apps/reviews/models.py`, `forms.py`, `views.py`, `services.py`, `urls.py`, `admin.py` |
| **IA 4 — sentiment** | `apps/reviews/ai.py`, `apps/reviews/management/commands/evaluate_sentiment.py`, `data/ai/reviews_sentiment_*.csv`, `docs/ai/sentiment.md` |
| Évaluation commune | `apps/core/ai/evaluation.py` (latence moyenne / p95, rapports, matrices de confusion) |
| Notifications | `apps/notifications/*`, `templates/notifications/*` |
| Tableaux de bord | `apps/dashboard/*`, `templates/dashboard/*` |
| Accueil & accessibilité | `templates/core/home.html`, `templates/errors/*`, `docs/accessibility.md`, revue accessibilité du socle (`base.html`, `navbar.html`, `cargolink.css`) |
| Tests | `apps/reviews/tests/`, `apps/notifications/tests/`, `apps/dashboard/tests/`, `apps/core/tests/test_core.py` |

**Soutenance** : page d'accueil, avis après livraison → note moyenne et score de réputation, notifications, tableaux de
bord PME / transporteur / admin, démonstration clavier (lien d'évitement, focus, modale) et audit Lighthouse / axe.
**À maîtriser** : TF-IDF + régression logistique, précision / rappel / F1 / matrice de confusion, biais du jeu de test,
formule de réputation (lissage bayésien) ; context processor, `aria-live` ; WCAG AA : repères sémantiques, un seul h1,
`aria-describedby`, contrastes 4,5:1, `:focus-visible`, piège de focus des modales.

---

## Commun à tous (QCM individuel)
Chacun doit pouvoir expliquer : le cycle requête → URL → vue → template, les modèles et migrations, l'ORM et
`select_related`, les CBV et mixins, les formulaires et la validation, CSRF et l'authentification, la structure des
settings, les tests (`pytest`, `manage.py test`, couverture), Docker / docker compose et le rôle de Celery.
Voir aussi `docs/JURY_QA.md`.

## Règles de contribution
1. Travailler sur sa branche, commits petits et conventionnels : `feat(scope): …`, `fix(scope): …`, `test(scope): …`,
   `docs(scope): …`, `refactor(scope): …`, `chore(scope): …`.
2. `ruff check . && ruff format --check . && pytest` avant chaque push.
3. Pull request vers `main`, CI verte, relecture par un autre membre, merge `--no-ff`.
4. Chacun commite avec **sa propre identité Git** (`git config user.name` / `user.email`).
