from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "message", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__username", "message")
    list_select_related = ("user",)
