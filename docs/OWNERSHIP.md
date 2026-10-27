# Répartition du code par membre

Chaque membre est **propriétaire** de son périmètre : il en connaît le code, le défend à la soutenance, relit les
pull requests qui le touchent et y fait ses commits depuis **son propre compte Git**, sur sa branche.

Le **socle commun** est partagé : `config/` (settings, urls), `manage.py`, `apps/core/` (mixins, `geo.py`, `choices.py`,
`forms.py`, `views.py`, `urls.py`, `templatetags/`, `testing/factories.py`), `templates/base.html`,
`templates/partials/` génériques et `static/`. Toute modification du socle passe par une PR relue par au moins un
autre membre.

## Membre 1 — Comptes, modération, IA fraude, déploiement
Branche : `member1/accounts-moderation-fraud-deploy`

| Domaine | Fichiers |
|---|---|
| Comptes & profils | `apps/accounts/models.py` (User, CompanyProfile, CarrierProfile, Report), `forms.py`, `views.py`, `urls.py`, `signals.py`, `admin.py` |
| Groupes & permissions | `apps/accounts/migrations/0002_create_groups.py` |
| Contrôle d'accès | `apps/core/mixins.py` (RoleRequiredMixin, OwnerRequiredMixin) |
| Modération | `ModerationView`, `ModerationActionView`, `templates/accounts/moderation.html`, `report_form.html` |
| **IA 5 — fraude/spam** | `apps/accounts/fraud.py`, `apps/accounts/management/commands/evaluate_fraud.py`, `data/ai/fraud_labeled.csv`, `docs/ai/fraud.md` |
| Déploiement | `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`, `render.yaml`, `.github/workflows/ci.yml`, `config/settings/prod.py`, `.env.example` |
| Données de démo | `apps/core/management/commands/seed_demo.py` |
| Templates | `templates/accounts/*` |
| Tests | `apps/accounts/tests/`, `apps/core/tests/test_permissions.py` |

## Membre 2 — Annonces de fret, IA annonce intelligente
Branche : `member2/shipments-smart-annonce`

| Domaine | Fichiers |
|---|---|
| Annonces | `apps/shipments/models.py` (FreightRequest), `forms.py` (FreightRequestForm, SearchForm), `views.py`, `urls.py`, `admin.py` |
| Recherche & filtres | `FreightSearchView`, `templates/partials/search_form.html`, `templates/partials/pagination.html` |
| **IA 1 — annonce intelligente** | `apps/shipments/ai.py`, `apps/shipments/management/commands/evaluate_smart_annonce.py`, `data/ai/smart_annonce_50.jsonl`, `docs/ai/smart_annonce.md`, partie « smart annonce » de `static/js/app.js` |
| Client LLM | `apps/core/ai/llm_client.py` |
| Templates | `templates/shipments/*`, `templates/partials/freight_card.html` |
| Tests | `apps/shipments/tests/` |

## Membre 3 — Trajets & véhicules, IA prix
Branche : `member3/trips-price`

| Domaine | Fichiers |
|---|---|
| Véhicules & trajets | `apps/trips/models.py` (Vehicle, Trip), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Référentiel géographique | `apps/core/geo.py` (villes tunisiennes, distances) |
| **IA 2 — prix** | `apps/trips/pricing.py`, `apps/trips/ai.py`, `apps/trips/management/commands/evaluate_price.py`, `data/ai/price_synth.csv`, `docs/ai/price.md`, partie « prix » de `static/js/app.js` |
| Entraînement | `apps/core/management/commands/train_ai_models.py` |
| Templates | `templates/trips/*`, `templates/partials/trip_card.html` |
| Tests | `apps/trips/tests/` |

## Membre 4 — Réservations, IA matching, messagerie
Branche : `member4/bookings-matching-messaging`

| Domaine | Fichiers |
|---|---|
| Réservations | `apps/bookings/models.py` (BookingRequest, BookingStatusHistory), `forms.py`, `views.py`, `urls.py`, `admin.py` |
| Machine à états | `apps/bookings/services.py` |
| **IA 3 — matching** | `apps/bookings/matching.py`, `apps/bookings/ai.py`, `apps/bookings/management/commands/evaluate_matching.py`, `data/ai/matching_labeled.json`, `docs/ai/matching.md`, partie « matching » de `static/js/app.js` |
| Messagerie | `apps/messaging/*`, `templates/messaging/*` |
| Infrastructure IA asynchrone | `apps/core/models.py` (AIJob), `apps/core/tasks.py`, `apps/core/ai/registry.py`, `config/celery.py` |
| Templates | `templates/bookings/*`, `templates/partials/booking_row.html` |
| Tests | `apps/bookings/tests/`, `apps/messaging/tests/`, `apps/core/tests/test_ai_infra.py` |

## Membre 5 — Avis, notifications, tableau de bord, IA sentiment
Branche : `member5/reviews-notifs-dashboard-sentiment`

| Domaine | Fichiers |
|---|---|
| Avis & réputation | `apps/reviews/models.py`, `forms.py`, `views.py`, `services.py`, `urls.py`, `admin.py` |
| **IA 4 — sentiment** | `apps/reviews/ai.py`, `apps/reviews/management/commands/evaluate_sentiment.py`, `data/ai/reviews_sentiment_*.csv`, `docs/ai/sentiment.md` |
| Notifications | `apps/notifications/*`, `templates/notifications/*` |
| Tableaux de bord | `apps/dashboard/*`, `templates/dashboard/*` |
| Accueil & accessibilité | `templates/core/home.html`, `templates/errors/*`, `docs/accessibility.md`, revue accessibilité du socle (`base.html`, `navbar.html`, `cargolink.css`) |
| Évaluation commune | `apps/core/ai/evaluation.py` |
| Tests | `apps/reviews/tests/`, `apps/notifications/tests/`, `apps/dashboard/tests/`, `apps/core/tests/test_core.py` |

## Règles de contribution
1. Travailler sur sa branche `memberN/...`, commits petits et conventionnels : `feat(scope): …`, `fix(scope): …`,
   `test(scope): …`, `docs(scope): …`, `refactor(scope): …`, `chore(scope): …`.
2. `ruff check . && ruff format --check . && pytest` avant chaque push.
3. Pull request vers `main`, CI verte, relecture par un autre membre, merge `--no-ff`.
4. Chacun commite avec **sa propre identité Git** (`git config user.name` / `user.email`).
