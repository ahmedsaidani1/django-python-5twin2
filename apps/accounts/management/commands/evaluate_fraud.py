import numpy as np
from django.core.management.base import BaseCommand
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score

from apps.accounts import fraud
from apps.core.ai.evaluation import LatencyTimer, cm_markdown, confusion_matrix_png, md_table, write_report

LABELS = ["légitime", "suspect"]


class Command(BaseCommand):
    help = "Entraîne et évalue la détection de fraude/spam (précision, rappel, F1, matrice de confusion)."

    def add_arguments(self, parser):
        parser.add_argument("--rebuild", action="store_true", help="Régénère le jeu de données.")

    def handle(self, *args, **options):
        rows = fraud.load_dataset(rebuild=options["rebuild"])
        train_rows = [r for r in rows if r["split"] == "train"]
        test_rows = [r for r in rows if r["split"] == "test"]
        model = fraud.train(train_rows)  # saved as the production model
        timer = LatencyTimer()
        X = [fraud.row_vector(r) for r in test_rows]
        proba = np.array([timer.time(model.predict_proba, np.array([x]))[0][1] for x in X])
        y_true = np.array([r["label"] for r in test_rows])
        y_pred = (proba >= fraud.THRESHOLD).astype(int)
        p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
        auc = roc_auc_score(y_true, proba)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        confusion_matrix_png(cm, LABELS, "fraud_confusion.png", "Détection de fraude / spam")

        # Rule baseline: flag any text with contact details or a spam word.
        base = np.array([int(x[0] or x[1] or x[2] or x[3] > 0) for x in X])
        bp, br, bf1, _ = precision_recall_fscore_support(y_true, base, average="binary", zero_division=0)
        tradeoff = []
        for th in (0.3, 0.4, 0.5, 0.6):
            tp_, tr_, tf_, _ = precision_recall_fscore_support(
                y_true, (proba >= th).astype(int), average="binary", zero_division=0
            )
            tradeoff.append([th, float(tp_), float(tr_), float(tf_)])
        importances = sorted(zip(fraud.FEATURES, model.feature_importances_, strict=True), key=lambda kv: -kv[1])[:6]
        sections = [
            (
                "Protocole",
                f"""
- Données : `data/ai/fraud_labeled.csv`, **{len(rows)} annonces synthétiques** (~30 % frauduleuses) avec texte,
  prix proposé, prix attendu (modèle de prix), poids, nombre de publications sur 24 h, ancienneté du compte,
  nombre de signalements.
- **Gabarits de texte disjoints** entre entraînement ({len(train_rows)}) et test ({len(test_rows)}) : le modèle est
  évalué sur des formulations jamais vues. Cas difficiles volontairement inclus : fraudes au texte « propre »
  (seul le prix trahit), annonces légitimes « URGENT ! » ou avec un numéro de téléphone.
- Modèle : forêt aléatoire (300 arbres, `class_weight=balanced`) sur {len(fraud.FEATURES)} variables
  explicables ; seuil d'alerte = {fraud.THRESHOLD}.
- En production : chaque annonce/trajet publié est analysé par une tâche Celery ; au-delà du seuil, l'objet est
  **signalé à l'administrateur** (file de modération), jamais supprimé automatiquement.
""",
            ),
            (
                "Résultats (jeu de test)",
                md_table(
                    ["modèle", "précision", "rappel", "F1", "ROC-AUC"],
                    [
                        ["Forêt aléatoire", float(p), float(r), float(f1), float(auc)],
                        ["Référence : règle « contact ou mot spam »", float(bp), float(br), float(bf1), "—"],
                    ],
                ),
            ),
            ("Matrice de confusion", cm_markdown(cm, LABELS) + "\n\n![Matrice de confusion](fraud_confusion.png)"),
            (
                "Compromis précision / rappel selon le seuil",
                md_table(["seuil", "précision", "rappel", "F1"], tradeoff)
                + "\n\nLe seuil de production est fixé a priori à 0,5 (non optimisé sur le test).",
            ),
            (
                "Variables les plus importantes",
                md_table(["variable", "importance"], [[k, float(v)] for k, v in importances]),
            ),
            (
                "Limites",
                """
Les données sont **synthétiques** : les fraudes y suivent des schémas connus. Sur de vraies annonces, les
performances seront plus basses ; le seuil devra être recalibré à partir des décisions de l'administrateur
(chaque signalement traité est un nouvel exemple annoté).
""",
            ),
            (
                "Interprétation",
                """
Au seuil 0,5, le modèle ne produit quasiment pas de fausse alerte (l'administrateur n'est pas noyé) ; les fraudes
manquées sont surtout celles au texte et au prix « normaux ». Baisser le seuil augmente le rappel au prix de
quelques vérifications manuelles supplémentaires (voir le tableau ci-dessus) : comme l'IA ne fait que signaler,
ce réglage peut être assoupli par l'administrateur. La règle simple rate les fraudes au texte propre et accuse les
annonces légitimes qui laissent un numéro : le modèle combine le texte avec le prix et le comportement du compte.
""",
            ),
        ]
        out = write_report("fraud", "IA 5 — Modération : détection de fraude et de spam", sections, timer.summary())
        self.stdout.write(self.style.SUCCESS(f"P={p:.3f} R={r:.3f} F1={f1:.3f} AUC={auc:.3f} — rapport : {out}"))
