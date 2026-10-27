from django.contrib import admin

from .models import BookingRequest, BookingStatusHistory


class HistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    can_delete = False


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "freight", "trip", "sender", "receiver", "proposed_price", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("freight__title", "sender__username", "receiver__username", "message")
    list_select_related = ("freight", "trip", "sender", "receiver")
    inlines = [HistoryInline]


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("booking", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
    list_select_related = ("booking", "changed_by")
