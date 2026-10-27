# Accessibilité — WCAG 2.1 niveau AA

## Checklist appliquée

### Structure et sémantique
- [x] `<html lang="fr">`, titre de page unique (`<title>… · CargoLink</title>`).
- [x] Repères `<header>`, `<nav aria-label>`, `<main id="main">`, `<footer>` dans `templates/base.html`.
- [x] **Exactement un `<h1>` par page** et hiérarchie h1 → h2 → h3 cohérente (vérifiée automatiquement par le script de
      fumée sur toutes les pages, et par les tests sur les pages principales).
- [x] Fil d'Ariane (`nav aria-label="Fil d'Ariane"`, `aria-current="page"`), tableaux avec `<caption>` et `scope="col"`.
- [x] Listes de définitions (`<dl>`) pour les fiches détaillées.

### Navigation clavier
- [x] **Lien d'évitement** « Aller au contenu principal », visible au focus (`.skip-link`).
- [x] Focus toujours visible : `:focus-visible` = contour jaune 3 px + halo marine (contraste ≥ 3:1 sur tous les fonds).
- [x] Tout est atteignable au clavier (Tab / Maj+Tab / Entrée / Espace) ; aucun `tabindex` positif.
- [x] **Modales** (confirmation de refus/annulation) : Bootstrap 5 piège le focus dans la modale, `Échap` la ferme et le
      focus revient sur le bouton déclencheur ; `aria-labelledby` sur le titre.
- [x] Menu mobile : bouton `aria-controls` / `aria-expanded` / `aria-label="Ouvrir le menu"`.
- [x] Navigation principale avec `aria-current="page"` sur la section active (`{% nav_current %}`).

### Formulaires
- [x] Chaque champ a un `<label for>` ; les champs obligatoires sont marqués `*` + texte masqué « (obligatoire) » et
      l'attribut HTML5 `required`.
- [x] **Erreurs liées au champ** : `aria-invalid="true"` et `aria-describedby="id_<champ>_error"` (+ aide) —
      `apps/core/forms.py` (`StyledFormMixin`) et `templates/partials/form_field.html`.
- [x] Résumé d'erreurs en tête de formulaire (`role="alert"`).
- [x] Validation HTML5 côté client (`type="date"`, `min`, `maxlength`, `pattern`) **et** validation serveur.
- [x] Groupes de boutons radio (note de l'avis) dans un `<fieldset>` avec `<legend>`.

### Contenus dynamiques
- [x] Messages Django affichés en toasts dans une région **`aria-live="polite"`** (`role="alert"` pour les erreurs).
- [x] Panneaux IA : `aria-busy="true"` pendant le calcul, spinner décoratif `aria-hidden`, statut dans un
      `role="status" aria-live="polite"`, **message d'erreur explicite en français** en cas d'échec ou de délai.
- [x] Fil de messages `role="log" aria-live="polite"`, nombre de résultats de recherche annoncé.
- [x] Badge de notifications : le lien porte `aria-label="Notifications : N non lues"`.

### Images, icônes, couleurs
- [x] Logo : SVG avec `alt=""` à côté du texte « CargoLink » (pas de doublon lu par les lecteurs d'écran).
- [x] Icônes Bootstrap Icons **toujours** `aria-hidden="true"` ; boutons icône seuls avec `aria-label`
      (ex. « Modifier <titre> », « Fermer la notification »).
- [x] Barres de score : `role="img"` + `aria-label="Score de compatibilité 87 %"` ; étoiles : `aria-label="Note : 4,5 sur 5"`.
- [x] Statut jamais transmis par la couleur seule : chaque badge contient le libellé du statut.

### Contrastes (≥ 4,5:1 texte normal)
| Couple | Ratio |
|---|---|
| Texte `#1b2533` sur fond `#F3F6FA` | 14,3:1 |
| Texte secondaire `#4f5a68` sur `#F3F6FA` (remplace le `#6c757d` de Bootstrap, 4,2:1 insuffisant) | 6,5:1 |
| Liens `#123a78` sur blanc / sur `#F3F6FA` | 11,0:1 / 10,2:1 |
| Blanc sur marine `#0B2A5B` (navbar, footer, boutons) | 14,0:1 |
| Jaune `#FFB400` sur marine (lien actif, slogan) | 7,9:1 |
| Marine sur jaune (boutons « accent », badge « en attente ») | 7,9:1 |
| Jaune sur bleu du dégradé `#143f80` (slogan de l'accueil) | 5,7:1 |
| Blanc sur badges `#0a58ca` / `#146c43` / `#b02a37` / `#5b2c9c` / `#495057` | 6,4 / 6,5 / 6,5 / 9,2 / 8,2 |
| Erreurs `#a1202c` sur blanc | 7,6:1 |
| Étoiles `#8a5a00` sur blanc | 5,9:1 |

Ratios calculés avec la formule de luminance relative WCAG 2.1.

**Règle** : le jaune n'est **jamais** utilisé comme couleur de texte sur fond blanc — seulement sur fond marine ou en
décoration (barre d'accent des cartes, soulignement des titres).

### Divers
- [x] Responsive (grilles Bootstrap, tableaux `table-responsive`), zoom 200 % sans perte.
- [x] `prefers-reduced-motion` : animations et transitions désactivées.
- [x] Langue et formats français (dates `d/m/Y`, nombres « 1 234,50 TND »).

## Vérifier avec Lighthouse

1. Lancer l'application (`python manage.py runserver` ou `docker compose up`) et charger les données de démo.
2. Chrome → F12 → onglet **Lighthouse** → catégorie **Accessibility** → *Analyze page load*.
3. Pages à auditer : `/`, `/comptes/connexion/`, `/annonces/`, `/trajets/`, une fiche annonce, une demande
   (`/demandes/<id>/`), un tableau de bord. Pour les pages connectées, se connecter d'abord dans le même onglet.
4. Ligne de commande : `npx lighthouse http://localhost:8000/ --only-categories=accessibility --view`.

## Vérifier avec axe

- Extension navigateur **axe DevTools** (Deque) → *Scan all of my page* sur les mêmes pages.
- Ligne de commande (pages publiques) :
  ```bash
  npx @axe-core/cli http://localhost:8000/ http://localhost:8000/comptes/connexion/ http://localhost:8000/comptes/inscription/pme/ --exit
  ```
  `--exit` renvoie un code d'erreur si une violation est trouvée (utilisable en CI).

## Tests manuels recommandés
- Parcourir une demande de réservation **uniquement au clavier** : Tab jusqu'à « Refuser », Entrée (modale), Tab dans
  la modale (le focus ne sort pas), Échap (retour au bouton).
- Lecteur d'écran (NVDA sous Windows) : vérifier l'annonce des toasts après une action et du statut des panneaux IA.
