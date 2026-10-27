"""Maps each AI job kind to the module implementing it.

Every module exposes:
- ``validate(payload: dict, user) -> dict``: cleans input, raises ``AIInputError``
  or ``PermissionDenied`` (checked synchronously, before the job is queued);
- ``handle(payload: dict, user) -> dict``: does the work (runs in Celery).
"""

from importlib import import_module


class AIInputError(ValueError):
    """Invalid input for an AI job (shown to the user, HTTP 400)."""


MODULES = {
    "smart_annonce": "apps.shipments.ai",
    "price": "apps.trips.ai",
    "matching": "apps.bookings.ai",
    "sentiment": "apps.reviews.ai",
    "fraud": "apps.accounts.fraud",
}

ALLOWED_ROLES = {
    "smart_annonce": ("pme",),
    "price": ("pme", "transporteur"),
    "matching": ("pme", "transporteur"),
    "sentiment": ("admin",),
    "fraud": ("admin",),
}


def get_module(kind: str):
    try:
        return import_module(MODULES[kind])
    except KeyError as exc:
        raise AIInputError(f"Type de tâche IA inconnu: {kind}") from exc
