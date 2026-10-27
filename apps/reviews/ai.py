"""AI #4 — Review sentiment (TF-IDF + logistic regression) feeding the carrier reputation score.

Training data: ``data/ai/reviews_sentiment_train.csv`` (generated from varied French templates,
including negations). Evaluation: ``data/ai/reviews_sentiment_test.csv``, hand-written reviews
never seen during training.
"""

import csv
import logging
import random
import threading
from pathlib import Path

import joblib
from django.conf import settings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from apps.core.ai.registry import AIInputError
from apps.core.geo import normalize

logger = logging.getLogger("apps.ai")

LABELS = ["negatif", "neutre", "positif"]
TRAIN_PATH = Path(settings.AI_DATA_DIR) / "reviews_sentiment_train.csv"
TEST_PATH = Path(settings.AI_DATA_DIR) / "reviews_sentiment_test.csv"
_lock = threading.Lock()
_model = None

POS = [
    "livraison rapide et soignée",
    "transporteur très professionnel",
    "marchandise arrivée en parfait état",
    "chauffeur ponctuel et aimable",
    "excellent service",
    "je recommande vivement",
    "communication au top",
    "très bonne expérience",
    "délais respectés",
    "prix correct et service impeccable",
    "rien à redire",
    "camion propre et bien équipé",
    "palettes bien sanglées",
    "il nous a tenus informés tout au long du trajet",
    "super transporteur",
    "aucun problème, tout s'est bien passé",
    "parfait du début à la fin",
    "vraiment sérieux",
    "service au top",
    "livré en avance",
]
NEG = [
    "livraison en retard de deux jours",
    "marchandise abîmée à l'arrivée",
    "chauffeur injoignable",
    "très déçu",
    "je ne recommande pas",
    "service catastrophique",
    "cartons écrasés",
    "aucune communication",
    "prix augmenté au dernier moment",
    "camion sale",
    "la chaîne du froid n'a pas été respectée",
    "il a annulé la veille",
    "comportement désagréable",
    "colis perdu",
    "attente interminable au chargement",
    "jamais plus",
    "une arnaque",
    "très mauvaise expérience",
    "délais non respectés",
    "pas professionnel",
]
NEU = [
    "livraison effectuée",
    "service correct sans plus",
    "dans les délais annoncés",
    "rien de particulier à signaler",
    "conforme à ce qui était prévu",
    "prix dans la moyenne",
    "moyen",
    "ça peut aller",
    "un peu de retard mais livré",
    "transport standard",
    "correct dans l'ensemble",
    "quelques soucis de communication mais livré",
    "ni bien ni mal",
    "expérience normale",
    "la livraison s'est faite",
    "le chauffeur a fait le travail",
    "acceptable",
    "pas mal mais peut mieux faire",
    "satisfaisant sans plus",
    "comme prévu",
]
# generic French sentiment vocabulary, combined into short sentences
POS_WORDS = [
    "satisfait",
    "ravi",
    "content",
    "efficace",
    "fiable",
    "rapide",
    "courtois",
    "arrangeant",
    "soigneux",
    "excellent",
    "parfait",
    "agréable",
    "compétent",
    "réactif",
    "de qualité",
    "intact",
    "bravo",
]
NEG_WORDS = [
    "inadmissible",
    "mécontent",
    "furieux",
    "lent",
    "impoli",
    "cassé",
    "rayé",
    "mouillé",
    "abîmé",
    "chaotique",
    "désastreux",
    "injoignable",
    "en retard",
    "incomplet",
    "sale",
    "à éviter",
    "inacceptable",
    "négligent",
]
NEU_WORDS = [
    "correct",
    "standard",
    "normal",
    "classique",
    "conforme",
    "acceptable",
    "moyen",
    "habituel",
    "sans plus",
    "ordinaire",
]
SUBJECTS = ["le service", "le chauffeur", "le transporteur", "la livraison", "le transport", "la prestation"]
NEG_FLIP = ["pas", "jamais", "aucunement"]
OPENERS = [
    "",
    "Bonjour, ",
    "Franchement, ",
    "Bilan : ",
    "Pour notre envoi Sfax-Tunis, ",
    "Nous avons fait appel à lui, ",
    "Deuxième commande avec ce transporteur : ",
    "Avis : ",
]
CLOSERS = ["", ".", " !", " Merci.", " À revoir.", " Merci à toute l'équipe.", " Nous verrons la prochaine fois."]


def generate_training_set(n_per_class: int = 400, seed: int = 3) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    rows = []
    pools = {"positif": POS, "negatif": NEG, "neutre": NEU}
    for label, pool in pools.items():
        for _ in range(n_per_class):
            parts = rng.sample(pool, rng.choice([1, 2, 2, 3]))
            text = rng.choice(OPENERS) + ", ".join(parts) + rng.choice(CLOSERS)
            rows.append((text[0].upper() + text[1:], label))
    words = {"positif": POS_WORDS, "negatif": NEG_WORDS, "neutre": NEU_WORDS}
    for label, pool in words.items():
        for _ in range(n_per_class // 2):
            a, b = rng.sample(pool, 2)
            text = f"{rng.choice(OPENERS)}{rng.choice(SUBJECTS)} : {a} et {b}{rng.choice(CLOSERS)}"
            rows.append((text[0].upper() + text[1:], label))
    # negated positives are negative ("pas professionnel", "pas du tout satisfait")
    for _ in range(n_per_class // 4):
        word = rng.choice(["satisfait", "ponctuel", "sérieux", "soigneux", "fiable", "aimable"])
        rows.append(
            (
                f"{rng.choice(OPENERS)}{rng.choice(NEG_FLIP)} du tout {word}{rng.choice(CLOSERS)}".strip().capitalize(),
                "negatif",
            )
        )
    rng.shuffle(rows)
    return rows


def _read_csv(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [(r["text"], r["label"]) for r in csv.DictReader(fh)]


def load_training_set(rebuild: bool = False) -> list[tuple[str, str]]:
    if rebuild or not TRAIN_PATH.exists():
        TRAIN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRAIN_PATH.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["text", "label"])
            w.writerows(generate_training_set())
    return _read_csv(TRAIN_PATH)


def load_test_set() -> list[tuple[str, str]]:
    return _read_csv(TEST_PATH)


def build_pipeline() -> Pipeline:
    features = FeatureUnion(
        [
            ("words", TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            (
                "chars",
                TfidfVectorizer(
                    preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True
                ),
            ),
        ]
    )
    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")
    return Pipeline([("features", features), ("clf", clf)])


def model_path() -> Path:
    return Path(settings.AI_MODELS_DIR) / "sentiment.joblib"


def train(rows=None, save: bool = True) -> Pipeline:
    rows = rows or load_training_set()
    texts, labels = zip(*rows, strict=True)
    pipe = build_pipeline().fit(list(texts), list(labels))
    if save:
        model_path().parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, model_path())
    return pipe


def get_model() -> Pipeline:
    global _model
    with _lock:
        if _model is None:
            try:
                _model = joblib.load(model_path())
            except Exception:
                logger.info("Sentiment model not found or unreadable, training it now")
                _model = train()
        return _model


def predict(text: str) -> tuple[str, float]:
    model = get_model()
    proba = model.predict_proba([text])[0]
    idx = int(proba.argmax())
    return str(model.classes_[idx]), float(proba[idx])


def validate(payload: dict, user) -> dict:
    if payload.get("review_id"):
        try:
            return {"review_id": int(payload["review_id"])}
        except ValueError as exc:
            raise AIInputError("Avis invalide.") from exc
    text = str(payload.get("text", "")).strip()
    if len(text) < 3:
        raise AIInputError("Texte à analyser manquant.")
    return {"text": text[:1500]}


def handle(payload: dict, user) -> dict:
    """Classify a stored review (and refresh the carrier's reputation) or a raw text."""
    from .models import Review
    from .services import refresh_carrier_stats

    if "review_id" in payload:
        review = Review.objects.select_related("carrier").get(pk=payload["review_id"])
        label, confidence = predict(review.comment)
        review.sentiment, review.sentiment_confidence = label, round(confidence, 3)
        review.save(update_fields=["sentiment", "sentiment_confidence"])
        profile = refresh_carrier_stats(review.carrier)
        return {
            "label": label,
            "confidence": round(confidence, 3),
            "review_id": review.pk,
            "reputation_score": profile.reputation_score if profile else None,
            "provider": "local:tfidf-logreg",
        }
    label, confidence = predict(payload["text"])
    return {"label": label, "confidence": round(confidence, 3), "provider": "local:tfidf-logreg"}
