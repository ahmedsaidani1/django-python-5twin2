"""AI #5 — Fraud / spam moderation for annonces, trips and profiles.

Hand-crafted features (contact details in text, spam vocabulary, shouting, price far from the
price model's estimate, absurd quantities, posting burst, account age) → random forest.
Suspicious objects are flagged (``is_flagged``) and appear in the admin moderation queue.
"""

import csv
import logging
import math
import random
import re
import threading
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings
from django.utils import timezone
from sklearn.ensemble import RandomForestClassifier

from apps.core.ai.registry import AIInputError
from apps.core.choices import MerchandiseType
from apps.core.geo import CITIES, normalize

logger = logging.getLogger("apps.ai")

THRESHOLD = 0.5
DATASET_PATH = Path(settings.AI_DATA_DIR) / "fraud_labeled.csv"
_lock = threading.Lock()
_model = None

SPAM_TERMS = [
    "gratuit",
    "gagnez",
    "gagner",
    "crypto",
    "bitcoin",
    "investissement",
    "investir",
    "cliquez",
    "promo",
    "100%",
    "garanti",
    "western union",
    "paiement d'avance",
    "avance",
    "whatsapp",
    "telegram",
    "urgent urgent",
    "offre exceptionnelle",
    "contactez",
    "lien",
    "bonus",
    "argent facile",
    "mandat",
    "virement",
    "forex",
]
PHONE_RE = re.compile(r"(?:\+?216[\s.-]?)?\b[2-9]\d(?:[\s.-]?\d{3}){2}\b")
URL_RE = re.compile(r"https?://|www\.|\.com\b|\.tn\b|bit\.ly", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
FEATURES = [
    "has_phone",
    "has_url",
    "has_email",
    "spam_terms",
    "upper_ratio",
    "exclamations",
    "text_len_log",
    "price_log_ratio",
    "weight_log",
    "absurd_quantity",
    "posts_24h",
    "account_age_days_log",
    "reports",
]


def text_features(text: str) -> dict:
    t = text or ""
    n = normalize(t)
    letters = [c for c in t if c.isalpha()]
    return {
        "has_phone": int(bool(PHONE_RE.search(t))),
        "has_url": int(bool(URL_RE.search(t))),
        "has_email": int(bool(EMAIL_RE.search(t))),
        "spam_terms": sum(n.count(normalize(term)) for term in SPAM_TERMS),
        "upper_ratio": round(sum(c.isupper() for c in letters) / len(letters), 3) if letters else 0.0,
        "exclamations": t.count("!"),
        "text_len_log": round(math.log1p(len(t)), 3),
    }


def features(text, price, expected_price, weight_kg, posts_24h, account_age_days, reports=0) -> dict:
    f = text_features(text)
    ratio = (price / expected_price) if (price and expected_price) else 1.0
    f.update(
        {
            "price_log_ratio": round(math.log(max(ratio, 1e-3)), 3),
            "weight_log": round(math.log1p(weight_kg or 0), 3),
            "absurd_quantity": int((weight_kg or 0) > 40000 or (weight_kg or 0) < 1),
            "posts_24h": posts_24h,
            "account_age_days_log": round(math.log1p(account_age_days), 3),
            "reports": reports,
        }
    )
    return f


def vector(f: dict) -> list[float]:
    return [float(f[k]) for k in FEATURES]


# ---- synthetic labeled dataset ------------------------------------------------------

LEGIT_TEXTS = [
    [
        "Palettes filmées, chargement par chariot élévateur sur place.",
        "Marchandise conditionnée en cartons, quai de chargement disponible.",
        "Produits à livrer chez notre client, réception de 8h à 16h.",
        "Merci de prévoir des sangles, chargement au rez-de-chaussée.",
        "Livraison en centre-ville, accès camion porteur possible.",
        "Sacs sur palettes, manutention assurée par nos équipes.",
        "Besoin d'un camion bâché, la marchandise craint la pluie.",
        "Envoi régulier chaque semaine si la collaboration se passe bien.",
        "Facture avec matricule fiscal exigée.",
        "Contact du magasinier communiqué après réservation.",
    ],
    [
        "Chargement possible le matin uniquement, merci de confirmer l'heure.",
        "Les cartons sont légers mais fragiles, à empiler avec soin.",
        "Produits emballés et étiquetés, bon de livraison fourni.",
        "Déchargement par nos soins à l'arrivée.",
        "Merci d'indiquer votre délai et votre prix dans la demande.",
        "Transport à prévoir avec hayon si possible.",
        "Marchandise assurée par l'expéditeur.",
        "Nous pouvons attendre un jour de plus si le prix est meilleur.",
        "Accès entrepôt zone industrielle, parking poids lourds.",
        "Tél. du responsable donné une fois la demande acceptée.",
    ],
]
FRAUD_TEXTS = [
    [
        "GAGNEZ DE L'ARGENT FACILE !!! Contactez-moi sur WhatsApp {phone}",
        "Offre exceptionnelle, paiement d'avance par Western Union uniquement.",
        "Investissement crypto garanti 100% !!! www.gain-rapide.com",
        "Transport gratuit, il suffit de payer les frais de dossier par virement.",
        "URGENT URGENT envoyez un mandat avant chargement {phone}",
        "Cliquez sur le lien bit.ly/promo-fret pour réserver !!!",
        "Promo -70% sur tous les trajets, contactez telegram @fretpromo",
        "Bonus de 500 DT pour chaque inscription, écrivez à gain@mail.com",
        "Prix imbattable, avance de 50% obligatoire sur mon compte.",
        "Forex et bitcoin : doublez votre argent, appelez {phone}",
    ],
    [
        "Réservez vite !!! paiement d'avance exigé, aucune facture.",
        "Contact direct uniquement hors plateforme : {phone} WhatsApp",
        "Je transporte tout, payez maintenant et gagnez un trajet gratuit !!!",
        "Visitez www.fret-discount.tn pour un prix 10 fois moins cher",
        "Envoyez l'argent par mandat minute avant le départ.",
        "OFFRE LIMITÉE !!! INVESTISSEZ DANS MON CAMION",
        "Remise exceptionnelle si virement aujourd'hui, écrivez à transport.pas.cher@mail.com",
        "Argent facile : devenez partenaire, bonus garanti",
        "Payez par carte cadeau, livraison garantie 100%",
        "Appelez {phone} et oubliez la plateforme, c'est moins cher !!!",
    ],
]
TRICKY_LEGIT = [
    "URGENT : marchandise périssable, départ demain matin !",
    "Prix négociable, appelez-nous via la messagerie CargoLink.",
]
TRICKY_FRAUD = [
    "Transport de marchandises entre Tunis et Sfax, très bon prix.",
    "Camion disponible, tarif très bas, places limitées.",
]


def _phone(rng):
    return f"{rng.choice([2, 5, 9])}{rng.randint(0, 9)} {rng.randint(100, 999)} {rng.randint(100, 999)}"


def generate_dataset(n: int = 1600, fraud_rate: float = 0.3, seed: int = 5) -> list[dict]:
    """Template split 0 → train rows, split 1 → test rows (disjoint phrasings)."""
    from apps.core.geo import distance_km
    from apps.trips.pricing import market_price

    rng = random.Random(seed)
    cities = list(CITIES)
    rows = []
    for i in range(n):
        split = 0 if i < int(n * 0.7) else 1
        fraud = rng.random() < fraud_rate
        a, b = rng.sample(cities, 2)
        weight = round(math.exp(rng.uniform(math.log(80), math.log(20000))))
        mtype = rng.choice(list(MerchandiseType.values))
        volume = round(weight / 400, 2)
        expected = market_price(distance_km(a, b), weight, volume, mtype, 3)
        if fraud:
            text = rng.choice(FRAUD_TEXTS[split]).format(phone=_phone(rng))
            if rng.random() < 0.35:
                text = rng.choice(TRICKY_FRAUD + LEGIT_TEXTS[split])  # clean-looking fraud: only numbers betray it
            price = expected * rng.choice(
                [rng.uniform(0.05, 0.4), rng.uniform(2, 8), rng.uniform(0.7, 1.4), rng.uniform(0.7, 1.4)]
            )
            if rng.random() < 0.1:
                weight = rng.choice([0, 99999, 150000])
            posts = rng.choice([0, 1, 2, 4, 8, 15, 25])
            age = rng.choice([0, 0, 1, 2, 5, 30, 90, 200, 400])
            reports = rng.choice([0, 0, 0, 1, 2, 3])
        else:
            text = rng.choice(LEGIT_TEXTS[split])
            if rng.random() < 0.15:
                text += " " + rng.choice(TRICKY_LEGIT)
            if rng.random() < 0.08:
                text += f" Tél. {_phone(rng)}"  # some honest users still leave a number
            price = expected * (rng.uniform(0.6, 1.6) if rng.random() < 0.9 else rng.choice([0.35, 2.2]))
            posts = rng.choice([0, 0, 1, 1, 2, 3, 5, 9])
            age = rng.choice([0, 1, 3, 10, 30, 90, 200, 500, 900])
            reports = rng.choice([0, 0, 0, 0, 0, 1, 2])
        rows.append(
            {
                "split": "train" if split == 0 else "test",
                "label": int(fraud),
                "text": text,
                "price": round(price, 2),
                "expected_price": expected,
                "weight_kg": weight,
                "posts_24h": posts,
                "account_age_days": age,
                "reports": reports,
            }
        )
    return rows


def load_dataset(rebuild: bool = False) -> list[dict]:
    if rebuild or not DATASET_PATH.exists():
        rows = generate_dataset()
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DATASET_PATH.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with DATASET_PATH.open(encoding="utf-8", newline="") as fh:
        return [
            {
                **r,
                "label": int(r["label"]),
                "price": float(r["price"]),
                "expected_price": float(r["expected_price"]),
                "weight_kg": float(r["weight_kg"]),
                "posts_24h": int(r["posts_24h"]),
                "account_age_days": int(r["account_age_days"]),
                "reports": int(r["reports"]),
            }
            for r in csv.DictReader(fh)
        ]


def row_vector(r: dict) -> list[float]:
    return vector(
        features(
            r["text"],
            r["price"],
            r["expected_price"],
            r["weight_kg"],
            r["posts_24h"],
            r["account_age_days"],
            r["reports"],
        )
    )


def build_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=2, class_weight="balanced", random_state=42
    )


def model_path() -> Path:
    return Path(settings.AI_MODELS_DIR) / "fraud.joblib"


def train(rows=None, save: bool = True) -> RandomForestClassifier:
    rows = rows if rows is not None else [r for r in load_dataset() if r["split"] == "train"]
    model = build_model().fit(np.array([row_vector(r) for r in rows]), [r["label"] for r in rows])
    if save:
        model_path().parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_path())
    return model


def get_model() -> RandomForestClassifier:
    global _model
    with _lock:
        if _model is None:
            try:
                _model = joblib.load(model_path())
            except Exception:
                logger.info("Fraud model not found or unreadable, training it now")
                _model = train()
        return _model


def fraud_probability(f: dict) -> float:
    return float(get_model().predict_proba(np.array([vector(f)]))[0][1])


# ---- application side ---------------------------------------------------------------


def _user_activity(user):
    since = timezone.now() - timedelta(hours=24)
    posts = (
        user.freight_requests.filter(created_at__gte=since).count() + user.trips.filter(created_at__gte=since).count()
    )
    age = max((timezone.now() - user.date_joined).days, 0)
    return posts, age


def _reports_for(obj) -> int:
    from django.contrib.contenttypes.models import ContentType

    from .models import Report

    return Report.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk).count()


def object_features(obj) -> dict:
    """Features for a FreightRequest, a Trip or a User."""
    from apps.shipments.models import FreightRequest
    from apps.trips.models import Trip
    from apps.trips.pricing import suggest_price

    from .models import User

    if isinstance(obj, User):
        profile = getattr(obj, "company_profile", None) or getattr(obj, "carrier_profile", None)
        text = " ".join(filter(None, [profile.company_name if profile else "", profile.description if profile else ""]))
        posts, age = _user_activity(obj)
        return features(text, None, None, 1000, posts, age, _reports_for(obj))

    if isinstance(obj, FreightRequest):
        owner, text, weight = obj.pme, f"{obj.title} {obj.description} {obj.constraints}", obj.weight_kg
        volume, mtype, price = obj.volume_m3, obj.merchandise_type, float(obj.budget) if obj.budget else None
        urgency = (obj.delivery_deadline - obj.pickup_date).days
    elif isinstance(obj, Trip):
        owner, text, weight = obj.carrier, obj.notes, obj.available_weight_kg
        volume, mtype, urgency = obj.available_volume_m3, "autre", 3
        quote = obj.quote(weight)
        price = float(quote) if quote else None
    else:
        raise TypeError(f"Objet non pris en charge : {type(obj)}")
    expected = None
    if price:
        try:
            expected = suggest_price(
                obj.origin, obj.destination, max(weight, 1), max(volume, 0.01), mtype, max(0, min(urgency, 10))
            )["price"]
        except Exception:
            logger.exception("Price model unavailable during fraud screening")
    posts, age = _user_activity(owner)
    return features(text, price, expected, weight, posts, age, _reports_for(obj))


def screen_object(obj) -> dict:
    f = object_features(obj)
    proba = fraud_probability(f)
    flagged = proba >= THRESHOLD
    obj.fraud_score = round(proba, 3)
    obj.is_flagged = flagged or obj.is_flagged
    obj.save(update_fields=["fraud_score", "is_flagged"])
    reasons = [k for k in ("has_phone", "has_url", "has_email") if f[k]]
    if f["spam_terms"]:
        reasons.append("spam_terms")
    if abs(f["price_log_ratio"]) > 1:
        reasons.append("price_outlier")
    if f["posts_24h"] >= 8:
        reasons.append("posting_burst")
    return {"score": round(proba, 3), "flagged": flagged, "reasons": reasons}


TARGETS = {"annonce": ("shipments", "FreightRequest"), "trajet": ("trips", "Trip"), "utilisateur": ("accounts", "User")}


def _get_target(kind, pk):
    from django.apps import apps

    app_label, model = TARGETS[kind]
    return apps.get_model(app_label, model).objects.get(pk=pk)


def validate(payload: dict, user) -> dict:
    kind = payload.get("target")
    if kind not in TARGETS:
        raise AIInputError("Cible inconnue (annonce, trajet ou utilisateur).")
    try:
        obj = _get_target(kind, int(payload.get("id")))
    except (TypeError, ValueError, LookupError) as exc:
        raise AIInputError("Objet introuvable.") from exc
    except Exception as exc:
        raise AIInputError("Objet introuvable.") from exc
    return {"target": kind, "id": obj.pk}


def handle(payload: dict, user) -> dict:
    obj = _get_target(payload["target"], payload["id"])
    result = screen_object(obj)
    if payload["target"] != "utilisateur" and result["flagged"]:
        owner = getattr(obj, "pme", None) or getattr(obj, "carrier", None)
        flagged_posts = (
            owner.freight_requests.filter(is_flagged=True).count() + owner.trips.filter(is_flagged=True).count()
        )
        if flagged_posts >= 2 and not owner.is_flagged:
            owner.is_flagged = True
            owner.save(update_fields=["is_flagged"])
    return {**result, "target": payload["target"], "id": payload["id"], "provider": "local:random-forest"}
