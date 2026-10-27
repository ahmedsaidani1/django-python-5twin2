# CargoLink

**Marketplace de covoiturage de fret entre PME et transporteurs indépendants — _Connecter • Optimiser • Avancer ensemble_.**

Projet ESPRIT 5TWIN (équipe de 4 : Ahmed Saidani, Fedi Ben Khalifa, Farah Maiti, Wissem). Les PME publient leurs besoins de transport, les transporteurs déclarent leurs
trajets et leur capacité libre ; CargoLink les met en relation, gère les demandes de réservation jusqu'à la livraison,
la messagerie, les avis et la modération, avec 5 fonctionnalités d'IA mesurées.

| | |
|---|---|
| Stack | Python 3.12 · Django 5.2 · PostgreSQL 16 · Redis 7 + Celery 5 · Bootstrap 5 · JS natif |
| IA | scikit-learn (régression, classification), règles NLP françaises, client LLM multi-fournisseur |
| Qualité | 150+ tests (pytest + `manage.py test`), couverture ≈ 98 %, ruff, CI GitHub Actions |
| Déploiement | Docker + docker compose (web gunicorn, db, redis, worker), WhiteNoise, Render (`render.yaml`) |

---

## Sommaire

1. [Fonctionnalités](#fonctionnalités)
2. [Architecture](#architecture)
3. [Installation locale (venv)](#installation-locale-venv)
4. [Docker](#docker)
5. [Tests et qualité](#tests-et-qualité)
6. [Intelligence artificielle](#intelligence-artificielle)
7. [Déploiement sur Render](#déploiement-sur-render)
8. [Comptes de démonstration](#comptes-de-démonstration)
9. [Scénario de démonstration (soutenance)](#scénario-de-démonstration-soutenance)
10. [Organisation Git de l'équipe](#organisation-git-de-léquipe)
11. [Documentation complémentaire](#documentation-complémentaire)

---

## Fonctionnalités

| # | Fonctionnalité | Où |
|---|---|---|
| 1 | Inscription par rôle (PME / transporteur), connexion, déconnexion, mot de passe oublié, édition du profil (`CompanyProfile`, `CarrierProfile`, véhicules) | `apps/accounts`, `apps/trips` |
| 2 | Publication d'annonces de fret (`FreightRequest`) et de trajets (`Trip`, prix au kg ou forfait) | `apps/shipments`, `apps/trips` |
| 3 | Recherche : ville de départ/arrivée, date, volume, type de marchandise, texte libre, pagination | vues `*SearchView` |
| 4 | Mise en relation : demande depuis un trajet (PME) ou offre depuis une annonce (transporteur), message + prix proposé | `apps/bookings` |
| 5 | Machine à états `en_attente → acceptee → en_cours → livree` (+ `refusee`, `annulee`), transitions contrôlées par rôle, historique | `apps/bookings/services.py` |
| 6 | Tableaux de bord par rôle : annonces/trajets, demandes reçues/envoyées, livraisons, historique, notifications, statistiques | `apps/dashboard` |
| 7 | Messagerie : un fil par réservation, non-lus | `apps/messaging` |
| 8 | Avis après livraison, note moyenne et score de réputation du transporteur | `apps/reviews` |
| 9 | Notifications in-app (nouvelle demande, changement de statut, nouveau message, avis, modération) | `apps/notifications` |
| 10 | Signalement d'une annonce / d'un trajet / d'un utilisateur, file de modération, désactivation, admin Django complet | `apps/accounts` |
| 11 | Page d'accueil : problème, solution, valeur pour chaque acteur, appels à l'action | `templates/core/home.html` |

**IA** : annonce intelligente, suggestion de prix, matching, sentiment des avis → réputation, détection de fraude
(voir [Intelligence artificielle](#intelligence-artificielle)).

---

## Architecture

```mermaid
flowchart LR
    subgraph Client["Navigateur (Bootstrap 5 + JS natif)"]
        UI[Pages Django<br/>templates accessibles]
        JS[app.js<br/>polling /ai/jobs/&lt;id&gt;/]
    end

    subgraph Web["Django (gunicorn + WhiteNoise)"]
        MW[Middlewares<br/>CSRF · Axes · Security]
        V[Vues CBV<br/>RoleRequiredMixin · OwnerRequiredMixin]
        S[Services métier<br/>machine à états, notifications]
        AIV[API IA<br/>POST /ai/&lt;kind&gt;/ · GET /ai/jobs/&lt;id&gt;/]
    end

    subgraph Worker["Celery worker"]
        T[run_ai_job]
        M[Modèles locaux<br/>règles FR · GBR · TF-IDF+LogReg · RandomForest · score pondéré]
        LLM[LLMClient<br/>OpenAI-compatible / Anthropic<br/>timeout · retries]
    end

    DB[(PostgreSQL)]
    R[(Redis<br/>broker)]

    UI -->|HTTP| MW --> V --> S --> DB
    JS -->|fetch JSON| AIV
    AIV -->|crée AIJob| DB
    AIV -->|apply_async| R --> T
    T --> M
    T -.->|si AI_API_KEY| LLM
    T -->|output, latency_ms| DB
```

**Applications Django** (`apps/`) :

| App | Rôle |
|---|---|
| `core` | gabarit, accueil, pages d'erreur 403/404/500, mixins d'accès, `AIJob`, client LLM, tâches Celery, `seed_demo`, `train_ai_models` |
| `accounts` | `User` (rôle), profils PME/transporteur, signalements, modération, groupes (migration de données), IA anti-fraude |
| `shipments` | annonces de fret, recherche, IA « annonce intelligente » |
| `trips` | véhicules, trajets, recherche, IA de prix |
| `bookings` | demandes de réservation, machine à états, historique, IA de matching |
| `messaging` | fil de messages par réservation |
| `reviews` | avis, réputation, IA de sentiment |
| `notifications` | notifications in-app, compteur dans la barre de navigation |
| `dashboard` | tableaux de bord PME / transporteur / admin |

**Choix clés**
- `User(AbstractUser)` avec un champ `role`, créé dès la première migration ; groupes et permissions créés par une migration de données (`accounts/0002_create_groups`) et synchronisés au rôle par un signal.
- Contrôle d'accès sur **chaque** vue : `RoleRequiredMixin` (anonyme → connexion, mauvais rôle → 403) et `OwnerRequiredMixin` (objet d'un autre → 403).
- Logique métier hors des vues (`bookings/services.py`) : transitions atomiques (`select_for_update`), capacité réservée/libérée, refus automatique des offres concurrentes.
- Performance : `select_related`/`prefetch_related`, index sur les champs de recherche (villes, dates, type, statut), pagination partout.
- Paramètres séparés `config/settings/{base,dev,prod,test}.py` ; secrets uniquement dans l'environnement (`.env`, voir `.env.example`).

---

## Installation locale (venv)

Prérequis : Python 3.12+ (testé aussi en 3.14), Git. PostgreSQL et Redis sont optionnels en local
(SQLite par défaut ; sans Redis, les tâches IA tournent dans un thread d'arrière-plan).

```bash
git clone <url-du-repo> cargolink && cd cargolink
python -m venv .venv
# Windows : .venv\Scripts\activate    —    Linux/macOS : source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # puis éditer SECRET_KEY ; commenter DATABASE_URL pour rester en SQLite

python manage.py migrate
python manage.py train_ai_models   # entraîne les modèles IA locaux (quelques secondes)
python manage.py seed_demo         # comptes et données de démonstration
python manage.py runserver         # http://127.0.0.1:8000
```

Avec PostgreSQL et Redis de docker compose :

```bash
docker compose up -d db redis
# .env : DATABASE_URL=postgres://cargolink:cargolink@localhost:5432/cargolink  et  REDIS_URL=redis://localhost:6379/0
# (ports à publier : ajouter "5432:5432" et "6379:6379" aux services db/redis si besoin)
celery -A config worker -l info --pool=solo   # --pool=solo sous Windows
python manage.py runserver
```

---

## Docker

```bash
docker compose up --build
```

- **web** : gunicorn sur http://localhost:8000 — applique les migrations puis charge les données de démo (`SEED_DEMO=1` par défaut ; `SEED_DEMO=0 docker compose up` pour ne pas réinitialiser) ;
- **db** : PostgreSQL 16 (volume `pgdata`) ; **redis** : broker Celery ; **worker** : `celery -A config worker`.
- L'image (Python 3.12-slim, utilisateur non-root) contient les fichiers statiques (WhiteNoise) et les modèles IA entraînés.
- En local, compose désactive la redirection HTTPS et les cookies `Secure` (HTTP simple) ; en production ils restent actifs.

---

## Tests et qualité

```bash
pytest                    # tests + couverture (échoue sous 80 %), rapport HTML dans htmlcov/index.html
python manage.py test     # mêmes tests via le runner Django (settings de test automatiques)
ruff check . && ruff format --check .
python manage.py makemigrations --check --dry-run
```

- **Unitaires** : modèles, validateurs de formulaires, **toutes** les transitions de la machine à états (valides et invalides, bon et mauvais acteur), capacité, prix, matching, sentiment, fraude, parseur d'annonce.
- **Intégration** : codes HTTP, contexte, redirections, réponses JSON des endpoints IA (client LLM simulé avec `unittest.mock`).
- **Permissions** : `apps/core/tests/test_permissions.py` parcourt **toutes les vues** et vérifie anonyme / mauvais rôle / non-propriétaire / propriétaire — un accès direct par URL donne une redirection de connexion ou un 403.
- **Sécurité** testée : CSRF présent, mots de passe hachés, échappement XSS, verrouillage après 5 échecs de connexion (django-axes, HTTP 429), redirections ouvertes refusées.
- La CI GitHub Actions (`.github/workflows/ci.yml`) exécute ruff, le contrôle des migrations, `check --deploy`, pytest (PostgreSQL), `manage.py test`, publie `htmlcov/` et construit l'image Docker.

---

## Intelligence artificielle

Chaque appel IA : **tâche Celery asynchrone** → enregistré dans `AIJob` (utilisateur, type, statut, entrée, sortie,
erreur, `latency_ms`) → le navigateur interroge `/ai/jobs/<id>/` (spinner, `aria-busy`, message d'erreur en français).
Le fournisseur se configure par l'environnement (`AI_PROVIDER`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`) via un client
LLM agnostique (timeout, retries exponentiels, exceptions propres). **Sans clé, des modèles locaux prennent le relais**.

| IA | Modèle | Jeu d'évaluation | Résultat | Rapport |
|---|---|---|---|---|
| 1. Annonce intelligente | LLM (JSON) ou règles françaises locales | 50 textes annotés à la main | précision par champ **98,6 %** | [docs/ai/smart_annonce.md](docs/ai/smart_annonce.md) |
| 2. Suggestion de prix | GradientBoostingRegressor (scikit-learn) | 800 trajets de test (synthétiques) | MAE **≈ 39 TND**, RMSE ≈ 74, R² **0,968** | [docs/ai/price.md](docs/ai/price.md) |
| 3. Matching | score pondéré trajet/date/capacité/prix/note | 40 requêtes × 15 candidats annotés | P@5 **0,445** (max 0,48), NDCG@5 **0,917** | [docs/ai/matching.md](docs/ai/matching.md) |
| 4. Sentiment → réputation | TF-IDF mots+caractères + régression logistique | 75 avis rédigés à la main | F1 macro **0,867** | [docs/ai/sentiment.md](docs/ai/sentiment.md) |
| 5. Fraude / spam | RandomForest sur 13 variables explicables | 480 annonces (gabarits disjoints) | P **1,00** · R **0,83** · F1 **0,91** | [docs/ai/fraud.md](docs/ai/fraud.md) |

```bash
python manage.py evaluate_smart_annonce
python manage.py evaluate_price
python manage.py evaluate_matching
python manage.py evaluate_sentiment
python manage.py evaluate_fraud
```

Chaque commande calcule ses métriques **et la latence moyenne / p95**, puis écrit `docs/ai/<feature>.md`
(+ matrice de confusion PNG pour le sentiment et la fraude). Jeux de données : `data/ai/`.
Les limites (données synthétiques, biais éventuels) sont écrites dans chaque rapport.

---

## Déploiement sur Render

Le fichier `render.yaml` (Blueprint) utilise uniquement l'**offre gratuite** : une base PostgreSQL et le service web.

1. Pousser le dépôt sur GitHub (branche `main`).
2. Sur [dashboard.render.com](https://dashboard.render.com) (connexion avec GitHub) : **New + → Blueprint**, choisir le
   dépôt et la branche `main`, laisser `AI_API_KEY` vide, puis **Apply**.
3. Render crée `cargolink-db` et `cargolink-web`. `SECRET_KEY` est générée automatiquement.
4. Build : `pip install`, `collectstatic`, `train_ai_models`. Démarrage : `migrate`, `seed_demo --if-empty` (les comptes
   de démo sont créés au premier démarrage seulement), puis gunicorn (1 worker, 4 threads).
5. Ouvrir l'URL affichée (`https://cargolink-web….onrender.com`) ; le nom d'hôte Render est ajouté automatiquement à
   `ALLOWED_HOSTS` et `CSRF_TRUSTED_ORIGINS`. Chaque push sur `main` redéploie.

**Choix liés à l'offre gratuite** : pas de worker Celery ni de Redis (payants). Sans broker, les tâches IA s'exécutent
dans un thread d'arrière-plan : la requête renvoie toujours `202` immédiatement et le navigateur interroge
`/ai/jobs/<id>/`. Celery + Redis tournent avec `docker compose`. Le service s'endort après ~15 min d'inactivité
(premier chargement ≈ 1 min) et la base gratuite expire au bout d'environ 30 jours.

Production : `DEBUG=False`, redirection HTTPS, HSTS 1 an, cookies `Secure`/`HttpOnly`, `X-Frame-Options: DENY`,
`SECURE_PROXY_SSL_HEADER`, WhiteNoise (fichiers compressés + hachés). `python manage.py check --deploy` est vert en CI.

---

## Comptes de démonstration

Créés par `python manage.py seed_demo` (la commande supprime et recrée ces comptes à chaque exécution).

| Rôle | Identifiant | Mot de passe | Entreprise |
|---|---|---|---|
| Administrateur | `admin` | `Admin2026!` | — (accès aussi à `/admin/`) |
| PME | `pme_sfax` | `Demo2026!` | Agro Sfax SARL (Sfax) |
| PME | `pme_monastir` | `Demo2026!` | Textiles Monastir |
| PME | `pme_bizerte` | `Demo2026!` | Matériaux du Nord (Bizerte) |
| Transporteur | `trans_sahel` | `Demo2026!` | Trans Sahel (Sousse) — semi-remorque + camionnette |
| Transporteur | `frigo_sud` | `Demo2026!` | Frigo Sud Express (Gabès) — camion frigorifique |
| Transporteur | `capbon_log` | `Demo2026!` | Cap Bon Logistique (Nabeul) |

Les données comprennent : des annonces et des trajets ouverts (dates relatives au jour du seed), des réservations **dans chaque statut**
(en attente, acceptée, en cours, livrée, refusée, annulée), des messages, 3 avis (sentiment calculé), une livraison
non encore notée, une annonce frauduleuse détectée par l'IA (compte `promo_fret`) et un signalement ouvert.

> Ces mots de passe sont publics : ne jamais lancer `seed_demo` sur une instance contenant de vraies données.

---

## Scénario de démonstration (soutenance)

Durée ≈ 12 min. Ouvrir deux navigateurs (ou une fenêtre privée) : un pour la PME, un pour le transporteur.

1. **Accueil (1 min)** — `http://localhost:8000` : problème (trajets à vide, PME, acteurs mal connectés), solution, valeur. Montrer le lien d'évitement (Tab) et le focus visible.
2. **PME — annonce intelligente (2 min)** — connexion `pme_sfax` → *Publier une annonce* → saisir « 8 palettes de dattes de Sfax à Tunis demain, livraison sous 3 jours, budget 600 DT » → **Remplir avec l'IA** (spinner, champs pré-remplis) → **Suggérer un budget (IA)** → publier. Expliquer : tâche Celery, `AIJob`, polling, latence affichée.
3. **PME — matching (1 min)** — sur la page de l'annonce : **Trouver les meilleurs trajets** → classement avec score détaillé (trajet, date, capacité, prix, note) → *Envoyer une demande* au trajet *Sfax → Tunis* de Trans Sahel (prix proposé, message).
4. **Transporteur — traitement (2 min)** — autre navigateur, `trans_sahel` : badge de notification → demande reçue → **Accepter** (la capacité du trajet est réservée ; s'il y avait d'autres offres en attente sur l'annonce, elles seraient refusées automatiquement) → message dans le fil → **Démarrer la livraison** → **Marquer comme livrée**. Montrer l'historique des statuts. Tenter une transition interdite par URL directe (`/demandes/<id>/livrer/` sur une demande en attente) → message « non autorisée ».
5. **PME — avis (1 min)** — notification « livrée » → **Noter le transporteur** (5 étoiles + commentaire) → profil public du transporteur : note moyenne et **score de réputation IA** mis à jour.
6. **Recherche (1 min)** — `Trouver un trajet` : filtres ville / date / volume / type « Produits frais » (seuls les camions frigorifiques) + pagination.
7. **Admin — modération (2 min)** — `admin` → tableau de bord (statistiques globales, tâches IA et latences) → *Modération* : annonce « OFFRE EXCEPTIONNELLE !!! » signalée par l'IA (score) + signalement d'une PME → **Masquer** → admin Django (`/admin/`) : tous les modèles, actions de masse.
8. **Qualité (2 min)** — terminal : `pytest` (couverture), `python manage.py evaluate_fraud` (rapport + matrice de confusion), onglet Actions GitHub (CI verte), `docker compose ps`.

---

## Organisation Git de l'équipe

Chaque membre est propriétaire d'un périmètre (fichiers, partie de la soutenance et points à maîtriser dans [docs/OWNERSHIP.md](docs/OWNERSHIP.md)) :

| Membre | Périmètre | Branche(s) |
|---|---|---|
| Ahmed Saidani | comptes, modération, IA fraude, intégration & déploiement | `member1/accounts-moderation-fraud-deploy` |
| Fedi Ben Khalifa | annonces de fret, trajets/véhicules, IA annonce intelligente, IA prix | `member2/shipments-smart-annonce`, `member3/trips-price` |
| Farah Maiti | réservations, messagerie, IA matching, infrastructure IA asynchrone | `member4/bookings-matching-messaging` |
| Wissem | avis, notifications, tableaux de bord, accessibilité, IA sentiment | `member5/reviews-notifs-dashboard-sentiment` |

Flux : une branche par périmètre, commits conventionnels (`feat(bookings): …`, `test(trips): …`, `docs(ai): …`),
pull request vers `main` avec CI verte, revue par un autre membre, merge `--no-ff`.

---

## Documentation complémentaire

- [docs/OWNERSHIP.md](docs/OWNERSHIP.md) — répartition du travail par membre
- [docs/JURY_QA.md](docs/JURY_QA.md) — questions probables du jury et réponses argumentées
- [docs/accessibility.md](docs/accessibility.md) — checklist WCAG AA, Lighthouse et axe
- [docs/ai/](docs/ai/) — rapports d'évaluation des 5 IA
