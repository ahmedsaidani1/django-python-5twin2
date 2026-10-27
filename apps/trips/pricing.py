"""AI #2 — Price suggestion: scikit-learn regression on a synthetic Tunisian freight dataset.

The generator encodes a plausible market price (fixed cost + distance × load cost, merchandise
multiplier, urgency premium, log-normal noise). The model only sees the features
(distance, weight, volume, merchandise type, urgency), never the formula.
"""

import logging
import math
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from apps.core.choices import MerchandiseType
from apps.core.geo import CITIES, distance_km

logger = logging.getLogger("apps.ai")

FEATURES = ["distance_km", "weight_kg", "volume_m3", "merchandise_type", "urgency_days"]
TYPE_MULTIPLIER = {
    "alimentaire": 1.0,
    "frais": 1.35,
    "materiaux": 0.9,
    "textile": 1.0,
    "electronique": 1.25,
    "mobilier": 1.15,
    "industriel": 1.1,
    "agricole": 0.95,
    "autre": 1.0,
}
DATASET_PATH = Path(settings.AI_DATA_DIR) / "price_synth.csv"
_lock = threading.Lock()
_model = None


def market_price(distance, weight, volume, mtype, urgency_days, rng=None) -> float:
    """Ground-truth generator (hidden from the model)."""
    chargeable = max(weight, volume * 250)  # volumetric weight: 1 m³ ≈ 250 kg
    base = 35 + distance * (0.85 + 0.00012 * chargeable) + 0.012 * chargeable
    urgency = 1 + 0.30 * math.exp(-urgency_days / 2)
    price = base * TYPE_MULTIPLIER[mtype] * urgency
    if rng is not None:
        price *= rng.lognormal(0, 0.08)
    return round(price, 2)


def generate_dataset(n: int = 4000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cities = list(CITIES)
    types = list(MerchandiseType.values)
    rows = []
    while len(rows) < n:
        a, b = rng.choice(cities, 2, replace=False)
        dist = distance_km(a, b)
        mtype = str(rng.choice(types))
        weight = float(np.round(np.exp(rng.uniform(np.log(50), np.log(24000))), 0))
        density = {"materiaux": 1200, "mobilier": 150, "electronique": 200, "textile": 250}.get(mtype, 450)
        volume = round(max(weight / density * rng.uniform(0.7, 1.3), 0.05), 2)
        urgency = int(rng.integers(0, 11))
        rows.append(
            {
                "origin": a,
                "destination": b,
                "distance_km": dist,
                "weight_kg": weight,
                "volume_m3": volume,
                "merchandise_type": mtype,
                "urgency_days": urgency,
                "price_tnd": market_price(dist, weight, volume, mtype, urgency, rng),
            }
        )
    return pd.DataFrame(rows)


def load_dataset(rebuild: bool = False) -> pd.DataFrame:
    if rebuild or not DATASET_PATH.exists():
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        generate_dataset().to_csv(DATASET_PATH, index=False)
    return pd.read_csv(DATASET_PATH)


def build_pipeline() -> Pipeline:
    log = FunctionTransformer(np.log1p, feature_names_out="one-to-one")
    pre = ColumnTransformer(
        [
            ("type", OneHotEncoder(handle_unknown="ignore"), ["merchandise_type"]),
            ("log", log, ["weight_kg", "volume_m3"]),
            ("num", "passthrough", ["distance_km", "urgency_days"]),
        ]
    )
    reg = GradientBoostingRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.9, random_state=42)
    # Learn log(price): errors are multiplicative, as in real freight pricing.
    return Pipeline([("pre", pre), ("reg", TransformedTargetRegressor(reg, func=np.log, inverse_func=np.exp))])


def model_path() -> Path:
    return Path(settings.AI_MODELS_DIR) / "price.joblib"


def train(df: pd.DataFrame | None = None, save: bool = True) -> Pipeline:
    df = load_dataset() if df is None else df
    pipe = build_pipeline().fit(df[FEATURES], df["price_tnd"])
    if save:
        model_path().parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, model_path())
    return pipe


def get_model() -> Pipeline:
    """Load the trained model (train it on first use if missing)."""
    global _model
    with _lock:
        if _model is None:
            try:
                _model = joblib.load(model_path())
            except Exception:
                logger.info("Price model not found or unreadable, training it now")
                _model = train()
        return _model


def suggest_price(origin, destination, weight_kg, volume_m3, merchandise_type, urgency_days) -> dict:
    dist = distance_km(origin, destination)
    row = pd.DataFrame(
        [
            {
                "distance_km": dist,
                "weight_kg": float(weight_kg),
                "volume_m3": float(volume_m3),
                "merchandise_type": merchandise_type,
                "urgency_days": int(urgency_days),
            }
        ]
    )
    price = float(get_model().predict(row)[0])
    return {
        "price": round(price, 0),
        "low": round(price * 0.88, 0),
        "high": round(price * 1.12, 0),
        "distance_km": dist,
        "per_kg": round(price / float(weight_kg), 3) if weight_kg else None,
    }
