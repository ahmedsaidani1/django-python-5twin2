"""AI #1 — Smart annonce: free French text → structured FreightRequest fields.

With an LLM key, the remote model extracts the fields (JSON mode). Otherwise, or if
the call fails, a local rule-based French parser does it. Both outputs go through
``normalize_fields`` so the form always receives valid values.
"""

import logging
import re
from datetime import date, timedelta

from apps.core.ai.llm_client import LLMClient, LLMError
from apps.core.ai.registry import AIInputError
from apps.core.choices import MerchandiseType
from apps.core.geo import CITIES, CITY_ALIASES, canonical_city, normalize

logger = logging.getLogger("apps.ai")

FIELDS = (
    "title",
    "merchandise_type",
    "description",
    "weight_kg",
    "volume_m3",
    "origin",
    "destination",
    "pickup_date",
    "delivery_deadline",
    "constraints",
    "budget",
)
EVALUATED_FIELDS = (
    "merchandise_type",
    "weight_kg",
    "volume_m3",
    "origin",
    "destination",
    "pickup_date",
    "delivery_deadline",
    "budget",
)

# keyword (normalized) → merchandise type; checked in order, first match wins.
TYPE_KEYWORDS = [
    (
        (
            "refrigere",
            "frigo",
            "surgele",
            "yaourt",
            "lait",
            "fromage",
            "viande",
            "poisson",
            "glace",
            "fraise",
            "produits laitiers",
            "poulet",
        ),
        MerchandiseType.FRAIS,
    ),
    (
        (
            "tomate",
            "pomme de terre",
            "pommes de terre",
            "patate",
            "oignon",
            "agrume",
            "orange",
            "citron",
            "datte",
            "olive",
            "ble",
            "orge",
            "fourrage",
            "foin",
            "piment",
            "pasteque",
            "melon",
            "legume",
            "fruit",
            "engrais",
            "semence",
        ),
        MerchandiseType.AGRICOLE,
    ),
    (
        (
            "ciment",
            "brique",
            "sable",
            "carrelage",
            "fer a beton",
            "acier",
            "platre",
            "parpaing",
            "marbre",
            "gravier",
            "beton",
            "bois de construction",
            "tuile",
        ),
        MerchandiseType.MATERIAUX,
    ),
    (("textile", "tissu", "vetement", "jean", "chaussure", "habit", "linge", "coton", "fil"), MerchandiseType.TEXTILE),
    (
        (
            "ordinateur",
            "electronique",
            "telephone",
            "ecran",
            "televiseur",
            "electromenager",
            "frigidaire",
            "climatiseur",
            "serveur",
            "composant",
            "cable",
        ),
        MerchandiseType.ELECTRONIQUE,
    ),
    (
        ("meuble", "canape", "armoire", "table", "chaise", "lit", "matelas", "mobilier", "bureau"),
        MerchandiseType.MOBILIER,
    ),
    (
        (
            "machine",
            "piece",
            "moteur",
            "pompe",
            "compresseur",
            "industriel",
            "generateur",
            "outillage",
            "palette de pieces",
            "equipement",
        ),
        MerchandiseType.INDUSTRIEL,
    ),
    (
        (
            "huile",
            "farine",
            "sucre",
            "conserve",
            "pate",
            "couscous",
            "boisson",
            "eau minerale",
            "cafe",
            "the",
            "biscuit",
            "harissa",
            "semoule",
            "riz",
            "alimentaire",
            "epicerie",
        ),
        MerchandiseType.ALIMENTAIRE,
    ),
]

# unit → (kg per unit, m³ per unit)
UNITS = {
    "palette": (500.0, 1.5),
    "carton": (15.0, 0.06),
    "colis": (10.0, 0.05),
    "sac": (50.0, 0.05),
    "caisse": (20.0, 0.08),
    "bidon": (20.0, 0.025),
    "fut": (200.0, 0.22),
    "big bag": (1000.0, 1.0),
}
# typical density (kg/m³) used to estimate a missing volume
DENSITY = {
    MerchandiseType.MATERIAUX: 1200,
    MerchandiseType.AGRICOLE: 450,
    MerchandiseType.FRAIS: 400,
    MerchandiseType.ALIMENTAIRE: 500,
    MerchandiseType.TEXTILE: 250,
    MerchandiseType.ELECTRONIQUE: 200,
    MerchandiseType.MOBILIER: 150,
    MerchandiseType.INDUSTRIEL: 600,
    MerchandiseType.AUTRE: 350,
}
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = [
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
]
CONSTRAINT_KEYWORDS = {
    "fragile": "fragile",
    "refrigere": "réfrigéré",
    "frigo": "réfrigéré",
    "froid": "réfrigéré",
    "hayon": "hayon",
    "bache": "bâché",
    "urgent": "urgent",
    "manutention": "manutention",
    "assurance": "assurance",
    "sec": "au sec",
}

NUM = r"(\d+(?:[.,]\d+)?)"
CITY_NAMES = sorted({normalize(c) for c in CITIES} | set(CITY_ALIASES), key=len, reverse=True)
CITY_RE = "|".join(re.escape(c) for c in CITY_NAMES)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _next_weekday(today: date, idx: int) -> date:
    days = (idx - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def _parse_one_date(t: str, today: date) -> date | None:
    """Parse a single French date expression (already normalized)."""
    if "apres-demain" in t or "apres demain" in t:
        return today + timedelta(days=2)
    if "demain" in t:
        return today + timedelta(days=1)
    if "aujourd" in t:
        return today
    if m := re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", t):
        d, mth = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            result = date(y, mth, d)
        except ValueError:
            return None
        if not m.group(3) and result < today:
            result = result.replace(year=y + 1)
        return result
    if m := re.search(r"(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")", t):
        try:
            result = date(today.year, MONTHS.index(m.group(2)) + 1, int(m.group(1)))
        except ValueError:
            return None
        return result if result >= today else result.replace(year=today.year + 1)
    for i, wd in enumerate(WEEKDAYS):
        if re.search(rf"\b{wd}\b", t):
            return _next_weekday(today, i)
    if "semaine prochaine" in t:
        return _next_weekday(today, 0)
    return None


def _find_cities(t: str) -> tuple[str | None, str | None]:
    patterns = [
        rf"\b(?:de|depuis|du|d')\s*({CITY_RE})\b.*?\b(?:a|vers|pour|jusqu'a|sur|direction)\s+({CITY_RE})\b",
        rf"\b({CITY_RE})\s*(?:->|→|—|-|/|a destination de|vers)\s*({CITY_RE})\b",
        rf"\b(?:a|vers|pour)\s+({CITY_RE})\b.*?\b(?:depuis|de|au depart de)\s+({CITY_RE})\b",
    ]
    for i, p in enumerate(patterns):
        if m := re.search(p, t):
            a, b = canonical_city(m.group(1)), canonical_city(m.group(2))
            return (b, a) if i == 2 else (a, b)
    found = [canonical_city(m.group(1)) for m in re.finditer(rf"\b({CITY_RE})\b", t)]
    found = list(dict.fromkeys(found))
    return (found[0] if found else None, found[1] if len(found) > 1 else None)


def _merchandise(t: str) -> str:
    for keywords, mtype in TYPE_KEYWORDS:
        if any(re.search(rf"\b{re.escape(k)}s?\b", t) for k in keywords):
            return mtype
    return MerchandiseType.AUTRE


def _quantities(t: str, mtype: str) -> tuple[float | None, float | None, str]:
    weight = volume = None
    unit_phrase = ""
    if m := re.search(NUM + r"\s*(tonnes?|t)\b", t):
        weight = _num(m.group(1)) * 1000
    elif m := re.search(NUM + r"\s*(kg|kilos?|kilogrammes?)\b", t):
        weight = _num(m.group(1))
    if m := re.search(NUM + r"\s*(m3|m³|metres? cubes?)", t):
        volume = _num(m.group(1))
    for unit, (kg, m3) in UNITS.items():
        if m := re.search(NUM + rf"\s*{unit}s?\b", t):
            n = _num(m.group(1))
            unit_phrase = f"{m.group(1)} {unit}{'s' if n > 1 else ''}"
            weight = weight if weight is not None else n * kg
            volume = volume if volume is not None else n * m3
            break
    if weight is not None and volume is None:
        volume = weight / DENSITY.get(mtype, 350)
    return (round(weight, 1) if weight else None, round(volume, 2) if volume else None, unit_phrase)


def _dates(t: str, today: date) -> tuple[date | None, date | None]:
    deadline_expr = None
    m = re.search(r"\b(avant|au plus tard|livraison (?:le|pour|avant)?|limite|d'ici)\b(.{0,25})", t)
    pickup_text = t
    if m:
        deadline_expr = m.group(2)
        pickup_text = t[: m.start()] + t[m.end() :]
    pickup = _parse_one_date(pickup_text, today)
    deadline = _parse_one_date(deadline_expr, today) if deadline_expr else None
    if (dm := re.search(r"(?:sous|en|dans les)\s+(\d{1,2})\s+jours?", t)) and deadline is None:
        deadline = (pickup or today + timedelta(days=1)) + timedelta(days=int(dm.group(1)))
    if pickup is None:
        pickup = today + timedelta(days=1)
    if deadline is None or deadline < pickup:
        deadline = pickup + timedelta(days=2)
    return pickup, deadline


def _budget(t: str) -> float | None:
    if m := re.search(NUM + r"\s*(?:dt|tnd|dinars?)\b", t):
        return _num(m.group(1))
    if m := re.search(r"budget\D{0,15}" + NUM, t):
        return _num(m.group(1))
    return None


def parse_freight_text(text: str, today: date | None = None) -> dict:
    """Local rule-based extractor (the fallback model)."""
    today = today or date.today()
    t = normalize(text)
    t = re.sub(r"\s+", " ", t)
    mtype = _merchandise(t)
    origin, destination = _find_cities(t)
    weight, volume, unit_phrase = _quantities(t, mtype)
    pickup, deadline = _dates(t, today)
    constraints = sorted({v for k, v in CONSTRAINT_KEYWORDS.items() if re.search(rf"\b{k}", t)})
    if mtype == MerchandiseType.FRAIS and "réfrigéré" not in constraints:
        constraints.append("réfrigéré")
    label = MerchandiseType(mtype).label
    title = f"{unit_phrase} — {label}" if unit_phrase else f"{label}"
    if origin and destination:
        title += f" {origin} → {destination}"
    return {
        "title": title[:120],
        "merchandise_type": mtype,
        "description": text.strip()[:2000],
        "weight_kg": weight,
        "volume_m3": volume,
        "origin": origin,
        "destination": destination,
        "pickup_date": pickup.isoformat() if pickup else None,
        "delivery_deadline": deadline.isoformat() if deadline else None,
        "constraints": ", ".join(constraints),
        "budget": _budget(t),
    }


def normalize_fields(raw: dict, text: str, today: date) -> dict:
    """Coerce any model output (LLM or local) to valid form values; drop the invalid ones."""
    out = {k: None for k in FIELDS}
    out.update({k: raw.get(k) for k in FIELDS if k in raw})
    out["origin"] = canonical_city(out["origin"] or "")
    out["destination"] = canonical_city(out["destination"] or "")
    if out["merchandise_type"] not in MerchandiseType.values:
        out["merchandise_type"] = MerchandiseType.AUTRE
    for key in ("weight_kg", "volume_m3", "budget"):
        try:
            out[key] = round(float(out[key]), 2) if out[key] not in (None, "") else None
            if out[key] is not None and out[key] <= 0:
                out[key] = None
        except (TypeError, ValueError):
            out[key] = None
    for key in ("pickup_date", "delivery_deadline"):
        try:
            out[key] = date.fromisoformat(str(out[key])).isoformat() if out[key] else None
        except ValueError:
            out[key] = None
    if out["pickup_date"] and out["pickup_date"] < today.isoformat():
        out["pickup_date"] = today.isoformat()
    out["description"] = (out["description"] or text)[:2000]
    out["title"] = (out["title"] or MerchandiseType(out["merchandise_type"]).label)[:120]
    out["constraints"] = (out["constraints"] or "")[:255]
    return out


SYSTEM_PROMPT = (
    "Tu extrais une annonce de fret (Tunisie) depuis un texte libre en français. Réponds uniquement par un "
    "objet JSON avec les clés: title, merchandise_type (une de: {types}), description, weight_kg (nombre, kg), "
    "volume_m3 (nombre), origin, destination (villes tunisiennes), pickup_date, delivery_deadline (YYYY-MM-DD), "
    "constraints (texte court), budget (nombre en TND ou null). Aujourd'hui: {today}. Une palette ≈ 500 kg et "
    "1,5 m³. Sans date limite, mets enlèvement + 2 jours."
)


def extract(text: str, today: date | None = None, client: LLMClient | None = None) -> tuple[dict, str]:
    """Return (fields, provider). Uses the LLM when configured, local parser otherwise."""
    today = today or date.today()
    client = client or LLMClient.from_settings()
    if client.is_remote:
        try:
            raw = client.complete_json(
                SYSTEM_PROMPT.format(types=", ".join(MerchandiseType.values), today=today.isoformat()), text
            )
            return normalize_fields(raw, text, today), client.name
        except LLMError as exc:
            logger.warning("Smart annonce LLM failed, using local parser: %s", exc)
            return normalize_fields(parse_freight_text(text, today), text, today), "local-fallback"
    return normalize_fields(parse_freight_text(text, today), text, today), "local:rules-fr"


def validate(payload: dict, user) -> dict:
    text = str(payload.get("text", "")).strip()
    if len(text) < 10:
        raise AIInputError("Décrivez votre besoin en au moins 10 caractères.")
    if len(text) > 1000:
        raise AIInputError("Texte trop long (1000 caractères maximum).")
    return {"text": text}


def handle(payload: dict, user) -> dict:
    fields, provider = extract(payload["text"])
    return {"fields": fields, "provider": provider}
