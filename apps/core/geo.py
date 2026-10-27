"""Tunisian cities used across the app (forms, AI distance features, demo data)."""

import math
import unicodedata

# name: (latitude, longitude, governorate)
CITIES = {
    "Tunis": (36.8065, 10.1815, "Tunis"),
    "Ariana": (36.8665, 10.1647, "Ariana"),
    "Ben Arous": (36.7531, 10.2189, "Ben Arous"),
    "La Manouba": (36.8101, 10.0956, "Manouba"),
    "Bizerte": (37.2744, 9.8739, "Bizerte"),
    "Nabeul": (36.4561, 10.7376, "Nabeul"),
    "Hammamet": (36.4000, 10.6167, "Nabeul"),
    "Zaghouan": (36.4029, 10.1429, "Zaghouan"),
    "Béja": (36.7256, 9.1817, "Béja"),
    "Jendouba": (36.5011, 8.7802, "Jendouba"),
    "Le Kef": (36.1742, 8.7049, "Le Kef"),
    "Siliana": (36.0849, 9.3708, "Siliana"),
    "Sousse": (35.8256, 10.6084, "Sousse"),
    "Monastir": (35.7643, 10.8113, "Monastir"),
    "Mahdia": (35.5047, 11.0622, "Mahdia"),
    "Kairouan": (35.6781, 10.0963, "Kairouan"),
    "Kasserine": (35.1676, 8.8365, "Kasserine"),
    "Sidi Bouzid": (35.0382, 9.4849, "Sidi Bouzid"),
    "Sfax": (34.7406, 10.7603, "Sfax"),
    "Gafsa": (34.4250, 8.7842, "Gafsa"),
    "Tozeur": (33.9197, 8.1335, "Tozeur"),
    "Kébili": (33.7044, 8.9690, "Kébili"),
    "Gabès": (33.8815, 10.0982, "Gabès"),
    "Médenine": (33.3549, 10.5055, "Médenine"),
    "Djerba": (33.8076, 10.8451, "Médenine"),
    "Zarzis": (33.5036, 11.1122, "Médenine"),
    "Tataouine": (32.9297, 10.4518, "Tataouine"),
}

CITY_CHOICES = [(c, c) for c in sorted(CITIES)]


def normalize(text: str) -> str:
    """Lowercase and strip accents, for tolerant city matching."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


# common alternative spellings (normalized) → canonical name
CITY_ALIASES = {
    "manouba": "La Manouba",
    "kef": "Le Kef",
    "jerba": "Djerba",
    "ben arous": "Ben Arous",
}

_NORMALIZED = {normalize(c): c for c in CITIES} | CITY_ALIASES


def canonical_city(name: str) -> str | None:
    return _NORMALIZED.get(normalize(name))


def governorate(city: str) -> str | None:
    c = canonical_city(city)
    return CITIES[c][2] if c else None


def distance_km(a: str, b: str) -> float:
    """Road-distance estimate: haversine × 1.25 detour factor. Unknown cities → 0."""
    ca, cb = canonical_city(a), canonical_city(b)
    if not ca or not cb:
        return 0.0
    lat1, lon1, _ = CITIES[ca]
    lat2, lon2, _ = CITIES[cb]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)) * 1.25, 1)
