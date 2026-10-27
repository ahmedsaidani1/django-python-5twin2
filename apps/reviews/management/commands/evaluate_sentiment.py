from django.core.management.base import BaseCommand
from sklearn.metrics import classification_report, confusion_matrix

from apps.core.ai.evaluation import LatencyTimer, cm_markdown, confusion_matrix_png, md_table, write_report
from apps.reviews import ai


class Command(BaseCommand):
    help = "Entraîne et évalue le classifieur de sentiment des avis (précision, rappel, F1, matrice de confusion)."

    def add_arguments(self, parser):
        parser.add_argument("--rebuild", action="store_true", help="Régénère le jeu d'entraînement.")

    def handle(self, *args, **options):
        train_rows = ai.load_training_set(rebuild=options["rebuild"])
        test_rows = ai.load_test_set()
        model = ai.train(train_rows)  # saved as the production model
        texts, y_true = zip(*test_rows, strict=True)
        timer = LatencyTimer()
        y_pred = [timer.time(model.predict, [t])[0] for t in texts]
        report = classification_report(y_true, y_pred, labels=ai.LABELS, output_dict=True, zero_division=0)
        cm = confusion_matrix(y_true, y_pred, labels=ai.LABELS)
        confusion_matrix_png(cm, ai.LABELS, "sentiment_confusion.png", "Sentiment des avis")
        rows = [
            [lab, report[lab]["precision"], report[lab]["recall"], report[lab]["f1-score"], int(report[lab]["support"])]
            for lab in ai.LABELS
        ]
        rows.append(
            [
                "**macro**",
                report["macro avg"]["precision"],
                report["macro avg"]["recall"],
                report["macro avg"]["f1-score"],
                len(y_true),
            ]
        )
        errors = [[t, e, p] for t, e, p in zip(texts, y_true, y_pred, strict=True) if e != p]
        sections = [
            (
                "Protocole",
                f"""
- Entraînement : `data/ai/reviews_sentiment_train.csv`, **{len(train_rows)} avis** générés à partir de gabarits
  français variés (3 classes équilibrées + négations « pas du tout … »).
- Test : `data/ai/reviews_sentiment_test.csv`, **{len(test_rows)} avis rédigés à la main**, formulations jamais
  vues à l'entraînement (pas de fuite de données).
- Modèle : TF-IDF mots (1–2-grammes) + caractères (3–5-grammes, robuste aux fautes et accents) →
  régression logistique (`class_weight=balanced`).
- Usage : chaque nouvel avis est classé par une tâche Celery ; le sentiment alimente le **score de
  réputation** du transporteur (60 % note moyenne + 40 % sentiment, lissage bayésien vers 50 avec k = 3).
""",
            ),
            (
                "Résultats (jeu de test)",
                md_table(["classe", "précision", "rappel", "F1", "support"], rows)
                + f"\n\nExactitude globale : **{report['accuracy']:.1%}**.",
            ),
            (
                "Matrice de confusion",
                cm_markdown(cm, ai.LABELS) + "\n\n![Matrice de confusion](sentiment_confusion.png)",
            ),
            (
                "Limite méthodologique",
                """
Le vocabulaire générique des gabarits d'entraînement (mots isolés positifs / négatifs / neutres) a été élargi
**une fois après une première évaluation** (v1 : F1 macro = 0,774). Le jeu de test a donc servi en partie au
développement : le score ci-dessus est probablement un peu optimiste. Pour une mesure strictement non biaisée,
il faudrait annoter un second jeu d'avis réels collectés sur la plateforme (prévu dès que des avis réels
existent : `Review.sentiment` est conservé pour cela).
""",
            ),
            ("Erreurs", md_table(["avis", "réel", "prédit"], errors) if errors else "Aucune erreur."),
        ]
        out = write_report("sentiment", "IA 4 — Sentiment des avis et réputation", sections, timer.summary())
        self.stdout.write(
            self.style.SUCCESS(
                f"F1 macro={report['macro avg']['f1-score']:.3f} accuracy={report['accuracy']:.3f} — rapport : {out}"
            )
        )
