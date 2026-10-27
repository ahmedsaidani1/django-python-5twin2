import logging

from .models import Notification

logger = logging.getLogger("apps.notifications")


def notify(user, kind: str, message: str, url: str = "") -> Notification | None:
    """Create an in-app notification. A failure here must never break the caller."""
    if user is None:
        return None
    try:
        return Notification.objects.create(user=user, kind=kind, message=message[:255], url=url)
    except Exception:
        logger.exception("Could not create notification for user %s", getattr(user, "pk", None))
        return None
