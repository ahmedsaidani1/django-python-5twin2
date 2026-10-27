from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("booking", "sender", "short_body", "created_at", "read_at")
    search_fields = ("body", "sender__username")
    list_select_related = ("booking", "sender")

    @admin.display(description="message")
    def short_body(self, obj):
        return obj.body[:60]
