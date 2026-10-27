from .models import Notification


def notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {"unread_notifications_count": Notification.objects.filter(user=user, is_read=False).count()}
