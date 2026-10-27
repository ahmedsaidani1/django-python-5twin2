# Questions probables du jury — réponses argumentées

## Architecture

**Pourquoi Django et pas un SPA (React) + API ?**
Le besoin est un back-office transactionnel (formulaires, rôles, workflow) : Django fournit ORM, auth, formulaires
validés, admin et protection CSRF/XSS intégrés. Le rendu serveur garde l'accessibilité et le SEO simples ; le JS natif
n'est utilisé que là où il apporte quelque chose (polling IA, toasts). Une API REST pourrait être ajoutée plus tard
(DRF) sans toucher aux services métier.

**Pourquoi un `User` personnalisé dès le départ ?**
Changer de modèle utilisateur après la première migration est très coûteux. `User(AbstractUser)` avec un champ `role`
est créé dans `accounts/0001` ; les groupes et permissions sont créés par une migration de données (`0002`) et un
signal garde chaque utilisateur dans le groupe de son rôle.

**Comment garantissez-vous les droits d'accès ?**
Deux mixins réutilisables sur **toutes** les vues : `RoleRequiredMixin` (anonyme → page de connexion, mauvais rôle → 403)
et `OwnerRequiredMixin` (objet d'un autre utilisateur → 403). Les querysets sont aussi filtrés (une annonce masquée
renvoie 404 aux autres). Un test parcourt toutes les vues et vérifie les 4 cas : anonyme, mauvais rôle, non-propriétaire,
propriétaire — un accès direct par URL ne contourne rien.

**Où est la logique métier ?**
Dans `apps/bookings/services.py` et non dans les vues : la machine à états est une table `TRANSITIONS`
`(statut_actuel, statut_cible) → acteur autorisé`. Chaque transition est atomique (`transaction.atomic` +
`select_for_update`), met à jour la capacité du trajet et le statut de l'annonce, écrit l'historique et notifie
l'autre partie. Les vues ne font qu'appeler `transition()`. C'est testable unitairement : nous testons les 36 couples
de statuts.

**Que se passe-t-il si deux transporteurs acceptent en même temps ?**
Le verrou `select_for_update` sur la réservation et le trajet sérialise les acceptations ; la seconde voit l'annonce
déjà « attribuée » et lève `InvalidTransition`. À l'acceptation, les autres offres en attente sur la même annonce sont
refusées automatiquement (et leurs auteurs notifiés).

**Comment gérez-vous la performance ?**
`select_related`/`prefetch_related` sur toutes les listes (pas de N+1), index sur les champs filtrés (villes, dates,
type, statut, couples `user/status`), pagination partout, `CONN_MAX_AGE` pour réutiliser les connexions PostgreSQL,
fichiers statiques compressés et mis en cache longue durée par WhiteNoise. Les appels IA ne bloquent jamais la requête.

## Sécurité

**Quelles protections avez-vous mises en place ?**
- CSRF actif sur tous les formulaires et les appels `fetch` (en-tête `X-CSRFToken`) ; déconnexion en POST.
- ORM uniquement, aucune requête SQL brute → pas d'injection SQL.
- Échappement automatique des templates (un test vérifie qu'un `<script>` dans un titre est échappé) ; le JS insère les
  résultats IA avec `textContent`, jamais `innerHTML` sur des données utilisateur.
- Mots de passe hachés (PBKDF2 de Django) + validateurs de robustesse.
- **Limitation des tentatives de connexion** : django-axes bloque le couple identifiant + IP après 5 échecs pendant
  15 minutes (HTTP 429, testé).
- Redirections : la notification n'ouvre que des URLs internes (`url_has_allowed_host_and_scheme`).
- Production : `DEBUG=False`, HTTPS forcé, HSTS 1 an, cookies `Secure` + `HttpOnly`, `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy`. `manage.py check --deploy` passe sans avertissement en CI.
- Secrets uniquement dans l'environnement (`.env`, jamais commité ; `.env.example` fourni).

**Et les erreurs ?**
Pages 403/404/500 personnalisées (la 500 est rendue sans contexte pour ne pas dépendre de la base). Les appels externes
(LLM, broker) sont entourés de `try/except` avec journalisation, et une notification qui échoue ne casse jamais l'action
principale. Les erreurs internes de l'IA sont journalisées mais l'utilisateur ne voit qu'un message français générique.

## Intelligence artificielle

**Pourquoi les appels IA sont-ils asynchrones ?**
Un appel LLM peut prendre plusieurs secondes ou échouer. La vue crée un `AIJob`, le met en file Celery et renvoie
immédiatement `202 {job_id}` ; le navigateur interroge `/ai/jobs/<id>/`. Chaque job garde l'entrée, la sortie, l'erreur
et la **latence en ms**, ce qui permet de suivre les performances (tableau de bord admin). Si Redis est indisponible,
le job s'exécute dans un thread d'arrière-plan : la requête HTTP ne bloque toujours pas.

**Votre IA dépend-elle d'OpenAI ?**
Non. `LLMClient` est agnostique (API compatible OpenAI — OpenAI, Groq, Mistral, Ollama… — ou Anthropic), configuré par
variables d'environnement, avec timeout, retries exponentiels sur les erreurs transitoires et une exception unique
`LLMError`. Sans clé (ou en cas d'échec), des modèles **locaux** prennent le relais : la démo fonctionne hors ligne.

**Comment avez-vous mesuré la qualité de chaque IA ?**
Une commande `evaluate_<feature>` par IA calcule les métriques + latence moyenne/p95 et écrit `docs/ai/<feature>.md` :
- annonce intelligente : précision par champ sur 50 textes annotés à la main (98,6 %) ;
- prix : MAE / RMSE / R² sur un jeu de test séparé (R² 0,968), comparé à une référence « tarif médian » ;
- matching : Precision@5 et NDCG@5 sur 40 requêtes annotées, comparés à deux références et à la borne supérieure ;
- sentiment : précision / rappel / F1 + matrice de confusion sur 75 avis rédigés à la main, jamais vus à l'entraînement ;
- fraude : précision / rappel / F1 / ROC-AUC + matrice de confusion, gabarits de texte disjoints entre train et test,
  tableau du compromis selon le seuil.

**Vos données sont synthétiques : les résultats sont-ils crédibles ?**
Nous le disons explicitement dans chaque rapport. Nous avons limité les biais : jeux de test rédigés à la main
(annonces, avis), gabarits disjoints (fraude), grille d'annotation indépendante des poids (matching), bruit
irréductible injecté (prix). Nous documentons aussi un biais réel : le vocabulaire du modèle de sentiment a été élargi
une fois après une première évaluation (F1 0,774 → 0,867), le score est donc probablement un peu optimiste. Les modèles
sont conçus pour être ré-entraînés sur les vraies données de la plateforme (avis notés, décisions de modération).

**Pourquoi un score pondéré pour le matching et pas du deep learning ?**
Sans historique d'interactions, un modèle appris n'a rien à apprendre. Un score explicable (trajet, date, capacité,
prix, réputation) est affiché à l'utilisateur avec le détail de chaque composante, respecte les contraintes dures
(capacité, chaîne du froid) et atteint un NDCG@5 de 0,92. Avec des données réelles (demandes acceptées), on pourrait
apprendre ces poids (learning-to-rank).

**Comment la fraude est-elle utilisée ? Bannissez-vous automatiquement ?**
Non : l'IA **signale** (score + raisons : téléphone, lien, vocabulaire de spam, prix aberrant, rafale de publications),
l'administrateur décide (masquer, valider, désactiver le compte). Un faux positif coûte une vérification, pas un client.

**Comment la réputation est-elle calculée ?**
`60 % note moyenne + 40 % sentiment des commentaires`, ramené sur 100, avec lissage bayésien vers 50 (k = 3) pour qu'un
transporteur avec un seul avis 5★ ne dépasse pas un transporteur avec 30 avis 4,8★.

## Tests et qualité

**Comment prouvez-vous que le code fonctionne ?**
150+ tests (pytest + factory_boy), exécutables aussi par `python manage.py test`, couverture ≈ 98 % (seuil bloquant
80 %) : modèles, validations, toutes les transitions, permissions de toutes les vues, endpoints IA avec client LLM
simulé, commandes d'évaluation. La CI GitHub Actions les relance sur PostgreSQL à chaque push, avec ruff, le contrôle
des migrations et `check --deploy`.

## Accessibilité

**Comment avez-vous vérifié l'accessibilité ?**
Checklist WCAG AA appliquée (`docs/accessibility.md`) : repères sémantiques, un seul h1 par page (contrôlé
automatiquement sur toutes les pages), lien d'évitement, focus visible, erreurs liées par `aria-describedby`, régions
`aria-live`, modales qui piègent le focus, contrastes calculés (jaune jamais en texte sur blanc). Vérification avec
Lighthouse et axe (procédure dans le document).

## Déploiement

**Comment déployez-vous ?**
Image Docker (Python 3.12-slim, utilisateur non-root, statiques et modèles IA intégrés), `docker compose up` lance web
(gunicorn), PostgreSQL, Redis et le worker Celery, migrations et données de démo automatiques. Sur Render (offre
gratuite), le Blueprint `render.yaml` crée la base PostgreSQL et le service web ; migrations et premier chargement des
données de démo s'exécutent au démarrage.

**Sur Render il n'y a pas de Celery : l'IA est-elle encore asynchrone ?**
Oui. Les workers Render sont payants ; sans broker, `submit_job` le détecte (sonde TCP rapide) et exécute la tâche dans
un thread d'arrière-plan. La requête HTTP renvoie toujours `202` immédiatement et le navigateur interroge
`/ai/jobs/<id>/`. Le même code utilise Celery + Redis dès qu'un broker est disponible (docker compose, ou Render payant
en ajoutant un service Key Value et un worker).

**Pourquoi WhiteNoise et pas nginx ?**
Sur un PaaS, il n'y a pas de nginx devant l'application : WhiteNoise sert les statiques compressés avec des noms hachés
(cache navigateur d'un an) directement depuis gunicorn, sans service supplémentaire.

**Comment passer à l'échelle ?**
Le web est sans état (sessions en base, fichiers statiques dans l'image) : on ajoute des instances derrière le
load balancer. Les workers Celery se multiplient indépendamment. Les modèles IA sont chargés une fois par processus.

## Organisation

**Comment l'équipe s'est-elle répartie le travail ?**
Par domaine fonctionnel (voir `docs/OWNERSHIP.md`) : chaque membre possède une app Django, son IA, ses templates et ses
tests, sur sa branche `memberN/...`, avec commits conventionnels et pull requests relues par un autre membre.
