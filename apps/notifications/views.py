from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin

from .models import Notification


class NotificationListView(RoleRequiredMixin, ListView):
    template_name = "notifications/list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationOpenView(RoleRequiredMixin, View):
    """Mark one notification read and go to its target."""

    http_method_names = ["post"]

    def post(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk)
        if notif.user_id != request.user.pk:
            raise PermissionDenied
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        if notif.url and url_has_allowed_host_and_scheme(notif.url, allowed_hosts={request.get_host()}):
            return redirect(notif.url)
        return redirect("notifications:list")


class NotificationMarkAllReadView(RoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, f"{count} notification(s) marquée(s) comme lue(s).")
        return redirect("notifications:list")
